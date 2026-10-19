# Step 6: LangChain + OpenAI engineering brief

Requires the files and database from Steps 2–5. Keep the existing database and samples.

1. Stop Streamlit with Ctrl+C. Merge this package into your project root.
2. With the virtual environment active, run `python -m pip install -r requirements-ai.txt`.
3. Copy `.streamlit/secrets.example.toml` to `.streamlit/secrets.toml`. Enter the key locally.
4. Run `python -m streamlit run app.py` from the project root.
5. Run historical matching for the desired request in tab 2. Select the same request in tab 3 and generate a brief.

The secrets file is TOML, not Python or JSON. It is a local plaintext credentials file, excluded from Git by the existing .gitignore. Do not share or upload it. The example contains a placeholder only. Restart Streamlit after creating or changing the real secrets file. Credentials are passed from the UI to the API clients, not stored in SQLite.

## Actual workflow

* Read current request facts and saved deterministic matching results.
* Embed approved synthetic notes through LangChain's OpenAIEmbeddings integration. Reuse unchanged vectors cached in SQLite's new `note_embeddings` table. The first successful run embeds 30 notes; later runs only embed additions or changed notes.
* Apply hard vehicle/ECU/hardware/software scope filters. Global policies remain available. Notes tied to historical projects are eligible only when those projects appear in the matching result's reference candidates.
* Embed the question plus customer note; rank eligible notes by cosine similarity. Retrieve at most five above the demo threshold of 0.25. This threshold needs evaluation; it is not a factuality or confidence guarantee.
* Wrap notes as LangChain Documents and compose ChatPromptTemplate with ChatOpenAI structured output. Use the instructions in config/prompts.py.
* Validate that evidence statements cite supplied note IDs, REQUEST or MATCHING. This checks IDs, not whether a cited source actually supports a claim.
* Save a structured draft to requests.llm_summary, the retrieved IDs to source_ids_json, and an ASSISTANT_BRIEF audit event. Status and blockers remain controlled by Python.

Each technician note is already a short, coherent document. We do not add arbitrary chunking to this tiny corpus. Vectors are cached in SQLite and ranked in Python; no FAISS or Chroma dependency is needed for 30 notes. This is semantic RAG, not an autonomous agent.

## What OpenAI receives

Embedding requests receive the approved fictional note texts and the question/customer note. The chat request receives the question, selected request metadata, status/blockers, a compact matching summary and up to five retrieved notes. It does not receive binary contents, the API key as prompt content, or an executable tool.

Default models: gpt-4.1-mini and text-embedding-3-small. Your API project must have access and usable API quota. Live calls are configured with a 25-second timeout and no automatic retries. No live provider call was made during this build.

## Demo questions

* Golf stock: “Why did some historical records qualify while others were excluded?”
* Mercedes missing information: “Which evidence is missing and what should we request?”
* Golf downpipe/P0420: “Why should this request remain on hold despite a matching reference?”
* Unsupported tuning values: “What boost value should I use?” Expected behavior is to explain that the supplied evidence cannot authorize calibration values.

Outputs are unverified drafts for a human. The model can still make mistakes or follow malicious text in its narrative; it cannot change status, execute code, select/release a file or modify binaries. A no-evidence result generates a clearly labelled deterministic abstention instead of calling the chat model. Approved note indexing/query embeddings can still use the API in that case.

Cached drafts persist after a browser reload. A snapshot check marks them stale if request or matching data changed. It does not recheck disk files at display time; rerun matching when file evidence changes. Request/matching changes during generation prevent saving the draft.

## Code map

config/ai_settings.py: defaults and limits.
config/prompts.py: actual system/user prompt.
schemas/engineering_brief.py: allowed output structure; no approval fields.
services/retrieval_service.py: embedding cache, hard scope filters and ranking.
services/llm_service.py: LangChain generation, citation-ID checks and draft persistence.
ui/assistant_page.py: secrets access, request picker and draft display.

## Validation limits

Offline checks use fake embedding/model adapters to verify scope filtering, cache reuse, citation rejection, failure handling and preservation of request status. They do not establish OpenAI availability, answer quality or live Streamlit rendering. The first local generation with your key is the integration check. Review every answer against the displayed sources.
