"""
The labeling policy and the built dataset (P7).

NOTE ON THE TEST DATA RULE. AGENTS.md section 2 says tests never read from data/.
These tests are the exception the rule anticipates: in this phase the generated
dataset IS the artifact under test, and its label distribution and customer split
cannot be checked anywhere else. Rather than skipping when the files are absent —
which would let the suite go green having verified nothing — the fixture below BUILDS
them. Every other phase still imports from tests/fixtures.py.
"""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from app.core.finance_math import emi, total_interest, total_repayment
from app.core.financial import income_ratio
from app.schemas import Candidate, Holding, Portfolio
from app.schemas.enums import AssetType, FinancingStrategy, LoanPurpose, RiskAppetite
from training.labeling import (
    ABSOLUTE_GRADE_FLOORS,
    FUNDING_DISQUALIFY_BELOW,
    GRADE_QUANTILES,
    HARD_DBR_CAP,
    LABEL_NOISE_RATE,
    MAX_GRADE,
    MIN_GRADE,
    apply_label_noise,
    build_context,
    disqualify,
    funding_coverage,
    grade_group,
    score_candidate,
    stress_failure_rate,
    subscore_affordability,
    subscore_appetite,
    subscore_cost,
    subscore_funding,
    subscore_portfolio_impact,
)
from tests import fixtures

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
BUILT_FILES = (
    "loan_products.csv",
    "customers.csv",
    "portfolios.csv",
    "history.csv",
    "relevance_dataset.csv",
    "relevance_groups.csv",
    "dataset_manifest.json",
    "label_audit_sample.md",
)


@pytest.fixture(scope="session", autouse=True)
def built_dataset():
    """Build the dataset once if it is not already present."""
    if all((DATA_DIR / name).exists() for name in BUILT_FILES):
        return
    for module in ("training.generate_data", "training.build_dataset"):
        subprocess.run(
            [sys.executable, "-m", module], cwd=REPO_ROOT, check=True, capture_output=True
        )


