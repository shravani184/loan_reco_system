"""
Portfolio Intelligence (P2).

The mixed-portfolio expectations are hand-computed from tests.fixtures.mixed_portfolio
and asserted as values, not as "is not None".
"""

import pytest

from app.config import settings
from app.core.portfolio import analyze_portfolio
from app.schemas import Holding, Portfolio
from app.schemas.enums import AssetType, PortfolioRisk
from tests import fixtures

# tests.fixtures.mixed_portfolio, by hand:
#   CASH   150000 (invested 150000)      FD      400000 (370000)
#   MF     650000 (500000)               STOCKS  800000 (900000)
#   BONDS  200000 (195000)               CRYPTO  100000 (140000)
#   total current 2_300_000   total invested 2_255_000
MIXED_TOTAL = 2_300_000.0


# ------------------------------------------------------------ mixed portfolio


def test_mixed_portfolio_total_and_unrealized_gain():
    metrics = analyze_portfolio(fixtures.mixed_portfolio())
    assert metrics.has_portfolio is True
    assert metrics.total_value == MIXED_TOTAL
    assert metrics.unrealized_gain_loss == pytest.approx(45_000.0)


def test_mixed_portfolio_allocation_is_hand_computed():
    allocation = analyze_portfolio(fixtures.mixed_portfolio()).allocation
    assert allocation[AssetType.CASH] == pytest.approx(150_000.0 / MIXED_TOTAL)
    assert allocation[AssetType.FIXED_DEPOSIT] == pytest.approx(400_000.0 / MIXED_TOTAL)
    assert allocation[AssetType.MUTUAL_FUNDS] == pytest.approx(650_000.0 / MIXED_TOTAL)
    assert allocation[AssetType.STOCKS] == pytest.approx(800_000.0 / MIXED_TOTAL)
    assert allocation[AssetType.BONDS] == pytest.approx(200_000.0 / MIXED_TOTAL)
    assert allocation[AssetType.CRYPTO] == pytest.approx(100_000.0 / MIXED_TOTAL)


def test_allocation_covers_every_asset_type_and_sums_to_one():
    allocation = analyze_portfolio(fixtures.mixed_portfolio()).allocation
    assert set(allocation) == set(AssetType)
    assert sum(allocation.values()) == pytest.approx(1.0)


def test_mixed_portfolio_liquidity_is_hand_computed():
    """Liquid = CASH + FD + MF = 1_200_000 of 2_300_000."""
    metrics = analyze_portfolio(fixtures.mixed_portfolio())
    assert metrics.liquid_value == pytest.approx(1_200_000.0)
    assert metrics.liquidity_ratio == pytest.approx(1_200_000.0 / MIXED_TOTAL)


def test_mixed_portfolio_exposures_are_hand_computed():
    metrics = analyze_portfolio(fixtures.mixed_portfolio())
    # equity = STOCKS + MF, debt = FD + BONDS, crypto = CRYPTO
    assert metrics.equity_exposure == pytest.approx(1_450_000.0 / MIXED_TOTAL)
    assert metrics.debt_exposure == pytest.approx(600_000.0 / MIXED_TOTAL)
    assert metrics.crypto_exposure == pytest.approx(100_000.0 / MIXED_TOTAL)


def test_exposures_do_not_partition_the_portfolio():
    """
    CASH and CRYPTO are each in neither the equity nor the debt list, so the three
    exposures are independent shares rather than a partition. Equity + debt is
    exactly the remainder after both are removed.
    """
    metrics = analyze_portfolio(fixtures.mixed_portfolio())
    unclassified = (
        metrics.allocation[AssetType.CASH] + metrics.allocation[AssetType.CRYPTO]
    )
    assert metrics.equity_exposure + metrics.debt_exposure == pytest.approx(
        1.0 - unclassified
    )
    assert AssetType.CASH not in settings.EQUITY_ASSET_TYPES
    assert AssetType.CASH not in settings.DEBT_ASSET_TYPES
    assert AssetType.CRYPTO not in settings.EQUITY_ASSET_TYPES
    assert AssetType.CRYPTO not in settings.DEBT_ASSET_TYPES


def test_mixed_portfolio_concentration_is_the_largest_holding():
    metrics = analyze_portfolio(fixtures.mixed_portfolio())
    assert metrics.concentration_risk == pytest.approx(800_000.0 / MIXED_TOTAL)


