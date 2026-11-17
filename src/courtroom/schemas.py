"""Strict Pydantic and JSON Schema contracts for all Agent Courtroom artifacts."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class SchemaValidationError(ValueError):
    """Raised when an artifact or LLM response fails strict schema validation."""


class EvidenceItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., pattern=r"^E\d+$")
    source: str = Field(..., min_length=1)
    finding: str = Field(..., min_length=1)
    quote: str | None = None
    ast_ref: str | None = None
    command: str | None = None
    exit_code: int | None = None
    output_sha256: str | None = None


class PlanItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    change: str = Field(..., min_length=1)
    rationale: str = Field(..., min_length=1)
    evidence_ids: list[str] = Field(..., min_length=1)
    risks: list[str] = Field(default_factory=list)
    verification: str = Field(..., min_length=1)


class BlastRadius(BaseModel):
    model_config = ConfigDict(extra="allow")

    allowed_files: list[str] = Field(default_factory=list)
    forbidden_files: list[str] = Field(default_factory=list)
    expected_deltas: dict[str, Any] = Field(default_factory=dict)


class PlanArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    plan_id: str = Field(..., pattern=r"^PLAN-\d+.*$")
    mode: Literal["pipeline", "software", "architecture"] = "pipeline"
    goal: str = Field(..., min_length=1)
    blast_radius: BlastRadius | None = None
    items: list[PlanItem] = Field(..., min_length=1)
    evidence: list[EvidenceItem] = Field(..., min_length=1)

    @model_validator(mode="after")
    def _check_evidence_refs(self) -> "PlanArtifact":
        known_ids = {ev.id for ev in self.evidence}
        for item in self.items:
            missing = [eid for eid in item.evidence_ids if eid not in known_ids]
            if missing:
                raise ValueError(
                    f"Plan item '{item.id}' references unknown evidence_ids: {missing}"
                )
        return self


class ChallengeObjection(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    role: Literal["prosecutor", "public_defender"]
    severity: Literal["blocking", "major", "minor"]
    attack: str = Field(..., min_length=1)
    required_evidence: str = Field(..., min_length=1)


class ChallengeArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    plan_id: str = Field(..., min_length=1)
    objections: list[ChallengeObjection] = Field(default_factory=list)


class RebuttalResponse(BaseModel):
    model_config = ConfigDict(extra="allow")

    objection_id: str = Field(..., min_length=1)
    item_id: str = Field(..., min_length=1)
    stance: Literal["concede", "defend"]
    argument: str = Field(..., min_length=1)
    amendment: str | None = None
    evidence_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_stance_fields(self) -> "RebuttalResponse":
        if self.stance == "concede" and not (self.amendment and self.amendment.strip()):
            raise ValueError(
                f"Response to '{self.objection_id}' concedes and must provide 'amendment'."
            )
        if self.stance == "defend" and not self.evidence_ids:
            raise ValueError(
                f"Response to '{self.objection_id}' defends and must cite non-empty 'evidence_ids'."
            )
        return self


class RebuttalArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    plan_id: str = Field(..., min_length=1)
    responses: list[RebuttalResponse] = Field(default_factory=list)


class ItemRuling(BaseModel):
    model_config = ConfigDict(extra="allow")

    item_id: str = Field(..., min_length=1)
    verdict: Literal["approve", "approve_with_conditions", "reject"]
    conditions: list[str] = Field(default_factory=list)
    rationale: str = Field(..., min_length=1)


class PrecedentRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str = Field(..., min_length=1)
    delegation_ref: str = Field(..., min_length=1)
    holding: str = Field(..., min_length=1)
    scope: str = Field(..., min_length=1)


class VerdictArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    plan_id: str = Field(..., min_length=1)
    overall: Literal["approved", "approved_with_conditions", "rejected"]
    item_rulings: list[ItemRuling] = Field(default_factory=list)
    binding_conditions: list[str] = Field(default_factory=list)
    new_precedents: list[PrecedentRecord] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_overall_consistency(self) -> "VerdictArtifact":
        if any(r.verdict == "reject" for r in self.item_rulings) and self.overall != "rejected":
            raise ValueError("If any item ruling is 'reject', overall verdict must be 'rejected'.")
        return self


class AdvocateCitation(BaseModel):
    model_config = ConfigDict(extra="allow")

    field: str = Field(..., min_length=1)
    quote: str = Field(..., min_length=1)
    source: str | None = None
    ast_ref: str | None = None
    rule_id: str | None = None


class AdvocateArgument(BaseModel):
    model_config = ConfigDict(extra="allow")

    opening: str = Field(..., min_length=1)
    rebuttal: str = Field(default="")
    conceded_fields: list[str] = Field(default_factory=list)
    citations: list[AdvocateCitation] = Field(default_factory=list)


class FactCheckEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    party: Literal["A", "B"]
    field: str = Field(..., min_length=1)
    quote_or_ref: str = Field(..., min_length=1)
    status: Literal["VERIFIED", "UNVERIFIED"]
    details: str = Field(default="")


class TrialRuling(BaseModel):
    model_config = ConfigDict(extra="allow")

    winner: Literal["A", "B", "split", "agreement"]
    field_rulings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    decisive_quote: str = Field(default="")
    decisive_quote_verified: bool = False
    retried: bool = False
    accepted_but_wrong: bool = False
    rationale: str = Field(..., min_length=1)
    cited_rules: list[str] = Field(default_factory=list)


class AppealRecord(BaseModel):
    model_config = ConfigDict(extra="allow")

    appeal_quote: str = Field(..., min_length=1)
    appeal_verified: bool
    outcome: Literal["upheld", "overturned"]
    ruling_after_appeal: dict[str, Any] = Field(default_factory=dict)


class TrialArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_id: str = Field(..., min_length=1)
    round_id: str = Field(..., min_length=1)
    mode: Literal["pipeline", "software", "architecture"] = "pipeline"
    reused_from: str | None = None
    ours_a: dict[str, Any] = Field(default_factory=dict)
    independent_b: dict[str, Any] = Field(default_factory=dict)
    disputed_fields: list[str] = Field(default_factory=list)
    advocate_a: AdvocateArgument
    advocate_b: AdvocateArgument
    fact_check: list[FactCheckEntry] = Field(default_factory=list)
    ruling: TrialRuling
    appeal: AppealRecord | None = None


class GeneratorOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    doc_id: str = Field(..., min_length=1)
    extraction: dict[str, Any] = Field(default_factory=dict)
    blind_assertions: list[dict[str, Any]] = Field(default_factory=list)
    notes: str = ""


class TrialJudgeOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    winner: Literal["A", "B", "split"]
    field_rulings: dict[str, dict[str, Any]] = Field(default_factory=dict)
    decisive_quote: str = Field(default="")
    accepted_but_wrong: bool = False
    rationale: str = Field(..., min_length=1)
    cited_rules: list[str] = Field(default_factory=list)


class LossGroup(BaseModel):
    model_config = ConfigDict(extra="allow")

    group_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    root_cause: str = Field(..., min_length=1)
    loss_ids: list[str] = Field(..., min_length=1)
    position: Literal["fix_rule", "fix_code", "accept_limit", "escalate_owner"]
    facts: list[str] = Field(default_factory=list)
    proposed_change: str = Field(..., min_length=1)


class ClosingBriefArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    round_id: str = Field(..., min_length=1)
    amends_brief_id: str | None = None
    correction_statement: str | None = None
    groups: list[LossGroup] = Field(default_factory=list)


class RequireFixItem(BaseModel):
    model_config = ConfigDict(extra="allow")

    group_id: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    rule_or_file: str = Field(..., min_length=1)


class ClosingVerdictArtifact(BaseModel):
    model_config = ConfigDict(extra="allow")

    round_id: str = Field(..., min_length=1)
    decision: Literal["continue", "consensus"]
    require_fix: list[RequireFixItem] = Field(default_factory=list)
    summary: str = Field(..., min_length=1)


MODEL_REGISTRY: dict[str, type[BaseModel]] = {
    "plan": PlanArtifact,
    "challenge": ChallengeArtifact,
    "rebuttal": RebuttalArtifact,
    "verdict": VerdictArtifact,
    "trial": TrialArtifact,
    "generator": GeneratorOutput,
    "advocate": AdvocateArgument,
    "trial_judge": TrialJudgeOutput,
    "closing_brief": ClosingBriefArtifact,
    "closing_verdict": ClosingVerdictArtifact,
}

PLAN_SCHEMA = PlanArtifact.model_json_schema()
CHALLENGE_SCHEMA = ChallengeArtifact.model_json_schema()
REBUTTAL_SCHEMA = RebuttalArtifact.model_json_schema()
VERDICT_SCHEMA = VerdictArtifact.model_json_schema()
TRIAL_SCHEMA = TrialArtifact.model_json_schema()
GENERATOR_SCHEMA = GeneratorOutput.model_json_schema()
ADVOCATE_SCHEMA = AdvocateArgument.model_json_schema()
TRIAL_JUDGE_SCHEMA = TrialJudgeOutput.model_json_schema()
CLOSING_BRIEF_SCHEMA = ClosingBriefArtifact.model_json_schema()
CLOSING_VERDICT_SCHEMA = ClosingVerdictArtifact.model_json_schema()

SCHEMAS: dict[str, dict[str, Any]] = {
    "plan": PLAN_SCHEMA,
    "challenge": CHALLENGE_SCHEMA,
    "rebuttal": REBUTTAL_SCHEMA,
    "verdict": VERDICT_SCHEMA,
    "trial": TRIAL_SCHEMA,
    "generator": GENERATOR_SCHEMA,
    "advocate": ADVOCATE_SCHEMA,
    "trial_judge": TRIAL_JUDGE_SCHEMA,
    "closing_brief": CLOSING_BRIEF_SCHEMA,
    "closing_verdict": CLOSING_VERDICT_SCHEMA,
}


def validate_schema(data: Any, schema_name: str) -> dict[str, Any]:
    """Validate arbitrary parsed JSON data against a named courtroom schema.

    Returns the normalized dictionary on success, or raises SchemaValidationError.
    """
    model_cls = MODEL_REGISTRY.get(schema_name)
    if model_cls is None:
        raise SchemaValidationError(f"Unknown schema name: '{schema_name}'")
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"Expected JSON object for schema '{schema_name}', got {type(data).__name__}"
        )
    try:
        validated = model_cls.model_validate(data)
    except ValidationError as exc:
        raise SchemaValidationError(f"Schema '{schema_name}' validation failed: {exc}") from exc
    return validated.model_dump()
