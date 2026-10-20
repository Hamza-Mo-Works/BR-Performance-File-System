"""Human intake decisions and audit history; no customer delivery or tuning approval."""
import json
from datetime import datetime, timezone

from config.settings import DB_PATH
from services.database_service import get_connection
from services.llm_service import _snapshot
from services.matching_service import _classify_projects, _verify_original
from services.request_service import fetch_request


def _latest_matching(connection, request_id):
    row = connection.execute(
        "SELECT details_json FROM audit_events WHERE request_id=? "
        "AND event_type='HISTORICAL_MATCHING' ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
    return json.loads(row["details_json"]) if row else None


def record_review(request_id, reviewer_name, decision, reference_id=None,
                  comment="", evidence_confirmed=False):
    if not isinstance(reviewer_name, str) or not 1 <= len(reviewer_name.strip()) <= 100:
        raise ValueError("Enter a reviewer name of 1 to 100 characters.")
    if not isinstance(comment, str) or len(comment) > 2000:
        raise ValueError("Review notes must contain at most 2000 characters.")
    if decision not in ("ACKNOWLEDGE_INTAKE", "REQUEST_INFORMATION"):
        raise ValueError("Unsupported review decision.")
    connection = get_connection(DB_PATH)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            request = fetch_request(connection, request_id)
            if request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
                raise ValueError("This request already has a recorded review decision.")
            matching = _latest_matching(connection, request_id)
            brief = json.loads(request["llm_summary"]) if request["llm_summary"] else None
            brief_current = bool(brief and matching and brief.get("snapshot") == _snapshot(request, matching))
            selected = None
            if decision == "ACKNOWLEDGE_INTAKE":
                if request["status"] != "REVIEW_REQUIRED" or request["blockers"] or not matching:
                    raise ValueError("A blocked or unmatched request cannot be acknowledged as ready for intake review.")
                if evidence_confirmed is not True:
                    raise ValueError("Confirm that you reviewed the displayed evidence.")
                if brief and not brief_current:
                    raise ValueError("The saved AI brief is stale. Regenerate it before acknowledging the intake.")
                _, current_blockers = _verify_original(request)
                if current_blockers:
                    raise ValueError("Original-file evidence changed or is incomplete. Rerun matching first.")
                candidates, near, excluded = _classify_projects(connection, request)
                if (candidates != matching["candidates"] or near != matching["near_matches"]
                    or excluded != matching["excluded"]):
                    raise ValueError("Reference evidence changed. Rerun matching and review the updated brief.")
                selected = next((item for item in candidates if item["project_id"] == reference_id), None)
                if selected is None:
                    raise ValueError("Select an eligible reference candidate for engineer assessment.")
                status = "INTAKE_REVIEWED"
            else:
                if not comment.strip():
                    raise ValueError("Describe the information you want to request.")
                status = "INFORMATION_REQUESTED"
                reference_id = None
            reviewed_at = datetime.now(timezone.utc).isoformat()
            connection.execute(
                "UPDATE requests SET status=?,selected_reference_id=?,reviewer_name=?,reviewed_at=? WHERE id=?",
                (status, reference_id, reviewer_name.strip(), reviewed_at, request_id))
            updated = fetch_request(connection, request_id)
            result = dict(request_id=request_id, request_code=request["request_code"], decision=decision,
                          previous_status=request["status"], status=status, reviewer=reviewer_name.strip(),
                          reviewed_at=reviewed_at, comment=comment.strip(), selected_reference=selected,
                          reviewed_brief_snapshot=brief["snapshot"] if brief_current else None,
                          post_review_snapshot=_snapshot(updated, matching) if matching else None,
                          boundary="Intake review only. No tuning approval, binary modification, vehicle flashing or customer delivery.")
            connection.execute(
                "INSERT INTO audit_events(request_id,event_type,actor,details_json) VALUES(?,?,?,?)",
                (request_id, "ENGINEER_REVIEW", reviewer_name.strip(), json.dumps(result)))
        return result
    finally:
        connection.close()


def audit_trail(request_id):
    connection = get_connection(DB_PATH)
    try:
        return [dict(id=row["id"], time=row["created_at"], event=row["event_type"], actor=row["actor"],
                     details=json.loads(row["details_json"]))
                for row in connection.execute(
                    "SELECT * FROM audit_events WHERE request_id=? ORDER BY id", (request_id,))]
    finally:
        connection.close()


def latest_review(request_id):
    reviews = [event for event in audit_trail(request_id) if event["event"] == "ENGINEER_REVIEW"]
    return reviews[-1]["details"] if reviews else None


def record_export(request_id, format_name, artifact_sha256):
    if format_name not in ("JSON", "HTML"):
        raise ValueError("Unsupported export format.")
    connection = get_connection(DB_PATH)
    try:
        with connection:
            request = fetch_request(connection, request_id)
            if request["status"] not in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
                raise ValueError("Record a review decision before exporting a reviewed work package.")
            connection.execute(
                "INSERT INTO audit_events(request_id,event_type,actor,details_json) VALUES(?,?,?,?)",
                (request_id, "EXPORT_REQUESTED", "LOCAL_DEMO_USER",
                 json.dumps(dict(format=format_name, artifact_sha256=artifact_sha256))))
    finally:
        connection.close()
