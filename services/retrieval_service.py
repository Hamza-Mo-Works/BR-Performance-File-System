"""Scoped semantic retrieval with LangChain embeddings cached in SQLite.

For just 30 short notes, cosine ranking in Python avoids an additional database.
Each complete note is one document; long-document chunking is not needed here.
"""
import json
import math

from config.ai_settings import API_TIMEOUT_SECONDS, MIN_SIMILARITY, RETRIEVAL_TOP_K
from config.settings import DB_PATH
from services.database_service import get_connection
from services.demo_file_service import sha256


def _embedding_client(api_key, model):
    from langchain_openai import OpenAIEmbeddings
    return OpenAIEmbeddings(model=model, api_key=api_key,
                            request_timeout=API_TIMEOUT_SECONDS, max_retries=0)


def _ensure_cache(connection):
    connection.execute("""CREATE TABLE IF NOT EXISTS note_embeddings (
        source_id TEXT NOT NULL REFERENCES technician_notes(source_id) ON DELETE CASCADE,
        model TEXT NOT NULL,
        content_sha256 TEXT NOT NULL,
        vector_json TEXT NOT NULL,
        created_at TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
        PRIMARY KEY(source_id, model)
    )""")


def _note_text(note):
    return note["title"] + "\n" + note["content"]


def _note_hash(note):
    return sha256(json.dumps(note, sort_keys=True).encode("utf-8"))


def _valid_vector(vector):
    if not isinstance(vector, list) or not vector:
        raise ValueError("Embedding response is empty or invalid.")
    if any(type(value) not in (int, float) or not math.isfinite(value) for value in vector):
        raise ValueError("Embedding response contains invalid values.")
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        raise ValueError("Embedding response has zero length.")
    return vector, norm


def sync_embeddings(api_key, model):
    connection = get_connection(DB_PATH)
    try:
        with connection:
            _ensure_cache(connection)
        notes = [dict(row) for row in connection.execute(
            "SELECT id,source_id,vehicle_id,project_id,ecu_family,hardware_id,software_id,"
            "title,content FROM technician_notes WHERE approved_for_demo=1 ORDER BY source_id")]
        cached = {row["source_id"]: row["content_sha256"] for row in connection.execute(
            "SELECT source_id,content_sha256 FROM note_embeddings WHERE model=?", (model,))}
        pending = [note for note in notes if cached.get(note["source_id"]) != _note_hash(note)]
        if not pending:
            return 0
        # API work happens outside a write transaction.
        vectors = _embedding_client(api_key, model).embed_documents([_note_text(note) for note in pending])
        if len(vectors) != len(pending):
            raise ValueError("Embedding response count differs from the document count.")
        for vector in vectors:
            _valid_vector(vector)
        with connection:
            for note, vector in zip(pending, vectors):
                connection.execute(
                    "INSERT INTO note_embeddings(source_id,model,content_sha256,vector_json) "
                    "VALUES(?,?,?,?) ON CONFLICT(source_id,model) DO UPDATE SET "
                    "content_sha256=excluded.content_sha256,vector_json=excluded.vector_json,"
                    "created_at=strftime('%Y-%m-%dT%H:%M:%fZ','now')",
                    (note["source_id"], model, _note_hash(note), json.dumps(vector)))
        return len(pending)
    finally:
        connection.close()


def retrieve_notes(request, matching_result, question, api_key, model):
    new_embeddings = sync_embeddings(api_key, model)
    project_ids = {item["project_id"] for item in matching_result["candidates"]}
    connection = get_connection(DB_PATH)
    try:
        rows = connection.execute(
            "SELECT n.id,n.source_id,n.vehicle_id,n.project_id,n.ecu_family,n.hardware_id,"
            "n.software_id,n.title,n.content,e.content_sha256,e.vector_json "
            "FROM technician_notes n JOIN note_embeddings e ON e.source_id=n.source_id "
            "WHERE n.approved_for_demo=1 AND e.model=? AND (n.ecu_family='GLOBAL' OR "
            "(n.ecu_family=? AND (n.vehicle_id IS NULL OR n.vehicle_id=?) AND "
            "(n.hardware_id IS NULL OR n.hardware_id=?) AND "
            "(n.software_id IS NULL OR n.software_id=?)))",
            (model, request["ecu_family"], request["vehicle_id"],
             request["hardware_id"], request["software_id"])).fetchall()
        notes = []
        for row in rows:
            note = dict(row)
            if note["project_id"] is not None and note["project_id"] not in project_ids:
                continue
            vector = note.pop("vector_json")
            content_hash = note.pop("content_sha256")
            if _note_hash(note) != content_hash:
                continue  # Changed note: do not use a stale vector.
            notes.append((note, vector, content_hash))
    finally:
        connection.close()
    if not notes:
        return dict(sources=[], new_embeddings=new_embeddings, eligible_notes=0)
    query = question + "\nCustomer note: " + request["customer_note"]
    query_vector, query_norm = _valid_vector(_embedding_client(api_key, model).embed_query(query))
    ranked = []
    for note, encoded_vector, content_hash in notes:
        vector, norm = _valid_vector(json.loads(encoded_vector))
        if len(vector) != len(query_vector):
            raise ValueError("Cached embeddings have a different dimension; rebuild the affected index.")
        score = sum(a * b for a, b in zip(vector, query_vector)) / (norm * query_norm)
        if score >= MIN_SIMILARITY:
            ranked.append(dict(source_id=note["source_id"], title=note["title"],
                               content=note["content"], similarity=round(score, 4),
                               content_sha256=content_hash))
    ranked.sort(key=lambda source: (-source["similarity"], source["source_id"]))
    return dict(sources=ranked[:RETRIEVAL_TOP_K], new_embeddings=new_embeddings,
                eligible_notes=len(notes))
