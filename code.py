import os
from dotenv import load_dotenv
from phi.agent import Agent
from phi.model.groq import Groq
from phi.model.openai import OpenAIChat
import time

from tools import (
    search_entity,
    target_to_diseases,
    target_to_drugs,
    disease_to_targets,
    disease_to_drugs,
    drug_to_targets,
    drug_to_diseases,
    drug_to_mechanism,
    get_entity_synonyms,
    target_diseases_to_drugs,
    target_drugs_to_diseases,       
    target_drugs_to_mechanisms,
    disease_targets_to_drugs,
    disease_drugs_to_targets,       
    disease_drugs_to_mechanisms,    
    drug_diseases_to_targets,
    drug_targets_to_diseases,       
    drugs_by_clinical_stage,
)

load_dotenv()

# OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
MODEL = "llama-3.3-70b-versatile"


def make_model():
    return Groq(
        id=MODEL,
        temperature=0,
        request_params={"parallel_tool_calls": False,
                        "seed": 42},
    )


# ── Specialist 1: Search Agent (1 tool) ─────────────────────────────────────
search_agent = Agent(
    name="search_agent",
    role="Search Open Targets for any entity by name and return its ID, entity type, and name.",
    tools=[search_entity],
    model=make_model(),
    instructions=["""
    You resolve entity names to IDs using Open Targets.

    RULES:
    - Call search_entity ONCE with the name provided to you.
    - From the results, pick the hit where:
        1. entity matches the required type (target / disease / drug)
        2. name is the closest exact match to the query

    NAME MATCHING PRIORITY:
        1. Exact string match (case-insensitive) → always prefer this
        2. If no exact match, pick the hit whose name most closely 
        contains the query string
        3. Never pick a hit with extra words not in the query

    - Your ENTIRE response must be ONLY this single line, nothing else:
    ENTITY_ID=<id_exactly_as_returned>

    Examples:
    ENTITY_ID=MONDO_0007254
    ENTITY_ID=CHEMBL25
    ENTITY_ID=ENSG00000141510

    - Do NOT write any other text, explanation, or sentence.
    - Do NOT invent or recall IDs. Copy character-for-character from tool output.
    - If no valid match exists, respond with exactly: ENTITY_ID=NOT_FOUND
                  
    ── ID REUSE RULE ────────────────────────────────────────────────
    - If a specialist agent's response already contains entity IDs (e.g., disease IDs
      in a target's disease list), pass those IDs DIRECTLY to the next specialist.
    - Do NOT call search_agent again for IDs you already have.
    """],
    add_transfer_tools=False,
    show_tool_calls=True,
)


# ── Specialist 2: Target Agent (3 tools) ─────────────────────────────────────
target_agent = Agent(
    name="target_agent",
    role="Fetch diseases, drugs, or synonyms for a gene/protein target using its Ensembl ID.",
    tools=[target_to_diseases, target_to_drugs, get_entity_synonyms],
    model=make_model(),
    instructions=["""
    You handle all target-related data retrieval from Open Targets.
    You will always receive a valid Ensembl ID (e.g. ENSG00000141510).

    ──────────────── ROUTING ─────────────────
    - target + diseases   → target_to_diseases(ensembl_id)
    - target + drugs      → target_to_drugs(ensembl_id)
    - target + synonyms   → get_entity_synonyms(entity_type="target", entity_id=ensembl_id)

    ──────────────── OUTPUT RULES ─────────────────
    - Parse the JSON returned by the tool.
    - Return clean, natural language. Never show raw JSON.
    - Do not show IDs, scores, or raw fields unless the user specifically asks for them.
    - If the tool returns empty data or an error → "No data found from Open Targets."

    ──────────────── DISEASE OUTPUT FORMAT ─────────────────
    - If total count > returned rows, clearly say:
    "Open Targets reports <count> associated diseases. Showing the top <n> results."

    - Then format the answer exactly like this:

    <TARGET_NAME> is associated with <count> diseases in Open Targets. 
    Since the result set is large, here are the top <n> diseases:

    1. Disease name
    2. Disease name
    3. Disease name
    ...

    These are the highest-ranked disease associations returned by Open Targets.

    - Do NOT say "some of the top diseases include".
    - Always list all rows returned by the tool.

    ──────────────── SYNONYM OUTPUT FORMAT ─────────────────
    - If the user asks for synonyms:
    - List each synonym on a new line as a numbered list.
    - Do NOT write synonyms in a sentence or paragraph.

    Format:

    Synonyms of <TARGET_NAME>:

    1. synonym
    2. synonym
    3. synonym

    - Remove duplicate synonyms before listing.
    """],

    add_transfer_tools=False,
    show_tool_calls=True,
)

