"""Deterministic matching of synthetic references; no LLM and no binary editing."""
import json
from pathlib import Path

from config.settings import DB_PATH, PROJECT_ROOT, REFERENCES_DIR, UPLOADS_DIR
from config.matching_rules import IDENTITY_FIELDS, CONFIGURATION_FIELDS
from config.validation import MAX_UPLOAD_BYTES, REQUIRED_METADATA
from services.database_service import get_connection
from services.demo_file_service import sha256
from services.ingestion_service import intake_blockers, parse_demo_binary
from services.request_service import fetch_request

def _read_file(relative_path, allowed_directory):
    if not relative_path:
        raise ValueError("No file path recorded.")
    path = (PROJECT_ROOT / Path(relative_path)).resolve()
    try:
        path.relative_to(allowed_directory.resolve())
    except ValueError as exc:
        raise ValueError("File path is outside its expected demo folder.") from exc
    if not path.is_file():
        raise ValueError("Recorded file is missing.")
    if path.stat().st_size > MAX_UPLOAD_BYTES:
        raise ValueError("Recorded file exceeds the demo size limit.")
    with path.open("rb") as original:
        content = original.read(MAX_UPLOAD_BYTES + 1)
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Recorded file exceeds the demo size limit.")
    return content


def _verify_original(request):
    """Recheck the stored original before trusting the persisted metadata."""
    try:
        content = _read_file(request["stored_file_path"], UPLOADS_DIR)
        if sha256(content) != request["original_sha256"]:
            return None, ["Stored original fingerprint changed; investigate before matching."]
        metadata = parse_demo_binary(content)
    except (ValueError, OSError) as exc:
        return None, [str(exc)]
    blockers = intake_blockers(metadata, request["customer_note"], request["tune_type"])
    if request["vehicle_id"] is None:
        blockers.append("Vehicle identity does not resolve uniquely in the demo library.")
    elif any(metadata.get(key) != request.get(key) for key in REQUIRED_METADATA + ("model_year",)):
        blockers.append("Stored request metadata differs from the original file header.")
    return metadata, blockers


def _reference_evidence(project):
    try:
        content = _read_file(project["reference_file_path"], REFERENCES_DIR)
        metadata = parse_demo_binary(content, expected_kind="REFERENCE_DEMO")
        expected_fields = REQUIRED_METADATA + ("model_year",)
        if any(metadata.get(field) != project.get(field) for field in expected_fields):
            return None, "Reference header differs from its historical record."
        return sha256(content), None
    except (ValueError, OSError) as exc:
        return None, str(exc)


def _classify_projects(connection, request):
    rows = connection.execute(
        "SELECT h.*,v.make,v.model,v.model_year,v.engine,v.ecu_family "
        "FROM historical_projects h JOIN vehicles v ON v.id=h.vehicle_id "
        "WHERE h.vehicle_id=? ORDER BY h.project_code", (request["vehicle_id"],)).fetchall()
    candidates, near_matches, excluded = [], [], []
    for row in rows:
        project = dict(row)
        differences = [field.replace("_", " ") + " differs"
                       for field in IDENTITY_FIELDS + CONFIGURATION_FIELDS
                       if project[field] != request[field]]
        digest_match = bool(project["original_sha256"]) and project["original_sha256"] == request["original_sha256"]
        entry = dict(project_id=project["id"], project_code=project["project_code"],
                     hardware_id=project["hardware_id"], software_id=project["software_id"],
                     transmission=project["transmission"], fuel_spec=project["fuel_spec"],
                     hardware_configuration=project["hardware_configuration"],
                     review_status=project["review_status"], original_digest_match=digest_match,
                     reference_file_path=project["reference_file_path"], outcome_notes=project["outcome_notes"])
        if project["review_status"] != "REFERENCE_CANDIDATE":
            entry["reasons"] = ["Historical status: " + project["review_status"]] + differences
            excluded.append(entry)
        elif differences:
            entry["reasons"] = differences
            near_matches.append(entry)
        elif not digest_match:
            entry["reasons"] = ["Historical original fingerprint differs or is missing."]
            near_matches.append(entry)
        else:
            reference_digest, error = _reference_evidence(project)
            if error:
                entry["reasons"] = ["Reference unavailable or invalid: " + error]
                excluded.append(entry)
            else:
                entry["reference_sha256"] = reference_digest
                entry["reasons"] = []
                candidates.append(entry)
    return candidates, near_matches, excluded


def run_matching(request_id):
    """Persist matching evidence and status. It never picks or releases a binary."""
    connection = get_connection(DB_PATH)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            request = fetch_request(connection, request_id)
            if request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
                raise ValueError("This request already has a review decision. Submit a revised request to rerun processing.")
            metadata, blockers = _verify_original(request)
            verified = bool(metadata and request["vehicle_id"] is not None
                            and all(metadata.get(field) for field in REQUIRED_METADATA)
                            and metadata.get("model_year") is not None
                            and "Stored request metadata differs from the original file header." not in blockers)
            if verified:
                candidates, near_matches, excluded = _classify_projects(connection, request)
                if not candidates:
                    blockers.append("No eligible exact reference found; specialist assessment is required.")
            else:
                candidates, near_matches, excluded = [], [], []
            status = "BLOCKED" if blockers else "REVIEW_REQUIRED"
            result = dict(request_id=request_id, request_code=request["request_code"],
                          status=status, blockers=list(dict.fromkeys(blockers)),
                          matching_performed=verified, candidates=candidates,
                          near_matches=near_matches, excluded=excluded,
                          original_sha256=request["original_sha256"],
                          checked_fields=list(IDENTITY_FIELDS + CONFIGURATION_FIELDS) + ["original_sha256"],
                          warning="Reference candidates are context for engineer review, not tuning approval. "
                          "Reference fingerprints are recorded observations, not verified ECU checksums.")
            connection.execute(
                "UPDATE requests SET status=?,blockers_json=?,selected_reference_id=NULL WHERE id=?",
                (status, json.dumps(result["blockers"]), request_id))
            connection.execute(
                "INSERT INTO audit_events(request_id,event_type,actor,details_json) VALUES(?,?,?,?)",
                (request_id, "HISTORICAL_MATCHING", "PYTHON_MATCHER", json.dumps(result)))
        return result
    finally:
        connection.close()


def latest_matching_result(request_id):
    connection = get_connection(DB_PATH)
    try:
        row = connection.execute(
            "SELECT details_json FROM audit_events WHERE request_id=? "
            "AND event_type='HISTORICAL_MATCHING' ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
        return json.loads(row["details_json"]) if row else None
    finally:
        connection.close()
