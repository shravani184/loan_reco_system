"""
Personalization store and context (P3).

Every test writes to a pytest tmp_path database. Nothing here touches data/ or the
configured PERSONALIZATION_DB_URL, and a test asserts that.
"""

import sqlite3

import pytest

from app.config import settings
from app.personalization.context import (
    get_personalization_context,
    neutral_personalization_context,
)
from app.personalization.store import TABLES, PersonalizationStore
from app.schemas.enums import FeedbackEventType, FinancingStrategy, LoanPurpose
from tests import fixtures

DAY = 86400.0
NOW = 1_800_000_000.0  # fixed clock, so decay is deterministic


@pytest.fixture
def store(tmp_path):
    """A throwaway database under pytest's tmp_path. Never a path under data/."""
    db = tmp_path / "personalization.db"
    with PersonalizationStore(f"sqlite:///{db}") as opened:
        yield opened


def _history(store: PersonalizationStore, user_id: str = "u-1") -> None:
    """
    A small hand-checkable history.

      HOME recommendation, 60 tenure, BORROW_100, 0 days ago     -> decay 1.0
      HOME recommendation, 60 tenure, BORROW_100, 90 days ago    -> decay 0.5
      VEHICLE recommendation, 36 tenure, BORROW_100, 90 days ago -> decay 0.5

    Purpose weights: HOME 1.5, VEHICLE 0.5, total 2.0 -> HOME 0.75, VEHICLE 0.25.
    """
    store.record_profile_snapshot(
        user_id=user_id,
        monthly_income=100_000.0,
        monthly_expenses=40_000.0,
        existing_emi=5_000.0,
        disposable_income=55_000.0,
        debt_burden_ratio=0.05,
        credit_score=750,
        at=NOW,
    )
    store.record_recommendation(
        user_id=user_id,
        purpose=LoanPurpose.HOME,
        product_id="HL-001",
        amount=2_000_000.0,
        tenure=60,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.8,
        status="RECOMMENDED",
        at=NOW,
    )
    store.record_recommendation(
        user_id=user_id,
        purpose=LoanPurpose.HOME,
        product_id="HL-001",
        amount=2_000_000.0,
        tenure=60,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.8,
        status="RECOMMENDED",
        at=NOW - 90 * DAY,
    )
    store.record_recommendation(
        user_id=user_id,
        purpose=LoanPurpose.VEHICLE,
        product_id="VL-001",
        amount=600_000.0,
        tenure=36,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.7,
        status="RECOMMENDED",
        at=NOW - 90 * DAY,
    )
    store.record_feedback_event(
        user_id=user_id,
        event_type=FeedbackEventType.ACCEPTED,
        product_id="HL-001",
        at=NOW,
    )


# ------------------------------------------------------------------ cold start


def test_none_user_id_returns_neutral_cold_start_context():
    context = get_personalization_context(None)
    assert context.is_cold_start is True
    assert context.session_count == 0
    assert context.prior_declines == 0
    assert context.engagement_score == 0.0
    assert context.preferred_tenure_band_months is None


def test_unknown_user_id_returns_the_same_neutral_context(store):
    assert get_personalization_context("nobody", store=store, now=NOW) == (
        neutral_personalization_context()
    )


def test_none_and_unknown_user_produce_identical_contexts(store):
    assert get_personalization_context(None) == get_personalization_context(
        "nobody", store=store, now=NOW
    )


def test_known_user_with_no_history_is_still_cold_start(store):
    """A row in users/ is not history. Inventing a preference from it would be wrong."""
    store.upsert_user("u-empty", at=NOW)
    context = get_personalization_context("u-empty", store=store, now=NOW)
    assert context.is_cold_start is True
    assert context == neutral_personalization_context()


def test_neutral_affinities_are_fully_shaped_and_uniform():
    """
    Every category present, no missing keys for the P8 feature path to handle, and
    uniform meaning "no preference" rather than "no evidence".
    """
    context = neutral_personalization_context()
    assert set(context.purpose_affinity) == set(LoanPurpose)
    assert set(context.strategy_affinity) == set(FinancingStrategy)
    assert sum(context.purpose_affinity.values()) == pytest.approx(1.0)
    assert sum(context.strategy_affinity.values()) == pytest.approx(1.0)
    assert len(set(context.purpose_affinity.values())) == 1


