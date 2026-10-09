"""Read persisted requests for the UI, matching and later review services."""
import json

from config.settings import DB_PATH
from services.database_service import get_connection


def fetch_request(connection, request_id):
    row = connection.execute(
        "SELECT r.*,v.make,v.model,v.model_year,v.engine,"
        "v.ecu_family AS vehicle_ecu_family FROM requests r "
        "LEFT JOIN vehicles v ON v.id=r.vehicle_id WHERE r.id=?", (request_id,)).fetchone()
    if row is None:
        raise ValueError("Request not found.")
    result = dict(row)
    result["blockers"] = json.loads(result["blockers_json"])
    return result


def get_request(request_id):
    connection = get_connection(DB_PATH)
    try:
        return fetch_request(connection, request_id)
    finally:
        connection.close()


def list_requests(limit=100):
    connection = get_connection(DB_PATH)
    try:
        rows = connection.execute(
            "SELECT id,request_code,upload_filename,status FROM requests ORDER BY id DESC LIMIT ?",
            (limit,)).fetchall()
        return [dict(row) for row in rows]
    finally:
        connection.close()