def test_mixed_portfolio_risk_band():
    """Value-weighted risk score is ~0.467, which lands in GROWTH (cut-point 0.45)."""
    assert analyze_portfolio(fixtures.mixed_portfolio()).portfolio_risk is (
        PortfolioRisk.GROWTH
    )


def test_input_is_not_mutated():
    portfolio = fixtures.mixed_portfolio()
    before = portfolio.model_dump()
    analyze_portfolio(portfolio)
    assert portfolio.model_dump() == before


# ------------------------------------------------------- the no-portfolio path


def test_empty_portfolio_returns_valid_zero_metrics():
    metrics = analyze_portfolio(fixtures.empty_portfolio())
    assert metrics.has_portfolio is False
    assert metrics.total_value == 0.0
    assert metrics.liquid_value == 0.0
    assert metrics.liquidity_ratio == 0.0
    assert metrics.equity_exposure == 0.0
    assert metrics.debt_exposure == 0.0
    assert metrics.crypto_exposure == 0.0
    assert metrics.concentration_risk == 0.0
    assert metrics.unrealized_gain_loss == 0.0
    assert metrics.portfolio_risk is PortfolioRisk.CONSERVATIVE


def test_none_portfolio_returns_valid_zero_metrics():
    """An absent portfolio is a supported input, not an error."""
    metrics = analyze_portfolio(None)
    assert metrics.has_portfolio is False
    assert metrics.total_value == 0.0
    assert metrics.portfolio_risk is PortfolioRisk.CONSERVATIVE


def test_none_and_empty_produce_identical_metrics():
    assert analyze_portfolio(None) == analyze_portfolio(fixtures.empty_portfolio())


def test_zero_portfolio_allocation_is_fully_shaped_not_empty():
    """
    The feature vector must not have to test for a missing key. Every AssetType is
    present at 0.0.
    """
    allocation = analyze_portfolio(None).allocation
    assert set(allocation) == set(AssetType)
    assert all(share == 0.0 for share in allocation.values())


def test_holdings_worth_nothing_are_treated_as_no_portfolio():
    """Present but collectively worthless — no division by zero, no exception."""
    portfolio = Portfolio(
        holdings=[
            Holding(asset_type=AssetType.STOCKS, current_value=0.0, invested_value=0.0)
        ]
    )
    metrics = analyze_portfolio(portfolio)
    assert metrics.has_portfolio is False
    assert metrics.total_value == 0.0


# --------------------------------------------------------------- single holding


def _single(asset_type: AssetType, value: float = 500_000.0) -> Portfolio:
    return Portfolio(
        holdings=[
            Holding(asset_type=asset_type, current_value=value, invested_value=value)
        ]
    )


def test_single_holding_has_maximum_concentration_risk():
    metrics = analyze_portfolio(_single(AssetType.STOCKS))
    assert metrics.concentration_risk == 1.0
    assert metrics.allocation[AssetType.STOCKS] == 1.0


def test_two_equal_holdings_halve_concentration_risk():
    portfolio = Portfolio(
        holdings=[
            Holding(
                asset_type=AssetType.STOCKS,
                current_value=500_000.0,
                invested_value=500_000.0,
            ),
            Holding(
                asset_type=AssetType.CASH,
                current_value=500_000.0,
                invested_value=500_000.0,
            ),
        ]
    )
    assert analyze_portfolio(portfolio).concentration_risk == pytest.approx(0.5)


def test_concentration_is_per_holding_not_per_asset_type():
    """Two separate stock positions are two holdings, not one concentrated block."""
    portfolio = Portfolio(
        holdings=[
            Holding(
                asset_type=AssetType.STOCKS,
                current_value=300_000.0,
                invested_value=300_000.0,
            ),
            Holding(
                asset_type=AssetType.STOCKS,
                current_value=300_000.0,
                invested_value=300_000.0,
            ),
        ]
    )
    metrics = analyze_portfolio(portfolio)
    assert metrics.allocation[AssetType.STOCKS] == 1.0
    assert metrics.concentration_risk == pytest.approx(0.5)


# ------------------------------------------------------------------ risk bands