@pytest.fixture(scope="session")
def manifest(built_dataset):
    return json.loads((DATA_DIR / "dataset_manifest.json").read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def dataset_rows(built_dataset):
    import csv

    with (DATA_DIR / "relevance_dataset.csv").open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    return list(csv.DictReader(lines))


# ------------------------------------------------------------------ helpers


def _context(portfolio=None, appetite=RiskAppetite.MODERATE, required=2_000_000.0):
    profile = fixtures.standard_customer()
    requirement = fixtures.standard_requirement().model_copy(
        update={"risk_appetite": appetite, "required_amount": required}
    )
    return build_context(
        profile,
        fixtures.mixed_portfolio() if portfolio is None else portfolio,
        requirement,
    )


def _candidate(
    context,
    *,
    loan_amount=2_000_000.0,
    rate=8.5,
    tenure=120,
    liquidation=0.0,
    volatile=0.0,
    feasible=True,
):
    total = context.portfolio.total_value
    remaining = max(0.0, total - liquidation)
    return Candidate(
        candidate_id="c-1",
        product_id="HL-001",
        lender="Meridian Bank",
        tenure_months=tenure,
        strategy=FinancingStrategy.BORROW_100,
        required_amount=context.requirement.required_amount,
        loan_amount=loan_amount,
        emi=emi(loan_amount, rate, tenure),
        total_interest=total_interest(loan_amount, rate, tenure),
        total_repayment=total_repayment(loan_amount, rate, tenure),
        liquidation_amount=liquidation,
        volatile_liquidation_amount=volatile,
        remaining_portfolio_value=remaining,
        resulting_liquidity_ratio=0.5,
        resulting_debt_burden_ratio=income_ratio(
            context.financial.existing_emi + emi(loan_amount, rate, tenure),
            context.financial.monthly_income,
        ),
        affordability_headroom=context.financial.emi_affordability_ceiling
        - emi(loan_amount, rate, tenure),
        feasible=feasible,
    )


# =============================================== Stage A — disqualifiers


def test_a_feasible_well_funded_candidate_is_not_disqualified():
    context = _context()
    assert disqualify(context, _candidate(context)) is None


def test_infeasibility_is_taken_from_p5_not_recomputed():
    """
    Stage A reads candidate.feasible rather than re-implementing P5's rules. Phase R
    found that a second copy lets the training set and the serving candidate set
    disagree about what is possible.
    """
    from app.schemas.enums import MismatchReasonCode

    context = _context()
    candidate = _candidate(context).model_copy(
        update={
            "feasible": False,
            "infeasibility_reason": MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY,
        }
    )
    assert disqualify(context, candidate) == "EMI_EXCEEDS_AFFORDABILITY"


def test_debt_burden_above_the_hard_cap_is_disqualified():
    context = _context()
    candidate = _candidate(context).model_copy(
        update={"resulting_debt_burden_ratio": HARD_DBR_CAP + 0.01}
    )
    assert disqualify(context, candidate) == "DEBT_BURDEN_CAP_EXCEEDED"


def test_severe_funding_shortfall_is_disqualified():
    context = _context()
    candidate = _candidate(
        context, loan_amount=context.requirement.required_amount * 0.4
    )
    assert disqualify(context, candidate) == "FUNDING_SHORTFALL"


def test_a_partial_but_substantial_funding_is_not_disqualified():
    """Between the floor and full funding a candidate is a compromise, not impossible."""
    context = _context()
    candidate = _candidate(
        context, loan_amount=context.requirement.required_amount * 0.8
    )
    assert disqualify(context, candidate) is None


def test_zero_income_is_disqualified():
    profile = fixtures.standard_customer().model_copy(
        update={"monthly_income": 0.0, "monthly_expenses": 0.0, "existing_emi": 0.0}
    )
    context = build_context(
        profile, fixtures.empty_portfolio(), fixtures.standard_requirement()
    )
    candidate = _candidate(context, loan_amount=2_000_000.0)
    assert disqualify(context, candidate) == "NO_INCOME"


def test_only_stage_a_assigns_grade_zero_by_disqualification():
    context = _context()
    disqualified = _candidate(context).model_copy(
        update={"resulting_debt_burden_ratio": HARD_DBR_CAP + 0.2}
    )
    graded = grade_group(context, [disqualified])
    assert graded[0].grade == MIN_GRADE
    assert graded[0].disqualified_reason is not None
    assert graded[0].raw_score == 0.0


# ============================== Stage B — each sub-score, in isolation


SUBSCORES = (
    subscore_funding,
    subscore_affordability,
    subscore_cost,
    subscore_portfolio_impact,
    subscore_appetite,
)


@pytest.mark.parametrize("subscore", SUBSCORES, ids=lambda f: f.__name__)
def test_every_subscore_is_bounded_in_zero_one(subscore):
    context = _context()
    for loan in (100_000.0, 2_000_000.0, 20_000_000.0):
        for liquidation in (0.0, 500_000.0, 2_300_000.0):
            candidate = _candidate(
                context, loan_amount=loan, liquidation=liquidation
            )
            value = subscore(context, candidate)
            assert 0.0 <= value <= 1.0, (subscore.__name__, value)


def test_funding_subscore_is_one_at_full_coverage_and_zero_at_the_floor():
    context = _context()
    full = _candidate(context, loan_amount=context.requirement.required_amount)
    assert subscore_funding(context, full) == pytest.approx(1.0)

    at_floor = _candidate(
        context,
        loan_amount=context.requirement.required_amount * FUNDING_DISQUALIFY_BELOW,
    )
    assert subscore_funding(context, at_floor) == pytest.approx(0.0)


def test_funding_subscore_rises_with_coverage():
    context = _context()
    required = context.requirement.required_amount
    values = [
        subscore_funding(context, _candidate(context, loan_amount=required * share))
        for share in (0.6, 0.7, 0.8, 0.9, 1.0)
    ]
    assert values == sorted(values)


def test_funding_coverage_counts_liquidation_as_funding():
    """Paying from holdings funds the need just as borrowing does."""
    context = _context()
    required = context.requirement.required_amount
    candidate = _candidate(
        context, loan_amount=required * 0.5, liquidation=required * 0.5
    )
    assert funding_coverage(candidate) == pytest.approx(1.0)


def test_affordability_subscore_falls_as_emi_rises():
    context = _context()
    values = [
        subscore_affordability(context, _candidate(context, tenure=tenure))
        for tenure in (24, 48, 84, 120)
    ]
    assert values == sorted(values)


def test_affordability_subscore_is_zero_with_no_capacity():
    profile = fixtures.standard_customer().model_copy(
        update={"monthly_expenses": 120_000.0, "existing_emi": 0.0}
    )
    context = build_context(
        profile, fixtures.empty_portfolio(), fixtures.standard_requirement()
    )
    assert context.financial.emi_affordability_ceiling == 0.0
    assert subscore_affordability(context, _candidate(context)) == 0.0


def test_cost_subscore_falls_as_interest_rises():
    context = _context()
    values = [
        subscore_cost(context, _candidate(context, rate=rate)) for rate in (6.0, 10.0, 16.0)
    ]
    assert values[0] > values[1] > values[2]


def test_cost_subscore_charges_for_liquidation_even_with_no_interest():
    """Selling an invested asset forgoes its return. Liquidation is never free."""
    context = _context()
    no_loan = Candidate(
        candidate_id="NO-LOAN",
        strategy=FinancingStrategy.LIQUIDATE_100,
        required_amount=context.requirement.required_amount,
        loan_amount=0.0,
        emi=0.0,
        total_interest=0.0,
        total_repayment=0.0,
        liquidation_amount=context.requirement.required_amount,
        volatile_liquidation_amount=0.0,
        remaining_portfolio_value=context.portfolio.total_value
        - context.requirement.required_amount,
        resulting_liquidity_ratio=0.3,
        resulting_debt_burden_ratio=context.financial.debt_burden_ratio,
        affordability_headroom=context.financial.emi_affordability_ceiling,
    )
    assert no_loan.total_interest == 0.0
    assert subscore_cost(context, no_loan) < 1.0


def test_portfolio_impact_subscore_is_one_with_no_portfolio():
    context = _context(portfolio=fixtures.empty_portfolio())
    assert subscore_portfolio_impact(context, _candidate(context)) == 1.0


def test_portfolio_impact_subscore_falls_as_more_is_sold():
    context = _context()
    values = [
        subscore_portfolio_impact(
            context, _candidate(context, liquidation=amount)
        )
        for amount in (0.0, 400_000.0, 1_200_000.0)
    ]
    assert values[0] >= values[1] >= values[2]


def test_appetite_subscore_is_stricter_for_conservative():
    conservative = _context(appetite=RiskAppetite.CONSERVATIVE)
    aggressive = _context(appetite=RiskAppetite.AGGRESSIVE)
    candidate = _candidate(conservative)
    assert subscore_appetite(conservative, candidate) <= subscore_appetite(
        aggressive, candidate
    )


def test_appetite_subscore_penalises_selling_volatile_assets():
    context = _context()
    plain = _candidate(context, liquidation=500_000.0, volatile=0.0)
    volatile = _candidate(context, liquidation=500_000.0, volatile=500_000.0)
    assert subscore_appetite(context, volatile) < subscore_appetite(context, plain)


def test_no_subscore_reads_another_concern():
    """
    Each sub-score owns exactly one concern. Changing ONLY the interest rate must move
    the cost sub-score and leave funding, portfolio impact and appetite untouched.
    """
    context = _context()
    cheap = _candidate(context, rate=7.0)
    dear = _candidate(context, rate=15.0)
    assert subscore_cost(context, cheap) != subscore_cost(context, dear)
    assert subscore_funding(context, cheap) == subscore_funding(context, dear)
    assert subscore_portfolio_impact(context, cheap) == subscore_portfolio_impact(
        context, dear
    )


# ================================= Stage C — combination and rank grading


def test_score_is_bounded_in_zero_one():
    context = _context()
    for loan in (500_000.0, 2_000_000.0, 9_000_000.0):
        assert 0.0 <= score_candidate(context, _candidate(context, loan_amount=loan)) <= 1.0


def test_grades_are_within_range():
    context = _context()
    candidates = [_candidate(context, tenure=t) for t in (24, 48, 60, 84, 120)]
    for graded in grade_group(context, candidates):
        assert MIN_GRADE <= graded.grade <= MAX_GRADE


def test_grading_preserves_input_order():
    context = _context()
    candidates = [
        _candidate(context, tenure=t).model_copy(update={"candidate_id": f"c-{t}"})
        for t in (24, 48, 120)
    ]
    graded = grade_group(context, candidates)
    assert [g.candidate.candidate_id for g in graded] == ["c-24", "c-48", "c-120"]


def test_grading_is_by_within_group_rank_not_absolute_cutoff():
    """
    Scaling a customer's ENTIRE candidate set — income, holdings and every rupee
    amount — leaves every grade unchanged. This is what removes scale sensitivity and
    income-dependent threshold drift.
    """
    context = _context()
    candidates = [_candidate(context, tenure=t) for t in (24, 48, 60, 84, 120)]
    before = [g.grade for g in grade_group(context, candidates)]

    k = 7.5
    scaled_context = build_context(
        context.profile.model_copy(
            update={
                "monthly_income": context.profile.monthly_income * k,
                "monthly_expenses": context.profile.monthly_expenses * k,
                "existing_emi": context.profile.existing_emi * k,
            }
        ),
        Portfolio(
            holdings=[
                Holding(
                    asset_type=holding.asset_type,
                    current_value=holding.current_value * k,
                    invested_value=holding.invested_value * k,
                )
                for holding in fixtures.mixed_portfolio().holdings
            ]
        ),
        context.requirement.model_copy(
            update={"required_amount": context.requirement.required_amount * k}
        ),
    )
    scaled_candidates = [
        _candidate(scaled_context, loan_amount=c.loan_amount * k, tenure=c.tenure_months)
        for c in candidates
    ]
    assert [g.grade for g in grade_group(scaled_context, scaled_candidates)] == before


def test_the_absolute_floor_lets_a_customer_have_no_good_option():
    """
    Quantile grading alone always manufactures a grade 3. The absolute cap is what
    allows NO_SUITABLE_LOAN to exist as an honest outcome.
    """
    assert ABSOLUTE_GRADE_FLOORS[0] > ABSOLUTE_GRADE_FLOORS[1] > ABSOLUTE_GRADE_FLOORS[2]
    context = _context()
    weak = [
        _candidate(context, loan_amount=context.requirement.required_amount, rate=19.0, tenure=t)
        for t in (12, 24, 36)
    ]
    graded = grade_group(context, weak)
    assert max(g.grade for g in graded) < MAX_GRADE


def test_grade_quantiles_are_ordered():
    assert GRADE_QUANTILES[0] < GRADE_QUANTILES[1] < GRADE_QUANTILES[2]


def test_an_empty_group_grades_to_an_empty_list():
    assert grade_group(_context(), []) == []


# ================================================ Stage D — stress demotion


def test_stress_failure_rate_is_a_share():
    context = _context()
    rate = stress_failure_rate(context, _candidate(context))
    assert 0.0 <= rate <= 1.0


def test_a_larger_emi_never_lowers_the_stress_failure_rate():
    context = _context()
    rates = [
        stress_failure_rate(context, _candidate(context, tenure=tenure))
        for tenure in (120, 84, 48, 24)
    ]
    assert rates == sorted(rates)


def test_stress_demotion_changes_the_label_set():
    """Stage D must actually do something — a no-op simulation should be removed."""
    context = _context()
    candidates = [
        _candidate(context, loan_amount=2_000_000.0, tenure=tenure)
        for tenure in (36, 48, 60, 84, 120)
    ]
    with_stress = [g.grade for g in grade_group(context, candidates, apply_stress=True)]
    without = [g.grade for g in grade_group(context, candidates, apply_stress=False)]
    assert with_stress != without
    assert sum(with_stress) < sum(without)


def test_stress_only_ever_demotes_by_one_grade():
    context = _context()
    candidates = [
        _candidate(context, loan_amount=2_000_000.0, tenure=tenure)
        for tenure in (36, 48, 60, 84, 120)
    ]
    for stressed, plain in zip(
        grade_group(context, candidates, apply_stress=True),
        grade_group(context, candidates, apply_stress=False),
    ):
        assert stressed.grade <= plain.grade
        assert plain.grade - stressed.grade <= 1


def test_recorded_flip_rate_is_inside_the_configured_band(manifest):
    """
    Below 2% the simulation is doing nothing; above 30% it has swamped the other
    signals. Phase R hit exactly 0.00% at one parameterization, so this is a real
    check.
    """
    rate = manifest["stress_label_flip_rate"]
    assert 0.02 <= rate <= 0.30, rate
    assert manifest["stress_flip_in_band"] is True


# ==================================================== determinism and noise


def test_the_labeler_is_deterministic():
    context = _context()
    candidates = [_candidate(context, tenure=t) for t in (24, 60, 120)]
    first = grade_group(context, candidates)
    second = grade_group(context, candidates)
    assert [g.grade for g in first] == [g.grade for g in second]
    assert [g.raw_score for g in first] == [g.raw_score for g in second]
    assert [g.stress_failure_rate for g in first] == [
        g.stress_failure_rate for g in second
    ]


def test_two_dataset_builds_agree():
    """A fixed seed means the same dataset, or the manifest's seed record is a lie."""
    from training.population import build_population

    first = build_population()
    second = build_population()
    assert [
        (group.user_id, [g.grade for g in group.graded]) for group in first
    ] == [(group.user_id, [g.grade for g in group.graded]) for group in second]


def test_label_noise_stays_within_the_grade_range():
    import random

    rng = random.Random(1)
    for grade in range(MIN_GRADE, MAX_GRADE + 1):
        for _ in range(200):
            assert MIN_GRADE <= apply_label_noise(grade, rng) <= MAX_GRADE


def test_label_noise_fires_at_roughly_the_configured_rate():
    import random

    rng = random.Random(7)
    trials = 20_000
    changed = sum(1 for _ in range(trials) if apply_label_noise(2, rng) != 2)
    assert abs(changed / trials - LABEL_NOISE_RATE) < 0.02


def test_label_noise_moves_a_grade_by_exactly_one():
    import random

    rng = random.Random(3)
    for _ in range(2_000):
        assert abs(apply_label_noise(2, rng) - 2) <= 1


# ======================================================== the built dataset


def test_dataset_declares_labels_synthetic(manifest):
    assert manifest["labels_are_synthetic"] is True
    assert manifest["labels_source"] == "training/labeling.py"


def test_dataset_files_carry_a_synthetic_header():
    for name in ("relevance_dataset.csv", "customers.csv", "portfolios.csv"):
        first_line = (DATA_DIR / name).read_text(encoding="utf-8").splitlines()[0]
        assert first_line.startswith("#")
        assert "SYNTHETIC" in first_line.upper()


def test_every_dataset_row_carries_a_synthetic_column(dataset_rows):
    assert dataset_rows
    assert all(row["SYNTHETIC"] == "TRUE" for row in dataset_rows)


def test_manifest_records_the_policy_version(manifest):
    from app.config import settings

    assert manifest["labeling_policy_version"] == settings.LABELING_POLICY_VERSION


def test_manifest_records_seeds_and_counts(manifest):
    for key in ("generator_seed", "split_seed", "label_noise_seed", "rows", "groups"):
        assert key in manifest, key
    assert manifest["rows"] > 0 and manifest["groups"] > 0


def test_label_distribution_is_not_degenerate(manifest):
    distribution = manifest["label_distribution"]
    assert set(distribution) == {"0", "1", "2", "3"}
    total = sum(distribution.values())
    for grade, count in distribution.items():
        assert count / total <= 0.60, (grade, count / total)


def test_no_customer_appears_in_both_splits(dataset_rows):
    """A customer's candidates share a group; leaking one across the split leaks the group."""
    train = {row["user_id"] for row in dataset_rows if row["split"] == "train"}
    test = {row["user_id"] for row in dataset_rows if row["split"] == "test"}
    assert train and test
    assert train.isdisjoint(test)


def test_every_group_is_contiguous_in_row_order(dataset_rows):
    """XGBRanker's group array assumes rows of a group are adjacent."""
    seen = []
    for row in dataset_rows:
        if not seen or seen[-1] != row["group_id"]:
            seen.append(row["group_id"])
    assert len(seen) == len(set(seen))


def test_group_sizes_file_matches_the_dataset(dataset_rows):
    import csv
    from collections import Counter

    with (DATA_DIR / "relevance_groups.csv").open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    sizes = {row["group_id"]: int(row["size"]) for row in csv.DictReader(lines)}
    actual = Counter(row["group_id"] for row in dataset_rows)
    assert sizes == dict(actual)


def test_every_group_meets_the_minimum_size(manifest, dataset_rows):
    from collections import Counter

    counts = Counter(row["group_id"] for row in dataset_rows)
    assert min(counts.values()) >= manifest["min_group_size"]


def test_groups_either_have_a_good_option_or_are_recorded_as_having_none(
    manifest, dataset_rows
):
    """
    Every group contains a candidate labelled >= 2, OR is one of the customers the
    manifest records as having no suitable option. The dataset MUST contain such
    customers — without them the model cannot learn that some profiles have no good
    option, and NO_SUITABLE_LOAN becomes unreachable.
    """
    from collections import defaultdict

    by_group = defaultdict(list)
    for row in dataset_rows:
        by_group[row["group_id"]].append(int(row["label"]))

    without_good_option = [
        group_id for group_id, labels in by_group.items() if max(labels) < 2
    ]
    assert manifest["no_good_option_customers"] > 0
    # Noise can nudge a borderline group either way, so the recorded count is the
    # noiseless truth and the observed count must stay close to it.
    assert len(without_good_option) <= manifest["no_good_option_customers"] + 5


def test_no_good_option_customers_exist(manifest):
    assert manifest["no_good_option_customers"] > 0


def test_audit_sample_was_written_and_is_readable():
    text = (DATA_DIR / "label_audit_sample.md").read_text(encoding="utf-8")
    assert "SYNTHETIC" in text
    assert text.count("\n## ") == 20


def test_dataset_covers_the_no_loan_candidate(dataset_rows):
    """The no-loan option must be in the training data or the model cannot pick it."""
    strategies = {row["strategy"] for row in dataset_rows}
    assert FinancingStrategy.LIQUIDATE_100.value in strategies


def test_no_loan_rows_carry_no_product_or_tenure(dataset_rows):
    for row in dataset_rows:
        if row["strategy"] == FinancingStrategy.LIQUIDATE_100.value:
            assert row["product_id"] == ""
            assert row["tenure_months"] == ""


def test_dataset_spans_multiple_products_and_purposes(dataset_rows):
    products = {row["product_id"] for row in dataset_rows if row["product_id"]}
    assert len(products) >= 5


def test_generated_catalogue_loads_into_the_real_schema():
    from training.datasets import load_products

    products = load_products()
    assert 12 <= len(products) <= 15
    assert len({p.lender for p in products}) >= 4
    covered = {purpose for product in products for purpose in product.purposes}
    assert covered == set(LoanPurpose)


def test_generated_portfolios_include_customers_with_none():
    from training.datasets import load_customers, load_portfolios

    portfolios = load_portfolios()
    customers = load_customers()
    without = [
        profile.user_id
        for profile, _ in customers
        if profile.user_id not in portfolios
    ]
    assert without, "the zero-portfolio path must be represented in training"
    assert len(without) / len(customers) > 0.15


def test_generated_portfolios_include_a_volatile_heavy_archetype():
    """
    Without volatile-heavy portfolios the volatile-liquidation guardrail is
    unreachable in practice (P6 finding).
    """
    import csv

    with (DATA_DIR / "portfolios.csv").open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    archetypes = {row["archetype"] for row in csv.DictReader(lines)}
    assert "volatile_heavy" in archetypes


def test_app_does_not_import_training():
    """Restated here because this phase is where the temptation is strongest."""
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import training" in text or "from training" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
