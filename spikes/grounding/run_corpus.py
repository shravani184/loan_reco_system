"""
SPIKE 2 — run the guard against the corpus and report the confusion matrix.

REQUIRED RESULT:
  * 100% of UNGROUNDED cases rejected            (a missed invented figure is the
                                                  failure that actually matters)
  * ZERO false rejections of GROUNDED cases      (a false positive gets the guard
                                                  switched off, which is worse)

SPIKE ONLY.
"""

from __future__ import annotations

import json
import pathlib
import sys
from collections import Counter

from guard import Outcome, verify_entity_grounding, verify_numeric_grounding

HERE = pathlib.Path(__file__).parent


def load(name: str) -> list[dict]:
    return [json.loads(line) for line in (HERE / name).read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    numeric = load("grounding_corpus.jsonl")
    entities = load("entity_corpus.jsonl")

    matrix: Counter = Counter()
    false_rejections: list[dict] = []
    missed_inventions: list[dict] = []
    other_mismatches: list[dict] = []

    for case in numeric:
        result = verify_numeric_grounding(case["response"], case["payload"])
        actual = result.outcome.value
        expected = case["expected"]
        matrix[(expected, actual)] += 1
        if expected == "GROUNDED" and actual == "UNGROUNDED":
            false_rejections.append({**case, "findings": [f.text for f in result.findings if f.outcome is Outcome.UNGROUNDED]})
        elif expected == "UNGROUNDED" and actual != "UNGROUNDED":
            missed_inventions.append({**case, "actual": actual})
        elif expected != actual:
            other_mismatches.append({**case, "actual": actual})

    entity_fail = []
    for case in entities:
        result = verify_entity_grounding(
            case["response"], case["payload_entities"], case["known_entities"]
        )
        if result.outcome.value != case["expected"]:
            entity_fail.append({**case, "actual": result.outcome.value})

    print("=" * 74)
    print("NUMERIC GROUNDING — confusion matrix (expected -> actual)")
    print("=" * 74)
    labels = ["GROUNDED", "UNVERIFIED", "UNGROUNDED"]
    print(f"{'expected':<14}" + "".join(f"{c:>13}" for c in labels))
    for exp in labels:
        row = "".join(f"{matrix[(exp, act)]:>13}" for act in labels)
        print(f"{exp:<14}{row}")

    total = len(numeric)
    n_ungrounded = sum(1 for c in numeric if c["expected"] == "UNGROUNDED")
    n_grounded = sum(1 for c in numeric if c["expected"] == "GROUNDED")
    caught = n_ungrounded - len(missed_inventions)

    print()
    print(f"cases                       : {total} numeric + {len(entities)} entity")
    print(f"UNGROUNDED rejected         : {caught}/{n_ungrounded}"
          f"  ({caught / n_ungrounded:.0%})   REQUIRED 100%")
    print(f"GROUNDED falsely rejected   : {len(false_rejections)}/{n_grounded}"
          f"                REQUIRED 0")
    print(f"other mismatches (UNVERIFIED drift, non-fatal): {len(other_mismatches)}")
    print(f"entity cases failing        : {len(entity_fail)}/{len(entities)}")

    for group, title in (
        (false_rejections, "FALSE REJECTIONS (fix the normalizer, never the corpus)"),
        (missed_inventions, "MISSED INVENTIONS"),
        (other_mismatches, "OTHER MISMATCHES"),
        (entity_fail, "ENTITY FAILURES"),
    ):
        if group:
            print(f"\n--- {title} ---")
            for case in group:
                print(f"  [{case['id']}] {case.get('note','')}")
                print(f"      {case['response']}")
                if case.get("findings"):
                    print(f"      offending: {case['findings']}")
                if case.get("actual"):
                    print(f"      got {case['actual']}, expected {case['expected']}")

    ok = not false_rejections and not missed_inventions and not entity_fail
    print()
    print("RESULT:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
