"""
eval.py - TargetMind Evaluation and Benchmarking Suite
=======================================================
Measures two production-critical metrics:
  1. Entity Resolution Accuracy  -> Did search_agent return the correct ID?  (target: >=85%)
  2. End-to-End Pipeline Latency -> How long does the full orchestrator take? (P95 target: <12s)

Usage:
    python eval.py                        # full run
    python eval.py --quick                # entity-resolution only (no LLM pipeline calls)
    python eval.py --export report.json   # save JSON report

Exit codes:
    0 -> all benchmarks passed
    1 -> one or more benchmarks failed
"""

import sys
import time
import json
import re
import argparse
import statistics
from dataclasses import dataclass, field, asdict
from typing import Optional

# Load agents (uses .env automatically)
from code import search_agent, orchestrator, run_with_retry, MODEL


# =============================================================================
# 1. GROUND-TRUTH DATASET
# =============================================================================

@dataclass
class EntityTest:
    """A single entity-resolution test case."""
    name: str           # The natural-language name to search
    expected_id: str    # The exact ID search_agent must return
    entity_type: str    # "target" | "disease" | "drug"
    description: str = ""


@dataclass
class PipelineTest:
    """A full end-to-end orchestrator test case."""
    query: str               # Natural language query
    expected_keywords: list  # At least one of these must appear in the response
    hop_type: str            # "single" | "multi"
    description: str = ""


# Entity Resolution Tests - 18 ground-truth cases
ENTITY_TESTS = [
    # Targets (genes/proteins)
    EntityTest("TP53",   "ENSG00000141510", "target", "Tumour suppressor gene"),
    EntityTest("BRCA1",  "ENSG00000012048", "target", "Breast cancer susceptibility gene 1"),
    EntityTest("EGFR",   "ENSG00000146648", "target", "Epidermal growth factor receptor"),
    EntityTest("BRAF",   "ENSG00000157764", "target", "B-Raf proto-oncogene"),
    EntityTest("VEGFA",  "ENSG00000112715", "target", "Vascular endothelial growth factor A"),
    EntityTest("PTEN",   "ENSG00000171862", "target", "Phosphatase and tensin homolog"),

    # Diseases (EFO / MONDO) — IDs verified against live Open Targets API
    EntityTest("breast cancer",       "MONDO_0007254", "disease", "Common female cancer"),
    EntityTest("type 2 diabetes",     "MONDO_0005148", "disease", "Metabolic disease"),
    EntityTest("Alzheimer disease",   "MONDO_0004975", "disease", "Neurodegenerative disease"),
    EntityTest("lung cancer",         "MONDO_0008903", "disease", "Leading cancer by mortality"),
    EntityTest("asthma",              "MONDO_0004979", "disease", "Chronic respiratory disease"),
    EntityTest("rheumatoid arthritis","MONDO_0008383", "disease", "Autoimmune joint disease"),

    # Drugs (ChEMBL) — IDs verified against live Open Targets API
    EntityTest("imatinib",   "CHEMBL941",     "drug", "BCR-ABL inhibitor, CML treatment"),
    EntityTest("aspirin",    "CHEMBL25",      "drug", "Classic NSAID / COX inhibitor"),
    EntityTest("metformin",  "CHEMBL1431",    "drug", "First-line type 2 diabetes drug"),
    EntityTest("nivolumab",  "CHEMBL2108738", "drug", "PD-1 checkpoint inhibitor"),
    EntityTest("trastuzumab","CHEMBL1201585", "drug", "HER2-targeted antibody"),
    EntityTest("erlotinib",  "CHEMBL553",     "drug", "EGFR tyrosine kinase inhibitor"),
]

# Full Pipeline Tests - 6 end-to-end cases
PIPELINE_TESTS = [
    PipelineTest(
        query="What diseases are associated with TP53?",
        expected_keywords=["cancer", "carcinoma", "tumor", "neoplasm", "Li-Fraumeni"],
        hop_type="single",
        description="Target -> diseases (single-hop)",
    ),
    PipelineTest(
        query="What drugs treat breast cancer?",
        expected_keywords=["tamoxifen", "trastuzumab", "letrozole", "palbociclib", "capecitabine"],
        hop_type="single",
        description="Disease -> drugs (single-hop)",
    ),
    PipelineTest(
        query="What is the mechanism of action of imatinib?",
        expected_keywords=["BCR-ABL", "kinase", "inhibitor", "tyrosine", "ABL"],
        hop_type="single",
        description="Drug -> mechanism (single-hop)",
    ),
    PipelineTest(
        query="What drugs target EGFR?",
        expected_keywords=["erlotinib", "gefitinib", "afatinib", "osimertinib", "cetuximab"],
        hop_type="single",
        description="Target -> drugs (single-hop)",
    ),
    PipelineTest(
        query="Which diseases does nivolumab treat and what are the top targets for those diseases?",
        expected_keywords=["cancer", "melanoma", "lung", "target", "PD"],
        hop_type="multi",
        description="Drug -> diseases -> targets (multi-hop fan-out)",
    ),
    PipelineTest(
        query="What diseases are linked to BRAF and which drugs treat those diseases?",
        expected_keywords=["melanoma", "cancer", "vemurafenib", "dabrafenib", "drug"],
        hop_type="multi",
        description="Target -> diseases -> drugs (multi-hop fan-out)",
    ),
]


