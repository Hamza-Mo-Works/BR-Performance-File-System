"""Build a grounded LangChain brief. Never change status, blockers or binary files."""
import json

from config.ai_settings import API_TIMEOUT_SECONDS, CHAT_MAX_TOKENS, MAX_QUESTION_CHARS
from config.prompts import SYSTEM_PROMPT, USER_PROMPT
from config.settings import DB_PATH
from services.database_service import get_connection
from services.demo_file_service import sha256
from services.matching_service import latest_matching_result
from services.request_service import fetch_request, get_request
from services.retrieval_service import retrieve_notes


class BriefGenerationError(ValueError):
    """Only safe, predefined messages may be supplied here; never provider text."""
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def _parsed_response(response):
    if not isinstance(response, dict):
        raise BriefGenerationError("RESPONSE_FORMAT", "The model response could not be read as a structured brief.")
    raw = response.get("raw")
    metadata = getattr(raw, "response_metadata", {}) or {}
    extra = getattr(raw, "additional_kwargs", {}) or {}
    if metadata.get("finish_reason") == "length":
        raise BriefGenerationError("OUTPUT_LIMIT", "The model response was cut short. Ask for a shorter brief and retry.")
    if extra.get("refusal") or metadata.get("finish_reason") == "content_filter":
        raise BriefGenerationError("MODEL_REFUSAL", "The model declined this question. Ask for an intake explanation using supplied evidence.")
    if response.get("parsing_error") is not None or response.get("parsed") is None:
        raise BriefGenerationError("STRUCTURED_OUTPUT", "The model did not return a complete valid brief. Ask a shorter question and retry.")
    parsed = response["parsed"]
    if not hasattr(parsed, "model_dump"):
        raise BriefGenerationError("SCHEMA_RESULT", "The response format is incompatible with the installed AI packages.")
    return parsed.model_dump()


def _request_context(request):
    keys = ("request_code", "upload_filename", "make", "model", "model_year", "ecu_family",
            "hardware_id", "software_id", "read_method", "transmission", "fuel_spec",
            "hardware_configuration", "tune_type", "customer_note", "status", "blockers",
            "original_sha256")
    return {key: request.get(key) for key in keys}


def _matching_context(result):
    return dict(status=result["status"], matching_performed=result["matching_performed"],
                counts=dict(candidates=len(result["candidates"]), near_matches=len(result["near_matches"]),
                            excluded=len(result["excluded"])),
                checked_fields=result.get("checked_fields", []),
                eligibility_rules=dict(
                    vehicle_scope="Same catalog vehicle: make, model, year, engine and ECU family.",
                    comparison="Exact equality of the listed identity/configuration fields and historical original SHA-256.",
                    historical_status="REFERENCE_CANDIDATE",
                    original_check="Stored original is re-read and its fingerprint/header are verified before matching.",
                    reference_check="Reference file exists, has the expected synthetic format and complete payload, and its header matches the historical record.",
                    safety_boundary="These checks do not verify actual ECU compatibility or safe calibration."),
                candidate_codes=[item["project_code"] for item in result["candidates"]],
                near_matches=[dict(project=item["project_code"], reasons=item["reasons"])
                              for item in result["near_matches"]],
                excluded=[dict(project=item["project_code"], reasons=item["reasons"])
                          for item in result["excluded"]], warning=result["warning"])


def _snapshot(request, result):
    return sha256(json.dumps(dict(request=_request_context(request), matching=result,
                                 prompt_version=sha256((SYSTEM_PROMPT + USER_PROMPT).encode())),
                             sort_keys=True).encode("utf-8"))


