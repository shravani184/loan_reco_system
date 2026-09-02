"""
SPIKE 2 — build the labelled grounding corpus.

Phase 13 moves the output to tests/data/grounding_corpus.jsonl, where it becomes the
permanent regression suite for the guard. Growing it is the fix path when a false
positive appears; loosening a tolerance is not.

SPIKE ONLY.
"""

from __future__ import annotations

import json
import pathlib

# The payload a real explanation prompt would receive. Display strings are what the
# prompt tells the model to reproduce verbatim (prevention over detection).
PAYLOAD = {
    "product_name": "Meridian Home Advantage",
    "lender": "Meridian Bank",
    "loan_amount": 600000,
    "emi": 12133,
    "tenure_months": 48,
    "interest_rate_pct": 8.0,
    "total_interest": 182384,
    "total_repayment": 782384,
    "suitability_score": 0.86,
    "credit_score": 780,
    "portfolio_value": 1200000,
    "liquidation_amount": 0,
    "sanctioned_limit": 15000000,
    "display": {
        "loan_amount": "Rs 6,00,000",
        "emi": "Rs 12,133",
        "tenure": "48 months",
        "rate": "8.0%",
    },
}

KNOWN_ENTITIES = [
    "Meridian Bank", "Meridian Home Advantage",
    "Kestrel Finance", "Northwind Bank", "Halcyon Credit", "Aurora Housing Finance",
]
PAYLOAD_ENTITIES = ["Meridian Bank", "Meridian Home Advantage"]

