# Final MVP step: human intake review and export

Merge this update into the existing project. No database reset, reseeding, new package installation or key changes are required. Stop/restart Streamlit to load the changed modules.

## What is fixed in the AI context

The previous draft correctly named candidates but said some criteria were not supplied. The model context now includes the complete checked-fields list, explicit candidate counts, vehicle scope, historical status rule, original-fingerprint requirement and synthetic-reference validation rules. The model must not present provided criteria as missing evidence.

Prompt versions are now included in the draft snapshot. Existing drafts will be marked stale after this update. Regenerate the Golf brief in tab 3 before acknowledging the intake. The note embedding cache can still be reused.

## Run the complete workflow

1. Start `python -m streamlit run app.py` from the project root with the virtual environment active.
2. For a new request, upload a generated sample, select Stage 1, enter its customer note and save.
3. In tab 2, select that saved request and run historical matching. Golf stock should yield 9 candidates, 2 near matches, 1 excluded.
4. In tab 3, generate or regenerate the engineering brief. Inspect its cited evidence and retrieved notes.
5. In tab 4, select the same request. Enter a demo reviewer name, explicitly choose a reference candidate, add an optional note, check the evidence-review checkbox and click Acknowledge intake.
6. Status becomes INTAKE_REVIEWED. Download HTML for a readable report or JSON for full structured evidence.

For Mercedes, acknowledgement is disabled because identifiers are incomplete. Enter a reviewer name and a note such as “Please provide the hardware ID and read method”, then choose Request information. Status becomes INFORMATION_REQUESTED, and the missing reasons are retained. You can export this decision as a work package too. No email, message or ticket is sent.

## Review boundaries

* Acknowledgement covers intake evidence only; it is not tuning or road-use approval.
* Python checks the current original and reference evidence again before acknowledgement. Changes since matching require a new matching run. A stale AI draft requires regeneration.
* References must come from the eligible candidate list. Rejected, near-match or pending-review records cannot be attached through the acknowledgement path.
* Once a decision is recorded, another decision, matching run or AI generation for the same request is blocked. Submit a revised request to start another cycle. The recorded brief remains viewable and is identified as included in review.
* Reviewer names are self-declared. There is no authentication, RBAC or signed approval. SQLite audit history is mutable, so this is a local interview demonstration, not a compliance system.

## What the export contains

Request metadata and customer note; original fingerprint and relative location; matching candidates/near matches/exclusions; saved AI draft and retrieved notes; reviewer decision, selected reference, comment and timestamp; per-request audit events. Configured credentials and binary contents are not included.

The HTML report escapes untrusted text. It opens in a browser and may be printed. JSON preserves the full structured evidence. Download clicks record EXPORT_REQUESTED with the exported content's SHA-256. The report cannot include its own later download-click event; subsequent exports can include earlier export events.

## Final interview rehearsal

Use one stock Golf and one incomplete Mercedes request. Show upload and parsing, Golf matching differences, evidence-backed explanation, named intake acknowledgement, readable export, and the Mercedes information-request path. Explain that ECU identification and binary files are simulated. Actual calibration, checksum correction, vehicle writing and customer delivery remain external to this MVP.

The completed scope is a local Python/Streamlit/LangChain RAG intake copilot with a bounded workflow. It is not an autonomous ECU tuning agent. Production integration would require supported ECU identification/tool interfaces and genuine engineering evidence.

Offline checks cover review gates, reference choice, original/reference changes, draft version handling, terminal decisions, HTML escaping and exported audit data. The live OpenAI path was confirmed by the user before this update; the new UI and regenerated prompt require the final local smoke check.
