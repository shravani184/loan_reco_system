"""
Serving memory checkpoint. The FIRST of three (P11, P13, P17).

Reports resident memory after import, after load_models(), and after one scoring call,
against MEMORY_CEILING_MB from config.

MEASURED IN A SUBPROCESS WITH TRAINING DEPENDENCIES BLOCKED. This matters more than it
looks. xgboost imports pandas and scikit-learn WHEN THEY ARE INSTALLED, and they are
installed in any development environment because training needs them. Measuring in
this process would therefore measure the development machine, not the deployment
target, where requirements.txt excludes both. The blocker below makes them
unimportable, which is exactly the serving target's situation.

Run:

    python -m scripts.measure_memory
"""

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PROBE = r"""
import json, os, sys

class _Blocker:
    BLOCKED = ("pandas", "sklearn", "shap", "matplotlib")

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BLOCKED:
            raise ImportError(name + " is not installed on the serving target")
        return None


sys.meta_path.insert(0, _Blocker())

import psutil

process = psutil.Process(os.getpid())


def rss_mb():
    return round(process.memory_info().rss / (1024 * 1024), 1)


baseline = rss_mb()

# --- after import: the whole serving surface, as the API will import it
from app.config import settings
import app.schemas
import app.ml.features
import app.ml.risk
import app.ml.recommender
import app.core.candidates
import app.core.eligibility
import app.core.guardrails
import app.personalization.context
import app.explain.grounding
import app.explain.llm
import app.explain.prompts
import app.explain.templates
import app.explain.xai
import fastapi
import uvicorn
import numpy
import xgboost

after_import = rss_mb()

# --- after load_models(): both boosters, the knots and the encoder dict
app.ml.risk.load_models()
app.ml.recommender.load_models()
after_load = rss_mb()

# --- after one full scoring call
from app.core.candidates import generate_candidates
from app.core.eligibility import check_eligibility
from app.core.financial import analyze_financials
from app.core.portfolio import analyze_portfolio
from app.schemas.enums import EligibilityStatus
from tests import fixtures

customer = fixtures.standard_customer()
requirement = fixtures.standard_requirement()
catalogue = fixtures.mock_catalogue()
financial = analyze_financials(customer)
portfolio = analyze_portfolio(fixtures.mixed_portfolio())
risk = app.ml.risk.predict_risk(customer, financial, portfolio, requirement)
eligible = {
    result.product_id
    for result in check_eligibility(customer, financial, requirement, catalogue)
    if result.status is EligibilityStatus.ELIGIBLE
}
candidates = [
    candidate
    for candidate in generate_candidates(
        requirement, financial, portfolio,
        [p for p in catalogue if p.product_id in eligible],
    ).candidates
    if candidate.feasible
]
result = app.ml.recommender.score_candidates(
    customer, financial, portfolio, fixtures.neutral_personalization(), requirement,
    {p.product_id: p for p in catalogue}, candidates, risk.probability_of_default,
)
after_scoring = rss_mb()

# --- after one XAI + explanation call (memory checkpoint 2, P13)
from app.explain.xai import explain_recommendation_choice

xai = explain_recommendation_choice(
    customer, financial, portfolio, fixtures.neutral_personalization(), requirement,
    {p.product_id: p for p in catalogue}, result.scored_candidates,
    risk.probability_of_default,
)
after_xai = rss_mb()

leaked = sorted(
    {m.split(".")[0] for m in sys.modules if m.split(".")[0] in _Blocker.BLOCKED}
)

print(json.dumps({
    "baseline_mb": baseline,
    "after_import_mb": after_import,
    "after_load_models_mb": after_load,
    "after_scoring_mb": after_scoring,
    "after_xai_mb": after_xai,
    "xai_method": xai.method.value,
    "xai_degraded": xai.degraded,
    "ceiling_mb": settings.MEMORY_CEILING_MB,
    "candidates_scored": len(result.scored_candidates),
    "source": result.source.value,
    "risk_imputed": risk.imputed,
    "forbidden_modules": leaked,
}))
"""


def main() -> int:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print("memory probe failed:\n" + result.stderr[-3000:])
        return 2

    report = json.loads(result.stdout.strip().splitlines()[-1])
    ceiling = report["ceiling_mb"]
    peak = report["after_xai_mb"]

    print("SERVING MEMORY — measured with pandas/sklearn/shap BLOCKED,")
    print("i.e. as the deployment target actually runs.\n")
    print(f"  baseline (python + psutil)   {report['baseline_mb']:>7.1f} MB")
    print(f"  after import                 {report['after_import_mb']:>7.1f} MB")
    print(f"  after load_models()          {report['after_load_models_mb']:>7.1f} MB")
    print(f"  after one scoring call       {report['after_scoring_mb']:>7.1f} MB")
    print(f"  after one XAI explanation    {report['after_xai_mb']:>7.1f} MB")
    print(f"  ceiling (MEMORY_CEILING_MB)  {ceiling:>7.1f} MB")
    print(
        f"  headroom                     {ceiling - peak:>7.1f} MB "
        f"({(1 - peak / ceiling) * 100:.0f}% of the ceiling unused)"
    )
    print(
        f"\n  scored {report['candidates_scored']} candidates via "
        f"{report['source']}; risk imputed: {report['risk_imputed']}"
    )
    print(
        f"  XAI via {report['xai_method']} (degraded: {report['xai_degraded']})"
    )
    print(f"  forbidden modules loaded: {report['forbidden_modules'] or 'none'}")

    if report["forbidden_modules"]:
        print("\nFAIL — a training dependency reached the serving import graph.")
        return 1
    if peak > ceiling:
        print(f"\nFAIL — {peak} MB exceeds the {ceiling} MB ceiling.")
        return 1
    print("\nPASS — within the configured ceiling.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
