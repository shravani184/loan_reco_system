"""
Candidate Generation Engine — deterministic enumeration + financial math, no ML.

Builds the option space the recommender will later score. It expresses NO opinion
about which option is better: there is no utility function here, no weighting, no
sorting by quality, and no preference of any kind. Adding one would move the decision
back out of the model and undo the v2.0 redesign (CONTEXT.md section 4).

This is bounded brute-force enumeration, a few hundred candidates per request after
pruning — not a solver. There is no scipy, no optimizer, and none is needed.

Order of operations, fixed:
    enumerate -> mark feasibility -> dominance-prune -> cap

Every grid value, cap and haircut comes from app/config.py.
"""

from app.config import settings
from app.core.finance_math import emi, total_interest, total_repayment
from app.core.financial import income_ratio
from app.schemas import (
    Candidate,
    CandidateGenerationCounts,
    CandidateGenerationResult,
    FinancialMetrics,
    LoanProduct,
    LoanRequirement,
    PortfolioMetrics,
)
from app.schemas.enums import AssetType, FinancingStrategy, MismatchReasonCode

NO_LOAN_CANDIDATE_ID = "NO-LOAN"

# Comparison precision for dominance. Money is float rupees, so raw == on a computed
# EMI would make two arithmetically identical candidates look different and defeat
# pruning. Paise is finer than any decision this system makes.
_DOMINANCE_PRECISION = 2


class _Liquidation:
    """
    The result of raising `net_needed` rupees from the portfolio.

    Holdings are consumed in ASCENDING HAIRCUT ORDER — cheapest to sell first — which
    naturally spends cash and deposits before stocks and crypto. That ordering is a
    cost fact, not a preference about the customer's goals.
    """

    def __init__(
        self,
        funded: bool,
        gross_sold: float,
        volatile_gross_sold: float,
        remaining_by_type: dict[AssetType, float],
    ) -> None:
        self.funded = funded
        self.gross_sold = gross_sold
        self.volatile_gross_sold = volatile_gross_sold
        self.remaining_by_type = remaining_by_type

    @property
    def remaining_total(self) -> float:
        return sum(self.remaining_by_type.values())

    @property
    def remaining_liquid(self) -> float:
        return sum(
            self.remaining_by_type[asset_type]
            for asset_type in settings.LIQUID_ASSET_TYPES
        )


def _value_by_type(portfolio_metrics: PortfolioMetrics) -> dict[AssetType, float]:
    return {
        asset_type: portfolio_metrics.allocation.get(asset_type, 0.0)
        * portfolio_metrics.total_value
        for asset_type in AssetType
    }


def _liquidate(portfolio_metrics: PortfolioMetrics, net_needed: float) -> _Liquidation:
    """
    Raise `net_needed` rupees of usable funds, applying the per-asset-type haircut.

    THE HAIRCUT IS APPLIED HERE AND NOWHERE ELSE. P2 deliberately left liquid_value
    gross so it would not be applied twice (CONTEXT.md 17.2 config, P2 record). To
    realise X rupees from a holding with haircut h, X / (1 - h) of it must be sold.

    ALL asset types can be sold, not just LIQUID_ASSET_TYPES. Whether a customer is
    ALLOWED to sell volatile holdings is a POLICY question owned by the guardrails in
    P6, which is why volatile_gross_sold is reported rather than pre-emptively
    refused here. Excluding volatile assets at this layer would make
    VOLATILE_ASSET_LIQUIDATION_PROHIBITED unreachable.
    """
    remaining = _value_by_type(portfolio_metrics)
    if net_needed <= 0.0:
        return _Liquidation(True, 0.0, 0.0, remaining)

    order = sorted(AssetType, key=lambda a: settings.ASSET_LIQUIDATION_HAIRCUT[a])
    outstanding = net_needed
    gross_sold = 0.0
    volatile_gross_sold = 0.0

    for asset_type in order:
        if outstanding <= 0.0:
            break
        gross_available = remaining[asset_type]
        if gross_available <= 0.0:
            continue
        retained = 1.0 - settings.ASSET_LIQUIDATION_HAIRCUT[asset_type]
        if retained <= 0.0:
            continue  # a 100% haircut raises nothing; no configured type has one
        net_available = gross_available * retained
        net_taken = min(outstanding, net_available)
        gross_taken = net_taken / retained

        # Floored at zero: accumulated float error on a fully-consumed holding
        # otherwise leaves a residue of ~1e-11, which is a negative portfolio value.
        remaining[asset_type] = max(0.0, gross_available - gross_taken)
        gross_sold += gross_taken
        if asset_type in settings.VOLATILE_ASSET_TYPES:
            volatile_gross_sold += gross_taken
        outstanding -= net_taken

    # A hair of float residue is not a funding shortfall.
    funded = outstanding <= 10.0 ** (-_DOMINANCE_PRECISION)
    return _Liquidation(funded, gross_sold, volatile_gross_sold, remaining)


