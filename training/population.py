"""
Build and inspect the labelled population (P7).

The degeneracy report is a BUILD ARTIFACT produced on every dataset build, not a
one-off check. Phase R found two real defects with it that no per-example invariant
could have caught — a strategy winning 92% of groups, and a product winning 99%.

OFFLINE ONLY.
"""

from collections import Counter
from dataclasses import dataclass
from functools import lru_cache

from app.core.candidates import generate_candidates
from app.core.eligibility import check_eligibility
from app.schemas import Candidate, LoanProduct
from app.schemas.enums import EligibilityStatus
from training.datasets import load_customers, load_portfolios, load_products
from training.labeling import CustomerContext, GradedCandidate, build_context, grade_group

# A learning-to-rank group needs at least two candidates to express an order. Phase R
# found 3.6% of groups had exactly one — useless for training and degenerate for NDCG.
MIN_GROUP_SIZE = 2

# Degeneracy limits. A population breaching any of these is teaching the model a
# shortcut rather than a preference.
MAX_SHARE_LIMIT = 0.60


@dataclass
class LabelledGroup:
    user_id: str
    context: CustomerContext
    graded: list[GradedCandidate]

    @property
    def best(self) -> GradedCandidate:
        return max(self.graded, key=lambda g: (g.grade, g.raw_score))

    @property
    def has_good_option(self) -> bool:
        """A "good option" is a grade >= 2 — the same bar the calibrator targets."""
        return any(g.grade >= 2 for g in self.graded)


def _eligible_products(
    profile, financial, requirement, catalogue: list[LoanProduct]
) -> list[LoanProduct]:
    outcomes = check_eligibility(profile, financial, requirement, catalogue)
    eligible = {
        result.product_id
        for result in outcomes
        if result.status is EligibilityStatus.ELIGIBLE
    }
    return [p for p in catalogue if p.product_id in eligible]


def _feasible(candidates: list[Candidate]) -> list[Candidate]:
    """
    Only FEASIBLE candidates are labelled.

    Phase R finding: labelling infeasible candidates inflated grade 0 to 75% of the
    dataset. In the v2.0 architecture the recommender only ever sees feasible
    candidates, so the labelled set must match what it will actually be scored on.
    """
    return [candidate for candidate in candidates if candidate.feasible]


def build_population(apply_stress: bool = True) -> list[LabelledGroup]:
    """
    Label every synthetic customer against the real catalogue, using the SAME
    candidate generator that runs at serving time.
    """
    catalogue = load_products()
    portfolios = load_portfolios()

    groups: list[LabelledGroup] = []
    for profile, requirement in load_customers():
        portfolio = portfolios.get(profile.user_id)
        context = build_context(profile, portfolio, requirement)
        products = _eligible_products(
            profile, context.financial, requirement, catalogue
        )
        generated = generate_candidates(
            requirement, context.financial, context.portfolio, products
        )
        candidates = _feasible(generated.candidates)
        if len(candidates) < MIN_GROUP_SIZE:
            continue
        groups.append(
            LabelledGroup(
                user_id=profile.user_id,
                context=context,
                graded=grade_group(context, candidates, apply_stress=apply_stress),
            )
        )
    return groups


@lru_cache(maxsize=2)
def cached_population(apply_stress: bool = True) -> tuple[LabelledGroup, ...]:
    """Labelling the whole population is slow; tests reuse one build."""
    return tuple(build_population(apply_stress=apply_stress))


def degeneracy_report(groups: list[LabelledGroup]) -> dict:
    """
    Population-level health. Every share below is a fraction of the relevant total.
    """
    grade_counts = Counter()
    product_wins = Counter()
    tenure_wins = Counter()
    strategy_wins = Counter()

    for group in groups:
        for graded in group.graded:
            grade_counts[graded.grade] += 1
        best = group.best
        product_wins[best.candidate.product_id] += 1
        tenure_wins[best.candidate.tenure_months] += 1
        strategy_wins[best.candidate.strategy.value] += 1

    total_labels = sum(grade_counts.values()) or 1
    total_groups = len(groups) or 1

    def _max_share(counter: Counter, denominator: int) -> float:
        return (max(counter.values()) / denominator) if counter else 0.0

    return {
        "groups": len(groups),
        "labels": sum(grade_counts.values()),
        "grade_counts": dict(sorted(grade_counts.items())),
        "grade_shares": {
            grade: round(count / total_labels, 4)
            for grade, count in sorted(grade_counts.items())
        },
        "max_grade_share": round(_max_share(grade_counts, total_labels), 4),
        "max_product_win_share": round(_max_share(product_wins, total_groups), 4),
        "max_tenure_win_share": round(_max_share(tenure_wins, total_groups), 4),
        "max_strategy_win_share": round(_max_share(strategy_wins, total_groups), 4),
        "no_good_option_customers": sum(
            1 for group in groups if not group.has_good_option
        ),
        "group_size_min": min((len(g.graded) for g in groups), default=0),
        "group_size_max": max((len(g.graded) for g in groups), default=0),
    }


def stress_label_flip_rate() -> dict:
    """
    Share of labels that Stage D changes.

    The 2%-30% band is the point of measuring it: below 2% the simulation is doing
    nothing and should be removed; above 30% it has swamped the other signals. Phase R
    hit exactly 0.00% at one parameterization, which is why this is a real check and
    not a formality.
    """
    with_stress = build_population(apply_stress=True)
    without_stress = build_population(apply_stress=False)

    flipped = 0
    total = 0
    for stressed_group, plain_group in zip(with_stress, without_stress):
        for stressed, plain in zip(stressed_group.graded, plain_group.graded):
            total += 1
            if stressed.grade != plain.grade:
                flipped += 1
    return {
        "flipped": flipped,
        "total": total,
        "rate": round(flipped / total, 6) if total else 0.0,
    }


if __name__ == "__main__":
    import json

    population = build_population()
    print(json.dumps(degeneracy_report(population), indent=2))
    print(json.dumps(stress_label_flip_rate(), indent=2))
