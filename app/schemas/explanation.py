"""
Explanation-layer contracts: XAI contributions, grounding results, the explanation.

Owners (AGENTS.md section 2):
  XaiExplanation    -> app/explain/xai.py
  GroundingCheck    -> app/explain/grounding.py
  Explanation       -> app/explain/llm.py
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.enums import ExplanationSource, GroundingOutcome, XaiMethod


class FeatureContribution(BaseModel):
    """
    One feature's signed push on the model's output. STRUCTURED DATA ONLY — the XAI
    layer produces no prose (CONTEXT.md section 4).
    """

    model_config = ConfigDict(extra="forbid")

    feature: str
    value: float
    contribution: float


class FeatureContrast(BaseModel):
    """
    Why the winner outranked the runner-up, feature by feature.

    This is the question the product actually needs answered — not "why is this
    candidate good" but "why THIS one rather than that one".
    """

    model_config = ConfigDict(extra="forbid")

    feature: str
    winner_value: float
    runner_up_value: float
    winner_contribution: float
    runner_up_contribution: float
    delta: float


class XaiExplanation(BaseModel):
    """
    Model behaviour, explained. Never a decision and never prose.

    `degraded` is True when contributions came from feature importances rather than
    TreeSHAP. A degradation that is not flagged is a correctness defect
    (AGENTS.md section 7).
    """

    model_config = ConfigDict(extra="forbid")

    candidate_id: str
    method: XaiMethod
    degraded: bool = False
    base_value: float | None = None
    contributions: list[FeatureContribution] = Field(default_factory=list)
    contrast: list[FeatureContrast] = Field(default_factory=list)
    runner_up_candidate_id: str | None = None
    note: str | None = None


class GroundingFinding(BaseModel):
    """One token the guard examined, and what it concluded about it."""

    model_config = ConfigDict(extra="forbid")

    text: str
    outcome: GroundingOutcome
    interpretations: list[float] = Field(default_factory=list)
    note: str = ""


class GroundingCheck(BaseModel):
    """
    The guard's verdict over a whole response.

    UNGROUNDED rejects and falls back to the template. UNVERIFIED ACCEPTS and flags —
    an unparseable token is a limitation of the guard, not evidence of a
    hallucination, and must not cost the user their explanation.
    """

    model_config = ConfigDict(extra="forbid")

    outcome: GroundingOutcome
    findings: list[GroundingFinding] = Field(default_factory=list)

    @property
    def rejected(self) -> bool:
        return self.outcome is GroundingOutcome.UNGROUNDED

    def offending(self) -> list[str]:
        return [
            finding.text
            for finding in self.findings
            if finding.outcome is GroundingOutcome.UNGROUNDED
        ]

    def unverified(self) -> list[str]:
        return [
            finding.text
            for finding in self.findings
            if finding.outcome is GroundingOutcome.UNVERIFIED
        ]


class Explanation(BaseModel):
    """
    The natural-language explanation handed to the user, plus how it was produced.

    Every degradation is visible: which writer produced it, both guard outcomes, and
    why the LLM was not used when it was not.
    """

    model_config = ConfigDict(extra="forbid")

    text: str
    source: ExplanationSource
    prompt_version: str
    numeric_grounding: GroundingCheck | None = None
    entity_grounding: GroundingCheck | None = None
    unverified_tokens: list[str] = Field(default_factory=list)
    degraded_reason: str | None = None
