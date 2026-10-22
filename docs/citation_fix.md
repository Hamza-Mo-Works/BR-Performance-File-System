# Citation validation update

The error means a model draft cited an ID not included in the supplied evidence.
It reached citation validation, so this attempt did return a model draft.
The rejected draft was not saved.

For example, DEMO-VW-001 is a historical project code inside the matching results.
It is not a citation source. A statement about that project should cite MATCHING.
A technician note such as NOTE-VW-003 is valid only if that note was retrieved
for this particular generation. This example does not identify the rejected
ID in your original response.

## Apply

Stop Streamlit with Ctrl+C. Extract the ZIP into D:\Projects\br-performance-mvp
and replace the included files. Restart with your virtual environment active:

    python -m streamlit run app.py

Select a request with saved matching and no completed engineering review.
Click Generate engineering brief again. You do not need to recreate the database,
regenerate data or change your API key.

## Change

- The prompt explicitly lists the complete valid citation IDs for this request.
- The structured output schema limits citation choices to exactly those IDs.
- Historical project codes are distinguished from citation source IDs.
- Python still validates the returned citations before saving.
- A citation-check failure triggers at most one fresh generation with a correction
  instruction using the same evidence. That means at most one additional chat
  API request. Other failures do not trigger this retry.
- If both drafts fail citation validation, no new draft is saved. An earlier saved
  brief, if any, remains intact.

Changing the prompt makes earlier briefs stale until regenerated. Previously
recorded reviews and exports remain historical records.

Citation IDs being valid does not prove that a statement is factually supported.
Engineer review remains required. The update does not edit binaries or change
the request's Python status.

Offline checks cover the citation enum, accepted and rejected IDs, successful
repair, bounded failed retries and saving behavior. A live OpenAI retry must be
performed in your local app.
