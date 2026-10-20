"""Export reviewed preparation evidence as JSON or an escaped HTML report."""
import html
import json
from datetime import datetime, timezone

from services.llm_service import saved_brief
from services.matching_service import latest_matching_result
from services.request_service import get_request
from services.review_service import audit_trail, latest_review


def build_work_package(request_id):
    request = get_request(request_id)
    review = latest_review(request_id)
    if not review or request["status"] not in ("INTAKE_REVIEWED", "INFORMATION_REQUESTED"):
        raise ValueError("Record the engineer's intake decision before exporting.")
    fields = ("request_code", "upload_filename", "stored_file_path", "make", "model", "model_year",
              "ecu_family", "hardware_id", "software_id", "read_method", "transmission", "fuel_spec",
              "hardware_configuration", "tune_type", "customer_note", "status", "blockers", "original_sha256")
    return dict(format_version=1, synthetic_demo=True, generated_at=datetime.now(timezone.utc).isoformat(),
                request={key: request.get(key) for key in fields},
                matching=latest_matching_result(request_id), assistant=saved_brief(request_id),
                review=review, audit=audit_trail(request_id),
                boundary="Engineering preparation evidence only. No usable tuned binary or calibration approval is included.")


def json_report(package):
    return (json.dumps(package, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def _text(value):
    if value in (None, ""):
        return "MISSING / NOT AVAILABLE"
    return html.escape(str(value), quote=True)


def _list(items):
    return "<ul>" + "".join("<li>" + _text(item) + "</li>" for item in items) + "</ul>"


def html_report(package):
    request, review = package["request"], package["review"]
    fields = ("request_code", "upload_filename", "make", "model", "model_year", "ecu_family",
              "hardware_id", "software_id", "read_method", "transmission", "fuel_spec",
              "hardware_configuration", "tune_type", "status", "original_sha256")
    rows = "".join("<tr><th>" + _text(field.replace("_", " ")) + "</th><td>"
                   + _text(request[field]) + "</td></tr>" for field in fields)
    body = "<h2>Request</h2><table>" + rows + "</table><p><b>Customer note:</b> " + _text(request["customer_note"]) + "</p>"
    if request["blockers"]:
        body += "<h3>Outstanding issues</h3>" + _list(request["blockers"])
    body += "<h2>Human intake decision</h2><p>" + _text(review["decision"]) + " by " + _text(review["reviewer"]) + "</p>"
    body += "<p>Recorded: " + _text(review["reviewed_at"]) + "</p><p>" + _text(review["comment"]) + "</p>"
    selected = review.get("selected_reference")
    if selected:
        body += "<p><b>Reference attached for assessment:</b> " + _text(selected["project_code"]) + "</p>"
    matching = package["matching"]
    if matching:
        body += "<h2>Historical matching</h2><p>Candidates: " + str(len(matching["candidates"]))
        body += " | Near matches: " + str(len(matching["near_matches"])) + " | Excluded: " + str(len(matching["excluded"])) + "</p>"
        body += "<p>Compared fields: " + _text(", ".join(matching["checked_fields"])) + "</p>"
        for label, key in (("Candidate projects", "candidates"), ("Near matches", "near_matches"), ("Excluded records", "excluded")):
            body += "<h3>" + label + "</h3>" + _list([item["project_code"] + (": " + "; ".join(item["reasons"]) if item["reasons"] else "") for item in matching[key]])
    assistant = package["assistant"]
    if assistant:
        brief = assistant["brief"]
        body += "<h2>AI draft</h2><p>Mode: " + _text(assistant["mode"]) + "</p>"
        body += "<p>Included in recorded review: " + _text(assistant.get("reviewed", False)) + "</p>"
        body += "<p>" + _text(brief["summary"]) + "</p>"
        body += _list([item["statement"] + " [" + ", ".join(item["source_ids"]) + "]" for item in brief["evidence"]])
        body += "<h3>Missing information / uncertainties</h3>" + _list(brief["missing_information"])
        body += "<h3>Preparation checks</h3>" + _list(brief["preparation_checks"])
        body += "<p>" + _text(brief["limitations"]) + "</p><h3>Retrieved technician notes</h3>"
        for source in assistant["sources"]:
            body += "<h4>" + _text(source["source_id"] + " - " + source["title"]) + "</h4><p>" + _text(source["content"]) + "</p>"
    else:
        body += "<h2>AI draft</h2><p>No AI brief was generated for this request.</p>"
    body += "<h2>Audit trail</h2><table><tr><th>UTC time</th><th>Event</th><th>Actor</th></tr>"
    body += "".join("<tr><td>" + _text(event["time"]) + "</td><td>" + _text(event["event"]) + "</td><td>" + _text(event["actor"]) + "</td></tr>" for event in package["audit"]) + "</table>"
    document = """<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Engineering intake work package</title><style>
body{font:15px system-ui;color:#17263b;max-width:960px;margin:40px auto;padding:0 24px;line-height:1.6}
h1{font-size:28px}h2{margin-top:32px;border-bottom:1px solid #d5dce5}table{border-collapse:collapse;width:100%;font-size:13px}
th,td{border:1px solid #d5dce5;text-align:left;padding:9px;overflow-wrap:anywhere}th{background:#f3f6fa}p{white-space:pre-wrap;overflow-wrap:anywhere}
.notice{background:#fff4d9;border:1px solid #e7cb88;padding:14px;border-radius:6px}@media print{body{margin:0}h2,h3{break-after:avoid}tr{break-inside:avoid}}
</style><h1>Engineering intake work package</h1>"""
    document += "<div class='notice'>" + _text(package["boundary"]) + " All data and files are synthetic.</div>"
    document += "<p>Generated: " + _text(package["generated_at"]) + "</p>" + body + "</html>"
    return document.encode("utf-8")