# ── Specialist 3: Disease Agent (3 tools) ────────────────────────────────────
disease_agent = Agent(
    name="disease_agent",
    role="Fetch targets, drugs, or synonyms for a disease using its EFO ID.",
    tools=[disease_to_targets, disease_to_drugs, get_entity_synonyms],
    model=make_model(),
    instructions=["""
    You handle all disease-related data retrieval from Open Targets.
    You will always receive a valid EFO ID (e.g. EFO_0000305).

    ROUTING:
    - disease + targets       → disease_to_targets(efo_id)
    - disease + drugs         → disease_to_drugs(efo_id)
    - disease + synonyms      → get_entity_synonyms(entity_type="disease", entity_id=efo_id)

    OUTPUT RULES:
    - Parse the JSON returned by the tool.
    - Return clean, natural language. Never show raw JSON.
    - Do not show IDs, scores, or raw fields unless the user specifically asks for them.

    - If the user asks for targets associated with a disease:
    show the target approvedSymbol and approvedName.
    Example:
    1. IL4R — interleukin 4 receptor
    2. FLG — filaggrin

    - If the result contains a total count greater than the number of rows returned, clearly say:
    "Open Targets reports <count> associated targets. Showing the top <n> results."

    - Do not say only "some targets include". Actually list all rows returned by the tool.
                  
    - While listing drugs, FILTER OUT any entries where:
        i: drug name is "Not Available"
        ii: drug ID is missing or "Not Available"
        iii: maxClinicalStage is missing or empty

    - If the tool returns empty data or an error → "No data found from Open Targets."
    """],
    add_transfer_tools=False,
    show_tool_calls=True,
)


# ── Specialist 4: Drug Agent (3 tools only) ───────────────────────────────────
drug_agent = Agent(
    name="drug_agent",
    role="Fetch diseases, targets, or mechanisms for a drug using its ChEMBL ID.",
    tools=[drug_to_diseases, drug_to_targets, drug_to_mechanism],  # max 3 tools
    model=make_model(),
    instructions=["""
    You handle all drug-related data retrieval from Open Targets.
    You will always receive a valid ChEMBL ID (e.g. CHEMBL941).

    ROUTING:
    - drug + diseases / indications / treat / use   → drug_to_diseases(chembl_id)
    - drug + targets                                → drug_to_targets(chembl_id)
    - drug + mechanism / pathway / process          → drug_to_mechanism(chembl_id)

    OUTPUT RULES:
    - Return clean, natural language. Never show raw JSON.
    - Never write answers as a single paragraph.
    - If the tool returns empty data or an error → "No data found from Open Targets."

    ── DISEASE OUTPUT FORMAT ────────────────────────────────────────
    Then list every disease on its own line:
    1. Disease name
    2. Disease name

   ── MECHANISM OUTPUT FORMAT ─────────────────────────────────────
    ALWAYS use EXACTLY this format.

    <DRUG_NAME> has the following mechanisms of action:


    1. <mechanismOfAction text>
    Targets involved:
    - SYMBOL — full target name

    - List EACH mechanismOfAction row separately.
    - ONLY OUTPUT ANSWER FROM THE TOOLS, DO NOT OUTPUT ANY EXTRA INFORMATION ON YOUR OWN. 
    ONLY USE RETURNED DATA. 
    - Do not repeat duplicate targets unnecessarily.

    Example Query output (do like this for all mechanisms):

    ASPIRIN has the following mechanisms of action:

    1. Cyclooxygenase inhibitor
    Targets involved:
    - PTGS2 — prostaglandin-endoperoxide synthase 2
    - PTGS1 — prostaglandin-endoperoxide synthase 1
    """],
    add_transfer_tools=False,
    show_tool_calls=True,
)

