"""
SPIKE 1 — synthetic population, degeneracy report, stress label-flip rate,
and the human audit sample.

SPIKE ONLY.
"""

from __future__ import annotations

import random
from collections import Counter

from domain import AGGRESSIVE, CONSERVATIVE, MODERATE, Customer, Product, generate_candidates
from policy import GradedCandidate, disqualify, grade_group

PRODUCTS = [
    Product("HOME-A", 8.25, 300_000, 10_000_000, 60, 240),
    Product("HOME-B", 8.90, 300_000, 8_000_000, 60, 180),
    Product("PERS-A", 11.50, 50_000, 2_000_000, 12, 60),
    Product("PERS-B", 13.75, 50_000, 1_500_000, 12, 48),
    Product("VEH-A", 9.40, 100_000, 3_000_000, 12, 84),
    Product("BUS-A", 12.25, 200_000, 5_000_000, 24, 84),
]
TENURES = [12, 24, 36, 48, 60, 84, 120]


def build_population(n_customers: int = 300, seed: int = 42):
    """Return [(customer, [GradedCandidate, ...]), ...]."""
    rng = random.Random(seed)
    groups = []
    for _ in range(n_customers):
        income = rng.choice(
            [
                rng.uniform(25_000, 60_000),
                rng.uniform(60_000, 150_000),
                rng.uniform(150_000, 600_000),
            ]
        )
        expenses = income * rng.uniform(0.25, 0.70)
        existing = income * rng.uniform(0.0, 0.22)
        has_portfolio = rng.random() < 0.65          # ~35% have no portfolio at all
        if has_portfolio:
            liquid = income * rng.uniform(0.0, 30.0)
            volatile = income * rng.uniform(0.0, 30.0)
        else:
            liquid = volatile = 0.0
        customer = Customer(
            monthly_income=income,
            monthly_expenses=expenses,
            existing_emi=existing,
            credit_score=rng.randint(520, 880),
            age=rng.randint(23, 60),
            risk_appetite=rng.choice([CONSERVATIVE, MODERATE, AGGRESSIVE]),
            portfolio_value=liquid + volatile,
            liquid_value=liquid,
            volatile_value=volatile,
        )
        required = income * rng.uniform(6.0, 40.0)
        candidates = generate_candidates(customer, PRODUCTS, required, TENURES)
        # FINDING (spike): infeasible candidates must be filtered BEFORE labeling.
        # In the v2.0 architecture the recommender only ever sees feasible
        # candidates (Phase 5 marks the rest), so labelling them inflates grade 0
        # to ~75% of the dataset and teaches the model nothing.
        candidates = [c for c in candidates if disqualify(customer, c) is None]
        if not candidates:
            continue
        groups.append((customer, grade_group(customer, candidates)))
    return groups


def degeneracy_report(groups) -> dict:
    grade_counts = Counter()
    product_wins = Counter()
    tenure_wins = Counter()
    strategy_wins = Counter()
    no_good_option = 0
    graded_groups = 0

    for _customer, graded in groups:
        for g in graded:
            grade_counts[g.grade] += 1
        best = max(graded, key=lambda g: (g.grade, g.raw_score))
        if best.grade < 2:
            no_good_option += 1
            continue
        graded_groups += 1
        product_wins[best.candidate.product_id] += 1
        tenure_wins[best.candidate.tenure_months] += 1
        strategy_wins[best.candidate.strategy] += 1

    total_labels = sum(grade_counts.values()) or 1
    denom = graded_groups or 1
    return {
        "customers": len(groups),
        "labels": total_labels,
        "grade_counts": dict(sorted(grade_counts.items())),
        "grade_shares": {
            k: round(v / total_labels, 4) for k, v in sorted(grade_counts.items())
        },
        "max_grade_share": max(grade_counts.values()) / total_labels,
        "max_product_win_share": (max(product_wins.values()) / denom) if product_wins else 0.0,
        "max_tenure_win_share": (max(tenure_wins.values()) / denom) if tenure_wins else 0.0,
        "max_strategy_win_share": (max(strategy_wins.values()) / denom) if strategy_wins else 0.0,
        "product_wins": dict(product_wins),
        "strategy_wins": dict(strategy_wins),
        "no_good_option_customers": no_good_option,
        "no_good_option_share": round(no_good_option / (len(groups) or 1), 4),
    }