def test_fixture_matches_the_real_neutral_constructor():
    """The fixture delegates, so it cannot drift from the pipeline's own output."""
    assert fixtures.neutral_personalization() == neutral_personalization_context()


# --------------------------------------------------------------- with history


def test_history_produces_affinities_that_differ_from_neutral(store):
    _history(store)
    context = get_personalization_context("u-1", store=store, now=NOW)
    assert context.is_cold_start is False
    assert context.purpose_affinity != neutral_personalization_context().purpose_affinity


def test_purpose_affinity_is_hand_computed(store):
    """HOME 1.0 + 0.5 = 1.5, VEHICLE 0.5, total 2.0 -> 0.75 / 0.25."""
    _history(store)
    affinity = get_personalization_context("u-1", store=store, now=NOW).purpose_affinity
    assert affinity[LoanPurpose.HOME] == pytest.approx(0.75)
    assert affinity[LoanPurpose.VEHICLE] == pytest.approx(0.25)
    assert affinity[LoanPurpose.EDUCATION] == 0.0
    assert sum(affinity.values()) == pytest.approx(1.0)


def test_strategy_affinity_concentrates_on_the_only_observed_strategy(store):
    _history(store)
    affinity = get_personalization_context(
        "u-1", store=store, now=NOW
    ).strategy_affinity
    assert affinity[FinancingStrategy.BORROW_100] == pytest.approx(1.0)
    assert affinity[FinancingStrategy.LIQUIDATE_100] == 0.0


def test_affinity_maps_stay_fully_shaped_with_history(store):
    _history(store)
    context = get_personalization_context("u-1", store=store, now=NOW)
    assert set(context.purpose_affinity) == set(LoanPurpose)
    assert set(context.strategy_affinity) == set(FinancingStrategy)


def test_session_count_counts_profile_snapshots(store):
    _history(store)
    assert get_personalization_context("u-1", store=store, now=NOW).session_count == 1
    store.record_profile_snapshot(
        user_id="u-1",
        monthly_income=100_000.0,
        monthly_expenses=40_000.0,
        existing_emi=5_000.0,
        disposable_income=55_000.0,
        debt_burden_ratio=0.05,
        credit_score=750,
        at=NOW,
    )
    assert get_personalization_context("u-1", store=store, now=NOW).session_count == 2


def test_prior_declines_counts_only_declined_events(store):
    _history(store)
    for _ in range(3):
        store.record_feedback_event(
            user_id="u-1",
            event_type=FeedbackEventType.DECLINED,
            product_id="VL-001",
            at=NOW,
        )
    store.record_feedback_event(
        user_id="u-1",
        event_type=FeedbackEventType.VIEWED,
        product_id="VL-001",
        at=NOW,
    )
    assert get_personalization_context("u-1", store=store, now=NOW).prior_declines == 3


def test_preferred_tenure_band_comes_from_accepted_history(store):
    """
    Only HL-001 was ACCEPTED, and its tenure is 60 -> band floor 60 at a 12-month
    band width. The declined/unaccepted VEHICLE tenure of 36 must not win.
    """
    _history(store)
    context = get_personalization_context("u-1", store=store, now=NOW)
    assert context.preferred_tenure_band_months == 60


def test_no_accepted_history_means_no_preferred_tenure_band(store):
    """Recommendations a user never accepted say nothing about their preference."""
    store.record_recommendation(
        user_id="u-2",
        purpose=LoanPurpose.PERSONAL,
        product_id="PL-001",
        amount=500_000.0,
        tenure=36,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.6,
        status="RECOMMENDED",
        at=NOW,
    )
    store.record_feedback_event(
        user_id="u-2",
        event_type=FeedbackEventType.DECLINED,
        product_id="PL-001",
        at=NOW,
    )
    context = get_personalization_context("u-2", store=store, now=NOW)
    assert context.preferred_tenure_band_months is None
    assert context.prior_declines == 1


def test_no_loan_history_rows_have_no_product_or_tenure(store):
    """LIQUIDATE_100 carries neither, matching the Candidate schema's shape rule."""
    store.record_recommendation(
        user_id="u-3",
        purpose=LoanPurpose.VEHICLE,
        amount=400_000.0,
        strategy=FinancingStrategy.LIQUIDATE_100,
        status="RECOMMENDED",
        at=NOW,
    )
    context = get_personalization_context("u-3", store=store, now=NOW)
    assert context.strategy_affinity[FinancingStrategy.LIQUIDATE_100] == pytest.approx(
        1.0
    )
    assert context.preferred_tenure_band_months is None


