"""
API routes (P14).

ROUTES CONTAIN NO BUSINESS LOGIC. They validate the request, call a core / ML module,
and return a schema. No EMI is computed here, nothing is re-ranked, no decision is
made in a handler. The recommendation decision always comes from
app/core/recommendation.py, which is the only place that walks the pipeline.

Every request and response body is a Pydantic schema. Graph of which core module each
route delegates to:

    POST /financial-health   -> app/core/financial.analyze_financials
    POST /portfolio-analysis -> app/core/portfolio.analyze_portfolio
    GET  /loan-products      -> app.api.catalogue.load_catalogue
    POST /eligibility        -> app.core.eligibility.check_eligibility
    POST /risk-prediction    -> app.ml.risk.predict_risk
    POST /candidates         -> app.core.candidates.generate_candidates
    POST /recommend          -> app.core.recommendation.recommend  (THE primary endpoint)
    POST /scenario           -> app.core.recommendation.recommend  (a full re-run)
    POST /explanation        -> app.explain.llm + app.explain.xai (describe a computed result)
    GET  /coverage           -> app.core.recommendation.recommend (funnel portion)
    GET  /health             -> liveness
    DELETE /personalization/{user_id} -> app.personalization.store
"""

import logging
from functools import lru_cache

from fastapi import APIRouter, HTTPException

from app.api.catalogue import load_catalogue
from app.config import settings
from app.core.candidates import generate_candidates
from app.personalization.store import PersonalizationStore
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.core.recommendation import recommend
from app.explain import llm as llm_module
from app.explain.xai import (
    XaiDisabled,
    explain_recommendation_choice,
    explain_risk,
)
from app.ml.features import build_risk_features
from app.ml.risk import predict_risk
from app.schemas import (
    CustomerProfile,
    FinancialMetrics,
    LoanProduct,
    Portfolio,
    PortfolioMetrics,
    Recommendation,
    RiskPrediction,
)
from app.schemas.api import ExplanationRequest, RecommendRequest
from app.schemas.enums import EligibilityStatus, RecommendationStatus
from app.schemas.explanation import Explanation, XaiExplanation

logger = logging.getLogger(__name__)

router = APIRouter()


@lru_cache(maxsize=1)
def _catalogue() -> list[LoanProduct]:
    return load_catalogue()


def _products_by_id(catalogue: list[LoanProduct]) -> dict[str, LoanProduct]:
    return {product.product_id: product for product in catalogue}


# ---------------------------------------------------------------------------
# Single-signal pipeline routes
# ---------------------------------------------------------------------------


@router.post("/financial-health", response_model=FinancialMetrics)
def financial_health(customer: CustomerProfile) -> FinancialMetrics:
    return analyze_financials(customer)


@router.post("/portfolio-analysis", response_model=PortfolioMetrics)
def portfolio_analysis(portfolio: Portfolio) -> PortfolioMetrics:
    return analyze_portfolio(portfolio)


@router.get("/loan-products", response_model=list[LoanProduct])
def loan_products() -> list[LoanProduct]:
    return _catalogue()


@router.post("/eligibility")
def eligibility(req: RecommendRequest):
    catalogue = _catalogue()
    financial = analyze_financials(req.customer)
    return check_eligibility(req.customer, financial, req.requirement, catalogue)


@router.post("/risk-prediction", response_model=RiskPrediction)
def risk_prediction(req: RecommendRequest) -> RiskPrediction:
    financial = analyze_financials(req.customer)
    portfolio = analyze_portfolio(req.portfolio)
    return predict_risk(req.customer, financial, portfolio, req.requirement)


@router.post("/candidates")
def candidates(req: RecommendRequest):
    catalogue = _catalogue()
    financial = analyze_financials(req.customer)
    portfolio = analyze_portfolio(req.portfolio)
    eligibility_results = check_eligibility(
        req.customer, financial, req.requirement, catalogue
    )
    eligible_ids = {
        result.product_id
        for result in eligibility_results
        if result.status is EligibilityStatus.ELIGIBLE
    }
    eligible_products = [
        product for product in catalogue if product.product_id in eligible_ids
    ]
    return generate_candidates(req.requirement, financial, portfolio, eligible_products)


# ---------------------------------------------------------------------------
# Primary recommendation endpoints
# ---------------------------------------------------------------------------


