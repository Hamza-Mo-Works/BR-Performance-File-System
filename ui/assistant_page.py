"""Credential boundary and assistant UI. Never display or persist the API key."""
import importlib.util
import sqlite3

import streamlit as st

from config.ai_settings import CHAT_MODEL, EMBEDDING_MODEL, MAX_QUESTION_CHARS
from services.llm_service import generate_brief, saved_brief
from services.matching_service import latest_matching_result
from services.request_service import get_request, list_requests


def _credentials():
    try:
        settings = st.secrets["openai"]
        key = settings["api_key"]
        if not isinstance(key, str) or not key.strip() or "PASTE" in key:
            return None
        return dict(api_key=key.strip(), chat_model=settings.get("chat_model", CHAT_MODEL),
                    embedding_model=settings.get("embedding_model", EMBEDDING_MODEL))
    except Exception:
        return None


def render_assistant_page():
    st.title("Engineering assistant")
    st.caption("Step 6: scoped technician-note retrieval and an OpenAI explanation")
    st.info("The model explains saved evidence. Python keeps control of the status. "
            "No binary bytes are sent to OpenAI.")
    credentials = _credentials()
    dependencies_ready = importlib.util.find_spec("langchain_openai") is not None
    if not dependencies_ready:
        st.warning("Install the AI packages and restart Streamlit:")
        st.code("python -m pip install -r requirements-ai.txt", language=None)
    if not credentials:
        st.warning("Configure .streamlit/secrets.toml using the supplied example, then restart Streamlit. "
                   "Keep your key private; do not enter it in a customer note.")
    else:
        st.caption("OpenAI key configured. Chat model: " + credentials["chat_model"]
                   + " | Embeddings: " + credentials["embedding_model"])
    try:
        records = list_requests()
        if not records:
            st.info("Upload a request and run historical matching first.")
            return
        by_id = {record["id"]: record for record in records}
        request_id = st.selectbox("Request to explain", list(by_id), key="assistant_request_id",
            format_func=lambda identifier: by_id[identifier]["request_code"] + " | "
                + by_id[identifier]["upload_filename"] + " | " + by_id[identifier]["status"])
        request = get_request(request_id)
        matching = latest_matching_result(request_id)
        st.write("Python status: " + request["status"])
        for blocker in request["blockers"]:
            st.write("- " + blocker)
        if not matching:
            st.warning("Run historical matching for this request in tab 2 before generating a brief.")
        question = st.text_area("What should the assistant explain?", key="assistant_question",
            value="Summarize this request, explain its current status and list the preparation checks an engineer should review.",
            max_chars=MAX_QUESTION_CHARS)
        st.caption("The first run indexes the 30 fictional notes. Later runs reuse unchanged note embeddings. "
                   "Explicit generation uses your OpenAI API account.")
        if st.button("Generate engineering brief", key="generate_brief",
                     disabled=not (credentials and dependencies_ready and matching)
                         or request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED")):
            with st.spinner("Retrieving technician evidence and generating a draft..."):
                generate_brief(request_id, question, **credentials)
        result = saved_brief(request_id)
        if not result:
            return
        st.subheader("Saved engineering brief")
        st.caption("Mode: " + result["mode"] + " | Python status when generated: " + result["request_status"])
        if result.get("reviewed"):
            st.success("This version of the brief was included in the recorded intake review.")
        if not result["is_current"]:
            st.warning("The request or matching evidence has changed since this draft. Generate a new brief.")
        brief = result["brief"]
        st.write(brief["summary"])
        if brief["evidence"]:
            st.write("Evidence")
            for item in brief["evidence"]:
                st.write("- " + item["statement"] + " [" + ", ".join(item["source_ids"]) + "]")
        if brief["missing_information"]:
            st.write("Missing information / uncertainties")
            for item in brief["missing_information"]:
                st.write("- " + item)
        if brief["preparation_checks"]:
            st.write("Preparation checks for human review")
            for item in brief["preparation_checks"]:
                st.write("- " + item)
        st.caption(brief["limitations"])
        st.caption(result["warning"])
        with st.expander("Retrieved technician notes and evidence sources"):
            st.write("REQUEST = saved request data. MATCHING = saved Python matching result.")
            st.write("Eligible scoped notes: " + str(result["eligible_notes"]))
            st.write("New note embeddings created on this run: " + str(result["new_embeddings"]))
            for source in result["sources"]:
                st.write(source["source_id"] + " - " + source["title"])
                st.text(source["content"])
                st.caption("Cosine similarity: " + str(source["similarity"]) + " (not an accuracy score)")
    except (RuntimeError, ValueError, OSError, sqlite3.Error) as exc:
        st.error(str(exc))