CASES: list[tuple[str, str, str]] = [
    # ---------------------------------------------------------------- GROUNDED
    # Indian numbering, all the same 600000
    ("GROUNDED", "Your loan amount is Rs 6,00,000.", "indian grouping"),
    ("GROUNDED", "Your loan amount is 600000.", "plain digits"),
    ("GROUNDED", "Your loan amount is 600,000.", "western grouping"),
    ("GROUNDED", "You will be borrowing 6 lakh.", "lakh word"),
    ("GROUNDED", "You will be borrowing 6 lakhs.", "lakh plural"),
    ("GROUNDED", "A loan amount of 6L has been recommended.", "L suffix"),
    ("GROUNDED", "The approved loan amount is Rs 6L.", "currency + L suffix"),
    ("GROUNDED", "Rs. 600000 is the loan amount.", "Rs. with period"),
    ("GROUNDED", "The loan amount is INR 6,00,000.", "INR prefix"),
    # portfolio 1200000
    ("GROUNDED", "Your portfolio is worth 12 lakh.", "portfolio in lakh"),
    ("GROUNDED", "Your portfolio value is Rs 12,00,000.", "portfolio grouped"),
    ("GROUNDED", "Your portfolio stands at 12 lakhs today.", "portfolio lakh plural"),
    # crore
    ("GROUNDED", "The lender's sanctioned limit is 1.5 crore.", "crore"),
    ("GROUNDED", "Their maximum exposure is Rs 1.5 crore.", "currency + crore"),
    # rates
    ("GROUNDED", "The interest rate is 8%.", "percent"),
    ("GROUNDED", "The interest rate is 8.0%.", "percent with decimal"),
    ("GROUNDED", "The interest rate works out to 0.08 as a decimal.", "rate as decimal"),
    ("GROUNDED", "You are being charged 8 percent per annum.", "percent word"),
    # tenure
    ("GROUNDED", "The tenure is 48 months.", "tenure months"),
    ("GROUNDED", "The tenure is 4 years.", "tenure years"),
    ("GROUNDED", "This is a 4 year loan.", "tenure year singular"),
    ("GROUNDED", "Repayment runs over 4 yrs.", "tenure yrs"),
    ("GROUNDED", "You have chosen a 48-month tenure.", "hyphenated month"),
    # emi / interest / repayment
    ("GROUNDED", "Your EMI is Rs 12,133 per month.", "emi"),
    ("GROUNDED", "Your monthly instalment is 12133.", "emi plain"),
    ("GROUNDED", "Total interest over the term is Rs 1,82,384.", "total interest"),
    ("GROUNDED", "You will repay Rs 7,82,384 in total.", "total repayment"),
    ("GROUNDED", "Total repayment comes to 782384.", "total repayment plain"),
    # scores
    ("GROUNDED", "The suitability score for this option is 0.86.", "suitability decimal"),
    ("GROUNDED", "Your credit score of 780 clears their requirement.", "credit score"),
    # structural numbers that must NOT be treated as figures
    ("GROUNDED", "Here are your 3 alternatives.", "count of alternatives"),
    ("GROUNDED", "We compared 5 options for you.", "count of options"),
    ("GROUNDED", "This is our 1st recommendation.", "ordinal 1st"),
    ("GROUNDED", "The 2nd option costs more.", "ordinal 2nd"),
    ("GROUNDED", "Option 2 has a shorter tenure.", "Option N"),
    ("GROUNDED", "See Section 7 for the full breakdown.", "Section N"),
    ("GROUNDED", "Step 3: compare the final offers.", "Step N"),
    ("GROUNDED", "We reviewed the top 3 lenders.", "top N"),
    ("GROUNDED", "Rates were last revised on 12/03/2026.", "slash date"),
    ("GROUNDED", "Effective from 2026-03-12 onwards.", "iso date"),
    ("GROUNDED", "We found 4 products and 2 lenders that fit.", "two counts"),
    # realistic full explanations
    ("GROUNDED",
     "We recommend the Meridian Home Advantage: a loan amount of Rs 6,00,000 over "
     "48 months at 8.0%, giving an EMI of Rs 12,133. Total interest is Rs 1,82,384 "
     "and total repayment Rs 7,82,384.",
     "full explanation"),
    ("GROUNDED",
     "Borrowing 6 lakh over 4 years at 8% keeps your EMI at Rs 12,133, which your "
     "disposable income comfortably covers. Here are your 3 alternatives.",
     "mixed forms + structural"),
    ("GROUNDED",
     "With a credit score of 780 and a portfolio of 12 lakh, this option scores 0.86 "
     "on suitability. It is our 1st recommendation of 3.",
     "scores + ordinal"),
    ("GROUNDED",
     "Meridian Bank has sanctioned up to Rs 1.5 crore; you are drawing Rs 6,00,000 "
     "of that over 4 years.",
     "crore + amount + tenure"),
    ("GROUNDED",
     "Your EMI of 12133 against total repayment of 782384 means you pay 182384 in "
     "interest across 48 months.",
     "all plain digits"),

    # -------------------------------------------------------------- UNGROUNDED
    ("UNGROUNDED", "Your EMI is Rs 15,000 per month.", "invented emi"),
    ("UNGROUNDED", "Your EMI works out to 18500.", "invented emi plain"),
    ("UNGROUNDED", "Total interest of Rs 2,50,000 applies.", "invented interest"),
    ("UNGROUNDED", "The interest rate is 9.5%.", "invented rate"),
    ("UNGROUNDED", "You are being charged 11 percent per annum.", "invented rate word"),
    ("UNGROUNDED", "The tenure is 60 months.", "invented tenure months"),
    ("UNGROUNDED", "Repayment runs over 5 years.", "invented tenure years"),
    ("UNGROUNDED", "We recommend a loan of Rs 8,00,000.", "invented amount"),
    ("UNGROUNDED", "We recommend borrowing 8 lakh.", "invented amount lakh"),
    ("UNGROUNDED", "Your portfolio is worth 20 lakh.", "invented portfolio"),
    ("UNGROUNDED", "Total repayment comes to Rs 9,00,000.", "invented repayment"),
    ("UNGROUNDED", "The suitability score for this option is 0.95.", "invented score"),
    ("UNGROUNDED", "Your credit score of 810 clears their requirement.", "invented credit score"),
    ("UNGROUNDED", "You could save Rs 45,000 by switching.", "invented saving"),
    ("UNGROUNDED", "A processing fee of Rs 7,500 applies.", "figure absent from payload"),
    ("UNGROUNDED",
     "We recommend the Meridian Home Advantage: Rs 6,00,000 over 48 months at 8.0%, "
     "with an EMI of Rs 13,900.",
     "mostly grounded, one invented figure"),
    ("UNGROUNDED",
     "Borrowing 6 lakh over 4 years at 8% gives an EMI of Rs 12,133 and total "
     "interest of Rs 3,10,000.",
     "one invented figure late in the text"),

    # -------------------------------------------------------------- UNVERIFIED
    ("UNVERIFIED", "Your rate is roughly 9 before adjustments.", "small cued number, no unit"),
    ("UNVERIFIED", "The tenure is about 5 on the shorter option.", "bare cued small number"),
    ("UNVERIFIED", "Interest lands near 7 on this product.", "ambiguous bare interest figure"),
# ------------------------------------------- adversarial / tolerance edges
    ("GROUNDED", "The amount sanctioned is Rs 6,00,000/- in total.", "trailing /-"),
    ("GROUNDED", "Your EMI is 12,133 a month.", "comma-grouped emi, no currency"),
    ("GROUNDED", "Interest paid comes to 1,82,384.", "comma-grouped interest"),
    ("GROUNDED", "This option scores 86% on suitability.", "score as percent"),
    ("GROUNDED", "You will pay about Rs 1,82,000 in interest.", "rounded within 1%"),
    ("GROUNDED", "Total outgo is roughly Rs 7,82,000.", "rounded repayment within 1%"),
    ("GROUNDED", "Nothing is liquidated, so the cost there is Rs 0.", "zero figure"),
    ("GROUNDED", "You have chosen a 48-month term.", "hyphenated unit, grounded"),
    ("UNGROUNDED", "Your EMI is Rs 12,500 a month.", "close but outside 1% tolerance"),
    ("UNGROUNDED", "The rate offered is 8.5%.", "rate just outside tolerance"),
    ("UNGROUNDED", "You have chosen a 60-month term.", "hyphenated unit, invented"),
    ("UNGROUNDED", "Interest paid comes to 1,92,384.", "invented, comma-grouped"),
]