def _invoke_model(request, matching_result, sources, question, api_key, model, citation_retry=False):
    from langchain_core.documents import Document
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_openai import ChatOpenAI
    from schemas.engineering_brief import scoped_brief_schema
    allowed_ids = sorted({source["source_id"] for source in sources} | {"REQUEST", "MATCHING"})
    output_schema = scoped_brief_schema(allowed_ids)
    documents = [Document(page_content=source["content"],
                          metadata={"source_id": source["source_id"], "title": source["title"]})
                 for source in sources]
    system_prompt = SYSTEM_PROMPT
    if citation_retry:
        system_prompt += "\nThe previous draft failed citation validation. Generate a fresh concise brief. Every evidence statement must cite at least one ID from allowed_source_ids. Omit unsupported evidence statements."
    prompt = ChatPromptTemplate.from_messages([("system", system_prompt), ("human", USER_PROMPT)])
    model_client = ChatOpenAI(model=model, api_key=api_key, temperature=0,
                             max_tokens=CHAT_MAX_TOKENS, timeout=API_TIMEOUT_SECONDS,
                             max_retries=0, use_responses_api=False)
    structured_model = model_client.with_structured_output(
        output_schema, method="json_schema", strict=True, include_raw=True)
    chain = prompt | structured_model
    response = chain.invoke(dict(question=question, allowed_source_ids_json=json.dumps(allowed_ids),
        request_json=json.dumps(_request_context(request)),
        matching_json=json.dumps(_matching_context(matching_result)),
        notes_json=json.dumps([dict(source_id=doc.metadata["source_id"],
                                    title=doc.metadata["title"], content=doc.page_content)
                               for doc in documents])))
    return _parsed_response(response)


def _validate_citations(brief, sources):
    allowed = {source["source_id"] for source in sources} | {"REQUEST", "MATCHING"}
    canonical = {}
    for identifier in allowed:
        folded = identifier.casefold()
        canonical[folded] = identifier if folded not in canonical else None
    for statement in brief["evidence"]:
        normalized = []
        for identifier in statement["source_ids"]:
            cleaned = identifier.strip()
            if cleaned.startswith("[") and cleaned.endswith("]"):
                cleaned = cleaned[1:-1].strip()
            # Normalize formatting only; never guess or substitute a different source.
            recognized = cleaned if cleaned in allowed else canonical.get(cleaned.casefold())
            if recognized is None:
                raise BriefGenerationError("CITATION_CHECK", "The draft cited a source that was not supplied. It was not saved. Regenerate the brief.")
            normalized.append(recognized)
        if not normalized:
            raise BriefGenerationError("CITATION_CHECK", "An evidence statement has no source reference. It was not saved. Regenerate the brief.")
        statement["source_ids"] = list(dict.fromkeys(normalized))


def _friendly_error(exception):
    if isinstance(exception, BriefGenerationError):
        return "[" + exception.code + "] " + str(exception)
    if isinstance(exception, ImportError):
        return "Install AI dependencies: python -m pip install -r requirements-ai.txt"
    error_type = type(exception).__name__
    if "Timeout" in error_type:
        return "[TIMEOUT] OpenAI did not respond before the time limit. Check your connection and retry."
    if error_type in ("APIConnectionError", "ConnectError", "NetworkError"):
        return "[CONNECTION] Could not reach OpenAI. Check network, proxy or VPN connectivity."
    if error_type == "LengthFinishReasonError":
        return "[OUTPUT_LIMIT] The model response was cut short. Ask for a shorter brief and retry."
    if error_type == "OpenAIRefusalError":
        return "[MODEL_REFUSAL] The model declined this question. Ask for an intake explanation using supplied evidence."
    if error_type in ("OutputParserException", "ValidationError"):
        return "[STRUCTURED_OUTPUT] The response did not match the expected brief format. Retry with a shorter question."
    code = getattr(exception, "status_code", None)
    if code == 401:
        return "OpenAI rejected the API key. Check the key in Streamlit secrets."
    if code == 429:
        return "OpenAI returned a quota or rate-limit error. Check API credits/limits or retry later."
    if code == 404:
        return "The configured model is unavailable to this API project. Check your model settings."
    if code == 403:
        return "This API project does not have permission for the requested operation."
    if code == 400:
        return "[API_400] OpenAI rejected the model settings or response schema. Check model/package compatibility."
    if isinstance(code, int) and code >= 500:
        return "[OPENAI_SERVER] OpenAI returned a server error. Retry later."
    return "[AI_ERROR] Generation failed. Copy the AI_DIAGNOSTIC line from the terminal for troubleshooting."


