"""
The LLM explanation layer (P13).

THE LLM EXPLAINS. It never decides and never computes (CONTEXT.md non-negotiable 14).
It is handed a validated structured payload of already-computed values and produces
prose. It is never in the path that produces a value or selects an option.

EVERY RESPONSE PASSES BOTH GUARDS before it reaches a user:
  UNGROUNDED (numeric or entity) -> REJECT, fall back to the deterministic template,
                                    log the offending figure or entity
  UNVERIFIED                     -> ACCEPT, flag on the response, log the token so the
                                    normalizer improves from real traffic
  GROUNDED                       -> accept

The guards may not be bypassed or disabled, and their tolerance may not be widened to
make a demo pass (AGENTS.md section 5).

NO PROMPT TEXT LIVES HERE. Every string comes from app/explain/prompts.py.

The template explainer is the fallback for every failure mode: no API key, a network
error, an empty response, or a rejected one. The user always gets an explanation.
"""

import logging

from app.config import settings
from app.explain import prompts
from app.explain.grounding import verify_entity_grounding, verify_numeric_grounding
from app.explain.payloads import (
    build_mismatch_payload,
    build_recommendation_payload,
    entity_vocabulary,
)
from app.explain.templates import template_explanation
from app.schemas import Recommendation
from app.schemas.enums import ExplanationSource, GroundingOutcome, RecommendationStatus
from app.schemas.explanation import Explanation

logger = logging.getLogger(__name__)

REQUEST_TIMEOUT_SECONDS = 20.0


class LLMUnavailable(RuntimeError):
    """The LLM could not be reached or is not configured."""


def _template(recommendation: Recommendation, reason: str) -> Explanation:
    return Explanation(
        text=template_explanation(recommendation),
        source=ExplanationSource.TEMPLATE,
        prompt_version=prompts.PROMPT_VERSION,
        degraded_reason=reason,
    )


# Transient HTTP statuses that warrant a single retry: rate limits, request-too-large
# and server errors. Auth (401/403) and not-found (404) are treated as permanent.
TRANSIENT_STATUSES = {429, 500, 502, 503, 504, 413}


def call_llm(prompt: str) -> str:
    """
    One HTTP call, with a single retry on transient provider-side failures (rate
    limits, 5xx, request-too-large). Isolated so tests can replace it without touching
    the guard logic.

    Raises LLMUnavailable for every failure mode; the caller degrades to the template.
    """
    if not settings.LLM_API_KEY or not settings.LLM_API_ENDPOINT:
        raise LLMUnavailable("LLM_API_KEY or LLM_API_ENDPOINT is not configured")

    import httpx

    last_response: httpx.Response | None = None
    success: httpx.Response | None = None
    for _ in range(2):
        response = httpx.post(
            settings.LLM_API_ENDPOINT,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": prompts.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        if response.is_success:
            success = response
            break
        if response.status_code not in TRANSIENT_STATUSES:
            response.raise_for_status()
        last_response = response
    if success is None:
        # Both attempts failed on transient errors; a permanent error already raised
        # above. Surface a clear degraded message rather than an opaque parse error.
        last_status = (
            last_response.status_code if last_response is not None else "unknown"
        )
        raise LLMUnavailable(
            f"transient LLM failure after retry (status {last_status})"
        )

    try:
        body = success.json()
    except Exception as error:  # noqa: BLE001 - every failure degrades identically
        raise LLMUnavailable(f"{type(error).__name__}: {error}") from error

    choices = body.get("choices") or []
    text = (choices[0].get("message", {}).get("content", "") if choices else "").strip()
    if not text:
        raise LLMUnavailable("the LLM returned an empty response")
    return text


def _guarded(
    recommendation: Recommendation, payload: dict, prompt: str
) -> Explanation:
    """
    Call the LLM and put its answer through both guards.

    A rejection is not an error: the customer gets the template explanation instead,
    and the rejection is logged with the offending figure or entity.
    """
    try:
        text = call_llm(prompt)
    except LLMUnavailable as error:
        logger.info("LLM unavailable (%s); using the deterministic template", error)
        return _template(recommendation, f"llm_unavailable: {error}")

    numeric = verify_numeric_grounding(text, payload)
    allowed_entities, known_entities = entity_vocabulary(recommendation)
    entity = verify_entity_grounding(text, allowed_entities, known_entities)

    if numeric.outcome is GroundingOutcome.UNGROUNDED:
        logger.warning(
            "LLM explanation REJECTED: invented figures %s", numeric.offending()
        )
        explanation = _template(
            recommendation,
            f"numeric_grounding_rejected: {numeric.offending()}",
        )
        return explanation.model_copy(
            update={"numeric_grounding": numeric, "entity_grounding": entity}
        )

    if entity.outcome is GroundingOutcome.UNGROUNDED:
        logger.warning(
            "LLM explanation REJECTED: invented entities %s", entity.offending()
        )
        explanation = _template(
            recommendation,
            f"entity_grounding_rejected: {entity.offending()}",
        )
        return explanation.model_copy(
            update={"numeric_grounding": numeric, "entity_grounding": entity}
        )

    # UNVERIFIED accepts. An unparseable token is a limitation of the guard, not
    # evidence of a hallucination, and must not cost the user their explanation.
    return Explanation(
        text=text,
        source=ExplanationSource.LLM,
        prompt_version=prompts.PROMPT_VERSION,
        numeric_grounding=numeric,
        entity_grounding=entity,
        unverified_tokens=numeric.unverified(),
    )


def explain_recommendation(recommendation: Recommendation) -> Explanation:
    """
    Explain a successful recommendation.

    A blocked ML top choice gets its own prompt, because "our model's best match for
    you was X, but it was not offered" is a materially different thing to say and the
    easiest place for a model to imply the blocked option is still available.
    """
    if recommendation.status is not RecommendationStatus.RECOMMENDED:
        return explain_mismatch(recommendation)

    payload = build_recommendation_payload(recommendation)
    prompt = (
        prompts.blocked_top_choice_prompt(payload)
        if recommendation.ml_top_choice_blocked is not None
        else prompts.recommendation_prompt(payload)
    )
    return _guarded(recommendation, payload, prompt)


def explain_mismatch(recommendation: Recommendation) -> Explanation:
    """Explain any of the four no-recommendation outcomes."""
    payload = build_mismatch_payload(recommendation)
    return _guarded(recommendation, payload, prompts.no_suitable_loan_prompt(payload))


def answer_question(
    question: str,
    recommendation: Recommendation,
    scenario_result: Recommendation | None = None,
) -> Explanation:
    """
    Answer a follow-up, optionally comparing against a what-if scenario result.

    THE SCENARIO RESULT IS A REAL PIPELINE RUN, not an arithmetic adjustment of the
    original (CONTEXT.md section 4). This function only describes the difference
    between two computed results; the prompt forbids the model from computing one.
    """
    if scenario_result is not None:
        payload = {
            "original": build_recommendation_payload(recommendation),
            "scenario": build_recommendation_payload(scenario_result),
        }
        prompt = prompts.scenario_comparison_prompt(payload)
        # The guard runs against the union of both payloads, so a figure from either
        # side is grounded and a figure from neither is not.
        return _guarded(recommendation, payload, prompt)

    payload = (
        build_recommendation_payload(recommendation)
        if recommendation.status is RecommendationStatus.RECOMMENDED
        else build_mismatch_payload(recommendation)
    )
    return _guarded(recommendation, payload, prompts.question_prompt(question, payload))
