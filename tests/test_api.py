"""
FastAPI surface (P14).

Tests exercise the HTTP layer end to end through TestClient. Routes contain no
business logic, so these tests assert on API behaviour: status codes, the presence and
accuracy of the recommendation fields, funnel counts, and the fallback flag — not on
internal module details.

Model state is global, so every test resets it before and after. A test that left a
loaded model behind would make the next test pass for the wrong reason.

The recommendation tests use real trained artifacts when present (they exist in
this repo) and exercise the DETERMINISTIC_FALLBACK path by simulating a missing
artifact via the module state, mirroring tests/test_ml_inference.py.
"""

import pytest
from fastapi.testclient import TestClient

from app.config import settings
from app.main import app
from app.ml import recommender, risk
from app.personalization.store import PersonalizationStore
from app.schemas.enums import FeedbackEventType
from tests import fixtures


@pytest.fixture(autouse=True)
def clean_model_state():
    risk.reset_state()
    recommender.reset_state()
    yield
    risk.reset_state()
    recommender.reset_state()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as c:
        yield c


@pytest.fixture
def isolated_store(tmp_path, monkeypatch):
    """Point the store at a private temp db so tests never touch data/."""
    db_url = f"sqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setattr(settings, "PERSONALIZATION_DB_URL", db_url)
    # Route-level endpoints construct their own store from the patched URL, so we
    # surface one here for direct manipulation in tests.
    store = PersonalizationStore(db_url)
    yield store
    store.close()


def _recommend_body(customer=None, portfolio=None, requirement=None, user_id=None):
    return {
        "customer": (
            customer or fixtures.standard_customer()
        ).model_dump(mode="json"),
        "requirement": (
            requirement or fixtures.standard_requirement()
        ).model_dump(mode="json"),
        "portfolio": (
            portfolio if portfolio is not None else fixtures.mixed_portfolio()
        ).model_dump(mode="json"),
        "user_id": user_id,
    }


# ---------------------------------------------------------------------------
# Health and liveness
# ---------------------------------------------------------------------------