def generate_brief(request_id, question, api_key, chat_model, embedding_model):
    if not isinstance(question, str) or not question.strip() or len(question) > MAX_QUESTION_CHARS:
        raise ValueError("Enter a question of 1 to 2000 characters.")
    request = get_request(request_id)
    if request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
        raise ValueError("A review decision is already recorded. Submit a revised request to generate a new brief.")
    matching_result = latest_matching_result(request_id)
    if not matching_result:
        raise ValueError("Run historical matching for this request in tab 2 first.")
    snapshot = _snapshot(request, matching_result)
    stage = "note_retrieval"
    try:
        retrieval = retrieve_notes(request, matching_result, question, api_key, embedding_model)
        sources = retrieval["sources"]
        if sources:
            for attempt in range(2):
                stage = "model_generation"
                brief = _invoke_model(request, matching_result, sources, question, api_key, chat_model,
                                      citation_retry=bool(attempt))
                stage = "citation_validation"
                try:
                    _validate_citations(brief, sources)
                    break
                except BriefGenerationError as exc:
                    if exc.code != "CITATION_CHECK" or attempt == 1:
                        raise
            mode = "LIVE_LLM_DRAFT"
        else:
            brief = dict(summary="No relevant approved demo notes met the retrieval threshold.",
                         evidence=[], missing_information=["Supporting technician evidence for this question."],
                         preparation_checks=["Ask the engineer for relevant documentation."],
                         limitations="No chat-model response was generated. Request status is unchanged.")
            mode = "NO_EVIDENCE"
    except Exception as exc:
        # Do not echo raw provider exceptions, headers, credentials or request bodies.
        diagnostic = dict(stage=stage, error_type=type(exc).__name__,
                          code=exc.code if isinstance(exc, BriefGenerationError) else None,
                          http_status=getattr(exc, "status_code", None))
        print("AI_DIAGNOSTIC " + json.dumps(diagnostic), flush=True)
        raise RuntimeError(_friendly_error(exc) + " Stage: " + stage + ".") from None
    result = dict(request_id=request_id, request_code=request["request_code"],
                  request_status=request["status"], mode=mode, question=question,
                  brief=brief, sources=sources, embedding_model=embedding_model,
                  chat_model=chat_model, new_embeddings=retrieval["new_embeddings"],
                  generation_attempts=attempt + 1 if sources else 0,
                  eligible_notes=retrieval["eligible_notes"], snapshot=snapshot,
                  warning="Human review required. Citation IDs were checked; factual support was not automatically verified.")
    connection = get_connection(DB_PATH)
    try:
        with connection:
            connection.execute("BEGIN IMMEDIATE")
            current_request = fetch_request(connection, request_id)
            current_matching = latest_matching_result(request_id)
            if _snapshot(current_request, current_matching) != snapshot:
                raise ValueError("Request or matching evidence changed. Generate a new brief.")
            connection.execute("UPDATE requests SET llm_summary=?,source_ids_json=? WHERE id=?",
                               (json.dumps(result), json.dumps([source["source_id"] for source in sources]), request_id))
            connection.execute(
                "INSERT INTO audit_events(request_id,event_type,actor,details_json) VALUES(?,?,?,?)",
                (request_id, "ASSISTANT_BRIEF", "LANGCHAIN_RAG", json.dumps(result)))
        return result
    finally:
        connection.close()


def saved_brief(request_id):
    request = get_request(request_id)
    if not request["llm_summary"]:
        return None
    result = json.loads(request["llm_summary"])
    matching_result = latest_matching_result(request_id)
    result["is_current"] = bool(matching_result and result.get("snapshot") == _snapshot(request, matching_result))
    result["reviewed"] = False
    if matching_result and request["status"] in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
        connection = get_connection(DB_PATH)
        try:
            row = connection.execute(
                "SELECT details_json FROM audit_events WHERE request_id=? "
                "AND event_type='ENGINEER_REVIEW' ORDER BY id DESC LIMIT 1", (request_id,)).fetchone()
            if row:
                review = json.loads(row["details_json"])
                if (review.get("reviewed_brief_snapshot") == result.get("snapshot")
                    and review.get("post_review_snapshot") == _snapshot(request, matching_result)):
                    result["is_current"] = True
                    result["reviewed"] = True
        finally:
            connection.close()
    return result
