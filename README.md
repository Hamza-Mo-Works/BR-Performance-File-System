# BR-Performance File System

Independent interview MVP for preparing ECU file-service requests for human
engineering review. Python, Streamlit, SQLite and LangChain/OpenAI are used for a
synthetic demonstration; this project is not affiliated with BR-Performance.

## Local setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python database.py
python -m scripts.generate_demo_data
Copy-Item .streamlit/secrets.example.toml .streamlit/secrets.toml
```

Enter your own OpenAI key in `.streamlit/secrets.toml` locally. Keep that file
private. Start the app with `python -m streamlit run app.py` from the project root.
Generating a brief uses your OpenAI API account; intake and matching use Python.

## Workflow

1. Upload an original synthetic sample and save the customer request.
2. Run historical matching and inspect eligible, near-match and excluded records.
3. Generate an evidence-cited engineering brief and inspect retrieved notes.
4. Record an intake acknowledgement or a request for information.
5. Export a readable HTML report or a structured JSON work package.

The seed creates five vehicles, thirty historical projects, thirty technician
notes, ten sample containers and thirty reference containers. SQLite and generated
data remain local; the history helper stages source files by explicit path.

## Code structure

- `config/`: paths, validation, matching rules, AI defaults and prompts.
- `services/`: database, seed, intake, matching, retrieval, AI, review and export.
- `schemas/`: engineering brief output structure and valid citation choices.
- `ui/`: Streamlit pages; `app.py` connects them.
- `scripts/`: reproducible demo data generation.
- `docs/`: scope, AI setup, troubleshooting, review and rehearsal guides.
- `helper/`: optional reconstruction of a Git history from existing source files.

## Demonstration boundaries

The files contain an invented header and random payload, not real ECU firmware.
Candidate matching is preparation for human assessment, not compatibility or
calibration approval. The AI cannot change status or edit binaries. It can still
make unsupported claims even when its source IDs are valid; review is required.

There is no authentication, real ECU-tool integration, vehicle writing or customer
delivery. Reviewer names are self-declared and SQLite audit history is mutable.

## Git history

The optional helper assigns weekday dates from 5-23 October 2026 to actual file
groups. It explicitly labels the history as reconstructed; these timestamps do
not establish when implementation occurred. It preserves existing commits and
never pushes automatically. See `helper/README.md` after running it.
