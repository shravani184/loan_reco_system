"""
SPIKE ONLY — throwaway local domain objects for the labeling spike.

This is NOT production code and is NOT imported by app/ or training/.
Phase 7 re-implements the policy against the real Pydantic schemas; only the
invariant suite carries forward.

Everything here is deliberately minimal: just enough shape to exercise the
labeling policy and its invariants.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

CONSERVATIVE = "CONSERVATIVE"
MODERATE = "MODERATE"
AGGRESSIVE = "AGGRESSIVE"

# Strategies as (borrow_fraction, liquidate_fraction) of the required amount.
STRATEGIES = [
    ("BORROW_100", 1.00, 0.00),
    ("BORROW_80_LIQ_20", 0.80, 0.20),
    ("BORROW_60_LIQ_40", 0.60, 0.40),
    ("BORROW_40_LIQ_60", 0.40, 0.60),
    ("BORROW_20_LIQ_80", 0.20, 0.80),
    ("LIQUIDATE_100", 0.00, 1.00),
]


@dataclass(frozen=True)
class Customer:
    monthly_income: float
    monthly_expenses: float
    existing_emi: float
    credit_score: int
    age: int
    risk_appetite: str
    portfolio_value: float = 0.0
    liquid_value: float = 0.0        # cash, FD, liquid funds
    volatile_value: float = 0.0      # equity, crypto

    @property
    def disposable(self) -> float:
        return max(0.0, self.monthly_income - self.monthly_expenses - self.existing_emi)

    def affordability_ceiling(self, max_emi_share_of_disposable: float) -> float:
        return self.disposable * max_emi_share_of_disposable


@dataclass(frozen=True)
class Product:
    product_id: str
    annual_rate: float
    min_amount: float
    max_amount: float
    min_tenure: int
    max_tenure: int


@dataclass(frozen=True)
class Candidate:
    product_id: str
    annual_rate: float
    required_amount: float      # what the customer needs in total
    loan_amount: float          # borrowed portion
    liquidation_amount: float   # portion funded by selling holdings
    volatile_liquidated: float  # how much of the liquidation came from volatile assets
    tenure_months: int
    strategy: str

    @property
    def emi(self) -> float:
        return emi(self.loan_amount, self.annual_rate, self.tenure_months)

    @property
    def total_repayment(self) -> float:
        return self.emi * self.tenure_months

    @property
    def total_interest(self) -> float:
        return max(0.0, self.total_repayment - self.loan_amount)


def emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """Spike-local EMI. Phase 5 owns the single production implementation."""
    if tenure_months <= 0:
        raise ValueError("tenure must be positive")
    if principal <= 0:
        return 0.0
    r = annual_rate / 12.0 / 100.0
    if r == 0:
        return principal / tenure_months
    growth = (1.0 + r) ** tenure_months
    return principal * r * growth / (growth - 1.0)


def generate_candidates(
    customer: Customer,
    products: list[Product],
    required_amount: float,
    tenures: list[int],
) -> list[Candidate]:
    """
    Bounded enumeration, mirroring the shape Phase 5 will own.

    Zero-portfolio consistency is enforced here: with no holdings, only the
    100%-borrow strategy is emitted.
    """
    liquid_capacity = customer.liquid_value + customer.volatile_value
    out: list[Candidate] = []

    # FINDING (spike): a 100%-liquidate candidate borrows nothing, so product and
    # tenure are meaningless for it. Emitting one per product x tenure produces
    # dozens of candidates with identical scores, and the tie-break then decides
    # the "winner" arbitrarily — which showed up as one product winning 99% of
    # groups. It is emitted exactly ONCE per customer.
    if customer.portfolio_value > 0 and required_amount <= liquid_capacity:
        volatile_used = max(0.0, required_amount - customer.liquid_value)
        out.append(
            Candidate(
                product_id="NO_LOAN",
                annual_rate=0.0,
                required_amount=required_amount,
                loan_amount=0.0,
                liquidation_amount=required_amount,
                volatile_liquidated=volatile_used,
                tenure_months=1,
                strategy="LIQUIDATE_100",
            )
        )

    for product in products:
        for tenure in tenures:
            if not (product.min_tenure <= tenure <= product.max_tenure):
                continue
            for name, borrow_frac, liq_frac in STRATEGIES:
                if liq_frac >= 1.0:
                    continue                          # emitted once, above
                liquidation = required_amount * liq_frac
                if liq_frac > 0.0:
                    if customer.portfolio_value <= 0.0:
                        continue                      # zero-portfolio invariant
                    if liquidation > liquid_capacity:
                        continue                      # cannot fund it
                loan_amount = required_amount * borrow_frac
                if loan_amount > 0 and not (
                    product.min_amount <= loan_amount <= product.max_amount
                ):
                    continue
                # Liquid assets are consumed before volatile ones.
                volatile_used = max(0.0, liquidation - customer.liquid_value)
                out.append(
                    Candidate(
                        product_id=product.product_id,
                        annual_rate=product.annual_rate,
                        required_amount=required_amount,
                        loan_amount=loan_amount,
                        liquidation_amount=liquidation,
                        volatile_liquidated=volatile_used,
                        tenure_months=tenure,
                        strategy=name,
                    )
                )
    return out


def scale(customer: Customer, candidates: list[Candidate], k: float):
    """Multiply every rupee quantity by k. Used by the scale-invariance invariant."""
    scaled_customer = replace(
        customer,
        monthly_income=customer.monthly_income * k,
        monthly_expenses=customer.monthly_expenses * k,
        existing_emi=customer.existing_emi * k,
        portfolio_value=customer.portfolio_value * k,
        liquid_value=customer.liquid_value * k,
        volatile_value=customer.volatile_value * k,
    )
    scaled_candidates = [
        replace(
            c,
            required_amount=c.required_amount * k,
            loan_amount=c.loan_amount * k,
            liquidation_amount=c.liquidation_amount * k,
            volatile_liquidated=c.volatile_liquidated * k,
        )
        for c in candidates
    ]
    return scaled_customer, scaled_candidates