def stress_flip_rate(n_customers: int = 300, seed: int = 42) -> dict:
    """
    Share of labels that change when Stage D is switched on.

    Target band 2%-30%: below 2% the simulation does nothing, above 30% it has
    swamped the other signals.
    """
    rng_groups = build_population(n_customers=n_customers, seed=seed)
    flips = 0
    total = 0
    demoted = 0
    for customer, graded_with in rng_groups:
        candidates = [g.candidate for g in graded_with]
        graded_without = grade_group(customer, candidates, apply_stress=False)
        for a, b in zip(graded_with, graded_without):
            total += 1
            if a.grade != b.grade:
                flips += 1
            if a.demoted:
                demoted += 1
    return {
        "labels": total,
        "flipped": flips,
        "flip_rate": round(flips / (total or 1), 4),
        "demoted": demoted,
    }


def audit_sample(groups, n: int = 20, seed: int = 7) -> str:
    """Twenty customers rendered in plain language for a human to read."""
    rng = random.Random(seed)
    chosen = rng.sample(groups, min(n, len(groups)))
    lines = [
        "# Label audit sample (SPIKE)",
        "",
        "Twenty synthetic customers with their best- and worst-labelled candidates.",
        "Invariants catch logical flaws; this file is for catching labels that are",
        "self-consistent but that no human would call sensible.",
        "",
    ]
    for idx, (customer, graded) in enumerate(chosen, 1):
        best = max(graded, key=lambda g: (g.grade, g.raw_score))
        worst = min(graded, key=lambda g: (g.grade, g.raw_score))
        lines += [
            f"## Customer {idx}",
            f"- income Rs {customer.monthly_income:,.0f}/mo, expenses Rs {customer.monthly_expenses:,.0f}, "
            f"existing EMI Rs {customer.existing_emi:,.0f}, disposable Rs {customer.disposable:,.0f}",
            f"- appetite {customer.risk_appetite}, credit score {customer.credit_score}, "
            f"portfolio Rs {customer.portfolio_value:,.0f} "
            f"(liquid Rs {customer.liquid_value:,.0f} / volatile Rs {customer.volatile_value:,.0f})",
            f"- needs Rs {best.candidate.required_amount:,.0f}; {len(graded)} candidates generated",
            "",
            f"  BEST  grade {best.grade} | {best.candidate.product_id} "
            f"Rs {best.candidate.loan_amount:,.0f} borrowed + Rs {best.candidate.liquidation_amount:,.0f} liquidated, "
            f"{best.candidate.tenure_months}m, EMI Rs {best.candidate.emi:,.0f}, "
            f"interest Rs {best.candidate.total_interest:,.0f}, raw {best.raw_score:.3f}"
            + (f", DEMOTED (stress {best.stress_failure_rate:.0%})" if best.demoted else ""),
            f"  WORST grade {worst.grade} | {worst.candidate.product_id} "
            f"Rs {worst.candidate.loan_amount:,.0f} borrowed + Rs {worst.candidate.liquidation_amount:,.0f} liquidated, "
            f"{worst.candidate.tenure_months}m, EMI Rs {worst.candidate.emi:,.0f}, "
            f"raw {worst.raw_score:.3f}"
            + (f", disqualified: {worst.disqualified_reason}" if worst.disqualified_reason else ""),
            "",
        ]
    return "\n".join(lines)


if __name__ == "__main__":
    import json
    import pathlib

    groups = build_population(n_customers=300, seed=42)
    report = degeneracy_report(groups)
    flip = stress_flip_rate(n_customers=300, seed=42)

    print("=== DEGENERACY REPORT ===")
    print(json.dumps(report, indent=2))
    print()
    print("=== STRESS LABEL-FLIP RATE ===")
    print(json.dumps(flip, indent=2))
    band_ok = 0.02 <= flip["flip_rate"] <= 0.30
    print(f"\nflip rate {flip['flip_rate']:.2%} in target band 2%-30%: {band_ok}")

    pathlib.Path("label_audit_sample.md").write_text(audit_sample(groups), encoding="utf-8")
    print("wrote label_audit_sample.md")