# =============================================================================
# 2. RESULT DATA CLASSES
# =============================================================================

@dataclass
class EntityResult:
    name: str
    entity_type: str
    expected_id: str
    returned_id: Optional[str]
    passed: bool
    latency_ms: float
    raw_response: str = ""
    error: Optional[str] = None


@dataclass
class PipelineResult:
    query: str
    hop_type: str
    passed: bool
    latency_ms: float
    matched_keyword: Optional[str]
    raw_response: str = ""
    error: Optional[str] = None


@dataclass
class BenchmarkReport:
    timestamp: str
    model: str
    entity_total: int = 0
    entity_passed: int = 0
    entity_accuracy_pct: float = 0.0
    entity_mean_ms: float = 0.0
    entity_results: list = field(default_factory=list)
    pipeline_total: int = 0
    pipeline_passed: int = 0
    pipeline_pass_rate_pct: float = 0.0
    pipeline_mean_ms: float = 0.0
    pipeline_p50_ms: float = 0.0
    pipeline_p95_ms: float = 0.0
    pipeline_results: list = field(default_factory=list)
    overall_passed: bool = False
    verdict: str = "FAIL"


# =============================================================================
# 3. HELPERS
# =============================================================================

ENTITY_ID_PATTERN = re.compile(r"ENTITY_ID=([A-Z0-9_.\-/]+)", re.IGNORECASE)


def extract_entity_id(text: str) -> Optional[str]:
    """Pull the ID value from search_agent's 'ENTITY_ID=...' response."""
    if not text:
        return None
    match = ENTITY_ID_PATTERN.search(text)
    return match.group(1).strip() if match else None


def ids_match(returned: Optional[str], expected: str) -> bool:
    """Case-insensitive exact match."""
    if returned is None:
        return False
    return returned.strip().upper() == expected.strip().upper()


