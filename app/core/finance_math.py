"""
THE ONLY EMI IMPLEMENTATION IN THIS REPOSITORY.

Two implementations of EMI is a defect regardless of whether they agree
(AGENTS.md section 2). Everything that needs an EMI imports from here — candidate
generation in P5, and the deterministic validator in P12 that re-verifies the ML's
chosen candidate against this same function.

spikes/labeling/domain.py contains a throwaway EMI used to prototype the labeling
policy. It is not imported and is not authoritative (AGENTS.md section 15).

Money is float rupees. These functions round nothing: rounding is a presentation
concern, and rounding here would make the P12 re-verification compare two different
roundings instead of the same formula.
"""

MONTHS_PER_YEAR = 12
PERCENT = 100.0


def monthly_rate(annual_rate: float) -> float:
    """annual_rate is a percentage (8.5 means 8.5%), not a fraction."""
    return annual_rate / MONTHS_PER_YEAR / PERCENT


def emi(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    EMI = P * r * (1+r)^n / ((1+r)^n - 1),  r = annual_rate / 12 / 100

    Edge case, per CONTEXT.md section 4: r == 0 gives EMI = P / n, because the
    general formula is 0/0 there.

    A zero principal borrows nothing and repays nothing — this is the no-loan
    candidate, not a degenerate loan.
    """
    if tenure_months <= 0:
        raise ValueError("tenure_months must be positive")
    if principal < 0.0:
        raise ValueError("principal must not be negative")
    if principal == 0.0:
        return 0.0

    rate = monthly_rate(annual_rate)
    if rate == 0.0:
        return principal / tenure_months

    growth = (1.0 + rate) ** tenure_months
    return principal * rate * growth / (growth - 1.0)


def total_repayment(principal: float, annual_rate: float, tenure_months: int) -> float:
    """What the borrower pays in total over the full term."""
    return emi(principal, annual_rate, tenure_months) * tenure_months


def total_interest(principal: float, annual_rate: float, tenure_months: int) -> float:
    """
    Cost of credit over the full term.

    Floored at zero so floating-point noise on a zero-rate loan cannot produce a
    negative interest figure, which would be nonsense in a trace.
    """
    return max(
        0.0, total_repayment(principal, annual_rate, tenure_months) - principal
    )
