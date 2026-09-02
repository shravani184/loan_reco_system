"""
Build the relevance dataset for the primary recommender (P7).

Writes:
    data/relevance_dataset.csv   one row per (customer, candidate)
    data/relevance_groups.csv    group sizes, in row order, as XGBRanker requires
    data/dataset_manifest.json   seed, counts, label distribution, flip rate, versions
    data/label_audit_sample.md   twenty customers in plain language, for a human

THE LABELS ARE SYNTHETIC. They are produced by training/labeling.py, not observed from
customers. A model trained on them partially reproduces that policy, and reported
ranking metrics measure agreement with it — not real recommendation quality
(CONTEXT.md section 11, AGENTS.md section 6 rule 9).

OFFLINE ONLY. Run:

    python -m training.build_dataset
"""

import csv
import json
import random
from collections import Counter
from pathlib import Path

from app.config import settings
from training.labeling import (
    LABEL_NOISE_RATE,
    LABEL_NOISE_SEED,
    apply_label_noise,
)
from training.population import (
    MIN_GROUP_SIZE,
    LabelledGroup,
    build_population,
    degeneracy_report,
    stress_label_flip_rate,
)

DATA_DIR = Path("data")
SPLIT_SEED = 20260904
TEST_SHARE = 0.20
AUDIT_SAMPLE_SIZE = 20

SYNTHETIC_HEADER = (
    "# SYNTHETIC RELEVANCE LABELS — produced by training/labeling.py "
    "(LABELING_POLICY_VERSION {version}). These are not observed customer choices. "
    "A model trained on them partially reproduces that policy."
)

# Every field needed to rebuild the Candidate in P8, plus the label and the group key.
DATASET_COLUMNS = [
    "group_id",
    "user_id",
    "split",
    "label",
    "raw_score",
    "stress_failure_rate",
    "demoted",
    "noised",
    "candidate_id",
    "product_id",
    "lender",
    "tenure_months",
    "strategy",
    "required_amount",
    "loan_amount",
    "emi",
    "total_interest",
    "total_repayment",
    "liquidation_amount",
    "volatile_liquidation_amount",
    "remaining_portfolio_value",
    "resulting_liquidity_ratio",
    "resulting_debt_burden_ratio",
    "affordability_headroom",
    "SYNTHETIC",
]


def _split_assignment(groups: list[LabelledGroup]) -> dict[str, str]:
    """
    SPLIT BY CUSTOMER, NEVER BY ROW. A customer's candidates must not appear in both
    train and test: they share a group, and leaking one into the other would let the
    ranker see part of a group it is being evaluated on.
    """
    rng = random.Random(SPLIT_SEED)
    user_ids = sorted(group.user_id for group in groups)
    rng.shuffle(user_ids)
    cut = int(len(user_ids) * (1.0 - TEST_SHARE))
    return {user_id: ("train" if i < cut else "test") for i, user_id in enumerate(user_ids)}


def _rows(groups: list[LabelledGroup], splits: dict[str, str]) -> list[list]:
    noise_rng = random.Random(LABEL_NOISE_SEED)
    rows = []
    for group_id, group in enumerate(groups):
        for graded in group.graded:
            candidate = graded.candidate
            clean = graded.grade
            noisy = apply_label_noise(clean, noise_rng)
            rows.append(
                [
                    group_id,
                    group.user_id,
                    splits[group.user_id],
                    noisy,
                    round(graded.raw_score, 6),
                    round(graded.stress_failure_rate, 6),
                    graded.demoted,
                    noisy != clean,
                    candidate.candidate_id,
                    candidate.product_id or "",
                    candidate.lender or "",
                    candidate.tenure_months if candidate.tenure_months else "",
                    candidate.strategy.value,
                    round(candidate.required_amount, 2),
                    round(candidate.loan_amount, 2),
                    round(candidate.emi, 2),
                    round(candidate.total_interest, 2),
                    round(candidate.total_repayment, 2),
                    round(candidate.liquidation_amount, 2),
                    round(candidate.volatile_liquidation_amount, 2),
                    round(candidate.remaining_portfolio_value, 2),
                    round(candidate.resulting_liquidity_ratio, 6),
                    round(candidate.resulting_debt_burden_ratio, 6),
                    round(candidate.affordability_headroom, 2),
                    "TRUE",
                ]
            )
    return rows