@router.post("/recommend", response_model=Recommendation)
def recommend_endpoint(req: RecommendRequest) -> Recommendation:
    return recommend(
        req.customer,
        req.portfolio,
        req.requirement,
        _catalogue(),
        user_id=req.user_id,
    )


@router.post("/scenario", response_model=Recommendation)
def scenario(req: RecommendRequest) -> Recommendation:
    """
    What-if: a FULL re-run of the trusted pipeline on the given (possibly modified)
    inputs. Never an arithmetic adjustment of a previous recommendation — it recomputes
    metrics, re-enumerates candidates, re-scores and re-validates
    (CONTEXT.md section 4).
    """
    return recommend(
        req.customer,
        req.portfolio,
        req.requirement,
        _catalogue(),
        user_id=req.user_id,
    )


@router.get("/coverage")
def coverage(req: RecommendRequest):
    result = recommend(
        req.customer,
        req.portfolio,
        req.requirement,
        _catalogue(),
        user_id=req.user_id,
    )
    return {
        "recommendation_status": result.status,
        "recommendation_source": result.source,
        "coverage": result.coverage,
    }


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


@router.post("/explanation")
def explanation(req: ExplanationRequest):
    """
    Explain the recommendation computed from these inputs. Runs the SAME trusted
    pipeline once to obtain the decision, then describes it: the LLM writes the prose
    (or the template when the LLM is unavailable / rejects), and XAI reports the
    model's feature contributions. The LLM and XAI never compute or decide anything.
    """
    result = recommend(
        req.customer,
        req.portfolio,
        req.requirement,
        _catalogue(),
        user_id=req.user_id,
    )
    prose = _explain_prose(req, result)
    graphics = _explain_xai(req, result)
    return {"explanation": prose, "xai": graphics}


def _explain_prose(req: ExplanationRequest, result: Recommendation) -> Explanation:
    if req.question:
        return llm_module.answer_question(req.question, result)
    if result.status is RecommendationStatus.RECOMMENDED:
        return llm_module.explain_recommendation(result)
    return llm_module.explain_mismatch(result)


def _explain_xai(req: ExplanationRequest, result: Recommendation) -> XaiExplanation:
    if not settings.ENABLE_XAI_ENDPOINT:
        raise HTTPException(status_code=404, detail="XAI endpoint is disabled")
    if result.risk is None:
        raise HTTPException(status_code=422, detail="no risk information to explain")
    trace = result.decision_trace
    try:
        if result.status is RecommendationStatus.RECOMMENDED:
            return explain_recommendation_choice(
                customer=req.customer,
                financial_metrics=trace.financial_metrics,
                portfolio_metrics=trace.portfolio_metrics,
                personalization_context=trace.personalization,
                requirement=req.requirement,
                products_by_id=_products_by_id(_catalogue()),
                scored_candidates=trace.ranked_candidates,
                risk_pd=result.risk.probability_of_default,
                winner_candidate_id=(
                    result.selected_candidate.candidate_id
                    if result.selected_candidate
                    else None
                ),
            )
        features = build_risk_features(
            req.customer,
            trace.financial_metrics,
            trace.portfolio_metrics,
            req.requirement,
        )
        return explain_risk(features)
    except XaiDisabled:
        raise HTTPException(status_code=404, detail="XAI endpoint is disabled")


# ---------------------------------------------------------------------------
# Health and personalization
# ---------------------------------------------------------------------------


@router.get("/health")
def health() -> dict:
    from app.ml import recommender as ml_recommender
    from app.ml import risk as ml_risk

    return {
        "status": "ok",
        "ml": {
            "recommender_loaded": not ml_recommender.is_degraded(),
            "risk_loaded": not ml_risk.is_degraded(),
            "recommender_source": (
                "ML_RANKER"
                if not ml_recommender.is_degraded()
                else "DETERMINISTIC_FALLBACK"
            ),
        },
        "catalogue_products": len(_catalogue()),
    }


@router.delete("/personalization/{user_id}")
def delete_personalization(user_id: str) -> dict:
    # A fresh store per request: sqlite connections are not shareable across the
    # threadpool threads that serve sync endpoints, so we open and close one here.
    store = PersonalizationStore()
    try:
        return {"user_id": user_id, "rows_removed": store.delete_user(user_id)}
    finally:
        store.close()