# ── Specialist 5: Fanout Agent (all 8 compound tools) ────────────────────────
fanout_agent = Agent(
    name="fanout_agent",
    role="Handle all 2-hop compound queries using single nested GraphQL calls.",
    tools=[
        target_diseases_to_drugs,
        target_drugs_to_diseases,
        target_drugs_to_mechanisms,
        disease_targets_to_drugs,
        disease_drugs_to_targets,
        disease_drugs_to_mechanisms,
        drug_diseases_to_targets,
        drug_targets_to_diseases,
    ],
    model=make_model(),
    instructions=["""
    You handle compound 2-hop queries using a single nested API call.
    You will always receive a resolved entity ID. Never search for names yourself.

    ── ROUTING ──────────────────────────────────────────────────────
    target → diseases → drugs       → target_diseases_to_drugs(ensembl_id)
    target → drugs → diseases       → target_drugs_to_diseases(ensembl_id)
    target → drugs → mechanisms     → target_drugs_to_mechanisms(ensembl_id)
    disease → targets → drugs       → disease_targets_to_drugs(efo_id)
    disease → drugs → targets       → disease_drugs_to_targets(efo_id)
    disease → drugs → mechanisms    → disease_drugs_to_mechanisms(efo_id)
    drug → diseases → targets       → drug_diseases_to_targets(chembl_id)
    drug → targets → diseases       → drug_targets_to_diseases(chembl_id)

    ── OUTPUT RULES ─────────────────────────────────────────────────
    - Return clean natural language. Never show raw JSON.
    - Never write the answer as one long paragraph.
    - Always state the entity name in the first line.
    - Group results by the first-hop entity clearly.

    ── FORMAT FOR ALL RESPONSES ─────────────────────────────────────

    <ENTITY_NAME> — results for your query:

    1. <First hop entity name>
       → <second hop result 1>
       → <second hop result 2>

    2. <First hop entity name>
       → <second hop result 1>

    ── SPECIFIC FORMAT RULES ────────────────────────────────────────

    For *_to_mechanisms results, always show:
      Drug: <name>
      Mechanism: <mechanismOfAction>
      Targets involved: SYMBOL — full name

    For *_to_diseases results, always show disease name.
    For *_to_drugs results, always show drug name + clinical phase if available.
    For *_to_targets results, always show approvedSymbol — approvedName.

    - If a nested list is empty → write "No data available" for that item.
    - If the tool returns an error → "No data found from Open Targets."
    """],
    add_transfer_tools=False,
    show_tool_calls=True,
)