def _write_audit_sample(groups: list[LabelledGroup], path: Path) -> None:
    """
    Twenty customers, top and bottom candidates, in plain language.

    Invariants catch logical flaws. Only a person catches "these labels are
    self-consistent but no human would call that the best option" (CONTEXT.md 17.1,
    decision 5). This is regenerated on every dataset build and is meant to be READ.
    """
    rng = random.Random(SPLIT_SEED)
    sample = rng.sample(groups, min(AUDIT_SAMPLE_SIZE, len(groups)))

    def describe(graded) -> str:
        candidate = graded.candidate
        if candidate.product_id is None:
            action = (
                f"pay ₹{candidate.liquidation_amount:,.0f} from holdings and borrow "
                "nothing"
            )
        else:
            action = (
                f"borrow ₹{candidate.loan_amount:,.0f} from {candidate.lender} "
                f"({candidate.product_id}) over {candidate.tenure_months} months at "
                f"₹{candidate.emi:,.0f}/month"
            )
            if candidate.liquidation_amount > 0:
                action += f", selling ₹{candidate.liquidation_amount:,.0f} of holdings"
        return (
            f"grade {graded.grade} | score {graded.raw_score:.3f} | "
            f"stress-fail {graded.stress_failure_rate:.0%}"
            f"{' | DEMOTED' if graded.demoted else ''}\n      {action}\n"
            f"      total interest ₹{candidate.total_interest:,.0f}, "
            f"portfolio left ₹{candidate.remaining_portfolio_value:,.0f}"
        )

    lines = [
        "# Label audit sample",
        "",
        "**SYNTHETIC.** These customers do not exist and these labels are produced by",
        "`training/labeling.py`, not observed from anyone. Regenerated on every dataset",
        "build.",
        "",
        "Read this before trusting the dataset. The invariant suite proves the labels are",
        "*self-consistent*; only a person can notice that a self-consistent label is one",
        "no human would agree with.",
        "",
        f"Policy version: `{settings.LABELING_POLICY_VERSION}`",
        "",
        "---",
        "",
    ]

    for index, group in enumerate(sample, start=1):
        ranked = sorted(group.graded, key=lambda g: (-g.grade, -g.raw_score))
        context = group.context
        financial = context.financial
        portfolio = context.portfolio
        requirement = context.requirement
        lines += [
            f"## {index}. `{group.user_id}`",
            "",
            f"- income ₹{financial.monthly_income:,.0f}/month, "
            f"expenses ₹{financial.monthly_expenses:,.0f}, "
            f"existing EMI ₹{financial.existing_emi:,.0f}",
            f"- disposable ₹{financial.disposable_income:,.0f}, "
            f"EMI ceiling ₹{financial.emi_affordability_ceiling:,.0f}, "
            f"health {financial.financial_health.value}",
            f"- portfolio ₹{portfolio.total_value:,.0f} "
            f"({'none' if not portfolio.has_portfolio else portfolio.portfolio_risk.value})",
            f"- wants ₹{requirement.required_amount:,.0f} for "
            f"{requirement.purpose.value} over {requirement.preferred_tenure_months} "
            f"months, appetite {requirement.risk_appetite.value}",
            f"- {len(group.graded)} candidates; "
            f"{'HAS a good option' if group.has_good_option else 'NO good option'}",
            "",
            f"  BEST   {describe(ranked[0])}",
            "",
            f"  WORST  {describe(ranked[-1])}",
            "",
        ]

    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    groups = build_population()
    splits = _split_assignment(groups)
    rows = _rows(groups, splits)
    report = degeneracy_report(groups)
    flip = stress_label_flip_rate()

    dataset_path = DATA_DIR / "relevance_dataset.csv"
    with dataset_path.open("w", newline="", encoding="utf-8") as handle:
        handle.write(
            SYNTHETIC_HEADER.format(version=settings.LABELING_POLICY_VERSION) + "\n"
        )
        writer = csv.writer(handle)
        writer.writerow(DATASET_COLUMNS)
        writer.writerows(rows)

    # Group sizes in row order — this is the array XGBRanker's `group` parameter needs.
    groups_path = DATA_DIR / "relevance_groups.csv"
    with groups_path.open("w", newline="", encoding="utf-8") as handle:
        handle.write("# SYNTHETIC. Group sizes in dataset row order, for XGBRanker.\n")
        writer = csv.writer(handle)
        writer.writerow(["group_id", "user_id", "split", "size"])
        writer.writerows(
            [group_id, group.user_id, splits[group.user_id], len(group.graded)]
            for group_id, group in enumerate(groups)
        )

    label_counts = Counter(row[DATASET_COLUMNS.index("label")] for row in rows)
    split_counts = Counter(row[DATASET_COLUMNS.index("split")] for row in rows)
    split_groups = Counter(splits.values())

    manifest = {
        "labels_are_synthetic": True,
        "labels_source": "training/labeling.py",
        "note": (
            "Relevance labels are produced by a documented synthetic policy, not "
            "observed from customers. Ranking metrics measure agreement with that "
            "policy, not real recommendation quality."
        ),
        "labeling_policy_version": settings.LABELING_POLICY_VERSION,
        "config_version": settings.CONFIG_VERSION,
        "generator_seed": 20260902,
        "split_seed": SPLIT_SEED,
        "label_noise_seed": LABEL_NOISE_SEED,
        "label_noise_rate": LABEL_NOISE_RATE,
        "min_group_size": MIN_GROUP_SIZE,
        "rows": len(rows),
        "groups": len(groups),
        "label_distribution": {str(k): v for k, v in sorted(label_counts.items())},
        "split_rows": dict(split_counts),
        "split_groups": dict(split_groups),
        "stress_label_flip_rate": flip["rate"],
        "stress_label_flips": flip["flipped"],
        "stress_flip_band": [0.02, 0.30],
        "stress_flip_in_band": 0.02 <= flip["rate"] <= 0.30,
        "degeneracy_report": report,
        "no_good_option_customers": report["no_good_option_customers"],
    }
    (DATA_DIR / "dataset_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )

    _write_audit_sample(groups, DATA_DIR / "label_audit_sample.md")

    print(f"relevance_dataset.csv  {len(rows)} rows, {len(groups)} groups")
    print(f"label distribution     {dict(sorted(label_counts.items()))}")
    print(f"split rows             {dict(split_counts)}")
    print(f"split groups           {dict(split_groups)}")
    print(
        f"stress flip rate       {flip['rate']:.4%} "
        f"({'IN BAND' if manifest['stress_flip_in_band'] else 'OUT OF BAND'})"
    )
    print(f"no-good-option groups  {report['no_good_option_customers']}")
    print("LABELS ARE SYNTHETIC — produced by training/labeling.py")


if __name__ == "__main__":
    main()
