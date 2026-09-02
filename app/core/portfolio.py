"""
Portfolio Intelligence — deterministic, no ML.

Describes what the customer holds. It does NOT recommend liquidating anything, does
not compute an EMI, and never calls a model (CONTEXT.md section 4).

THE NO-PORTFOLIO PATH IS FIRST-CLASS. None, or a Portfolio with no holdings, returns
a fully valid zeroed PortfolioMetrics with has_portfolio = False. Every downstream
stage, including the ML feature vector, consumes it without special-casing
(CONTEXT.md non-negotiable 16).

HAIRCUTS ARE NOT APPLIED HERE. ASSET_LIQUIDATION_HAIRCUT describes what is lost when
holdings are actually sold, which is P5's liquidation math. liquid_value here is the
gross value of the holdings classified as liquid. Applying the haircut in both places
would double-count it.

Every threshold and every asset classification comes from app/config.py.
"""

from app.config import settings
from app.schemas import Portfolio, PortfolioMetrics
from app.schemas.enums import AssetType, PortfolioRisk


def _empty_metrics() -> PortfolioMetrics:
    """
    The zero-portfolio result. Valid, complete, and consumable everywhere.

    Every AssetType is present at 0.0 so the allocation map has the same shape as it
    does for a funded portfolio. The risk band is the floor: holding nothing carries
    no market risk.
    """
    return PortfolioMetrics(
        has_portfolio=False,
        total_value=0.0,
        allocation={asset_type: 0.0 for asset_type in AssetType},
        liquid_value=0.0,
        liquidity_ratio=0.0,
        equity_exposure=0.0,
        debt_exposure=0.0,
        crypto_exposure=0.0,
        concentration_risk=0.0,
        unrealized_gain_loss=0.0,
        portfolio_risk=PortfolioRisk.CONSERVATIVE,
    )


def _risk_band(allocation: dict[AssetType, float]) -> PortfolioRisk:
    """
    Value-weighted mean of the per-asset-type risk weights, placed on the band ladder.

    The ladder is derived from PORTFOLIO_RISK_MIN_SCORE sorted descending, so that one
    dict is the single source of both the cut-points and their order. CONSERVATIVE is
    the floor and has no threshold entry.
    """
    score = sum(
        share * settings.ASSET_RISK_WEIGHT[asset_type]
        for asset_type, share in allocation.items()
    )

    ordered = sorted(
        settings.PORTFOLIO_RISK_MIN_SCORE.items(),
        key=lambda item: item[1],
        reverse=True,
    )
    for band, min_score in ordered:
        if score >= min_score:
            return band
    return PortfolioRisk.CONSERVATIVE


def analyze_portfolio(portfolio: Portfolio | None) -> PortfolioMetrics:
    """
    Derive portfolio metrics. Pure: no I/O, no global state, no model calls, and the
    input is not mutated.
    """
    if portfolio is None or not portfolio.holdings:
        return _empty_metrics()

    holdings = portfolio.holdings
    total_value = sum(holding.current_value for holding in holdings)

    # Holdings that exist but are collectively worthless. Treated as no portfolio
    # rather than divided by zero: there is nothing here to allocate or liquidate.
    if total_value <= 0.0:
        return _empty_metrics()

    value_by_type: dict[AssetType, float] = {
        asset_type: 0.0 for asset_type in AssetType
    }
    for holding in holdings:
        value_by_type[holding.asset_type] += holding.current_value

    allocation = {
        asset_type: value / total_value for asset_type, value in value_by_type.items()
    }

    def _share_of(asset_types: list[AssetType]) -> float:
        return sum(allocation[asset_type] for asset_type in asset_types)

    liquid_value = sum(
        value_by_type[asset_type] for asset_type in settings.LIQUID_ASSET_TYPES
    )

    invested_value = sum(holding.invested_value for holding in holdings)

    return PortfolioMetrics(
        has_portfolio=True,
        total_value=total_value,
        allocation=allocation,
        liquid_value=liquid_value,
        liquidity_ratio=liquid_value / total_value,
        equity_exposure=_share_of(settings.EQUITY_ASSET_TYPES),
        debt_exposure=_share_of(settings.DEBT_ASSET_TYPES),
        crypto_exposure=allocation[AssetType.CRYPTO],
        # Largest SINGLE HOLDING, not largest asset type: two separate mutual fund
        # positions are two holdings and are not concentrated in one another.
        concentration_risk=max(holding.current_value for holding in holdings)
        / total_value,
        unrealized_gain_loss=total_value - invested_value,
        portfolio_risk=_risk_band(allocation),
    )