def _build_candidate(
    candidate_id: str,
    requirement: LoanRequirement,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    product: LoanProduct | None,
    tenure_months: int | None,
    strategy: FinancingStrategy,
    loan_amount: float,
    liquidation_amount: float,
) -> Candidate:
    """
    Compute every financial field of one candidate and mark its feasibility.

    A candidate is marked INFEASIBLE, never deleted (CONTEXT.md section 4). Two
    conditions, checked in this order because the first makes the second moot:
      1. the required liquidation exceeds what the portfolio can raise
      2. the EMI exceeds the affordability ceiling
    """
    annual_rate = product.annual_rate if product is not None else 0.0
    if tenure_months is None:
        monthly_emi = 0.0
        interest = 0.0
        repayment = 0.0
    else:
        monthly_emi = emi(loan_amount, annual_rate, tenure_months)
        interest = total_interest(loan_amount, annual_rate, tenure_months)
        repayment = total_repayment(loan_amount, annual_rate, tenure_months)

    liquidation = _liquidate(portfolio_metrics, liquidation_amount)

    infeasibility: MismatchReasonCode | None = None
    if not liquidation.funded:
        infeasibility = MismatchReasonCode.LIQUIDATION_EXCEEDS_PORTFOLIO
    elif monthly_emi > financial_metrics.emi_affordability_ceiling:
        infeasibility = MismatchReasonCode.EMI_EXCEEDS_AFFORDABILITY

    remaining_total = liquidation.remaining_total
    resulting_liquidity_ratio = (
        liquidation.remaining_liquid / remaining_total if remaining_total > 0.0 else 0.0
    )

    return Candidate(
        candidate_id=candidate_id,
        product_id=product.product_id if product is not None else None,
        lender=product.lender if product is not None else None,
        tenure_months=tenure_months,
        strategy=strategy,
        required_amount=requirement.required_amount,
        loan_amount=loan_amount,
        emi=monthly_emi,
        total_interest=interest,
        total_repayment=repayment,
        # Net funding contribution demanded by the strategy. The GROSS value sold is
        # larger by the haircut and is recoverable as
        # total_value - remaining_portfolio_value, which is what P6's liquidation
        # share cap measures.
        liquidation_amount=liquidation_amount,
        volatile_liquidation_amount=liquidation.volatile_gross_sold,
        remaining_portfolio_value=remaining_total,
        resulting_liquidity_ratio=min(resulting_liquidity_ratio, 1.0),
        resulting_debt_burden_ratio=income_ratio(
            financial_metrics.existing_emi + monthly_emi,
            financial_metrics.monthly_income,
        ),
        affordability_headroom=financial_metrics.emi_affordability_ceiling - monthly_emi,
        feasible=infeasibility is None,
        infeasibility_reason=infeasibility,
    )


def _tenure_options(product: LoanProduct, requirement: LoanRequirement) -> list[int]:
    """
    The configured grid plus the customer's own preferred tenure, restricted to the
    product's limits.

    Including the preferred tenure is not a preference ordering — it guarantees the
    option the customer actually asked for is in the space the model gets to score,
    rather than being absent because it fell between two grid steps.
    """
    options = set(settings.CANDIDATE_TENURE_OPTIONS_MONTHS)
    options.add(requirement.preferred_tenure_months)
    return sorted(
        tenure
        for tenure in options
        if product.min_tenure_months <= tenure <= product.max_tenure_months
    )


def _dominance_axes(candidate: Candidate, portfolio_value: float) -> tuple:
    """
    The three comparison axes, LOWER IS BETTER on each: EMI, total interest, and
    portfolio impact (gross value sold, including the haircut loss).
    """
    return (
        round(candidate.emi, _DOMINANCE_PRECISION),
        round(candidate.total_interest, _DOMINANCE_PRECISION),
        round(portfolio_value - candidate.remaining_portfolio_value, _DOMINANCE_PRECISION),
    )


def _prune_dominated(
    candidates: list[Candidate], portfolio_value: float
) -> list[Candidate]:
    """
    Drop candidate B when some candidate A, for the SAME product and SAME loan
    amount, is better-or-equal on EVERY axis and strictly better on at least one.

    This removes objectively worse options. It expresses no preference and is NOT
    ranking: a candidate that is worse on one axis and better on another survives,
    because nothing here is entitled to decide which axis matters to this customer.
    That is the recommender's job.
    """
    kept: list[Candidate] = []
    for candidate in candidates:
        group = [
            other
            for other in candidates
            if other is not candidate
            and other.product_id == candidate.product_id
            and round(other.loan_amount, _DOMINANCE_PRECISION)
            == round(candidate.loan_amount, _DOMINANCE_PRECISION)
        ]
        mine = _dominance_axes(candidate, portfolio_value)
        dominated = False
        for other in group:
            theirs = _dominance_axes(other, portfolio_value)
            if all(t <= m for t, m in zip(theirs, mine)) and any(
                t < m for t, m in zip(theirs, mine)
            ):
                dominated = True
                break
        if not dominated:
            kept.append(candidate)
    return kept


