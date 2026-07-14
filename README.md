# Target Mind: A Multi-Agent Framework for Open Targets Knowledge Extraction

Target Mind is an LLM-powered multi-agent system designed to query the Open Targets biomedical platform using natural language. It translates unstructured user queries into optimized GraphQL API calls, resolving entities and executing multi-hop relational data fetching without hardcoded pipelines.

Developed as part of a Bachelor's Thesis Project (BTP) at IIIT Delhi.



## System Architecture

The framework utilizes a decoupled orchestration pattern where a central Orchestrator manages state, plans execution paths, and delegates tasks to domain-specific specialist agents. Agents interact directly with the Open Targets GraphQL endpoint.


### Agent Registry & Tool Mapping

| Agent          | Core Responsibility                                 | Associated Tools / Functions 
|----------------|-----------------------------------------------------|------------------------------
| `search_agent` | Exact & fuzzy entity name resolution to IDs         | `search_entity`              
| `target_agent` | Ensembl-centric genomic and proteomic data fetching | `target_to_diseases`, `target_to_drugs``get_entity_synonyms` 
| `disease_agent` | EFO-centric therapeutic area mapping               | `disease_to_targets`, `disease_to_drugs` 
| `drug_agent` | ChEMBL-centric pharmacology & MOA tracking            | `drug_to_targets`, `drug_to_diseases`, `drug_to_mechanism` 
| `fanout_agent` | Multi-hop relational query resolution               | 8 specialized nested pipeline tools 

---

## Key Engineering Decisions

### 1. Deterministic Multi-Hop Queries via "Fan-Out" Tools
Instead of allowing independent agents to chain sequential `N+1` API calls (which introduces high latency and compounding token costs), we engineered **2-hop Fan-Out Tools**. For complex queries like *Target → Diseases → Drugs*, the `fanout_agent` constructs a single nested GraphQL payload, resolving the entire relation in a single database round-trip.

### 2. Elimination of Entity ID Hallucination
LLMs frequently hallucinate alphanumeric identifiers (e.g., ChEMBL or Ensembl IDs). To counter this, the pipeline enforces a strict execution barrier: the `search_agent` must isolate and format a valid ID (`ENTITY_ID=`) before downstream specialist agents are permitted to trigger data-fetching tools.

### 3. Sequential Orchestration over Parallel Execution
We explicitly configured `parallel_tool_calls: False` within the orchestrator. Because biological queries are highly dependent on contextual order (e.g., you cannot look up drug indications until the target gene's ID is resolved), sequential execution prevents race conditions and corrupted agent state.

---


## Getting Started

### Prerequisites
* Python 3.10+
* Groq API Key (Llama-3.3-70B inference)

### Installation & Setup

1. **Clone the repository and install dependencies:**
   ```bash
   pip install phidata groq chainlit python-dotenv requests

2. **Configure environment variables:**
   Create a .env file in the root directory:

   ```bash
   GROQ_API_KEY=your_actual_groq_api_key
   ```

3. **Launch the Interface:**

   ```bash
   python -m chainlit run app.py
   ```
   The UI will be served locally at `http://localhost:8000`.

Team & Acknowledgments
# Abhijaya (IIIT Delhi)
# Pragya (IIIT Delhi)

Project built using data provided by the Open Targets Platform (EMBL-EBI, GSK, Sanofi, Bristol Myers Squibb, and Wellcome Sanger Institute).


