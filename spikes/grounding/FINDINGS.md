# SPIKE 2 — Grounding normalizer + corpus: FINDINGS

**Risk addressed:** CONTEXT.md §17.3 — a guard that falsely rejects valid explanations
gets switched off, and then nothing protects the user from an invented figure. Indian
numbering makes naive matching unworkable.

**Status: RESOLVED.** 85 labelled cases, perfect confusion matrix, 100% of invented
figures rejected, zero false rejections.

Verified by:

```
python3 spikes/grounding/build_corpus.py   ->  78 numeric + 7 entity cases
python3 spikes/grounding/run_corpus.py     ->  RESULT: PASS
```

---

## 1. Final confusion matrix

```
expected           GROUNDED   UNVERIFIED   UNGROUNDED
GROUNDED                 54            0            0
UNVERIFIED                0            3            0
UNGROUNDED                0            0           21

UNGROUNDED rejected       : 21/21  (100%)   REQUIRED 100%   PASS
GROUNDED falsely rejected :  0/54           REQUIRED 0      PASS
entity cases              :  7/7                            PASS
```

## 2. The rule set that works

1. **Three outcomes, not a boolean.** `GROUNDED` accept / `UNVERIFIED` accept-and-flag /
   `UNGROUNDED` reject. Only a *confident* parse with no payload match rejects.
2. **Context gating.** A token is financial when it has a currency symbol or unit, or a
   cue word within ±28 characters, or exceeds a magnitude floor of 1,000. Structural
   shapes (ordinals, `Option N`, `Section N`, `Step N`, `top N`, `N alternatives`,
   dates) are excluded by pattern before anything else runs.
3. **Confidence rule** — this is what keeps false positives at zero:
   ```
   confident = explicit unit/currency
            or value >= 1000
            or (cued and (value >= 100 or the token is a decimal))
   ```
   A bare small cued integer ("your rate is roughly 9") is deliberately **not**
   confident and degrades to `UNVERIFIED`. That is where false positives live.
4. **Interpretation on the response side, not expansion on the payload side.**
   Each token yields every reading — `8%` → {8, 0.08}, `4 years` → {48, 4},
   `6 lakh` → {600000} — and matching any one grounds it.
5. **Tolerance:** 1% relative, plus ±1 absolute **only for values ≥ 100**.
6. **Entity grounding by known vocabulary.** A catalogue name present in the response
   but absent from the payload is `UNGROUNDED`. Unknown capitalised text is never
   asserted to be a product — that keeps the check precise instead of guessing.

## 3. Four real defects the corpus caught

The corpus earned its keep immediately. Two of these would have shipped.

**(a) The number regex silently truncated every plain number.**
`\d{1,3}(?:,\d{2,3})*` matched only the first three digits when there were no commas:

```
"600000"  ->  tokens ['600', '000']
"18500"   ->  tokens ['185', '00']
"12133"   ->  tokens ['121', '33']
```

Grounded cases involving plain digits were **passing for entirely the wrong reason** —
`600` happened to match a divided form of the loan amount. Fixed by requiring at least
one comma group in the grouped-digits branch. This is the finding that most justifies
building the corpus before the guard.

**(b) The accepted set was over-expanded to the point of uselessness.**
Adding `v/1000`, `v/100000` and `round(v, -2..-5)` for every payload figure produced 68
accepted values from 13 figures, and made fabrications match real ones:

| Fabrication | Matched | Because |
|---|---|---|
| "Your EMI is Rs 15,000" | `sanctioned_limit` 15,000,000 | ÷1000 form |
| "a loan of Rs 8,00,000" | `total_repayment` 782,384 | `round(-5)` |

Fixed by removing every divided and rounded form. The response side already converts
`6 lakh` → 600000, so the accepted set only needs base units, and a writer's rounding is
covered by the 1% relative tolerance. **Detection rate went 41% → 94%.**

**(c) ±1 absolute tolerance is catastrophic for small numbers.**
It made `5 years` match a 4-year tenure and `9%` match an 8% rate. Now applied only to
values ≥ 100.

**(d) A lakh suffix is unambiguous.** Keeping the bare base as a fallback let a
fabricated "8 lakh" match the 8% interest rate. `8 lakh` is 800,000, never 8.
This was the last case standing: **94% → 100%**.

## 4. Corpus coverage

| Group | Cases |
|---|---|
| Indian numbering (`6,00,000`, `6 lakh`, `6L`, `₹6L`, `12 lakhs`, `1.5 crore`) | 14 |
| Rate duals (`8%`, `8.0%`, `0.08`, `8 percent`) | 4 |
| Tenure duals (`48 months`, `4 years`, `4 yrs`, `48-month`) | 5 |
| Structural non-figures (ordinals, `Option 2`, `top 3`, dates, counts) | 11 |
| Full realistic explanations | 5 |
| Scores (`0.86`, `86%`, credit score) | 3 |
| Tolerance edges (rounded within 1%, just outside 1%) | 4 |
| Invented figures | 21 |
| Ambiguous → `UNVERIFIED` | 3 |
| Entity grounding | 7 |
| **Total** | **85** |

## 5. Known limitations, recorded not hidden

- **Hyphenated units** are handled (`48-month`), but a fabricated hyphenated tenure was
  originally degrading to `UNVERIFIED` rather than rejecting. Fixed by allowing
  `[\s-]*` between number and unit. Other separators (en-dash, non-breaking space) are
  untested and should become corpus cases when seen.
- **Small cued figures not in the payload are accepted with a flag**, by design. A
  model writing "you would save 2 months of payments" is not rejected. This is the
  deliberate trade: a missed small fabrication costs less than a guard nobody trusts.
- **The magnitude floor of 1,000 is currency-scale-dependent.** It suits rupees. A
  multi-currency deployment would need it per currency.
- **Entity grounding needs the catalogue vocabulary passed in.** It cannot detect an
  invented lender whose name is not in the known list — it detects *substitution* from
  the catalogue, not invention from nothing. Phase 13 should pass the full catalogue.

## 6. What Phase 13 inherits

- Move `grounding_corpus.jsonl` and `entity_corpus.jsonl` into `tests/data/`. They
  become the permanent regression suite.
- Re-implement the guard against the real payload schema, keeping the six rules in §2.
  The rule set is validated; do not redesign it.
- Move `MAGNITUDE_FLOOR`, `SMALL_CUED_FLOOR`, tolerances and `CUE_WORDS` into config.
- Payload builders must emit **display strings** for every figure, and prompts must
  instruct the model to reproduce them verbatim. Prevention is doing most of the work
  here; the guard is the safety net.
- When a false positive appears in production, add a corpus case and fix the
  normalizer. Never widen a tolerance, never delete a case.

## 7. Risks remaining

- The corpus was written by the same author as the guard, so it reflects one person's
  idea of how a model phrases things. Real LLM output will contain shapes it does not
  cover; the `UNVERIFIED` bucket and its logging exist precisely to surface those.
- No live LLM was involved in this spike. Phase 13 should sample real generations
  against the guard before trusting the false-positive rate in production.