# ------------------------------------------------------------------ time decay


def test_an_old_event_contributes_less_than_a_recent_identical_one(store):
    for user_id, days_ago in (("recent", 0.0), ("old", 365.0)):
        store.record_feedback_event(
            user_id=user_id,
            event_type=FeedbackEventType.ACCEPTED,
            product_id="HL-001",
            at=NOW - days_ago * DAY,
        )
    recent = get_personalization_context("recent", store=store, now=NOW)
    old = get_personalization_context("old", store=store, now=NOW)
    assert recent.engagement_score > old.engagement_score
    assert old.engagement_score > 0.0


def test_decay_halves_at_exactly_one_half_life(store):
    """
    Two users, one identical ACCEPTED event each, separated by one half-life. The
    engagement transform is monotone, so the older user's raw weight is half — which
    the saturating transform preserves as a strictly smaller score.
    """
    half_life = settings.PERSONALIZATION_DECAY_HALF_LIFE_DAYS
    weight = settings.PERSONALIZATION_EVENT_WEIGHT[FeedbackEventType.ACCEPTED]
    saturation = settings.ENGAGEMENT_SATURATION

    store.record_feedback_event(
        user_id="fresh",
        event_type=FeedbackEventType.ACCEPTED,
        product_id="HL-001",
        at=NOW,
    )
    store.record_feedback_event(
        user_id="aged",
        event_type=FeedbackEventType.ACCEPTED,
        product_id="HL-001",
        at=NOW - half_life * DAY,
    )
    fresh = get_personalization_context("fresh", store=store, now=NOW)
    aged = get_personalization_context("aged", store=store, now=NOW)

    assert fresh.engagement_score == pytest.approx(weight / (weight + saturation))
    half = weight * 0.5
    assert aged.engagement_score == pytest.approx(half / (half + saturation))


def test_decay_makes_a_recent_purpose_dominate_an_old_one(store):
    store.record_recommendation(
        user_id="u-4",
        purpose=LoanPurpose.EDUCATION,
        product_id="EL-001",
        amount=800_000.0,
        tenure=48,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.7,
        status="RECOMMENDED",
        at=NOW - 360 * DAY,
    )
    store.record_recommendation(
        user_id="u-4",
        purpose=LoanPurpose.BUSINESS,
        product_id="BL-001",
        amount=800_000.0,
        tenure=48,
        strategy=FinancingStrategy.BORROW_100,
        suitability=0.7,
        status="RECOMMENDED",
        at=NOW,
    )
    affinity = get_personalization_context("u-4", store=store, now=NOW).purpose_affinity
    assert affinity[LoanPurpose.BUSINESS] > affinity[LoanPurpose.EDUCATION]


def test_a_future_dated_event_is_not_amplified(store):
    """Clock skew must not let one row outweigh a real history."""
    store.record_feedback_event(
        user_id="skewed",
        event_type=FeedbackEventType.ACCEPTED,
        product_id="HL-001",
        at=NOW + 400 * DAY,
    )
    store.record_feedback_event(
        user_id="normal",
        event_type=FeedbackEventType.ACCEPTED,
        product_id="HL-001",
        at=NOW,
    )
    skewed = get_personalization_context("skewed", store=store, now=NOW)
    normal = get_personalization_context("normal", store=store, now=NOW)
    assert skewed.engagement_score == pytest.approx(normal.engagement_score)


def test_engagement_score_is_bounded(store):
    for index in range(200):
        store.record_feedback_event(
            user_id="busy",
            event_type=FeedbackEventType.ACCEPTED,
            product_id=f"P-{index}",
            at=NOW,
        )
    score = get_personalization_context("busy", store=store, now=NOW).engagement_score
    assert 0.0 <= score < 1.0


# -------------------------------------------------------------------- deletion


def test_delete_user_removes_every_row_across_all_tables(store):
    _history(store)
    assert store.user_exists("u-1")

    removed = store.delete_user("u-1")
    assert removed > 0

    for table in TABLES:
        remaining = store._connection.execute(
            f"SELECT COUNT(*) FROM {table} WHERE user_id = ?", ("u-1",)
        ).fetchone()[0]
        assert remaining == 0, f"{table} still holds rows for the deleted user"