def generate_candidates(
    requirement: LoanRequirement,
    financial_metrics: FinancialMetrics,
    portfolio_metrics: PortfolioMetrics,
    eligible_products: list[LoanProduct],
) -> CandidateGenerationResult:
    """
    Enumerate the feasible configuration space.

    Consumes only products that already passed eligibility. It does NOT re-check
    eligibility (CONTEXT.md non-negotiable 4).

    With no portfolio, only 100%-borrow strategies are generated and no no-loan
    candidate exists — there is nothing to liquidate. Nothing downstream special-cases
    this; the option space is simply smaller.
    """
    all_generated: list[Candidate] = []

    # THE NO-LOAN CANDIDATE, generated exactly ONCE PER CUSTOMER (Phase R finding).
    # It borrows nothing, so product and tenure are meaningless for it; emitting one
    # per product x tenure produced dozens of identical-scoring rows whose tie-break
    # then picked an arbitrary "winner".
    if portfolio_metrics.has_portfolio:
        all_generated.append(
            _build_candidate(
                candidate_id=NO_LOAN_CANDIDATE_ID,
                requirement=requirement,
                financial_metrics=financial_metrics,
                portfolio_metrics=portfolio_metrics,
                product=None,
                tenure_months=None,
                strategy=FinancingStrategy.LIQUIDATE_100,
                loan_amount=0.0,
                liquidation_amount=requirement.required_amount,
            )
        )

    borrowing_strategies = [
        (strategy, share)
        for strategy, share in settings.CANDIDATE_STRATEGY_BORROW_SHARE.items()
        if share > 0.0
    ]

    for product in eligible_products:
        for step in settings.CANDIDATE_AMOUNT_STEPS:
            funded_amount = requirement.required_amount * step
            for tenure in _tenure_options(product, requirement):
                for strategy, borrow_share in borrowing_strategies:
                    # No portfolio means nothing to liquidate, so only full borrowing
                    # is a real configuration.
                    if borrow_share < 1.0 and not portfolio_metrics.has_portfolio:
                        continue

                    loan_amount = funded_amount * borrow_share
                    # A loan outside the product's own amount limits is not a
                    # configuration OF THIS PRODUCT, so it is not generated. That is
                    # distinct from infeasible, which means the arithmetic does not
                    # work for this customer.
                    if not (
                        product.min_amount <= loan_amount <= product.max_amount
                    ):
                        continue

                    all_generated.append(
                        _build_candidate(
                            candidate_id=(
                                f"{product.product_id}"
                                f"-{round(loan_amount)}"
                                f"-{tenure}"
                                f"-{strategy.value}"
                            ),
                            requirement=requirement,
                            financial_metrics=financial_metrics,
                            portfolio_metrics=portfolio_metrics,
                            product=product,
                            tenure_months=tenure,
                            strategy=strategy,
                            loan_amount=loan_amount,
                            liquidation_amount=funded_amount - loan_amount,
                        )
                    )

    infeasible = [c for c in all_generated if not c.feasible]
    feasible = [c for c in all_generated if c.feasible]

    surviving = _prune_dominated(feasible, portfolio_metrics.total_value)
    pruned_count = len(feasible) - len(surviving)

    # CAPS. Truncation is by ENUMERATION ORDER, which is arbitrary but deterministic.
    # It is deliberately not by any quality measure: choosing which candidates to keep
    # by how good they look would be ranking, and ranking belongs to the recommender.
    capped_count = 0
    per_product: dict[str | None, int] = {}
    within_product_cap: list[Candidate] = []
    for candidate in surviving:
        seen = per_product.get(candidate.product_id, 0)
        if seen >= settings.MAX_CANDIDATES_PER_PRODUCT:
            capped_count += 1
            continue
        per_product[candidate.product_id] = seen + 1
        within_product_cap.append(candidate)

    if len(within_product_cap) > settings.MAX_CANDIDATES_TOTAL:
        capped_count += len(within_product_cap) - settings.MAX_CANDIDATES_TOTAL
        within_product_cap = within_product_cap[: settings.MAX_CANDIDATES_TOTAL]

    return CandidateGenerationResult(
        candidates=within_product_cap + infeasible,
        counts=CandidateGenerationCounts(
            generated=len(all_generated),
            infeasible=len(infeasible),
            dominance_pruned=pruned_count,
            capped=capped_count,
            surviving=len(within_product_cap),
        ),
    )
