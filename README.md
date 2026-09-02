# Personalized Loan Recommendation System (PLRS)

An **ML-first personalized loan recommendation system**. It answers a question ordinary
eligibility checkers cannot: not just *"what loan do I qualify for?"* but *"what loan is
actually right for me?"*

- **A machine-learning model makes the recommendation** (a learned, calibrated suitability
  per candidate).
- **Deterministic code decides what is possible**, computes every rupee (EMI, interest),
  and enforces safety policy.
- A **React frontend** lets a user enter their profile and see a clear, explainable result.

> **Architecture version 2.0.** The primary ML recommender chooses the recommendation;
> deterministic code decides feasibility, computes every rupee and enforces policy.

---

## What it produces

For a customer's financial profile, optional investment portfolio, loan requirement and
declared risk appetite, the system returns:

- Loan product and lender
- Loan amount and tenure
- Monthly EMI and financing strategy (borrow / liquidate investments / hybrid)
- A personalized ML **suitability score** (`0–100%`)
- Ranked alternatives and eliminated options
- Risk information (default probability + risk class)
- **XAI** feature contributions ("why this candidate beat the others")
- A **natural-language explanation** (LLM or deterministic template)
- A full **decision trace** and a **catalogue coverage funnel**

...or, when nothing in the catalogue is genuinely suitable, an explicit
**`NO_SUITABLE_LOAN`** result with structured, machine-generated reasons explaining why.

### Recommendation statuses

The four stop points are kept deliberately distinct — each means "how far the request got":

| Status | Meaning |
|---|---|
| `RECOMMENDED` | A candidate cleared eligibility, feasibility, suitability and guardrails |
| `NO_ELIGIBLE_PRODUCTS` | No catalogue product matched on the hard rules |
| `NO_FEASIBLE_CANDIDATES` | Eligible on paper, but nothing affordable / fundable |
| `ALL_CANDIDATES_BLOCKED` | Feasible and well-scored, but every one failed a safety cap |
| `NO_SUITABLE_LOAN` | Feasible, but none scored above the suitability threshold |

The system **never manufactures a recommendation**: if no candidate clears the bar, it says
so honestly rather than returning the best of a bad set.

---

## Pipeline

```
Customer input (profile + optional portfolio + requirement + risk appetite + optional user_id)
        |
        v
[Financial Intelligence]      deterministic  (income, expenses, affordability ceiling)
[Portfolio Intelligence]      deterministic  (zero-portfolio is a first-class path)
[Personalization Context]     deterministic  (cold-start is a first-class path)
        |
        v
[Eligibility Engine]          rule-based hard constraints, per catalogue product
        |
        v   eligible products only (ineligible retained with reason codes)
[Candidate Generation Engine] deterministic enumeration of amount x tenure x strategy
        |                     -> feasibility marking -> dominance pruning
        v   feasible, non-dominated candidate configurations
[Risk Model]                  XGBoost classifier -> default probability (a FEATURE)
        |
        v
[ PRIMARY ML RECOMMENDER ]    XGBRanker -> raw margin -> calibrated suitability [0,1]
                              (this IS the ranking)
        |
        v
[Deterministic Validation]    walk the ML ranking in order; recompute EMI, re-check
[Guardrail Validation]        limits & policy caps -> first candidate that passes wins
        |
        v
[Recommendation Orchestrator] assembles result + alternatives + coverage funnel + trace
        |
        +--> [XAI]  SHAP over the recommender ("why this one, not that one")
        +--> [LLM]  natural-language explanation of the already-decided result
        |
        v
[FastAPI surface]  ->  [React frontend]
```

**Three load-bearing principles:**

1. **Candidate generation happens before ML, not after.** The model scores fully-specified
   financing configurations, so amount, tenure and strategy are *learned* choices — not
   post-hoc arithmetic.
2. **Validation happens after ML, not instead of it.** Deterministic code never re-ranks;
   it only answers pass/fail on candidates the model has already ordered.
3. **ML never computes a rupee.** EMI, interest and affordability are always deterministic.

---

## Repository layout

```
app/                 FastAPI application (backend)
  api/               Routes + catalogue loader (no business logic)
  core/              Deterministic modules (eligibility, candidates, guardrails,
                     validation, finance math, orchestrator, mismatch, diagnostics)
  ml/                Feature assembly, risk model, primary recommender (lazy-loaded)
  explain/           XAI (TreeSHAP), LLM + deterministic template, grounding guards, prompts
  personalization/   Pseudonymous history store + context
  schemas/           Pydantic models & enums (every cross-module value)
  main.py            FastAPI app + startup lifespan
  config.py          All settings, thresholds & caps (single source of config)
frontend/            Vite + React + TypeScript + Tailwind UI
tests/               Test suite (419+ assertions; 719 passing)
training/            Offline synthetic-data generation, labeling policy & model training
scripts/             memory measurement & operational tooling
models/              Trained XGBoost artifacts (gitignored)
data/                Synthetic datasets (gitignored)
spikes/              Phase-R prototypes & validated corpora
CONTEXT.md           Authoritative architecture specification
IMPLEMENTATION_PLAN.md  Phase-by-phase implementation plan
PHASE_STATUS.md      Current implementation status per phase
AGENTS.md            Operating rules for AI agents
```

