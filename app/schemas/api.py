"""
Request bodies for the API layer (P14).

Routes validate, call a core module, and return — they contain no business logic.
These are the typed contracts for what a client can submit. Every input model
reuses the customer/portfolio/requirement schemas so a request cannot carry a field
the pipeline does not understand.

Owner: app/api/ (P14). Created here so every data structure crossing the client ->
pipeline boundary is a Pydantic model defined under app/schemas/ (AGENTS.md section 3).
"""

from pydantic import BaseModel, ConfigDict, Field

from app.schemas import CustomerProfile, LoanRequirement, Portfolio


class RecommendRequest(BaseModel):
    """
    The full set of pipeline inputs for a recommendation or a coverage query.

    `portfolio` is optional — the no-portfolio path is first-class
    (CONTEXT.md non-negotiable 16). `user_id` is the OPTIONAL pseudonymous id for
    personalization; omit it for an anonymous cold-start run.
    """

    model_config = ConfigDict(extra="forbid")

    customer: CustomerProfile
    requirement: LoanRequirement
    portfolio: Portfolio | None = None
    user_id: str | None = None


class ExplanationRequest(BaseModel):
    """
    Request an explanation for a recommendation computed from these inputs.

    Server-side, the SAME trusted pipeline (/recommend) is run on these inputs to
    obtain the already-decided Recommendation, and only then is it explained. The
    profile and requirement are required because XAI reconstructs the model's feature
    rows from them; the Recommendation itself and its trace deliberately carry no raw
    profile (traces hold no PII). The endpoint explains a computed result; it never
    makes a novel decision and never lets the LLM compute anything.
    """

    model_config = ConfigDict(extra="forbid")

    customer: CustomerProfile
    requirement: LoanRequirement
    portfolio: Portfolio | None = None
    user_id: str | None = None
    question: str | None = Field(default=None)
