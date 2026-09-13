How do you monitor your agents in production?

I implemented a custom decorator wrapper in observability.py that formats every agent execution as a structured JSON log. It tracks latency, error types, and matches them to a unique trace_id. This allows us to ingest these logs directly into standard monitoring pipelines like the ELK stack or Datadog to profile latency bottlenecks, trace multi-agent execution paths, and set up alerts for rate limits or API failures

How do you test and evaluate agentic systems before deploying them?

I built a custom automated benchmarking suite in eval.py containing ground-truth test datasets for target, disease, and drug entity mappings. It acts as a CI/CD quality gate that measures entity resolution accuracy & latency. By running this test suite, we ensure that updates to agent prompts or model versions do not cause regressions, keeping accuracy above our 85% target. 
Means deployment will not happen if accuracy drops below 85%. in github actions- exit code of 1 automatically fails build and block deployment.


**use of telemetry log**
targetmind_telemetry.log is mainly for*observability/debugging.*
It records things like:
Trace/request IDs to follow one query through the agents.
Agent/tool execution and latency to identify slow steps.
Errors/retries when GraphQL or agent execution fails.
Useful for performance analysis and troubleshooting during development/testing.

**What does N+1 mean?**
without optimization: we will require N+1 calls 
means 1 initial call to get 3 entities associated with it and 3 separate calls to get 3 drug candidates for each disease =>total 4 means n+1 calls.

<By solving n+1 query optimization - i know that i can improve database querying, latency optimization, and backend efficiency>

**With fan out optimization**
1 single nested GraphQL query retrieves the target, its diseases, and all corresponding drugs in 1 single network round-trip.

using deterministic GraphQL tool-calling and nested fan-out queries to reduce multi-hop network round trips

**Open target**
 an enterprise-grade GraphQL API used by real pharmaceutical giants

 **improving reliability**
 I improved reliability by making parallel tool call execution to false so that it can follow sequential order and prevent hallucination risk of ID. know how to build **fault-tolerant systems**. 

 *optimization*
 handled paging to improve  *memory management* and *token cost limits*.

 How did you reduce Hallucination in Target Mind?
# Strict Tool-Augmented Grounding. 
we engineered a system where LLm is never allowed to rely on its internal memory for any information. Instead, we force it to use external tools for every query, even for simple facts.
>Ex- Search agent
Instead of letting the main agent guess an ID, you created a dedicated search_agent whose only job is to query the Open Targets search API and return a verified ID. You forced it to output in a strict format.

>Strict orchestration prompts - Strict prompt engineering

> Sequetial tool calling
we disabled and set parallel_tool_calls: False. because if they were enabled , LLm might call serach entity and target_to_disease at exact same time. for teh same, i will have to hallucinate id for second tool because first tool haven't finished yet.

>Graceful "No data " fallbacks
LLM hallucinates if database return zero results , so we had strict output rules, instead of hallucination it returns- No data found from Open Targets and stop.


"I used a GraphQL API and wrote 19 custom tool functions with pagination and error handling"



How did you tested benchmarking?
I created a separate benchmark script to compare the baseline N+1 approach against the optimized nested GraphQL fan-out approach. I used the same TP53 target and retrieved the same 3 associated diseases and their drugs in both cases.

I first ran 3 warm-up requests to reduce cold-start effects. Then I executed 30 runs for each approach under the same environment and measured end-to-end HTTP latency using Python's time.perf_counter().

In the baseline, I made 4 sequential network requests — one request for the target's diseases and then one request for each of the 3 diseases. In the optimized version, I retrieved the same relationship using one nested GraphQL request.

I calculated the mean, P50, and P95 latency across the 30 runs. The mean latency was approximately 1.81 seconds for the sequential approach versus 453 milliseconds for the fan-out approach, giving about a 75% reduction.
============================================================================================================================================================================================================================================





How did you evaluate performance? what are metrics?
System Efficiency (Latency) and Agent Reliability (Accuracy).
Latency - we needed to ensure chatbot dont consume unnecessary tokens
API Round-Trip Time (Latency) - we tracked time took for each tool to respond. By using a single nesed query GraphQL call for 2 hop queries , we reduced API latency by 50% comapred to chaining multiple agnets calls sequentially.

Token Optimization - we optimised number of tool call, reduce the response payload and strictly controlled response size. By doing this we reduced the response token by 30%.which also help to reduce the hallucination

Accuracy - We focussed on Entity Resolution Accuracy, Routing Accuracy. Also Tool -call success rate . We measured and mitigates failures by implementing run_wuth_retry whcih catches malinformed tool calls and forces agent to try again and significantly boosting overall accuracy and success rate.

how you actually tested this?
We evaluated this manually using a qualitative test set of common, edge-case, and complex multi-hop queries .We monitored the terminal logs to verify that the Orchestrator's execution plan matched the expected routing.

==============================================================================================
What bottlenecks did you face? How did you solve them?
Bottlenecks are component or process that slows down the overall system's performance

> The N+1 Query Problem (Latency)
Multi-hop queries forced the agent to chain multiple API calls sequentially. This caused severe lag and wasted tokens. 
Solution: We switched from sequential API calls to a single, nested GraphQL query which is 2-hop "Fan-Out" tools. This allowed us to fetch all the data needed for a multi-hop path in a single request, reducing latency by 50% and eliminating redundant tool calls.

>  Context Window Overflow (Tokens)
 Open Targets returns massive JSON payloads. Sending thousands of rows of drugs to the LLM would overwhelm its context window, causing crashes and high costs.
 Solution: We enforced strict Pagination and Truncation.

