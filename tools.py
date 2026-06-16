import requests
import json

OPEN_TARGETS_URL = "https://api.platform.opentargets.org/api/v4/graphql"

PAGE_SIZE = 20  # Global cap — change this one value to adjust everywhere

def _run_query(query: str) -> str:
    """
    Execute a GraphQL query against Open Targets and return the raw JSON response as a string.
    Returns an error JSON string if the request fails.
    """
    if not query:
        return json.dumps({"error": "Empty query"}, indent=2)
    try:
        print("\nEXECUTE TOOL CALLED:")
        print("QUERY SENT TO API:\n", query)
        response = requests.post(
            OPEN_TARGETS_URL,
            json={"query": query},
            timeout=30
        )
        print("Status Code:", response.status_code)
        if response.status_code == 200:
            print("-----------------API call successful-----------------")
            print(response.json())
        else:
            print("API failed")
            try:
                print(response.json())
            except Exception:
                print(response.text)
        response.raise_for_status()
        return json.dumps(response.json(), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)}, indent=2)


def _truncate(data: dict, path: list, limit: int = PAGE_SIZE) -> dict:
    """
    Truncate a nested list at path to `limit` rows.
    path is a list of keys to traverse, e.g. ["drug", "indications", "rows"]
    Modifies data in-place and returns it.
    """
    node = data
    try:
        for key in path[:-1]:
            if isinstance(node, dict):
                node = node.get(key, {})
        last_key = path[-1]
        if isinstance(node, dict) and isinstance(node.get(last_key), list):
            node[last_key] = node[last_key][:limit]
    except Exception:
        pass
    return data



# ── 1. search_entity ─────────────────────────────────────────────────────────
def search_entity(name: str) -> str:
    """
    Search Open Targets for a target, disease, or drug by name.
    Returns up to 5 matching hits with id, name, entity type, and description.
    """
    try:
        safe_name = json.dumps(name)
        query = f"""
        {{
          search(queryString: {safe_name}, entityNames: ["target", "disease", "drug"], page: {{index: 0, size: 5}}) {{
            hits {{
              id
              name
              entity
              description
            }}
          }}
        }}
        """
        return _run_query(query)
    except Exception as e:
        return json.dumps({"error": f"search_entity failed: {str(e)}"}, indent=2)


# ── 2. target_to_diseases ─────────────────────────────────────────────────────
# page arg SUPPORTED on associatedDiseases ✅
def target_to_diseases(ensembl_id: str) -> str:
    
    """Fetch diseases associated with a target using its ID.
    Returns top 20."""
    query = f"""
    {{
      target(ensemblId: "{ensembl_id}") {{
        id
        approvedSymbol
        approvedName
        associatedDiseases(page: {{index: 0, size: {PAGE_SIZE}}}) {{
          count
          rows {{
            disease {{
              id
              name
            }}
            score
          }}
        }}
      }}
    }}
    """
    return _run_query(query)


