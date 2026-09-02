"""
Seed synthetic personalization history for demos and local development.

OFFLINE ONLY. This lives in training/ and is never imported by anything under app/
(AGENTS.md section 2). Run it directly:

    python -m training.seed_personalization

SYNTHETIC DATA. These users never existed and this history never happened. It is
labelled synthetic here, and anything surfacing it must say so (CONTEXT.md section
11).
"""

import time

from app.personalization.store import PersonalizationStore
from app.schemas.enums import FeedbackEventType, FinancingStrategy, LoanPurpose

DAY = 86400.0

# Three users, each demonstrating a different history shape the recommender should
# see differently. Nothing here is a real person.
SEED_USERS = {
    # Settled borrower: repeatedly accepted long-tenure home financing.
    "demo-returning-home": {
        "recommendations": [
            (LoanPurpose.HOME, "HL-001", 120, FinancingStrategy.BORROW_100, 200.0),
            (LoanPurpose.HOME, "HL-001", 120, FinancingStrategy.BORROW_100, 90.0),
            (LoanPurpose.HOME, "HL-002", 108, FinancingStrategy.BORROW_80_LIQUIDATE_20, 20.0),
        ],
        "events": [
            (FeedbackEventType.VIEWED, "HL-001", 200.0),
            (FeedbackEventType.ACCEPTED, "HL-001", 199.0),
            (FeedbackEventType.VIEWED, "HL-001", 90.0),
            (FeedbackEventType.ACCEPTED, "HL-001", 89.0),
            (FeedbackEventType.VIEWED, "HL-002", 20.0),
        ],
    },
    # Hesitant shopper: lots of looking, repeated declines, nothing accepted. Should
    # produce a high decline count and no preferred tenure band.
    "demo-declining": {
        "recommendations": [
            (LoanPurpose.PERSONAL, "PL-001", 36, FinancingStrategy.BORROW_100, 60.0),
            (LoanPurpose.PERSONAL, "PL-001", 48, FinancingStrategy.BORROW_100, 30.0),
            (LoanPurpose.MEDICAL, "PL-001", 24, FinancingStrategy.BORROW_100, 5.0),
        ],
        "events": [
            (FeedbackEventType.VIEWED, "PL-001", 60.0),
            (FeedbackEventType.DECLINED, "PL-001", 59.0),
            (FeedbackEventType.VIEWED, "PL-001", 30.0),
            (FeedbackEventType.DECLINED, "PL-001", 29.0),
            (FeedbackEventType.DECLINED, "PL-001", 5.0),
        ],
    },
    # Liquidator: prefers funding from holdings rather than borrowing in full.
    "demo-liquidator": {
        "recommendations": [
            (LoanPurpose.VEHICLE, "VL-001", 36, FinancingStrategy.BORROW_40_LIQUIDATE_60, 45.0),
            (LoanPurpose.VEHICLE, "VL-001", 36, FinancingStrategy.BORROW_60_LIQUIDATE_40, 10.0),
        ],
        "events": [
            (FeedbackEventType.VIEWED, "VL-001", 45.0),
            (FeedbackEventType.ACCEPTED, "VL-001", 44.0),
            (FeedbackEventType.VIEWED, "VL-001", 10.0),
        ],
    },
}


def seed(store: PersonalizationStore, now: float | None = None) -> None:
    now = time.time() if now is None else now

    for user_id, history in SEED_USERS.items():
        for purpose, product_id, tenure, strategy, days_ago in history["recommendations"]:
            at = now - days_ago * DAY
            store.record_profile_snapshot(
                user_id=user_id,
                monthly_income=110_000.0,
                monthly_expenses=52_000.0,
                existing_emi=9_000.0,
                disposable_income=49_000.0,
                debt_burden_ratio=0.082,
                credit_score=745,
                at=at,
            )
            store.record_recommendation(
                user_id=user_id,
                purpose=purpose,
                product_id=product_id,
                amount=1_500_000.0,
                tenure=tenure,
                strategy=strategy,
                suitability=0.78,
                status="RECOMMENDED",
                at=at,
            )
        for event_type, product_id, days_ago in history["events"]:
            store.record_feedback_event(
                user_id=user_id,
                event_type=event_type,
                product_id=product_id,
                at=now - days_ago * DAY,
            )


def main() -> None:
    with PersonalizationStore() as store:
        seed(store)
        print(f"seeded {len(SEED_USERS)} synthetic users into {store.db_path}")


if __name__ == "__main__":
    main()
