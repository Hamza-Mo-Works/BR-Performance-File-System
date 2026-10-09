"""Parse synthetic containers, validate intake and persist the original.

This service has no Streamlit or LLM dependency. Real ECU firmware is unsupported.
"""
import json
import re
import struct
import uuid

from config.settings import DB_PATH, PROJECT_ROOT, SAMPLES_DIR, UPLOADS_DIR
from config.validation import (MAX_HEADER_BYTES, MAX_METADATA_CHARS, MAX_NOTE_CHARS,
                               MAX_UPLOAD_BYTES, REQUIRED_METADATA, SUPPORTED_TUNES)
from services.database_service import get_connection
from services.demo_file_service import MAGIC, PAYLOAD_SIZE, sha256


class DemoParseError(ValueError):
    """A file cannot be identified as a structurally valid original demo file."""


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise DemoParseError("Duplicate fields in demo header.")
        result[key] = value
    return result


def parse_demo_binary(content, expected_kind="ORIGINAL_DEMO"):
    if not isinstance(content, bytes) or not content:
        raise DemoParseError("The uploaded file is empty or unreadable.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise DemoParseError("The demo upload exceeds the 1 MB limit.")
    if len(content) < 12 or content[:8] != MAGIC:
        raise DemoParseError("Unsupported file format: expected a BRDEMO1 synthetic container.")
    header_size = struct.unpack(">I", content[8:12])[0]
    if not 0 < header_size <= MAX_HEADER_BYTES:
        raise DemoParseError("Invalid demo header length.")
    header_end = 12 + header_size
    if header_end > len(content):
        raise DemoParseError("The demo header is incomplete.")
    try:
        header = json.loads(content[12:header_end].decode("utf-8"), object_pairs_hook=_unique_object)
    except (UnicodeDecodeError, json.JSONDecodeError, RecursionError) as exc:
        raise DemoParseError("The demo header is not valid UTF-8 JSON.") from exc
    if not isinstance(header, dict):
        raise DemoParseError("The demo header must be a JSON object.")
    if type(header.get("schema_version")) is not int or header["schema_version"] != 1:
        raise DemoParseError("Unsupported demo schema version.")
    if header.get("is_synthetic") is not True:
        raise DemoParseError("Only explicitly synthetic files are supported.")
    if header.get("file_kind") != expected_kind:
        if expected_kind == "ORIGINAL_DEMO":
            raise DemoParseError("Upload an original demo file, not a reference file.")
        raise DemoParseError("Unexpected file kind for a reference demo container.")
    if type(header.get("payload_size")) is not int or header["payload_size"] != PAYLOAD_SIZE:
        raise DemoParseError("Invalid declared demo payload size.")
    if len(content) - header_end != header["payload_size"]:
        raise DemoParseError("Incomplete or altered file length: payload does not match its header.")
    metadata = {}
    for field in REQUIRED_METADATA:
        value = header.get(field, "")
        if not isinstance(value, str) or len(value) > MAX_METADATA_CHARS:
            raise DemoParseError(f"Invalid metadata field: {field}.")
        metadata[field] = value.strip()
    year = header.get("model_year")
    if year is not None and (type(year) is not int or not 1980 <= year <= 2100):
        raise DemoParseError("Invalid model year in demo header.")
    metadata["model_year"] = year
    return metadata


def intake_blockers(metadata, customer_note, tune_type):
    blockers = ["Missing " + field.replace("_", " ") + "."
                for field in REQUIRED_METADATA if not metadata.get(field)]
    if metadata.get("model_year") is None:
        blockers.append("Missing model year.")
    if tune_type not in SUPPORTED_TUNES:
        blockers.append("Unsupported request type.")
    # Conservative demo rule, not diagnosis. The LLM will explain evidence later.
    if re.search(r"\bP0420\b", customer_note, flags=re.IGNORECASE):
        blockers.append("Customer note mentions P0420: hold for diagnostic assessment.")
    return blockers


def _vehicle_id(connection, metadata):
    rows = connection.execute(
        "SELECT id FROM vehicles WHERE make=? AND model=? AND model_year=? "
        "AND engine=? AND ecu_family=?",
        tuple(metadata.get(k) for k in ("make", "model", "model_year", "engine", "ecu_family")),
    ).fetchall()
    return rows[0]["id"] if len(rows) == 1 else None


def ingest_request(filename, content, customer_note="", tune_type="Stage 1"):
    """Save one submission and its audit event. Invalid containers become BLOCKED.

    No bytes are modified. User filenames never determine storage paths.
    Repeated explicit submissions are separate requests; the UI prevents a second
    identical save in the same session.
    """
    if not isinstance(content, bytes) or not content or len(content) > MAX_UPLOAD_BYTES:
        raise ValueError("Choose a non-empty file up to 1 MB.")
    if not isinstance(customer_note, str) or len(customer_note) > MAX_NOTE_CHARS:
        raise ValueError("Customer note must contain at most 4000 characters.")
    if not isinstance(filename, str) or not filename:
        raise ValueError("A filename is required.")
    safe_name = filename.replace("\\", "/").rsplit("/", 1)[-1][:200]
    if not safe_name.lower().endswith(".bin"):
        raise ValueError("Choose a .bin demo file.")
    if tune_type not in SUPPORTED_TUNES:
        raise ValueError("Only Stage 1 demo requests are supported.")
    metadata = {}
    parse_error = None
    try:
        metadata = parse_demo_binary(content)
        blockers = intake_blockers(metadata, customer_note, tune_type)
    except DemoParseError as exc:
        parse_error = str(exc)
        blockers = [parse_error]

    token = uuid.uuid4().hex
    request_code = "REQ-" + token[:12].upper()
    digest = sha256(content)
    stored_path = UPLOADS_DIR / (token + ".bin")
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    connection = get_connection(DB_PATH)
    file_created = False
    try:
        vehicle_id = _vehicle_id(connection, metadata) if metadata else None
        if metadata and vehicle_id is None:
            blockers.append("Vehicle identity does not resolve uniquely in the demo library.")
        status = "BLOCKED" if blockers else "NEW"
        with connection:
            with stored_path.open("xb") as output:
                file_created = True
                output.write(content)
            cursor = connection.execute(
                "INSERT INTO requests(request_code,vehicle_id,upload_filename,stored_file_path,"
                "original_sha256,hardware_id,software_id,ecu_family,read_method,transmission,"
                "fuel_spec,hardware_configuration,tune_type,customer_note,status,blockers_json) "
                "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (request_code, vehicle_id, safe_name, stored_path.relative_to(PROJECT_ROOT).as_posix(),
                 digest, metadata.get("hardware_id"), metadata.get("software_id"),
                 metadata.get("ecu_family"), metadata.get("read_method"),
                 metadata.get("transmission"), metadata.get("fuel_spec"),
                 metadata.get("hardware_configuration"), tune_type, customer_note.strip(),
                 status, json.dumps(blockers)))
            request_id = cursor.lastrowid
            connection.execute(
                "INSERT INTO audit_events(request_id,event_type,actor,details_json) VALUES(?,?,?,?)",
                (request_id, "REQUEST_INGESTED", "DEMO_USER",
                 json.dumps(dict(status=status, sha256=digest, bytes=len(content),
                                 parse_error=parse_error, blockers=blockers))))
        return dict(request_id=request_id, request_code=request_code, metadata=metadata,
                    status=status, blockers=blockers, sha256=digest, bytes=len(content),
                    stored_file_path=stored_path.relative_to(PROJECT_ROOT).as_posix(),
                    upload_filename=safe_name)
    except Exception:
        if file_created:
            stored_path.unlink(missing_ok=True)
        raise
    finally:
        connection.close()


def recent_requests(limit=10):
    connection = get_connection(DB_PATH)
    try:
        rows = connection.execute(
            "SELECT request_code,upload_filename,tune_type,status,created_at "
            "FROM requests ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()


def sample_tickets():
    manifest = SAMPLES_DIR / "sample_tickets.json"
    if not manifest.exists():
        return []
    return json.loads(manifest.read_text(encoding="utf-8"))["tickets"]
