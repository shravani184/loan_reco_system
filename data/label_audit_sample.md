# Label audit sample

**SYNTHETIC.** These customers do not exist and these labels are produced by
`training/labeling.py`, not observed from anyone. Regenerated on every dataset
build.

Read this before trusting the dataset. The invariant suite proves the labels are
*self-consistent*; only a person can notice that a self-consistent label is one
no human would agree with.

Policy version: `2.0.0`

---

## 1. `syn-0078`

- income ₹453,200/month, expenses ₹173,400, existing EMI ₹67,700
- disposable ₹212,100, EMI ceiling ₹106,050, health EXCELLENT
- portfolio ₹0 (none)
- wants ₹1,008,000 for MEDICAL over 36 months, appetite AGGRESSIVE
- 30 candidates; HAS a good option

  BEST   grade 3 | score 0.836 | stress-fail 16%
      borrow ₹1,008,000 from Sundial Credit Union (ML-501) over 48 months at ₹26,175/month
      total interest ₹248,392, portfolio left ₹0

  WORST  grade 0 | score 0.653 | stress-fail 21%
      borrow ₹604,800 from Anvil Credit (PL-401) over 12 months at ₹53,991/month
      total interest ₹43,089, portfolio left ₹0

## 2. `syn-0122`

- income ₹78,500/month, expenses ₹31,000, existing EMI ₹12,700
- disposable ₹34,800, EMI ceiling ₹17,400, health EXCELLENT
- portfolio ₹2,791,100 (CONSERVATIVE)
- wants ₹1,865,000 for HOME over 120 months, appetite MODERATE
- 63 candidates; HAS a good option

  BEST   grade 3 | score 0.728 | stress-fail 11%
      pay ₹1,865,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹922,768

  WORST  grade 0 | score 0.444 | stress-fail 30%
      borrow ₹671,400 from Sundial Credit Union (HL-103) over 48 months at ₹17,109/month, selling ₹447,600 of holdings
      total interest ₹149,840, portfolio left ₹2,343,500

## 3. `syn-0232`

- income ₹76,600/month, expenses ₹41,700, existing EMI ₹6,400
- disposable ₹28,500, EMI ceiling ₹14,250, health GOOD
- portfolio ₹0 (none)
- wants ₹224,000 for PERSONAL over 12 months, appetite AGGRESSIVE
- 17 candidates; HAS a good option

  BEST   grade 3 | score 0.792 | stress-fail 24%
      borrow ₹224,000 from Cobalt Money (PL-402) over 48 months at ₹6,291/month
      total interest ₹77,968, portfolio left ₹0

  WORST  grade 0 | score 0.593 | stress-fail 32%
      borrow ₹134,400 from Harbourline Finance (PL-403) over 12 months at ₹12,315/month
      total interest ₹13,385, portfolio left ₹0

## 4. `syn-0170`

- income ₹108,300/month, expenses ₹67,800, existing EMI ₹14,600
- disposable ₹25,900, EMI ceiling ₹12,950, health FAIR
- portfolio ₹11,237,900 (CONSERVATIVE)
- wants ₹326,000 for PERSONAL over 24 months, appetite CONSERVATIVE
- 27 candidates; HAS a good option

  BEST   grade 3 | score 0.849 | stress-fail 28%
      pay ₹326,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹10,911,900

  WORST  grade 0 | score 0.539 | stress-fail 34%
      borrow ₹117,360 from Harbourline Finance (PL-403) over 12 months at ₹10,754/month, selling ₹78,240 of holdings
      total interest ₹11,688, portfolio left ₹11,159,660

## 5. `syn-0291`

- income ₹46,600/month, expenses ₹33,200, existing EMI ₹5,400
- disposable ₹8,000, EMI ceiling ₹4,000, health FAIR
- portfolio ₹980,100 (BALANCED)
- wants ₹262,000 for PERSONAL over 48 months, appetite AGGRESSIVE
- 21 candidates; HAS a good option

  BEST   grade 2 | score 0.836 | stress-fail 34% | DEMOTED
      pay ₹262,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹716,939

  WORST  grade 0 | score 0.568 | stress-fail 34%
      borrow ₹125,760 from Cobalt Money (PL-402) over 48 months at ₹3,532/month, selling ₹31,440 of holdings
      total interest ₹43,774, portfolio left ₹948,660

