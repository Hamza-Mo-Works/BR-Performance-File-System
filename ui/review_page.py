"""Final human intake review, downloadable evidence and persistent audit history."""
import sqlite3

import streamlit as st

from services.demo_file_service import sha256
from services.export_service import build_work_package, html_report, json_report
from services.llm_service import saved_brief
from services.matching_service import latest_matching_result
from services.request_service import get_request, list_requests
from services.review_service import audit_trail, latest_review, record_export, record_review


def render_review_page():
    st.title("Engineer review and export")
    st.caption("Final MVP step: record a human preparation decision and export its evidence")
    st.info("Intake acknowledgement is not tuning approval. Request information records a local "
            "decision; it does not send an email or contact a customer.")
    try:
        records = list_requests()
        if not records:
            st.info("Upload a demo request first.")
            return
        by_id = {record["id"]: record for record in records}
        request_id = st.selectbox("Request to review", list(by_id), key="review_request_id",
            format_func=lambda identifier: by_id[identifier]["request_code"] + " | "
                + by_id[identifier]["upload_filename"] + " | " + by_id[identifier]["status"])
        request = get_request(request_id)
        matching = latest_matching_result(request_id)
        brief = saved_brief(request_id)
        decision = latest_review(request_id)
        st.write("Current status: " + request["status"])
        st.write("Customer note:")
        st.text(request["customer_note"] or "No customer note provided.")
        if request["blockers"]:
            st.warning("Outstanding issues")
            for blocker in request["blockers"]:
                st.write("- " + blocker)
        if matching:
            st.write("Historical evidence: " + str(len(matching["candidates"])) + " candidates, "
                     + str(len(matching["near_matches"])) + " near matches, "
                     + str(len(matching["excluded"])) + " excluded records.")
        else:
            st.warning("Historical matching has not been run. You may request information, "
                       "but cannot acknowledge this request as ready.")
        if brief:
            with st.expander("AI brief to review", expanded=True):
                st.write(brief["brief"]["summary"])
                for item in brief["brief"]["evidence"]:
                    st.write("- " + item["statement"] + " [" + ", ".join(item["source_ids"]) + "]")
                for label, key in (("Missing information / uncertainties", "missing_information"),
                                   ("Preparation checks", "preparation_checks")):
                    if brief["brief"][key]:
                        st.write(label)
                        for item in brief["brief"][key]:
                            st.write("- " + item)
                st.caption(brief["brief"]["limitations"])
                if not brief["is_current"]:
                    st.warning("This brief is stale. Regenerate it in tab 3 before acknowledging intake.")
        else:
            st.caption("No AI draft is attached. Human review can use the deterministic evidence alone.")

        if not decision:
            candidates = {item["project_id"]: item for item in matching["candidates"]} if matching else {}
            with st.form("engineer_review_" + str(request_id)):
                reviewer = st.text_input("Demo reviewer name", max_chars=100)
                selected_reference = st.selectbox("Reference candidate to attach for engineer assessment",
                    [None] + list(candidates), format_func=lambda identifier:
                    "Select a reference" if identifier is None else candidates[identifier]["project_code"])
                comment = st.text_area("Review notes / information to request", max_chars=2000,
                    placeholder="For a held request, describe exactly what information is needed.")
                confirmed = st.checkbox("I reviewed the original identity, matching evidence and AI brief where available.")
                acknowledge = st.form_submit_button("Acknowledge intake",
                    disabled=request["status"] != "REVIEW_REQUIRED" or bool(request["blockers"])
                        or not candidates or bool(brief and not brief["is_current"]))
                request_information = st.form_submit_button("Request information")
            if acknowledge or request_information:
                record_review(request_id, reviewer,
                              "ACKNOWLEDGE_INTAKE" if acknowledge else "REQUEST_INFORMATION",
                              reference_id=selected_reference, comment=comment, evidence_confirmed=confirmed)
                st.rerun()
        else:
            st.subheader("Recorded human decision")
            st.write(decision["decision"] + " by " + decision["reviewer"])
            st.caption("UTC time: " + decision["reviewed_at"])
            st.text(decision["comment"] or "No additional review note.")
            if decision.get("selected_reference"):
                st.write("Reference attached: " + decision["selected_reference"]["project_code"])
            st.caption("Submit a revised upload for another processing/review cycle.")
            package = build_work_package(request_id)
            html_bytes, json_bytes = html_report(package), json_report(package)
            st.subheader("Download reviewed work package")
            st.caption("HTML is the readable report. JSON contains the complete structured evidence. "
                       "Both include the decision and audit history; neither includes tuning binaries.")
            left, right = st.columns(2)
            with left:
                if st.download_button("Download HTML report", data=html_bytes, mime="text/html",
                                      file_name=request["request_code"] + "-work-package.html",
                                      key="download_html_" + str(request_id)):
                    record_export(request_id, "HTML", sha256(html_bytes))
                    st.rerun()
            with right:
                if st.download_button("Download JSON package", data=json_bytes, mime="application/json",
                                      file_name=request["request_code"] + "-work-package.json",
                                      key="download_json_" + str(request_id)):
                    record_export(request_id, "JSON", sha256(json_bytes))
                    st.rerun()

        with st.expander("Audit trail", expanded=False):
            if st.button("Refresh audit trail", key="refresh_audit_" + str(request_id)):
                st.rerun()
            events = audit_trail(request_id)
            st.dataframe([{key: event[key] for key in ("time", "event", "actor")} for event in events],
                         hide_index=True, use_container_width=True)
            with st.expander("Full event details"):
                st.json(events)
            st.caption("Demo reviewer names are self-declared. SQLite history is not an authenticated or tamper-proof approval log.")
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error(str(exc))
