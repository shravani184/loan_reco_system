"""
History-derived features for the primary recommender.

THIS IS A FEATURE SOURCE, NOT A SECOND RECOMMENDER (CONTEXT.md section 10). Nothing
here scores a candidate, orders anything, or decides anything. Every value it emits
is an input to app/ml/recommender.py, which is the only module allowed to rank.

COLD START IS FIRST-CLASS, exactly like the zero portfolio. A None user_id, an
unknown user_id, or a known user with no history all return a valid neutral context
with is_cold_start = True, and the pipeline runs identically.

All weights, the decay half-life and the tenure band width come from config.
"""

import sqlite3
import time

from app.config import settings
from app.personalization.store import PersonalizationStore
from app.schemas import PersonalizationContext
from app.schemas.enums import FeedbackEventType, FinancingStrategy, LoanPurpose

SECONDS_PER_DAY = 86400.0


def _uniform(categories: list) -> dict:
    """
    The no-preference map: every category present, all equal, summing to 1.0.

    Fully shaped rather than empty so P8's feature path never tests for a missing
    key — the same decision P2 made for the allocation map. An observed-preference
    map also sums to 1.0, so neutral and observed are on one scale.
    """
    share = 1.0 / len(categories)
    return {category: share for category in categories}


def neutral_personalization_context() -> PersonalizationContext:
    """
    The cold-start block. Valid, complete, and consumable everywhere.

    This is the single definition of "neutral"; tests/fixtures.py delegates to it so
    a fixture can never drift from what the pipeline actually produces.
    """
    return PersonalizationContext(
        is_cold_start=True,
        session_count=0,
        prior_declines=0,
        engagement_score=0.0,
        preferred_tenure_band_months=None,
        purpose_affinity=_uniform(list(LoanPurpose)),
        strategy_affinity=_uniform(list(FinancingStrategy)),
    )


def _decay(event_at: float, now: float) -> float:
    """
    Weight halves every PERSONALIZATION_DECAY_HALF_LIFE_DAYS.

    A future-dated row is clamped to weight 1.0 rather than amplified, so a clock
    skew cannot make one event outweigh a real history.
    """
    age_days = max(now - event_at, 0.0) / SECONDS_PER_DAY
    return 0.5 ** (age_days / settings.PERSONALIZATION_DECAY_HALF_LIFE_DAYS)


def _normalized_affinity(weights: dict, categories: list) -> dict:
    """
    Turn accumulated weights into a fully-shaped map summing to 1.0. With no
    evidence at all, fall back to the uniform no-preference map.
    """
    total = sum(weights.values())
    if total <= 0.0:
        return _uniform(categories)
    return {category: weights.get(category, 0.0) / total for category in categories}


def _tenure_band(tenure_months: int) -> int:
    """Group a tenure into a band of TENURE_BAND_WIDTH_MONTHS, labelled by its floor."""
    width = settings.TENURE_BAND_WIDTH_MONTHS
    return (tenure_months // width) * width


def _accepted_product_ids(events: list[sqlite3.Row]) -> set[str]:
    return {
        row["product_id"]
        for row in events
        if row["event_type"] == FeedbackEventType.ACCEPTED.value
        and row["product_id"] is not None
    }


def get_personalization_context(
    user_id: str | None,
    store: PersonalizationStore | None = None,
    now: float | None = None,
) -> PersonalizationContext:
    """
    Read the store and emit the history-derived feature block.

    `store` and `now` are parameters so tests can use a temp database and a fixed
    clock. In production both default from config and the system clock.
    """
    if user_id is None:
        return neutral_personalization_context()

    owned_store = store is None
    store = store or PersonalizationStore()
    now = time.time() if now is None else now

    try:
        if not store.user_exists(user_id):
            return neutral_personalization_context()

        recommendations = store.recommendations(user_id)
        events = store.feedback_events(user_id)
        session_count = store.session_count(user_id)

        # A known user with nothing recorded is still a cold start: there is no
        # history to derive a preference from, so returning anything other than the
        # neutral block would invent one.
        if not recommendations and not events:
            return neutral_personalization_context()

        purpose_weights: dict[LoanPurpose, float] = {}
        strategy_weights: dict[FinancingStrategy, float] = {}
        for row in recommendations:
            weight = _decay(row["at"], now)
            purpose = LoanPurpose(row["purpose"])
            strategy = FinancingStrategy(row["strategy"])
            purpose_weights[purpose] = purpose_weights.get(purpose, 0.0) + weight
            strategy_weights[strategy] = strategy_weights.get(strategy, 0.0) + weight

        # Engagement: decayed, event-type-weighted interaction volume, saturated into
        # [0,1). Saturation rather than a clamp, so the first interactions matter most
        # and a very active user never pins the feature at exactly 1.0.
        engagement_weight = sum(
            settings.PERSONALIZATION_EVENT_WEIGHT[FeedbackEventType(row["event_type"])]
            * _decay(row["at"], now)
            for row in events
        )
        engagement_score = engagement_weight / (
            engagement_weight + settings.ENGAGEMENT_SATURATION
        )

        prior_declines = sum(
            1
            for row in events
            if row["event_type"] == FeedbackEventType.DECLINED.value
        )

        # Preferred tenure band: the decay-weighted favourite among tenures the user
        # actually ACCEPTED. Recommendations they never accepted say nothing about
        # preference, and the no-loan candidate has no tenure at all.
        accepted_products = _accepted_product_ids(events)
        band_weights: dict[int, float] = {}
        for row in recommendations:
            if row["tenure"] is None or row["product_id"] not in accepted_products:
                continue
            band = _tenure_band(int(row["tenure"]))
            band_weights[band] = band_weights.get(band, 0.0) + _decay(row["at"], now)
        preferred_tenure_band = (
            max(band_weights, key=lambda band: band_weights[band])
            if band_weights
            else None
        )

        return PersonalizationContext(
            is_cold_start=False,
            session_count=session_count,
            prior_declines=prior_declines,
            engagement_score=engagement_score,
            preferred_tenure_band_months=preferred_tenure_band,
            purpose_affinity=_normalized_affinity(purpose_weights, list(LoanPurpose)),
            strategy_affinity=_normalized_affinity(
                strategy_weights, list(FinancingStrategy)
            ),
        )
    finally:
        if owned_store:
            store.close()