## 6. `syn-0149`

- income ₹190,300/month, expenses ₹82,600, existing EMI ₹17,500
- disposable ₹90,200, EMI ceiling ₹45,100, health EXCELLENT
- portfolio ₹11,464,900 (CONSERVATIVE)
- wants ₹2,857,000 for BUSINESS over 36 months, appetite CONSERVATIVE
- 44 candidates; HAS a good option

  BEST   grade 3 | score 0.827 | stress-fail 8%
      pay ₹2,857,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹8,596,412

  WORST  grade 0 | score 0.456 | stress-fail 27%
      borrow ₹1,714,200 from Ironvale Capital (BL-602) over 60 months at ₹41,459/month
      total interest ₹773,319, portfolio left ₹11,464,900

## 7. `syn-0284`

- income ₹133,200/month, expenses ₹36,500, existing EMI ₹11,900
- disposable ₹84,800, EMI ceiling ₹42,400, health EXCELLENT
- portfolio ₹566,300 (GROWTH)
- wants ₹1,810,000 for VEHICLE over 48 months, appetite MODERATE
- 23 candidates; HAS a good option

  BEST   grade 3 | score 0.671 | stress-fail 15%
      borrow ₹1,810,000 from Meridian Bank (VL-201) over 84 months at ₹29,490/month
      total interest ₹667,160, portfolio left ₹566,300

  WORST  grade 0 | score 0.296 | stress-fail 22%
      borrow ₹868,800 from Meridian Bank (VL-201) over 24 months at ₹39,851/month, selling ₹217,200 of holdings
      total interest ₹87,613, portfolio left ₹345,592

## 8. `syn-0081`

- income ₹48,400/month, expenses ₹30,900, existing EMI ₹4,200
- disposable ₹13,300, EMI ceiling ₹6,650, health GOOD
- portfolio ₹5,920,500 (AGGRESSIVE)
- wants ₹765,000 for VEHICLE over 36 months, appetite CONSERVATIVE
- 18 candidates; HAS a good option

  BEST   grade 3 | score 0.622 | stress-fail 26%
      pay ₹765,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹5,130,817

  WORST  grade 0 | score 0.326 | stress-fail 34%
      borrow ₹183,600 from Harbourline Finance (VL-202) over 36 months at ₹6,076/month, selling ₹275,400 of holdings
      total interest ₹35,145, portfolio left ₹5,645,100

## 9. `syn-0007`

- income ₹124,100/month, expenses ₹44,600, existing EMI ₹300
- disposable ₹79,200, EMI ceiling ₹39,600, health EXCELLENT
- portfolio ₹13,728,600 (AGGRESSIVE)
- wants ₹1,561,000 for VEHICLE over 24 months, appetite MODERATE
- 46 candidates; HAS a good option

  BEST   grade 3 | score 0.694 | stress-fail 2%
      borrow ₹561,960 from Harbourline Finance (VL-202) over 60 months at ₹12,430/month, selling ₹374,640 of holdings
      total interest ₹183,817, portfolio left ₹13,353,960

  WORST  grade 0 | score 0.414 | stress-fail 20%
      borrow ₹374,640 from Harbourline Finance (VL-202) over 12 months at ₹33,243/month, selling ₹561,960 of holdings
      total interest ₹24,270, portfolio left ₹13,166,640

## 10. `syn-0165`

- income ₹54,900/month, expenses ₹24,200, existing EMI ₹5,700
- disposable ₹25,000, EMI ceiling ₹12,500, health EXCELLENT
- portfolio ₹701,600 (CONSERVATIVE)
- wants ₹496,000 for PERSONAL over 48 months, appetite MODERATE
- 64 candidates; HAS a good option

  BEST   grade 3 | score 0.684 | stress-fail 10%
      pay ₹496,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹200,024

  WORST  grade 0 | score 0.483 | stress-fail 26%
      borrow ₹119,040 from Cobalt Money (PL-402) over 12 months at ₹10,772/month, selling ₹178,560 of holdings
      total interest ₹10,229, portfolio left ₹522,299