# ── 3. target_to_drugs ───────────────────────────────────────────────────────
# drugAndClinicalCandidates does NOT support page → truncate client-side
def target_to_drugs(ensembl_id: str) -> str:
    """Fetch drugs associated with a target using its ID. Returns top 20."""
    query = f"""
    {{
      target(ensemblId: "{ensembl_id}") {{
        id
        approvedSymbol
        approvedName
        drugAndClinicalCandidates {{
          count
          rows {{
            id
            maxClinicalStage
            drug {{
              id
              name
              drugType
            }}
            diseases {{
              disease {{
                id
                name
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("target", {})
                    .get("drugAndClinicalCandidates", {})
                    .get("rows", []))
        data["data"]["target"]["drugAndClinicalCandidates"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "target_to_drugs failed"}, indent=2)


# ── 4. disease_to_targets ────────────────────────────────────────────────────
# page arg SUPPORTED on associatedTargets ✅
def disease_to_targets(efo_id: str) -> str:
    """Fetch targets associated with a disease using its ID. Returns top 20."""
    query = f"""
    {{
      disease(efoId: "{efo_id}") {{
        id
        name
        associatedTargets(page: {{index: 0, size: {PAGE_SIZE}}}) {{
          count
          rows {{
            target {{
              id
              approvedSymbol
              approvedName
            }}
            score
          }}
        }}
      }}
    }}
    """
    return _run_query(query)


# ── 5. disease_to_drugs ──────────────────────────────────────────────────────
# drugAndClinicalCandidates does NOT support page → truncate client-side
def disease_to_drugs(efo_id: str) -> str:
    """Fetch drugs for a disease using its ID. Returns top 20."""
    query = f"""
    {{
      disease(efoId: "{efo_id}") {{
        id
        name
        drugAndClinicalCandidates {{
          count
          rows {{
            id
            maxClinicalStage
            drug {{
              id
              name
              drugType
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("disease", {})
                    .get("drugAndClinicalCandidates", {})
                    .get("rows", []))
        data["data"]["disease"]["drugAndClinicalCandidates"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "disease_to_drugs failed"}, indent=2)


# ── 6. drug_to_targets ───────────────────────────────────────────────────────
# mechanismsOfAction does NOT support page → truncate client-side
def drug_to_targets(chembl_id: str) -> str:
    """Fetch targets of a drug via mechanisms of action. Returns top 20 mechanism rows."""
    query = f"""
    {{
      drug(chemblId: "{chembl_id}") {{
        id
        name
        drugType
        maximumClinicalStage
        mechanismsOfAction {{
          rows {{
            mechanismOfAction
            targets {{
              approvedSymbol
              approvedName
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("drug", {})
                    .get("mechanismsOfAction", {})
                    .get("rows", []))
        data["data"]["drug"]["mechanismsOfAction"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "drug_to_targets failed"}, indent=2)


# ── 7. drug_to_diseases ──────────────────────────────────────────────────────
# drug.indications does NOT support page → truncate client-side
def drug_to_diseases(chembl_id: str) -> str:
    """Fetch disease indications for a drug using its ID. Returns top 20."""
    query = f"""
    {{
      drug(chemblId: "{chembl_id}") {{
        id
        name
        indications {{
          count
          rows {{
            disease {{
              id
              name
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("drug", {})
                    .get("indications", {})
                    .get("rows", []))
        data["data"]["drug"]["indications"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "drug_to_diseases failed"}, indent=2)

# ── 8. drug_to_mechanism ─────────────────────────────────────────────────────
# mechanismsOfAction does NOT support page → truncate client-side
def drug_to_mechanism(chembl_id: str) -> str:
    """Fetch mechanism-of-action information for a drug using its ID."""
    query = f"""
    {{
      drug(chemblId: "{chembl_id}") {{
        id
        name
        mechanismsOfAction {{
          rows {{
            mechanismOfAction
            targets {{
              approvedSymbol
              approvedName
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("drug", {})
                    .get("mechanismsOfAction", {})
                    .get("rows", []))
        data["data"]["drug"]["mechanismsOfAction"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "drug_to_mechanism failed"}, indent=2)


# ── 9. drug_to_indications ───────────────────────────────────────────────────
# drug.indications does NOT support page → truncate client-side
# def drug_to_indications(chembl_id: str) -> str:
#     """Fetch disease indications with phase for a drug. Returns top 20."""
#     query = f"""
#     {{
#       drug(chemblId: "{chembl_id}") {{
#         id
#         name
#         indications {{
#           rows {{
#             disease {{
#               name
#             }}
#             maxPhaseForIndication
#           }}
#         }}
#       }}
#     }}
#     """
#     try:
#         raw = _run_query(query)
#         data = json.loads(raw)
#         rows = (data.get("data", {})
#                     .get("drug", {})
#                     .get("indications", {})
#                     .get("rows", []))
#         data["data"]["drug"]["indications"]["rows"] = rows[:PAGE_SIZE]
#         return json.dumps(data, indent=2)
#     except Exception:
#         return raw if 'raw' in dir() else json.dumps({"error": "drug_to_indications failed"}, indent=2)


# ── 10. get_entity_synonyms ──────────────────────────────────────────────────
# Synonyms are flat lists — no pagination needed, counts are always small
def get_entity_synonyms(entity_type: str, entity_id: str) -> str:
    """Fetch synonyms for a drug, target, or disease."""
    if entity_type == "drug":
        query = f"""
        {{
          drug(chemblId: "{entity_id}") {{
            name
            synonyms
            tradeNames
          }}
        }}
        """
    elif entity_type == "target":
        query = f"""
        {{
          target(ensemblId: "{entity_id}") {{
            approvedSymbol
            symbolSynonyms {{ label source }}
            nameSynonyms {{ label source }}
          }}
        }}
        """
    elif entity_type == "disease":
        query = f"""
        {{
          disease(efoId: "{entity_id}") {{
            name
            synonyms {{
              hasBroadSynonym
              hasExactSynonym
              hasRelatedSynonym
              hasNarrowSynonym
            }}
          }}
        }}
        """
    else:
        return json.dumps({"error": "Invalid entity_type"}, indent=2)
    return _run_query(query)


# ── COMPOUND QUERIES ──────────────────────────────────────────────────────────
# For compound queries, the OUTER list uses page where supported.
# The INNER list (drugAndClinicalCandidates, mechanismsOfAction, indications)
# does not support page, so we cap the outer to top_n=3 to keep response small.

# ── 11. target_diseases_to_drugs ─────────────────────────────────────────────
# outer: associatedDiseases supports page ✅  inner: drugAndClinicalCandidates does not
def target_diseases_to_drugs(ensembl_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top diseases linked to a target, then fetch drugs for each disease.
    Returns grouped disease-to-drug results for a target."""
    query = f"""
    {{
      target(ensemblId: "{ensembl_id}") {{
        approvedSymbol
        approvedName
        associatedDiseases(page: {{index: 0, size: {top_n}}}) {{
          count
          rows {{
            score
            disease {{
              id
              name
              drugAndClinicalCandidates {{
                count
                rows {{
                  maxClinicalStage
                  drug {{
                    id
                    name
                    drugType
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        disease_rows = (data.get("data", {})
                            .get("target", {})
                            .get("associatedDiseases", {})
                            .get("rows", []))
        for dr in disease_rows:
            cands = dr.get("disease", {}).get("drugAndClinicalCandidates", {})
            if "rows" in cands:
                cands["rows"] = cands["rows"][:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "target_diseases_to_drugs failed"}, indent=2)


# ── 12. target_drugs_to_diseases ─────────────────────────────────────────────
# outer: drugAndClinicalCandidates no page  inner: indications no page → truncate both
def target_drugs_to_diseases(ensembl_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top drugs linked to a target, then fetch diseases treated by each drug.
    Returns grouped drug-to-disease results for a target."""
    query = f"""
    {{
      target(ensemblId: "{ensembl_id}") {{
        approvedSymbol
        approvedName
        drugAndClinicalCandidates {{
          count
          rows {{
            maxClinicalStage
            drug {{
              id
              name
              drugType
              indications {{
                count
                rows {{
                  maxPhaseForIndication
                  disease {{
                    id
                    name
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        outer = (data.get("data", {})
                     .get("target", {})
                     .get("drugAndClinicalCandidates", {})
                     .get("rows", []))
        outer = outer[:top_n]  # cap outer to top_n
        for row in outer:
            ind = row.get("drug", {}).get("indications", {})
            if "rows" in ind:
                ind["rows"] = ind["rows"][:PAGE_SIZE]
        data["data"]["target"]["drugAndClinicalCandidates"]["rows"] = outer
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "target_drugs_to_diseases failed"}, indent=2)


# ── 13. target_drugs_to_mechanisms ───────────────────────────────────────────
# outer: drugAndClinicalCandidates no page  inner: mechanismsOfAction no page → truncate both
def target_drugs_to_mechanisms(ensembl_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top drugs linked to a target, then fetch mechanism-of-action data for each drug.
    Returns grouped drug-to-mechanism results for a target."""
    query = f"""
    {{
      target(ensemblId: "{ensembl_id}") {{
        approvedSymbol
        approvedName
        drugAndClinicalCandidates {{
          count
          rows {{
            maxClinicalStage
            drug {{
              id
              name
              drugType
              mechanismsOfAction {{
                rows {{
                  mechanismOfAction
                  targets {{
                    approvedSymbol
                    approvedName
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        outer = (data.get("data", {})
                     .get("target", {})
                     .get("drugAndClinicalCandidates", {})
                     .get("rows", []))
        outer = outer[:top_n]
        for row in outer:
            moa = row.get("drug", {}).get("mechanismsOfAction", {})
            if "rows" in moa:
                moa["rows"] = moa["rows"][:PAGE_SIZE]
        data["data"]["target"]["drugAndClinicalCandidates"]["rows"] = outer
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "target_drugs_to_mechanisms failed"}, indent=2)


# ── 14. disease_targets_to_drugs ─────────────────────────────────────────────
# outer: associatedTargets supports page ✅  inner: drugAndClinicalCandidates no page
def disease_targets_to_drugs(efo_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top targets linked to a disease, then fetch drugs for each target.
    Returns grouped target-to-drug results for a disease."""
    query = f"""
    {{
      disease(efoId: "{efo_id}") {{
        name
        associatedTargets(page: {{index: 0, size: {top_n}}}) {{
          count
          rows {{
            score
            target {{
              id
              approvedSymbol
              approvedName
              drugAndClinicalCandidates {{
                count
                rows {{
                  maxClinicalStage
                  drug {{
                    id
                    name
                    drugType
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        target_rows = (data.get("data", {})
                           .get("disease", {})
                           .get("associatedTargets", {})
                           .get("rows", []))
        for tr in target_rows:
            cands = tr.get("target", {}).get("drugAndClinicalCandidates", {})
            if "rows" in cands:
                cands["rows"] = cands["rows"][:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "disease_targets_to_drugs failed"}, indent=2)


# ── 15. disease_drugs_to_targets ─────────────────────────────────────────────
# outer: drugAndClinicalCandidates no page  inner: mechanismsOfAction no page → truncate both
def disease_drugs_to_targets(efo_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top drugs linked to a disease, then fetch targets acted on by each drug.
    Returns grouped drug-to-target results for a disease."""
    query = f"""
    {{
      disease(efoId: "{efo_id}") {{
        name
        drugAndClinicalCandidates {{
          count
          rows {{
            maxClinicalStage
            drug {{
              id
              name
              drugType
              mechanismsOfAction {{
                rows {{
                  mechanismOfAction
                  targets {{
                    id
                    approvedSymbol
                    approvedName
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        outer = (data.get("data", {})
                     .get("disease", {})
                     .get("drugAndClinicalCandidates", {})
                     .get("rows", []))
        outer = outer[:top_n]
        for row in outer:
            moa = row.get("drug", {}).get("mechanismsOfAction", {})
            if "rows" in moa:
                moa["rows"] = moa["rows"][:PAGE_SIZE]
        data["data"]["disease"]["drugAndClinicalCandidates"]["rows"] = outer
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "disease_drugs_to_targets failed"}, indent=2)


# ── 16. disease_drugs_to_mechanisms ──────────────────────────────────────────
# outer: drugAndClinicalCandidates no page  inner: mechanismsOfAction no page → truncate both
def disease_drugs_to_mechanisms(efo_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch top drugs linked to a disease, then fetch mechanism-of-action data for each drug.
    Returns grouped drug-to-mechanism results for a disease."""
    query = f"""
    {{
      disease(efoId: "{efo_id}") {{
        name
        drugAndClinicalCandidates {{
          count
          rows {{
            maxClinicalStage
            drug {{
              id
              name
              drugType
              mechanismsOfAction {{
                rows {{
                  mechanismOfAction
                  targets {{
                    approvedSymbol
                    approvedName
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        outer = (data.get("data", {})
                     .get("disease", {})
                     .get("drugAndClinicalCandidates", {})
                     .get("rows", []))
        outer = outer[:top_n]
        for row in outer:
            moa = row.get("drug", {}).get("mechanismsOfAction", {})
            if "rows" in moa:
                moa["rows"] = moa["rows"][:PAGE_SIZE]
        data["data"]["disease"]["drugAndClinicalCandidates"]["rows"] = outer
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "disease_drugs_to_mechanisms failed"}, indent=2)


# ── 17. drug_diseases_to_targets ─────────────────────────────────────────────
# outer: indications no page  inner: associatedTargets supports page ✅
def drug_diseases_to_targets(chembl_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch diseases indicated for a drug, then fetch top targets for each disease.
    Returns grouped disease-to-target results for a drug."""
    query = f"""
    {{
      drug(chemblId: "{chembl_id}") {{
        name
        drugType
        indications {{
          count
          rows {{
            maxPhaseForIndication
            disease {{
              id
              name
              associatedTargets(page: {{index: 0, size: {top_n}}}) {{
                count
                rows {{
                  score
                  target {{
                    id
                    approvedSymbol
                    approvedName
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        rows = (data.get("data", {})
                    .get("drug", {})
                    .get("indications", {})
                    .get("rows", []))
        data["data"]["drug"]["indications"]["rows"] = rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "drug_diseases_to_targets failed"}, indent=2)


# ── 18. drug_targets_to_diseases ─────────────────────────────────────────────
# outer: mechanismsOfAction no page  inner: associatedDiseases supports page ✅
def drug_targets_to_diseases(chembl_id: str, top_n: int = 3) -> str:
    """Fan-out: fetch targets acted on by a drug, then fetch top diseases linked to each target.
    Returns grouped target-to-disease results for a drug."""
    query = f"""
    {{
      drug(chemblId: "{chembl_id}") {{
        name
        drugType
        mechanismsOfAction {{
          rows {{
            mechanismOfAction
            targets {{
              id
              approvedSymbol
              approvedName
              associatedDiseases(page: {{index: 0, size: {top_n}}}) {{
                count
                rows {{
                  score
                  disease {{
                    id
                    name
                  }}
                }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    try:
        raw = _run_query(query)
        data = json.loads(raw)
        moa_rows = (data.get("data", {})
                        .get("drug", {})
                        .get("mechanismsOfAction", {})
                        .get("rows", []))
        data["data"]["drug"]["mechanismsOfAction"]["rows"] = moa_rows[:PAGE_SIZE]
        return json.dumps(data, indent=2)
    except Exception:
        return raw if 'raw' in dir() else json.dumps({"error": "drug_targets_to_diseases failed"}, indent=2)


# ── 19. drugs_by_clinical_stage ──────────────────────────────────────────────
def drugs_by_clinical_stage(max_clinical_stage: int) -> str:
    """
    Approximate a global drug filter by collecting drugs from broad disease categories
    and keeping only those with the requested maximum clinical stage.
    Results are not exhaustive.
    """
    broad_diseases = [
        ("MONDO_0004992", "cancer"),
        ("EFO_0000408",   "disease"),
        ("EFO_0000651",   "phenotype"),
    ]
    all_drugs = {}
    for efo_id, label in broad_diseases:
        query = f"""
        {{
          disease(efoId: "{efo_id}") {{
            name
            drugAndClinicalCandidates {{
              count
              rows {{
                maxClinicalStage
                drug {{
                  id
                  name
                  drugType
                  mechanismsOfAction {{
                    rows {{
                      mechanismOfAction
                      targets {{
                        approvedSymbol
                        approvedName
                      }}
                    }}
                  }}
                }}
              }}
            }}
          }}
        }}
        """
        try:
            raw = _run_query(query)
            data = json.loads(raw)
            rows = (data.get("data", {})
                        .get("disease", {})
                        .get("drugAndClinicalCandidates", {})
                        .get("rows", []))
            for row in rows:
                if row.get("maxClinicalStage") == max_clinical_stage:
                    drug = row.get("drug", {})
                    drug_id = drug.get("id")
                    if drug_id and drug_id not in all_drugs:
                        moa_rows = drug.get("mechanismsOfAction", {}).get("rows", [])
                        all_drugs[drug_id] = {
                            "name": drug.get("name", "Unknown"),
                            "drugType": drug.get("drugType", "Unknown"),
                            "maxClinicalStage": max_clinical_stage,
                            "mechanismsOfAction": moa_rows[:PAGE_SIZE]
                        }
        except Exception:
            continue

    if not all_drugs:
        return json.dumps({
            "error": "NO_DATA",
            "message": (
                f"No drugs found at clinical stage {max_clinical_stage}. "
                f"Try asking about a specific disease or target instead."
            )
        }, indent=2)

    drug_list = list(all_drugs.values())[:PAGE_SIZE]
    return json.dumps({
        "note": (
            f"Open Targets has no global drug filter. Showing stage "
            f"{max_clinical_stage} drugs found across broad disease categories. "
            f"Results may not be exhaustive."
        ),
        "count": len(drug_list),
        "drugs": drug_list
    }, indent=2)