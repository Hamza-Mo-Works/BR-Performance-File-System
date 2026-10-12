"""Step 4 screen. Widgets call services; they do not execute SQL or call an LLM."""
import json
import sqlite3

import streamlit as st

from config.settings import DB_PATH, SAMPLES_DIR
from config.validation import MAX_NOTE_CHARS
from services.demo_file_service import sha256
from services.ingestion_service import ingest_request, recent_requests, sample_tickets
from services.request_service import get_request


def render_ingestion_page():
    st.title("Engineering Request Copilot")
    st.caption("Step 4: upload, parse and save an incoming request")
    st.info("Independent interview demo. All files and identifiers are synthetic. "
            "This app does not tune or connect to a vehicle.")
    if not DB_PATH.exists():
        st.error("Create the database and generate the demo data before running the app.")
        st.stop()

    with st.expander("Where to find the sample files"):
        st.write("Upload a .bin file from this folder:")
        st.code(str(SAMPLES_DIR), language=None)
        st.write("Start with golf_gti_orig.bin. Customer-note examples are below.")
        tickets = sample_tickets()
        if tickets:
            selected = st.selectbox("Example customer ticket", tickets,
                                    format_func=lambda t: t["ticket_id"] + " - " + t["file_name"])
            st.code(selected["customer_note"], language=None)
            st.caption("Copy this note into the form. Selecting a ticket does not submit a request.")

    with st.form("new_request"):
        uploaded = st.file_uploader("Original demo binary file", type=["bin"],
                                    help="Use the samples generated in Step 3.")
        tune = st.selectbox("Requested service", ["Stage 1"])
        note = st.text_area("Customer note", max_chars=MAX_NOTE_CHARS,
                            placeholder="Describe the requested service, hardware changes or reported faults.")
        submitted = st.form_submit_button("Parse and save request")

    if submitted:
        if uploaded is None:
            st.warning("Choose a sample .bin file first.")
        else:
            content = uploaded.getvalue()
            fingerprint = sha256(json.dumps([sha256(content), uploaded.name, tune, note.strip()]).encode())
            saved_receipts = st.session_state.setdefault("ingestion_receipts", {})
            if fingerprint in saved_receipts:
                st.session_state["last_ingestion_result"] = saved_receipts[fingerprint]
                st.info("This same submission is already saved in this session. Showing its receipt below.")
            else:
                try:
                    result = ingest_request(uploaded.name, content, note, tune)
                    saved_receipts[fingerprint] = result
                    st.session_state["last_ingestion_result"] = result
                except (ValueError, OSError, sqlite3.Error) as exc:
                    st.error("Could not save request: " + str(exc))

    receipt = st.session_state.get("last_ingestion_result")
    if receipt:
        current_request = get_request(receipt["request_id"])
        receipt = dict(receipt, status=current_request["status"], blockers=current_request["blockers"])
        st.subheader("Last saved request")
        st.write("Request code: " + receipt["request_code"])
        st.caption("File: " + receipt["upload_filename"])
        if receipt["status"] == "BLOCKED":
            st.warning("BLOCKED - request saved, but these issues need attention:")
            for blocker in receipt["blockers"]:
                st.write("- " + blocker)
        elif receipt["status"] == "NEW":
            st.success("NEW - file parsed and request saved. Historical matching is the next step.")
        else:
            st.info(receipt["status"] + " - see the matching tab for saved evidence.")
        if receipt["metadata"]:
            st.write("Extracted identifiers and configuration")
            st.dataframe([{"Field": field.replace("_", " "), "Value": str(value) if value not in (None, "") else "MISSING"}
                          for field, value in receipt["metadata"].items()], hide_index=True,
                         use_container_width=True)
        else:
            st.write("No identifiers accepted: the file did not pass the demo-format checks.")
        with st.expander("Saved file evidence"):
            st.write("Size in bytes: " + str(receipt["bytes"]))
            st.write("SHA-256:")
            st.code(receipt["sha256"], language=None)
            st.caption("A byte fingerprint, not an ECU checksum or safety assessment.")
            st.write("Saved original: " + receipt["stored_file_path"])

    st.subheader("Recent saved requests")
    try:
        records = recent_requests()
        if records:
            st.dataframe(records, hide_index=True, use_container_width=True)
        else:
            st.caption("No uploads submitted yet. Your historical library remains separate.")
    except sqlite3.Error:
        st.error("Database tables are unavailable. Run python database.py first.")
