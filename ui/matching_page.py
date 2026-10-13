"""Historical matching and persistent request details, independent of an LLM."""
import sqlite3

import streamlit as st

from services.matching_service import latest_matching_result, run_matching
from services.request_service import get_request, list_requests


def _reference_table(records, include_reasons=False):
    rows = []
    for record in records:
        row = {"Project": record["project_code"], "Software": record["software_id"],
               "Transmission": record["transmission"], "Fuel": record["fuel_spec"],
               "Hardware configuration": record["hardware_configuration"],
               "Historical status": record["review_status"],
               "Same original bytes": record["original_digest_match"]}
        if include_reasons:
            row["Reason"] = "; ".join(record["reasons"])
        rows.append(row)
    st.dataframe(rows, hide_index=True, use_container_width=True)


def render_matching_page():
    st.title("Historical matching")
    st.caption("Step 5: compare a saved request with the fictional reference library")
    try:
        records = list_requests()
        if not records:
            st.info("Upload a sample in the first tab before running matching.")
            return
        by_id = {record["id"]: record for record in records}
        selected_id = st.selectbox(
            "Saved request", list(by_id), key="matching_request_id",
            format_func=lambda identifier: by_id[identifier]["request_code"] + " | "
                + by_id[identifier]["upload_filename"] + " | " + by_id[identifier]["status"])
        request = get_request(selected_id)
        if st.button("Run historical matching", key="run_matching",
                     disabled=request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED")):
            run_matching(selected_id)
            st.rerun()
        result = latest_matching_result(selected_id)

        st.subheader("Saved request details")
        st.write("Status: " + request["status"])
        st.write("Customer note:")
        st.text(request["customer_note"] or "No customer note provided.")
        if request["blockers"]:
            st.warning("Preparation is on hold for these reasons:")
            for reason in request["blockers"]:
                st.write("- " + reason)
        fields = ("make", "model", "model_year", "ecu_family", "hardware_id", "software_id",
                  "read_method", "transmission", "fuel_spec", "hardware_configuration")
        st.dataframe([{"Field": field.replace("_", " "),
                       "Value": str(request[field]) if request.get(field) not in (None, "") else "MISSING / NOT EXTRACTED"}
                      for field in fields], hide_index=True, use_container_width=True)
        if not result:
            st.info("Click Run historical matching to search the library. Missing reasons above are already stored in the database.")
            return

        st.subheader("Latest saved matching result")
        if not result["matching_performed"]:
            st.warning("Matching was skipped because the original or its identification evidence is incomplete or invalid.")
        left, middle, right = st.columns(3)
        left.metric("Reference candidates", len(result["candidates"]))
        middle.metric("Near matches", len(result["near_matches"]))
        right.metric("Excluded records", len(result["excluded"]))
        if result["status"] == "BLOCKED":
            st.warning("Reference information does not clear a blocked request. Engineer assessment is still required.")
        elif request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
            st.info("This matching evidence was recorded before the human intake decision shown above.")
        else:
            st.success("Matching complete: engineer review is required. No file has been selected or modified.")

        if result["candidates"]:
            st.write("Reference candidates - exact metadata/configuration and original fingerprint matches")
            _reference_table(result["candidates"])
        if result["near_matches"]:
            st.write("Near matches - inspect the differences; do not substitute automatically")
            _reference_table(result["near_matches"], include_reasons=True)
        if result["excluded"]:
            st.write("Excluded historical records")
            _reference_table(result["excluded"], include_reasons=True)
        st.caption(result["warning"])
        with st.expander("Full matching evidence"):
            st.json(result)
    except (ValueError, OSError, sqlite3.Error) as exc:
        st.error("Could not process matching: " + str(exc))