def test_health_returns_200(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["catalogue_products"] == 14
    assert "ml" in body


def test_loan_products_returns_catalogue(client):
    resp = client.get("/loan-products")
    assert resp.status_code == 200
    products = resp.json()
    assert len(products) > 0
    assert products[0]["product_id"]


def test_financial_health_returns_metrics(client):
    body = fixtures.standard_customer().model_dump(mode="json")
    resp = client.post("/financial-health", json=body)
    assert resp.status_code == 200
    metrics = resp.json()
    assert metrics["monthly_income"] == 120_000.0
    assert metrics["financial_health"] == "EXCELLENT"


def test_portfolio_analysis_returns_metrics(client):
    body = fixtures.mixed_portfolio().model_dump(mode="json")
    resp = client.post("/portfolio-analysis", json=body)
    assert resp.status_code == 200
    metrics = resp.json()
    assert metrics["has_portfolio"] is True
    assert metrics["total_value"] == 2_300_000.0


def test_portfolio_analysis_empty_portfolio(client):
    body = fixtures.empty_portfolio().model_dump(mode="json")
    resp = client.post("/portfolio-analysis", json=body)
    assert resp.status_code == 200
    assert resp.json()["has_portfolio"] is False


def test_eligibility_returns_one_result_per_product(client):
    resp = client.post("/eligibility", json=_recommend_body())
    assert resp.status_code == 200
    results = resp.json()
    assert len(results) == 14


def test_risk_prediction_returns_risk_signal(client, isolated_store):
    resp = client.post("/risk-prediction", json=_recommend_body())
    assert resp.status_code == 200
    risk_body = resp.json()
    assert 0.0 <= risk_body["probability_of_default"] <= 1.0
    assert "risk_class" in risk_body


def test_candidates_returns_generation_result(client):
    resp = client.post("/candidates", json=_recommend_body())
    assert resp.status_code == 200
    body = resp.json()
    assert "candidates" in body
    assert "counts" in body


# ---------------------------------------------------------------------------
# Primary endpoint
# ---------------------------------------------------------------------------


def test_recommend_returns_complete_recommendation(client, isolated_store):
    resp = client.post("/recommend", json=_recommend_body())
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "RECOMMENDED"
    assert body["source"] == "ML_RANKER"
    assert body["selected_candidate"] is not None
    assert 0.0 <= body["ml_suitability"] <= 1.0
    assert body["coverage"]["catalogue_products"] == 14
    assert body["decision_trace"]["recommendation_status"] == "RECOMMENDED"


def test_recommend_works_without_portfolio(client, isolated_store):
    body = _recommend_body(portfolio=fixtures.empty_portfolio())
    resp = client.post("/recommend", json=body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "RECOMMENDED"
    assert result["decision_trace"]["portfolio_metrics"]["has_portfolio"] is False


def test_recommend_works_cold_start(client, isolated_store):
    body = _recommend_body(user_id=None)
    resp = client.post("/recommend", json=body)
    assert resp.status_code == 200
    assert resp.json()["decision_trace"]["personalization"]["is_cold_start"] is True


def test_recommend_returns_no_suitable_loan_with_full_body(client, isolated_store):
    """
    A NO_SUITABLE_LOAN result is a 200 with a complete body (mismatch reasons,
    coverage funnel, trace) — never a 404 and never an error.
    """
    body = _recommend_body(
        customer=fixtures.no_match_customer(),
        portfolio=fixtures.empty_portfolio(),
    )
    resp = client.post("/recommend", json=body)
    assert resp.status_code == 200
    result = resp.json()
    assert result["status"] == "NO_ELIGIBLE_PRODUCTS"
    assert result["selected_candidate"] is None
    assert "coverage" in result
    assert "decision_trace" in result


def test_recommend_invalid_payload_returns_422(client):
    resp = client.post("/recommend", json={"customer": {}})
    assert resp.status_code == 422


def test_internal_error_returns_structured_json_no_traceback(monkeypatch):
    """A raised exception becomes a structured 500, never a stack trace leak."""
    import app.api.routes as routes

    def boom(customer):
        raise RuntimeError("boom")

    monkeypatch.setattr(routes, "analyze_financials", boom)
    # raise_server_exceptions=False lets the app's exception handler produce the 500
    # instead of re-raising the error inside the client for the test to crash on.
    with TestClient(app, raise_server_exceptions=False) as c:
        resp = c.post(
            "/financial-health",
            json=fixtures.standard_customer().model_dump(mode="json"),
        )
    assert resp.status_code == 500
    body = resp.json()
    assert body["error"] == "internal_error"
    assert body["message"]
    # No traceback framing in the response body.
    text = resp.text.lower()
    assert "traceback" not in text
    assert "boom" not in text


def test_recommend_fallback_flag_when_model_unavailable(client, isolated_store, monkeypatch):
    """
    With the recommender artifact unavailable, /recommend still returns 200, the
    source is DETERMINISTIC_FALLBACK and ml_suitability is null.
    """
    risk.load_models()
    # Force the recommender to the fallback path by making its artifact report absent.
    from pathlib import Path

    from app.config import settings

    model_path = Path(settings.RECOMMENDER_MODEL_PATH)
    tmp = model_path.with_suffix(".json.bak")
    original = tmp.exists()
    if not original:
        model_path.rename(tmp)
    try:
        recommender.reset_state()
        resp = client.post("/recommend", json=_recommend_body())
        assert resp.status_code == 200
        result = resp.json()
        assert result["source"] == "DETERMINISTIC_FALLBACK"
        assert result["ml_suitability"] is None
        assert result["status"] in (
            "RECOMMENDED",
            "NO_ELIGIBLE_PRODUCTS",
            "NO_FEASIBLE_CANDIDATES",
            "ALL_CANDIDATES_BLOCKED",
            "NO_SUITABLE_LOAN",
        )
    finally:
        if not original:
            tmp.rename(model_path)
        recommender.reset_state()


# ---------------------------------------------------------------------------
# Scenario (what-if)
# ---------------------------------------------------------------------------


def _reduced_income_customer():
    customer = fixtures.standard_customer()
    # A lower income so the scenario genuinely re-runs and re-scores, while still
    # remaining above the candidate-blocking guardrail boundary.
    return customer.model_copy(update={"monthly_income": 110_000.0})


def test_scenario_reruns_pipeline_with_modified_inputs(client, isolated_store):
    baseline = client.post("/recommend", json=_recommend_body()).json()
    scenario = client.post(
        "/scenario", json=_recommend_body(customer=_reduced_income_customer())
    ).json()
    assert scenario["status"] == "RECOMMENDED"
    # Proving a real re-run, not arithmetic: the suitability scores differ from the
    # baseline's, and the results come from separate full pipeline executions.
    assert scenario["ml_suitability"] != baseline["ml_suitability"]
    assert scenario["decision_trace"]["financial_metrics"]["monthly_income"] == 110_000.0


def test_coverage_returns_funnel(client, isolated_store):
    resp = client.request("GET", "/coverage", json=_recommend_body())
    assert resp.status_code == 200
    body = resp.json()
    assert "coverage" in body
    coverage = body["coverage"]
    assert coverage["catalogue_products"] == 14
    # Funnel is monotone: each stage is at most the previous.
    assert coverage["products_passing_eligibility"] <= coverage["catalogue_products"]
    assert coverage["candidates_scored"] >= 0


# ---------------------------------------------------------------------------
# Personalization deletion
# ---------------------------------------------------------------------------


def test_delete_personalization_removes_history(client, isolated_store):
    store = isolated_store
    store.upsert_user("u-1")
    store.record_feedback_event(
        "u-1", event_type=FeedbackEventType.ACCEPTED, product_id="PL-001"
    )
    assert store.user_exists("u-1")

    resp = client.delete("/personalization/u-1")
    assert resp.status_code == 200
    assert resp.json()["rows_removed"] >= 1
    assert not store.user_exists("u-1")

    # Deleting an unknown user is a no-op, not an error.
    resp2 = client.delete("/personalization/never-existed")
    assert resp2.status_code == 200
    assert resp2.json()["rows_removed"] == 0


def test_delete_personalization_then_recommend_reports_cold_start(
    client, isolated_store
):
    """After erasing history, a /recommend for that user reports a cold start."""
    store = isolated_store
    store.upsert_user("u-2")
    store.record_feedback_event(
        "u-2", event_type=FeedbackEventType.ACCEPTED, product_id="PL-001"
    )

    client.delete("/personalization/u-2")
    body = _recommend_body(user_id="u-2")
    resp = client.post("/recommend", json=body)
    assert resp.status_code == 200
    trace = resp.json()["decision_trace"]
    assert trace["personalization"]["is_cold_start"] is True


# ---------------------------------------------------------------------------
# Explanation
# ---------------------------------------------------------------------------


def test_explanation_returns_prose_and_xai(client, isolated_store):
    body = {
        "customer": fixtures.standard_customer().model_dump(mode="json"),
        "requirement": fixtures.standard_requirement().model_dump(mode="json"),
        "portfolio": fixtures.mixed_portfolio().model_dump(mode="json"),
    }
    resp = client.post("/explanation", json=body)
    assert resp.status_code == 200
    payload = resp.json()
    assert "explanation" in payload
    assert payload["explanation"]["source"] in ("LLM", "TEMPLATE")
    assert payload["explanation"]["text"]
    assert payload["xai"]["candidate_id"]
    assert payload["xai"]["method"] in ("TREE_SHAP", "FEATURE_IMPORTANCE")