> Malformed Tool Calls (Reliability)
 The LLM would occasionally generate malformed JSON when trying to trigger a tool, causing the entire Python application to crash.
 We built a custom run_with_retry wrapper. It catches tool-use exceptions, pauses, and forces the agent to retry the tool call up to 3 times, completely eliminating crashes from bad JSON.

> Agent Routing Confusion
The Orchestrator agent would sometimes skip the ID resolution step or try to call multiple specialist agents at the exact same time.
We enforced Sequential Execution (parallel_tool_calls: False) so the agent had to wait for the verified ID then only move to next tool calling.

----------------------------------------------------------------------------------------------
# Why did you build an Agentic system instead of just using RAG (Retrieval-Augmented Generation)
RAG is great for unstructured text (like reading PDFs or Wikipedia), but it is terrible for structured, highly relational data like a biomedical knowledge graph. If I used RAG, I would have to download and embed millions of Open Targets relationships into a vector database, which would be massive and go out of date quickly.

Instead, an Agentic System with Tool-Calling allows the LLM to query the live, structured Open Targets database in real-time. It guarantees that the data (like clinical stages or drug targets) is 100% accurate and up-to-date, directly from the source.

--------------------------------------------------------------------------------------------------------------------------------
Now they will test how function calling works ?
# How does the LLM actually know which tool to use?
the Phidata framework takes the Python functions in my tools.py file and converts their docstrings and parameter types into a JSON schema. This schema is injected into the LLM's system prompt.

When the user asks a question, the LLM analyzes the prompt, looks at the available tools in its schema, and instead of generating normal text, it generates a structured JSON object containing the tool name and arguments (like ensembl_id). My Python script parses that JSON, executes the actual GraphQL request, and feeds the result back to the LLM.

----------------------------------------------------------------------------------------------
to test backend knowledge
# Why use GraphQL instead of a traditional REST API? 
GraphQL was perfect for this project because biological data is a highly interconnected graph (Genes → Diseases → Drugs).

If I used a REST API, getting drugs for a disease might require fetching a list of drug IDs from one endpoint, and then making 50 separate HTTP requests to a /drug/{id} endpoint to get their names. With GraphQL, I can write a single, nested query that fetches exactly the fields I want (like drug name and clinical stage) in one single HTTP request. This drastically reduced the latency for my multi-agent system

# What happens if a user asks a completely unrelated question, like 'What is the capital of France?
Because the Orchestrator has a strict system prompt instructing it to act as an Open Targets biomedical assistant, it will attempt to route the query to the search_agent. The search_agent will search Open Targets for 'capital of France', return ENTITY_ID=NOT_FOUND, and the Orchestrator will politely reply to the user that it cannot find any data on that topic in the biomedical database. The strict routing prevents it from breaking character.

to test software engineering practices?
# How does system handle  API rate limits or network failures
At the API level, the _run_query function uses a try/except block with a timeout. If the HTTP request fails, it returns a JSON string containing an error message rather than crashing the script.
At the Agent level, if the LLM generates a malformed tool call, my custom run_with_retry wrapper catches the tool_use_failed exception and automatically forces the LLM to retry up to 3 times before finally giving up and alerting the user.

# what is future scope of this project?
> Response Streaming: Right now, the user has to wait a few seconds for the entire response to generate. I would implement token streaming so the UI feels more responsive, like ChatGPT.

> Redis Caching: Many users search for the exact same diseases (like 'Breast Cancer'). I would add a Redis cache layer. If a query has been asked before, I would return the cached GraphQL result instantly without burning LLM tokens or hitting the Open Targets API.

>Dockerization: I would containerize the Chainlit app and Python environment using Docker so it could be deployed seamlessly to AWS or Google Cloud."


to understand if you know about DevOPS and cloud deployment
# How would you deploy this to production?

Currently, it runs locally on my machine. To deploy it to production, I would write a Dockerfile to package the application. Since it's a stateless Chainlit web application, I would deploy it on a fully managed container service like AWS Fargate or Google Cloud Run. Because it doesn't need a heavy local database (all data comes from the external Open Targets API), it would scale horizontally very easily.

# why did you build this project
1. The Problem: Platforms like Open Targets are incredibly powerful for drug discovery, but their data is locked behind complex GraphQL APIs. A biologist or medical researcher shouldn't have to learn GraphQL and read through JSON schemas just to find out what drugs target a specific disease. I wanted to build a bridge that lets them use natural language to access this enterprise-grade data instantly.

2. The Engineering Challenge: I wanted the challenge of making an LLM interact with a live, strict external database reliably. Solving problems like the N+1 query latency, preventing the LLM from hallucinating database IDs, and managing the orchestration of multiple specialist agents taught me far more about system design and fault tolerance

# probelm does it solve?
> Target Mind solves the data accessibility gap in drug discovery and bioinformatics. Right now, platforms like Open Targets hold massive, invaluable datasets linking genes, diseases, and drugs. However, to actually query that data, you have to know how to write complex, nested GraphQL queries, parse JSON responses, and handle database identifiers like Ensembl or ChEMBL IDs. The problem is that the people who need this data the most—biologists, medical researchers, and pharmacologists—are rarely software engineers. Target Mind acts as an AI translator. It allows researchers to ask complex relational questions in plain English, instantly handles the backend GraphQL translation and data fetching, and returns clean, readable results. It democratizes access to enterprise biomedical data by removing the coding barrier.


