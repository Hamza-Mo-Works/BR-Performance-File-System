# Engineering brief error update

Extract this ZIP into your existing project folder and replace the two Python files.
It contains no database, sample data, or API key.

1. Stop Streamlit in the terminal with Ctrl+C.
2. From your project folder, with the virtual environment active, restart:

   python -m streamlit run app.py

3. Select a request that has historical matching and no final engineering review.
4. Try: "Summarize this request in three short points using supplied evidence."
5. If generation fails, share the new on-screen message or the terminal line
   beginning AI_DIAGNOSTIC. Do not share secrets.toml or your API key.

The old generic message did not identify the cause. This update distinguishes
note retrieval, model generation and citation validation. It allows more output
tokens and a longer per-call timeout. Brackets, whitespace and letter case in
otherwise valid source IDs are normalized. Unknown or absent evidence citations
still cause the draft to be rejected. Stored request status is unchanged.

Error meanings:

- OUTPUT_LIMIT: the response was cut short.
- STRUCTURED_OUTPUT: the response did not match the brief format.
- CITATION_CHECK: an evidence statement cited an unknown source or had no citation.
- TIMEOUT or CONNECTION: the OpenAI request did not complete.
- API_400: model settings or response schema were rejected.
- OPENAI_SERVER: the provider returned a server error.
- AI_ERROR: an unclassified failure; share the safe diagnostic line.
- HTTP 401, 403, 404 or 429: the app reports key, permission, model, or quota/rate-limit issues.

Offline checks passed for structured-response handling, citation validation,
safe diagnostics and the SQLite generation workflow. No live API request was
made during these checks; your retry is needed to identify the original failure.