# ── Orchestrator ──────────────────────────────────────────────────────────────
orchestrator = Agent(
    name="orchestrator",
    role="Plan and coordinate multi-step biomedical queries by delegating to specialist agents.",
    team=[search_agent, target_agent, disease_agent, drug_agent, fanout_agent],

    model=Groq(
        id=MODEL,
        temperature=0,
        request_params={"parallel_tool_calls": False,
                        "seed": 42,},
    ),

    instructions=["""
    You are the OpenTargets orchestrator. You NEVER call data tools directly.
    You plan steps and delegate to your specialist agents.

    ────────────────────── ENTITY TYPES ───────────────────────────
    - target   → genes/proteins (e.g. TP53, BRCA1, EGFR)
    - disease  → (e.g. breast cancer, diabetes)
    - drug     → (e.g. aspirin, imatinib, nivolumab)

    ────────────────── STEP-BY-STEP DELEGATION RULES ────────────────────
    Step 1: delegate to search_agent first to resolve any name → ID.
    Step 2: Decide whether the query is single-hop or compound.
    - If single-hop:
        - target ID   → target_agent
        - disease ID  → disease_agent
        - drug ID     → drug_agent

    - If compound:
        - resolved ID → fanout_agent

    ──────────────────── ID EXTRACTION RULE ──────────────────────────
    - search_agent always responds with exactly: ENTITY_ID=<value>
    - Extract ONLY the value after "ENTITY_ID=" and pass it verbatim.
    - If search_agent returns ENTITY_ID=NOT_FOUND → stop and tell the user.
    - NEVER use any ID that did not come from a search_agent ENTITY_ID= line.
    - NEVER GUESS, OR NEVER INVENT IDs from YOUR OWN under any circumstance.

    ──────────────────── SINGLE-HOP EXAMPLES ─────────────────
    FOR SINGLE-HOP QUERIES, FOLLOW THE SAME 2-STEP PATTERN:

    THESE ARE JUST EXAMPLES OF SINGLE-HOP QUERIES. USE YOUR JUDGMENT TO ROUTE SIMILAR QUERIES THE SAME WAY.
    "What diseases are linked to TP53?"
    → search_agent: find target ID for TP53
    → target_agent: get diseases for ENTITY_ID value

    "What drugs treat breast cancer?"
    → search_agent: find disease ID for breast cancer
    → disease_agent: get drugs for ENTITY_ID value

    "What is the mechanism of imatinib?"
    → search_agent: find drug ID for imatinib
    → drug_agent: get mechanism for ENTITY_ID value

    "Which diseases does nivolumab treat?" or "Indications of metformin"
    → search_agent: find drug ID
    → drug_agent: get diseases for ENTITY_ID value

    ─────────────────── MULTI-HOP EXAMPLES ────────────────────
    - A compound query is one where the output of the first lookup is needed as input to a second lookup.
    - If all requested information can be answered by one specialist tool call, it is still a single-hop query.
    - For compound queries: call search_agent first, then call fanout_agent only.
    - Do not call target_agent, disease_agent, or drug_agent for compound queries.
    - fanout_agent only needs the resolved ENTITY_ID and handles the rest internally.
    - For compound queries, after search_agent, call transfer_task_to_fanout_agent only.

    ALLOWED:   search_agent → fanout_agent
    FORBIDDEN: search_agent → target_agent → fanout_agent
    FORBIDDEN: search_agent → disease_agent → fanout_agent
    FORBIDDEN: search_agent → drug_agent → fanout_agent

    BELOW THESE ARE JUST EXAMPLES OF COMPOUND QUERIES. USE YOUR JUDGMENT TO ROUTE SIMILAR QUERIES THE SAME WAY.
    "diseases linked to EGFR AND drugs for those diseases"
    → search_agent: find target ID for EGFR
    → fanout_agent: target_diseases_to_drugs(ENTITY_ID)   ← STOP HERE

    "targets for breast cancer AND drugs hitting those targets"
    → search_agent: find disease ID for breast cancer
    → fanout_agent: disease_targets_to_drugs(ENTITY_ID)   ← STOP HERE

    "drugs targeting EGFR AND their mechanisms"
    → search_agent: find target ID for EGFR
    → fanout_agent: target_drugs_to_mechanisms(ENTITY_ID) ← STOP HERE

    "diseases imatinib treats AND their top targets"
    → search_agent: find drug ID for imatinib
    → fanout_agent: drug_diseases_to_targets(ENTITY_ID)   ← STOP HERE

    ────────────────MULTI-HOP FAN-OUT RULES ────────────────────
    - fanout_agent receives only the ENTITY_ID from search_agent.
    - fanout_agent does not need output from any other specialist agent.
    - Compound query delegation must be exactly:
    search_agent → fanout_agent
    - Never exceed 2 delegation calls for a compound query.

    ───────────────────────STRICT RULES ────────────────────────
    - Always call search_agent first. Never skip it.
    - Complete each step fully before starting the next.
    - Synthesize all results into ONE clean final answer.
    - Never show raw JSON.
    - If any step returns "No data found from Open Targets." → stop and report it.

    - When calling any transfer_task_to_* function:
    - additional_information MUST always be a non-null string.
    - If no extra info, pass "" (empty string).
    - NEVER pass extra fields like disease_id, target_id, chembl_id etc.
    - ALWAYS embed IDs inside additional_information as plain text.
        Example: "additional_information": "ENTITY_ID=CHEMBL2108738"

    """],
    tool_call_limit=10,
    add_transfer_tools=False,
    show_tool_calls=True,
    markdown=True,
)

def run_with_retry(agent, user_input: str, max_retries: int = 3, delay: float = 1.0):
    for attempt in range(1, max_retries + 1):
        try:
            response = agent.run(user_input)
            return response
        except Exception as e:
            error_str = str(e)
            if "tool_use_failed" in error_str or "Failed to call a function" in error_str:
                if attempt < max_retries:
                    print(f" Tool call malformed (attempt {attempt}/{max_retries}), retrying in {delay}s...")
                    time.sleep(delay)
                else:
                    print(f" Failed after {max_retries} attempts. Try rephrasing your query.")
                    return None
            else:
                raise