## 11. `syn-0210`

- income ₹62,200/month, expenses ₹44,600, existing EMI ₹3,200
- disposable ₹14,400, EMI ceiling ₹7,200, health FAIR
- portfolio ₹299,700 (CONSERVATIVE)
- wants ₹849,000 for EDUCATION over 24 months, appetite CONSERVATIVE
- 13 candidates; NO good option

  BEST   grade 1 | score 0.533 | stress-fail 34% | DEMOTED
      borrow ₹509,400 from Kestrel Housing Finance (EL-301) over 120 months at ₹6,384/month
      total interest ₹256,697, portfolio left ₹299,700

  WORST  grade 0 | score 0.352 | stress-fail 34%
      borrow ₹305,640 from Sundial Credit Union (EL-302) over 60 months at ₹6,569/month, selling ₹203,760 of holdings
      total interest ₹88,524, portfolio left ₹95,547

## 12. `syn-0275`

- income ₹24,800/month, expenses ₹12,700, existing EMI ₹500
- disposable ₹11,600, EMI ceiling ₹5,800, health EXCELLENT
- portfolio ₹942,500 (CONSERVATIVE)
- wants ₹627,000 for EDUCATION over 84 months, appetite AGGRESSIVE
- 32 candidates; HAS a good option

  BEST   grade 3 | score 0.787 | stress-fail 8%
      pay ₹627,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹314,403

  WORST  grade 0 | score 0.512 | stress-fail 28%
      borrow ₹225,720 from Sundial Credit Union (EL-302) over 48 months at ₹5,779/month, selling ₹150,480 of holdings
      total interest ₹51,681, portfolio left ₹792,020

## 13. `syn-0301`

- income ₹55,500/month, expenses ₹29,800, existing EMI ₹7,400
- disposable ₹18,300, EMI ceiling ₹9,150, health GOOD
- portfolio ₹0 (none)
- wants ₹583,000 for EDUCATION over 60 months, appetite AGGRESSIVE
- 14 candidates; HAS a good option

  BEST   grade 3 | score 0.641 | stress-fail 30%
      borrow ₹466,400 from Kestrel Housing Finance (EL-301) over 120 months at ₹5,845/month
      total interest ₹235,029, portfolio left ₹0

  WORST  grade 0 | score 0.540 | stress-fail 34%
      borrow ₹349,800 from Sundial Credit Union (EL-302) over 48 months at ₹8,956/month
      total interest ₹80,091, portfolio left ₹0

## 14. `syn-0163`

- income ₹391,700/month, expenses ₹135,900, existing EMI ₹23,400
- disposable ₹232,400, EMI ceiling ₹116,200, health EXCELLENT
- portfolio ₹57,500 (CONSERVATIVE)
- wants ₹904,000 for MEDICAL over 12 months, appetite MODERATE
- 30 candidates; HAS a good option

  BEST   grade 3 | score 0.662 | stress-fail 2%
      borrow ₹904,000 from Sundial Credit Union (ML-501) over 48 months at ₹23,474/month
      total interest ₹222,764, portfolio left ₹57,500

  WORST  grade 0 | score 0.482 | stress-fail 8%
      borrow ₹542,400 from Anvil Credit (PL-401) over 12 months at ₹48,420/month
      total interest ₹38,643, portfolio left ₹57,500

## 15. `syn-0138`

- income ₹223,600/month, expenses ₹109,500, existing EMI ₹38,600
- disposable ₹75,500, EMI ceiling ₹37,750, health GOOD
- portfolio ₹0 (none)
- wants ₹1,314,000 for BUSINESS over 60 months, appetite AGGRESSIVE
- 26 candidates; HAS a good option

  BEST   grade 3 | score 0.679 | stress-fail 29%
      borrow ₹1,314,000 from Anvil Credit (BL-601) over 84 months at ₹24,083/month
      total interest ₹708,988, portfolio left ₹0

  WORST  grade 0 | score 0.533 | stress-fail 34%
      borrow ₹788,400 from Anvil Credit (BL-601) over 24 months at ₹37,575/month
      total interest ₹113,391, portfolio left ₹0

