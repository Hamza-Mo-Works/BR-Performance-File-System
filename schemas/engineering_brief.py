"""Structured explanation only. No field can approve a request or select a file."""
from typing import Literal

from pydantic import BaseModel, Field, create_model


class EvidenceStatement(BaseModel):
    statement: str = Field(description="A brief factual statement supported by supplied sources.")
    source_ids: list[str] = Field(description="One or more supplied source IDs supporting this statement.")


class EngineeringBrief(BaseModel):
    summary: str = Field(description="Brief request summary; preserve the Python status and demo limitations.")
    evidence: list[EvidenceStatement] = Field(description="Supported findings, with source IDs.")
    missing_information: list[str] = Field(description="Known gaps or uncertainties, without invented facts.")
    preparation_checks: list[str] = Field(description="Evidence-gathering checks for human review, never calibration instructions.")
    limitations: str = Field(description="Missing evidence and the boundary of this synthetic demonstration.")


def scoped_brief_schema(source_ids):
    """Limit structured-output citation choices to evidence supplied on this call."""
    allowed = tuple(sorted(set(source_ids) | {"REQUEST", "MATCHING"}))
    if any(not isinstance(identifier, str) or not identifier for identifier in allowed):
        raise ValueError("Source IDs must be non-empty strings.")
    citation_type = Literal[allowed]
    scoped_evidence = create_model(
        "ScopedEvidenceStatement", __base__=EvidenceStatement,
        source_ids=(list[citation_type], Field(description="Cite exact IDs from allowed_source_ids. Project codes are not source IDs.")))
    return create_model("ScopedEngineeringBrief", __base__=EngineeringBrief,
                        evidence=(list[scoped_evidence], Field(description="Supported findings with supplied evidence citations.")))