---

## Prerequisites

- **Python 3.13** (see `runtime.txt`)
- **Node.js 18+** and **npm** (frontend)
- Python packages are pinned exactly in `requirements.txt` / `requirements-train.txt`.

---

## Installation

```bash
# 1. Clone
git clone https://github.com/shravani184/loan_reco_system.git
cd loan_reco_system

# 2. Python (venv recommended)
python -m venv .venv
# Windows:  .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt

# 3. Frontend
cd frontend
npm install
cd ..
```

---

## Configuration

Copy `.env.example` to `.env` and adjust. `.env` is gitignored — never commit secrets.

```bash
cp .env.example .env
```

The most important setting is `LLM_API_KEY`, only used for the natural-language
explanation. With no key, the system transparently uses the deterministic template
explainer (a fully working state — the LLM is never in the path that computes or decides
anything).

All thresholds, guardrail caps, candidate grids and weights live as typed defaults in
`app/config.py`, not in `.env`.

---

## Running the app

### Backend (FastAPI on port 8000)

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

- Interactive API docs (Swagger UI): http://127.0.0.1:8000/docs
- Health check: http://127.0.0.1:8000/health

### Frontend (Vite dev server on port 5173)

```bash
cd frontend
npm run dev
```

Open http://localhost:5173 (CORS already allows this origin). The frontend calls the
backend at `http://localhost:8000`.

> **Note:** the trained model artifacts (`models/*.json`) and the loan catalogue
> (`data/loan_products.csv`) **are committed**, so a fresh clone runs the full ML
> pipeline — no manual restore and no `DETERMINISTIC_FALLBACK`. The personalization
> database (`data/personalization.db`) stays gitignored and is created on first use.
> For a GitHub-only deploy (e.g. Render), see `render.yaml`.

---

## API endpoints

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/recommend` | The primary recommendation (full pipeline) |
| POST | `/scenario` | Re-run the full pipeline on modified inputs (what-if) |
| POST | `/explanation` | Natural-language + XAI explanation of a decision |
| GET | `/coverage` | Catalogue coverage funnel |
| GET | `/loan-products` | The loan catalogue |
| GET | `/health` | Liveness + model-degraded flags |
| POST | `/financial-health` | Financial metrics block |
| POST | `/portfolio-analysis` | Portfolio metrics block |
| POST | `/eligibility` | Per-product eligibility outcomes |
| POST | `/risk-prediction` | Risk (PD + class) for a profile |
| POST | `/candidates` | Enumerated / feasible candidate configurations |
| DELETE | `/personalization/{user_id}` | Erase pseudonymous history |

Every recommendation response carries `recommendation_status`, `recommendation_source`,
the coverage funnel and a full decision trace. See `/docs` for schemas.

---

## Running the tests

```bash
python -m pytest -q            # full suite (719 passing)
python -m pytest tests/test_api.py -q   # API contract tests
```

Tests read only from `tests/fixtures.py` — they never require a trained model.

---

## Building the frontend for production

```bash
cd frontend
npm run build       # type-check (tsc) + production bundle into dist/
```

---

## Example recommendation payload

```json
{
  "customer": {
    "monthly_income": 120000,
    "monthly_expenses": 45000,
    "existing_emi": 8000,
    "credit_score": 780,
    "employment_type": "SALARIED",
    "employment_years": 8,
    "age": 34,
    "dependents": 1
  },
  "requirement": {
    "purpose": "HOME",
    "required_amount": 1500000,
    "preferred_tenure_months": 120,
    "risk_appetite": "MODERATE"
  },
  "portfolio": { "holdings": [] }
}
```

---

## Licensing / data notice

All customers, portfolios, products and interactions are **synthetic** — generated for
demonstration and research, not real banking data. This is an illustrative tool and does not
constitute financial advice, a credit decision or an offer of credit.

---

## Status

Implemented phase-by-phase (the project is built one verifiable phase at a time; see
`IMPLEMENTATION_PLAN.md` and `PHASE_STATUS.md` for the authoritative status). Current
state spans scaffold through the FastAPI surface and the React frontend. The README at the
repository root is the project-facing overview; the detailed architecture and rules live in
`CONTEXT.md`.