## 16. `syn-0308`

- income ₹87,400/month, expenses ₹58,600, existing EMI ₹12,200
- disposable ₹16,600, EMI ceiling ₹8,300, health FAIR
- portfolio ₹1,002,000 (CONSERVATIVE)
- wants ₹213,000 for PERSONAL over 48 months, appetite AGGRESSIVE
- 49 candidates; HAS a good option

  BEST   grade 2 | score 0.839 | stress-fail 34% | DEMOTED
      pay ₹213,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹788,367

  WORST  grade 0 | score 0.585 | stress-fail 34%
      borrow ₹76,680 from Cobalt Money (PL-402) over 12 months at ₹6,939/month, selling ₹51,120 of holdings
      total interest ₹6,589, portfolio left ₹950,880

## 17. `syn-0168`

- income ₹111,500/month, expenses ₹44,400, existing EMI ₹17,600
- disposable ₹49,500, EMI ceiling ₹24,750, health EXCELLENT
- portfolio ₹6,945,600 (CONSERVATIVE)
- wants ₹1,462,000 for EDUCATION over 48 months, appetite CONSERVATIVE
- 59 candidates; HAS a good option

  BEST   grade 3 | score 0.800 | stress-fail 11%
      pay ₹1,462,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹5,483,600

  WORST  grade 0 | score 0.466 | stress-fail 30%
      borrow ₹526,320 from Sundial Credit Union (EL-302) over 24 months at ₹24,409/month, selling ₹350,880 of holdings
      total interest ₹59,487, portfolio left ₹6,594,720

## 18. `syn-0038`

- income ₹249,800/month, expenses ₹99,800, existing EMI ₹14,900
- disposable ₹135,100, EMI ceiling ₹67,550, health EXCELLENT
- portfolio ₹3,159,300 (AGGRESSIVE)
- wants ₹1,252,000 for BUSINESS over 48 months, appetite MODERATE
- 45 candidates; HAS a good option

  BEST   grade 3 | score 0.613 | stress-fail 1%
      pay ₹1,252,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹1,849,719

  WORST  grade 0 | score 0.361 | stress-fail 23%
      borrow ₹600,960 from Cobalt Money (BL-603) over 12 months at ₹55,239/month, selling ₹150,240 of holdings
      total interest ₹61,909, portfolio left ₹3,009,060

## 19. `syn-0086`

- income ₹68,700/month, expenses ₹27,000, existing EMI ₹10,300
- disposable ₹31,400, EMI ceiling ₹15,700, health EXCELLENT
- portfolio ₹5,903,900 (GROWTH)
- wants ₹384,000 for MEDICAL over 60 months, appetite MODERATE
- 84 candidates; HAS a good option

  BEST   grade 3 | score 0.854 | stress-fail 10%
      pay ₹384,000 from holdings and borrow nothing
      total interest ₹0, portfolio left ₹5,519,900

  WORST  grade 0 | score 0.540 | stress-fail 26%
      borrow ₹138,240 from Anvil Credit (PL-401) over 12 months at ₹12,341/month, selling ₹92,160 of holdings
      total interest ₹9,849, portfolio left ₹5,811,740

## 20. `syn-0056`

- income ₹25,300/month, expenses ₹16,100, existing EMI ₹4,100
- disposable ₹5,100, EMI ceiling ₹2,550, health FAIR
- portfolio ₹0 (none)
- wants ₹117,000 for PERSONAL over 36 months, appetite CONSERVATIVE
- 3 candidates; NO good option

  BEST   grade 1 | score 0.528 | stress-fail 34% | DEMOTED
      borrow ₹70,200 from Cobalt Money (PL-402) over 48 months at ₹1,972/month
      total interest ₹24,435, portfolio left ₹0

  WORST  grade 0 | score 0.482 | stress-fail 34% | DEMOTED
      borrow ₹70,200 from Harbourline Finance (PL-403) over 36 months at ₹2,534/month
      total interest ₹21,038, portfolio left ₹0