def test_crypto_heavy_portfolio_is_aggressive():
    metrics = analyze_portfolio(_single(AssetType.CRYPTO))
    assert metrics.crypto_exposure == 1.0
    assert metrics.portfolio_risk is PortfolioRisk.AGGRESSIVE


def test_all_cash_portfolio_is_conservative():
    metrics = analyze_portfolio(_single(AssetType.CASH))
    assert metrics.portfolio_risk is PortfolioRisk.CONSERVATIVE
    assert metrics.liquidity_ratio == 1.0


def test_risk_band_rises_with_asset_risk_weight():
    ordered = [
        AssetType.CASH,
        AssetType.FIXED_DEPOSIT,
        AssetType.BONDS,
        AssetType.MUTUAL_FUNDS,
        AssetType.STOCKS,
        AssetType.CRYPTO,
    ]
    ladder = [
        PortfolioRisk.CONSERVATIVE,
        PortfolioRisk.BALANCED,
        PortfolioRisk.GROWTH,
        PortfolioRisk.AGGRESSIVE,
    ]
    positions = [
        ladder.index(analyze_portfolio(_single(asset_type)).portfolio_risk)
        for asset_type in ordered
    ]
    assert positions == sorted(positions)


@pytest.mark.parametrize(
    "band", [PortfolioRisk.AGGRESSIVE, PortfolioRisk.GROWTH, PortfolioRisk.BALANCED]
)
def test_band_transition_exactly_at_each_threshold(band):
    """
    A two-holding CASH (weight 0.0) / CRYPTO (weight 1.0) split makes the risk score
    equal to the crypto share exactly, so a cut-point can be hit on the nose.
    """
    threshold = settings.PORTFOLIO_RISK_MIN_SCORE[band]

    def band_at(crypto_share: float) -> PortfolioRisk:
        total = 1_000_000.0
        return analyze_portfolio(
            Portfolio(
                holdings=[
                    Holding(
                        asset_type=AssetType.CRYPTO,
                        current_value=total * crypto_share,
                        invested_value=total * crypto_share,
                    ),
                    Holding(
                        asset_type=AssetType.CASH,
                        current_value=total * (1.0 - crypto_share),
                        invested_value=total * (1.0 - crypto_share),
                    ),
                ]
            )
        ).portfolio_risk

    assert band_at(threshold) is band
    assert band_at(threshold - 0.001) is not band


def test_conservative_has_no_threshold_entry_because_it_is_the_floor():
    assert PortfolioRisk.CONSERVATIVE not in settings.PORTFOLIO_RISK_MIN_SCORE


def test_bands_are_ordered_by_risk_score():
    thresholds = settings.PORTFOLIO_RISK_MIN_SCORE
    assert (
        thresholds[PortfolioRisk.AGGRESSIVE]
        > thresholds[PortfolioRisk.GROWTH]
        > thresholds[PortfolioRisk.BALANCED]
    )


# ------------------------------------------------------------- classification


def test_bonds_are_debt_but_not_liquid_and_not_volatile():
    """
    Resolves the P0 gap: BONDS carried a haircut but appeared in neither the liquid
    nor the volatile list. It is a debt instrument that is not liquid enough to fund a
    purchase on demand, and not volatile enough to be barred from a conservative
    customer.
    """
    assert AssetType.BONDS in settings.DEBT_ASSET_TYPES
    assert AssetType.BONDS not in settings.LIQUID_ASSET_TYPES
    assert AssetType.BONDS not in settings.VOLATILE_ASSET_TYPES
    metrics = analyze_portfolio(_single(AssetType.BONDS))
    assert metrics.debt_exposure == 1.0
    assert metrics.liquidity_ratio == 0.0


def test_every_asset_type_has_a_risk_weight():
    assert set(settings.ASSET_RISK_WEIGHT) == set(AssetType)


def test_every_asset_type_has_a_liquidation_haircut():
    assert set(settings.ASSET_LIQUIDATION_HAIRCUT) == set(AssetType)


def test_liquid_value_is_gross_of_haircuts():
    """
    Haircuts belong to P5's liquidation math. If they were applied here they would be
    applied twice.
    """
    metrics = analyze_portfolio(_single(AssetType.FIXED_DEPOSIT, 500_000.0))
    assert settings.ASSET_LIQUIDATION_HAIRCUT[AssetType.FIXED_DEPOSIT] > 0.0
    assert metrics.liquid_value == 500_000.0
