"""
The memory budget, as a test rather than a convention (CONTEXT.md 17.2, AGENTS.md 14).

Phase R measured the serving dependency set at 186.3 MB resident, against 310.7 MB
with pandas + scikit-learn + shap added — a 124.4 MB saving that only exists while
app/ stays clean. This test is what keeps it clean, and it exists from Phase 0 so no
module can ever be written against a forbidden import in the first place.

It runs in a SUBPROCESS deliberately. Checking sys.modules in-process would be
polluted by anything pytest or a sibling test module (training tests, offline
analysis) had already imported, which would make the check pass for the wrong
reason.
"""

import json
import subprocess
import sys
from pathlib import Path

FORBIDDEN = ("pandas", "sklearn", "shap", "matplotlib")

REPO_ROOT = Path(__file__).resolve().parent.parent

PROBE = """
import json, sys

import app
import app.config
import app.schemas
import app.schemas.enums

forbidden = ("pandas", "sklearn", "shap", "matplotlib")
found = sorted(
    name
    for name in sys.modules
    if any(name == f or name.startswith(f + ".") for f in forbidden)
)
print(json.dumps(found))
"""


def _imported_forbidden_modules() -> list[str]:
    result = subprocess.run(
        [sys.executable, "-c", PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(result.stdout.strip().splitlines()[-1])


def test_serving_import_graph_contains_no_training_dependency():
    found = _imported_forbidden_modules()
    assert found == [], (
        "app/ imported a training-only dependency: "
        f"{found}. This is the serving memory budget, not a style preference. "
        "Move the import into training/, or into a lazily-imported function."
    )


SERVING_ENVIRONMENT_PROBE = """
import sys

# Simulate the SERVING target, where pandas / scikit-learn / shap / matplotlib are NOT
# installed because requirements.txt excludes them. Locally they ARE installed for
# training, and xgboost imports them opportunistically when present — so without this
# blocker the check would pass or fail for reasons that have nothing to do with the
# deployed service.
class _Blocker:
    BLOCKED = ("pandas", "sklearn", "shap", "matplotlib")

    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in self.BLOCKED:
            raise ImportError(name + " is not installed on the serving target")
        return None


sys.meta_path.insert(0, _Blocker())

import numpy
import xgboost

import app
import app.config
import app.schemas
import app.ml.features

booster = xgboost.Booster()
row = numpy.zeros((1, len(app.ml.features.RISK_FEATURE_COLUMNS)), dtype=numpy.float64)
matrix = xgboost.DMatrix(row)

forbidden = sorted(
    {m.split(".")[0] for m in sys.modules if m.split(".")[0] in _Blocker.BLOCKED}
)
print("OK" if not forbidden else "LEAKED:" + ",".join(forbidden))
"""


def test_the_serving_stack_works_without_any_training_dependency():
    """
    THE MEMORY BUDGET, TESTED AS THE DEPLOYED SERVICE ACTUALLY RUNS.

    xgboost imports pandas and scikit-learn WHEN THEY ARE PRESENT. They are present in
    this development environment because training needs them, so simply inspecting
    sys.modules here would show a leak that does not exist in production. This probe
    makes them unimportable — exactly the serving target's situation — and asserts that
    numpy, xgboost and the application still import and that a DMatrix can be built.

    If this ever fails, the serving image genuinely needs pandas or sklearn and Phase
    R's 186 MB measurement no longer holds.
    """
    result = subprocess.run(
        [sys.executable, "-c", SERVING_ENVIRONMENT_PROBE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "the serving stack cannot import without training dependencies:\n"
        + result.stderr[-2000:]
    )
    assert result.stdout.strip().splitlines()[-1] == "OK", result.stdout


def test_app_does_not_import_from_training_package():
    """training/ is offline code. Nothing under app/ may import it."""
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import training" in text or "from training" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"app/ imports from training/: {offenders}"


def test_app_does_not_import_from_spikes():
    """Spikes are throwaway prototypes (AGENTS.md section 15)."""
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "import spikes" in text or "from spikes" in text:
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"app/ imports from spikes/: {offenders}"


def test_no_os_getenv_outside_config():
    """AGENTS.md section 4: never call os.getenv outside app/config.py."""
    offenders = []
    for path in (REPO_ROOT / "app").rglob("*.py"):
        if path.name == "config.py":
            continue
        if "os.getenv" in path.read_text(encoding="utf-8"):
            offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == [], f"os.getenv called outside app/config.py: {offenders}"


def test_requirements_are_exactly_pinned():
    """An unpinned dependency breaks the deployment phase and is a defect."""
    for filename in ("requirements.txt", "requirements-train.txt"):
        for line in (REPO_ROOT / filename).read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            assert "==" in line, f"{filename}: unpinned dependency {line!r}"


def test_serving_requirements_exclude_training_dependencies():
    text = (REPO_ROOT / "requirements.txt").read_text(encoding="utf-8")
    lines = [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    for name in ("pandas", "scikit-learn", "shap", "matplotlib"):
        assert not any(line.startswith(name) for line in lines), (
            f"{name} is training-only and must not appear in requirements.txt"
        )