def main() -> None:
    out = pathlib.Path(__file__).parent / "grounding_corpus.jsonl"
    with out.open("w", encoding="utf-8") as fh:
        for index, (expected, response, note) in enumerate(CASES, 1):
            fh.write(
                json.dumps(
                    {
                        "id": f"G{index:03d}",
                        "expected": expected,
                        "response": response,
                        "note": note,
                        "payload": PAYLOAD,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    entity_out = pathlib.Path(__file__).parent / "entity_corpus.jsonl"
    entity_cases = [
        ("GROUNDED", "We recommend the Meridian Home Advantage from Meridian Bank.", "both in payload"),
        ("GROUNDED", "Meridian Bank offers this at 8.0%.", "lender only"),
        ("GROUNDED", "This product suits your profile well.", "no entity named"),
        ("UNGROUNDED", "Kestrel Finance offers a better rate.", "lender not in payload"),
        ("UNGROUNDED", "Consider Northwind Bank instead of Meridian Bank.", "one invented lender"),
        ("UNGROUNDED", "Aurora Housing Finance would also lend to you.", "invented lender"),
        ("UNGROUNDED", "Halcyon Credit has a similar product.", "invented lender"),
    ]
    with entity_out.open("w", encoding="utf-8") as fh:
        for index, (expected, response, note) in enumerate(entity_cases, 1):
            fh.write(
                json.dumps(
                    {
                        "id": f"E{index:03d}",
                        "expected": expected,
                        "response": response,
                        "note": note,
                        "payload_entities": PAYLOAD_ENTITIES,
                        "known_entities": KNOWN_ENTITIES,
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    print(f"wrote {len(CASES)} numeric cases -> {out.name}")
    print(f"wrote {len(entity_cases)} entity cases -> {entity_out.name}")


if __name__ == "__main__":
    main()