def test_delete_user_returns_the_context_to_cold_start(store):
    _history(store)
    assert get_personalization_context("u-1", store=store, now=NOW).is_cold_start is False

    store.delete_user("u-1")
    assert get_personalization_context("u-1", store=store, now=NOW) == (
        neutral_personalization_context()
    )


def test_delete_user_leaves_other_users_untouched(store):
    _history(store, "u-1")
    _history(store, "u-2")
    store.delete_user("u-1")
    assert not store.user_exists("u-1")
    assert store.user_exists("u-2")
    assert get_personalization_context("u-2", store=store, now=NOW).is_cold_start is False


def test_deleting_an_unknown_user_is_harmless(store):
    assert store.delete_user("never-existed") == 0


# --------------------------------------------------------------------- privacy


PII_SUBSTRINGS = (
    "name",
    "email",
    "phone",
    "mobile",
    "address",
    "dob",
    "birth",
    "pan",
    "aadhaar",
    "ssn",
    "passport",
    "note",
    "comment",
    "text",
)


def test_no_table_has_a_pii_column(store):
    """
    Privacy is a schema property: with no column to hold PII, no code path can
    persist it. Asserted against the live sqlite schema, not the source.
    """
    for table in TABLES:
        columns = [
            row["name"]
            for row in store._connection.execute(f"PRAGMA table_info({table})")
        ]
        for column in columns:
            lowered = column.lower()
            for banned in PII_SUBSTRINGS:
                assert banned not in lowered, f"{table}.{column} looks like PII"


def test_every_expected_table_exists(store):
    present = {
        row["name"]
        for row in store._connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    assert set(TABLES).issubset(present)


def test_store_rejects_a_non_sqlite_url():
    with pytest.raises(ValueError):
        PersonalizationStore("postgresql://localhost/plrs")


def test_tests_never_touch_the_configured_database(store):
    """The store under test is a tmp_path file, not the configured URL."""
    assert "data/personalization.db" not in store.db_path.replace("\\", "/")
    assert store.db_path != settings.PERSONALIZATION_DB_URL


# ----------------------------------------------------------------- seed script


def test_seed_script_produces_non_cold_start_users(tmp_path):
    """The seed script lives in training/ and is exercised, not just present."""
    from training.seed_personalization import SEED_USERS, seed

    db = tmp_path / "seeded.db"
    with PersonalizationStore(f"sqlite:///{db}") as seeded_store:
        seed(seeded_store, now=NOW)
        for user_id in SEED_USERS:
            context = get_personalization_context(
                user_id, store=seeded_store, now=NOW
            )
            assert context.is_cold_start is False
            assert context.session_count > 0


def test_seeded_declining_user_has_declines_and_no_tenure_preference(tmp_path):
    from training.seed_personalization import seed

    db = tmp_path / "seeded.db"
    with PersonalizationStore(f"sqlite:///{db}") as seeded_store:
        seed(seeded_store, now=NOW)
        context = get_personalization_context(
            "demo-declining", store=seeded_store, now=NOW
        )
        assert context.prior_declines == 3
        assert context.preferred_tenure_band_months is None


def test_seeded_returning_user_prefers_the_accepted_tenure_band(tmp_path):
    from training.seed_personalization import seed

    db = tmp_path / "seeded.db"
    with PersonalizationStore(f"sqlite:///{db}") as seeded_store:
        seed(seeded_store, now=NOW)
        context = get_personalization_context(
            "demo-returning-home", store=seeded_store, now=NOW
        )
        assert context.preferred_tenure_band_months == 120
        assert context.purpose_affinity[LoanPurpose.HOME] == pytest.approx(1.0)


def test_store_connection_is_usable_after_reopen(tmp_path):
    """Data persists across connections; it is a file, not an in-process cache."""
    db = tmp_path / "persist.db"
    with PersonalizationStore(f"sqlite:///{db}") as first:
        _history(first)
    with PersonalizationStore(f"sqlite:///{db}") as second:
        assert second.user_exists("u-1")
        assert isinstance(second.recommendations("u-1")[0], sqlite3.Row)