def percentile(data: list, p: int) -> float:
    """Return the p-th percentile of data (0-100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (p / 100) * (len(sorted_data) - 1)
    lo = int(idx)
    hi = min(int(idx) + 1, len(sorted_data) - 1)
    return sorted_data[lo] + (sorted_data[hi] - sorted_data[lo]) * (idx - lo)


def print_section(title: str, char: str = "=") -> None:
    width = 70
    print(f"\n{char * width}")
    print(f"  {title}")
    print(f"{char * width}")


def verdict_str(passed: bool) -> str:
    return "PASS" if passed else "FAIL"


# =============================================================================
# 4. ENTITY RESOLUTION BENCHMARK
# =============================================================================

def run_entity_benchmark(tests: list) -> tuple:
    """Run each entity name through search_agent and check the returned ID."""
    results = []
    latencies = []

    print_section("ENTITY RESOLUTION BENCHMARK")
    print(f"  Running {len(tests)} test cases against search_agent ...\n")

    for i, test in enumerate(tests, 1):
        label = f"[{i:02d}/{len(tests)}] {test.entity_type:<8} | {test.name:<22}"
        t0 = time.perf_counter()
        try:
            response = run_with_retry(search_agent, test.name, max_retries=2, delay=1.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            raw = response.content if (response and response.content) else ""
            returned_id = extract_entity_id(raw)
            passed = ids_match(returned_id, test.expected_id)
            result = EntityResult(
                name=test.name,
                entity_type=test.entity_type,
                expected_id=test.expected_id,
                returned_id=returned_id,
                passed=passed,
                latency_ms=round(elapsed_ms, 1),
                raw_response=raw[:200],
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            result = EntityResult(
                name=test.name,
                entity_type=test.entity_type,
                expected_id=test.expected_id,
                returned_id=None,
                passed=False,
                latency_ms=round(elapsed_ms, 1),
                error=str(exc),
            )

        results.append(result)
        latencies.append(result.latency_ms)

        id_display = result.returned_id or "NOT_FOUND"
        status = "[PASS]" if result.passed else "[FAIL]"
        print(f"  {status}  {label}  ->  {id_display:<26}  ({result.latency_ms:.0f} ms)")
        if not result.passed:
            print(f"         expected: {test.expected_id}")
        if result.error:
            print(f"         error:    {result.error}")

        time.sleep(0.5)   # respect Groq rate limits

    return results, latencies


# =============================================================================
# 5. PIPELINE LATENCY BENCHMARK
# =============================================================================

def run_pipeline_benchmark(tests: list) -> tuple:
    """Run each query through the full orchestrator; measure latency and keyword hit."""
    results = []
    latencies = []

    print_section("END-TO-END PIPELINE BENCHMARK")
    print(f"  Running {len(tests)} queries through the full orchestrator ...\n")

    for i, test in enumerate(tests, 1):
        hop_tag = f"[{test.hop_type}]"
        print(f"  [{i}/{len(tests)}] {hop_tag:<8} {test.description}")
        print(f"          Q: \"{test.query}\"")
        t0 = time.perf_counter()
        try:
            response = run_with_retry(orchestrator, test.query, max_retries=2, delay=2.0)
            elapsed_ms = (time.perf_counter() - t0) * 1000
            raw = response.content if (response and response.content) else ""
            raw_lower = raw.lower()
            matched_kw = next(
                (kw for kw in test.expected_keywords if kw.lower() in raw_lower),
                None
            )
            passed = matched_kw is not None
            result = PipelineResult(
                query=test.query,
                hop_type=test.hop_type,
                passed=passed,
                latency_ms=round(elapsed_ms, 1),
                matched_keyword=matched_kw,
                raw_response=raw[:300],
            )
        except Exception as exc:
            elapsed_ms = (time.perf_counter() - t0) * 1000
            result = PipelineResult(
                query=test.query,
                hop_type=test.hop_type,
                passed=False,
                latency_ms=round(elapsed_ms, 1),
                matched_keyword=None,
                error=str(exc),
            )

        results.append(result)
        latencies.append(result.latency_ms)

        status = "[PASS]" if result.passed else "[FAIL]"
        kw_disp = f'matched="{result.matched_keyword}"' if result.matched_keyword else "NO KEYWORD MATCH"
        print(f"          {status}  {kw_disp}  |  {result.latency_ms:.0f} ms\n")
        if result.error:
            print(f"          error: {result.error}\n")

        time.sleep(1.0)  # buffer between full pipeline calls

    return results, latencies


# =============================================================================
# 6. THRESHOLDS, REPORT BUILDER, SUMMARY PRINTER
# =============================================================================

# Benchmark thresholds - adjust here to tighten/loosen pass criteria
ACCURACY_THRESHOLD_PCT   = 85.0    # entity resolution must achieve this pass rate
PIPELINE_PASS_THRESHOLD  = 0.80    # 80% of pipeline queries must contain an expected keyword
P95_LATENCY_THRESHOLD_MS = 12000   # 12 seconds - realistic for multi-agent LLM pipelines


def build_report(
    entity_results: list,
    entity_latencies: list,
    pipeline_results: list,
    pipeline_latencies: list,
) -> BenchmarkReport:
    from datetime import datetime, timezone

    e_passed = sum(1 for r in entity_results if r.passed)
    e_acc    = (e_passed / len(entity_results) * 100) if entity_results else 0.0
    e_mean   = statistics.mean(entity_latencies) if entity_latencies else 0.0

    p_passed = sum(1 for r in pipeline_results if r.passed)
    p_rate   = (p_passed / len(pipeline_results) * 100) if pipeline_results else 100.0
    p_mean   = statistics.mean(pipeline_latencies) if pipeline_latencies else 0.0
    p_p50    = percentile(pipeline_latencies, 50)
    p_p95    = percentile(pipeline_latencies, 95)

    entity_ok   = e_acc >= ACCURACY_THRESHOLD_PCT
    pipeline_ok = p_rate >= PIPELINE_PASS_THRESHOLD * 100
    latency_ok  = (p_p95 <= P95_LATENCY_THRESHOLD_MS) if pipeline_latencies else True
    overall_ok  = entity_ok and pipeline_ok and latency_ok

    return BenchmarkReport(
        timestamp=datetime.now(timezone.utc).isoformat(),
        model=MODEL,
        entity_total=len(entity_results),
        entity_passed=e_passed,
        entity_accuracy_pct=round(e_acc, 1),
        entity_mean_ms=round(e_mean, 1),
        entity_results=[asdict(r) for r in entity_results],
        pipeline_total=len(pipeline_results),
        pipeline_passed=p_passed,
        pipeline_pass_rate_pct=round(p_rate, 1),
        pipeline_mean_ms=round(p_mean, 1),
        pipeline_p50_ms=round(p_p50, 1),
        pipeline_p95_ms=round(p_p95, 1),
        pipeline_results=[asdict(r) for r in pipeline_results],
        overall_passed=overall_ok,
        verdict="PASS" if overall_ok else "FAIL",
    )


def print_summary(report: BenchmarkReport) -> None:
    print_section("BENCHMARK SUMMARY")

    acc_ok = report.entity_accuracy_pct >= ACCURACY_THRESHOLD_PCT
    print(f"\n  Entity Resolution Accuracy:")
    print(f"    [{verdict_str(acc_ok)}]  {report.entity_passed}/{report.entity_total} correct "
          f"({report.entity_accuracy_pct:.1f}%)  [threshold: >={ACCURACY_THRESHOLD_PCT:.0f}%]")
    print(f"    Mean latency: {report.entity_mean_ms:.0f} ms")

    if report.pipeline_total > 0:
        pipe_ok = report.pipeline_pass_rate_pct >= PIPELINE_PASS_THRESHOLD * 100
        lat_ok  = report.pipeline_p95_ms <= P95_LATENCY_THRESHOLD_MS
        print(f"\n  End-to-End Pipeline:")
        print(f"    [{verdict_str(pipe_ok)}]  {report.pipeline_passed}/{report.pipeline_total} queries passed "
              f"({report.pipeline_pass_rate_pct:.1f}%)")
        print(f"    Mean : {report.pipeline_mean_ms:.0f} ms")
        print(f"    P50  : {report.pipeline_p50_ms:.0f} ms")
        print(f"    [{verdict_str(lat_ok)}]  P95  : {report.pipeline_p95_ms:.0f} ms  "
              f"[threshold: <={P95_LATENCY_THRESHOLD_MS} ms]")

        single = [r for r in report.pipeline_results if r.get("hop_type") == "single"]
        multi  = [r for r in report.pipeline_results if r.get("hop_type") == "multi"]
        if single:
            print(f"\n    Single-hop: {sum(1 for r in single if r['passed'])}/{len(single)} passed")
        if multi:
            print(f"    Multi-hop:  {sum(1 for r in multi if r['passed'])}/{len(multi)} passed")

    print(f"\n  {'-' * 60}")
    print(f"  OVERALL VERDICT  :  {report.verdict}")
    print(f"  Model            :  {report.model}")
    print(f"  {'-' * 60}\n")


# =============================================================================
# 7. ENTRY POINT
# =============================================================================

def main():
    parser = argparse.ArgumentParser(description="TargetMind Evaluation & Benchmarking Suite")
    parser.add_argument(
        "--quick", action="store_true",
        help="Run entity-resolution tests only (skip full pipeline benchmark)",
    )
    parser.add_argument(
        "--export", metavar="FILE", default=None,
        help="Save JSON report to FILE (e.g. --export report.json)",
    )
    args = parser.parse_args()

    print("\n" + "=" * 70)
    print("  TargetMind Evaluation Suite")
    print("=" * 70)
    print(f"  Entity tests  : {len(ENTITY_TESTS)}")
    print(f"  Pipeline tests: {len(PIPELINE_TESTS)}")
    print(f"  Quick mode    : {args.quick}")

    entity_results, entity_latencies = run_entity_benchmark(ENTITY_TESTS)

    pipeline_results, pipeline_latencies = [], []
    if not args.quick:
        pipeline_results, pipeline_latencies = run_pipeline_benchmark(PIPELINE_TESTS)
    else:
        print("\n  [Quick mode] Skipping pipeline benchmark.\n")

    report = build_report(entity_results, entity_latencies, pipeline_results, pipeline_latencies)
    print_summary(report)

    if args.export:
        with open(args.export, "w", encoding="utf-8") as f:
            json.dump(asdict(report), f, indent=2)
        print(f"  Report saved to: {args.export}\n")

    sys.exit(0 if report.overall_passed else 1)


if __name__ == "__main__":
    main()


# python eval.py --quick           # entity resolution only (faster)
# python eval.py                   # full benchmark
# python eval.py --export out.json # save results to JSON
