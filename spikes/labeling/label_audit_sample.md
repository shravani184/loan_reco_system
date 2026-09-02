# Label audit sample (SPIKE)

Twenty synthetic customers with their best- and worst-labelled candidates.
Invariants catch logical flaws; this file is for catching labels that are
self-consistent but that no human would call sensible.

## Customer 1
- income Rs 27,673/mo, expenses Rs 18,200, existing EMI Rs 2,127, disposable Rs 7,346
- appetite CONSERVATIVE, credit score 850, portfolio Rs 0 (liquid Rs 0 / volatile Rs 0)
- needs Rs 262,768; 1 candidates generated

  BEST  grade 1 | VEH-A Rs 262,768 borrowed + Rs 0 liquidated, 84m, EMI Rs 4,281, interest Rs 96,855, raw 0.531, DEMOTED (stress 34%)
  WORST grade 1 | VEH-A Rs 262,768 borrowed + Rs 0 liquidated, 84m, EMI Rs 4,281, raw 0.531

## Customer 2
- income Rs 239,248/mo, expenses Rs 134,165, existing EMI Rs 33,015, disposable Rs 72,069
- appetite AGGRESSIVE, credit score 827, portfolio Rs 11,647,383 (liquid Rs 5,544,444 / volatile Rs 6,102,939)
- needs Rs 7,801,795; 17 candidates generated

  BEST  grade 2 | NO_LOAN Rs 0 borrowed + Rs 7,801,795 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.570
  WORST grade 0 | BUS-A Rs 1,560,359 borrowed + Rs 6,241,436 liquidated, 48m, EMI Rs 41,282, raw 0.317

## Customer 3
- income Rs 50,448/mo, expenses Rs 24,995, existing EMI Rs 3,565, disposable Rs 21,888
- appetite CONSERVATIVE, credit score 828, portfolio Rs 1,464,120 (liquid Rs 1,000,259 / volatile Rs 463,862)
- needs Rs 1,485,790; 25 candidates generated

  BEST  grade 1 | VEH-A Rs 297,158 borrowed + Rs 1,188,632 liquidated, 84m, EMI Rs 4,842, interest Rs 109,531, raw 0.436
  WORST grade 0 | PERS-A Rs 594,316 borrowed + Rs 891,474 liquidated, 60m, EMI Rs 13,071, raw 0.255

## Customer 4
- income Rs 242,603/mo, expenses Rs 148,941, existing EMI Rs 3,339, disposable Rs 90,323
- appetite MODERATE, credit score 686, portfolio Rs 7,707,055 (liquid Rs 6,346,344 / volatile Rs 1,360,711)
- needs Rs 2,395,576; 93 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 2,395,576 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.822
  WORST grade 0 | BUS-A Rs 2,395,576 borrowed + Rs 0 liquidated, 60m, EMI Rs 53,591, raw 0.571

## Customer 5
- income Rs 392,683/mo, expenses Rs 220,076, existing EMI Rs 61,592, disposable Rs 111,016
- appetite CONSERVATIVE, credit score 784, portfolio Rs 12,311,886 (liquid Rs 7,912,806 / volatile Rs 4,399,079)
- needs Rs 5,665,944; 43 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 5,665,944 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.687
  WORST grade 0 | BUS-A Rs 3,399,567 borrowed + Rs 2,266,378 liquidated, 84m, EMI Rs 60,467, raw 0.436

## Customer 6
- income Rs 59,840/mo, expenses Rs 20,074, existing EMI Rs 2,866, disposable Rs 36,900
- appetite CONSERVATIVE, credit score 680, portfolio Rs 1,430,221 (liquid Rs 1,320,791 / volatile Rs 109,431)
- needs Rs 1,547,579; 61 candidates generated

  BEST  grade 2 | HOME-A Rs 619,032 borrowed + Rs 928,547 liquidated, 120m, EMI Rs 7,593, interest Rs 292,079, raw 0.538
  WORST grade 0 | PERS-B Rs 309,516 borrowed + Rs 1,238,063 liquidated, 24m, EMI Rs 14,824, raw 0.323

## Customer 7
- income Rs 99,880/mo, expenses Rs 57,727, existing EMI Rs 13,294, disposable Rs 28,860
- appetite AGGRESSIVE, credit score 728, portfolio Rs 4,060,568 (liquid Rs 1,323,559 / volatile Rs 2,737,009)
- needs Rs 3,544,183; 12 candidates generated

  BEST  grade 2 | NO_LOAN Rs 0 borrowed + Rs 3,544,183 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.533
  WORST grade 0 | BUS-A Rs 708,837 borrowed + Rs 2,835,346 liquidated, 60m, EMI Rs 15,857, raw 0.290

## Customer 8
- income Rs 409,250/mo, expenses Rs 212,426, existing EMI Rs 60,551, disposable Rs 136,272
- appetite CONSERVATIVE, credit score 858, portfolio Rs 5,463,788 (liquid Rs 3,704,910 / volatile Rs 1,758,878)
- needs Rs 8,209,976; 13 candidates generated

  BEST  grade 0 | HOME-A Rs 6,567,981 borrowed + Rs 1,641,995 liquidated, 120m, EMI Rs 80,558, interest Rs 3,098,980, raw 0.386, DEMOTED (stress 34%)
  WORST grade 0 | HOME-B Rs 4,925,986 borrowed + Rs 3,283,991 liquidated, 84m, EMI Rs 79,005, raw 0.243

## Customer 9
- income Rs 126,291/mo, expenses Rs 77,164, existing EMI Rs 24,007, disposable Rs 25,119
- appetite AGGRESSIVE, credit score 656, portfolio Rs 0 (liquid Rs 0 / volatile Rs 0)
- needs Rs 1,221,895; 1 candidates generated

  BEST  grade 1 | HOME-A Rs 1,221,895 borrowed + Rs 0 liquidated, 120m, EMI Rs 14,987, interest Rs 576,529, raw 0.528, DEMOTED (stress 34%)
  WORST grade 1 | HOME-A Rs 1,221,895 borrowed + Rs 0 liquidated, 120m, EMI Rs 14,987, raw 0.528

## Customer 10
- income Rs 43,057/mo, expenses Rs 16,050, existing EMI Rs 8,576, disposable Rs 18,432
- appetite MODERATE, credit score 633, portfolio Rs 1,787,572 (liquid Rs 565,085 / volatile Rs 1,222,487)
- needs Rs 1,620,489; 25 candidates generated

  BEST  grade 2 | NO_LOAN Rs 0 borrowed + Rs 1,620,489 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.460
  WORST grade 0 | PERS-B Rs 324,098 borrowed + Rs 1,296,391 liquidated, 36m, EMI Rs 11,038, raw 0.201

## Customer 11
- income Rs 259,444/mo, expenses Rs 91,230, existing EMI Rs 39,043, disposable Rs 129,170
- appetite CONSERVATIVE, credit score 854, portfolio Rs 0 (liquid Rs 0 / volatile Rs 0)
- needs Rs 5,131,654; 2 candidates generated

  BEST  grade 2 | HOME-A Rs 5,131,654 borrowed + Rs 0 liquidated, 120m, EMI Rs 62,941, interest Rs 2,421,276, raw 0.492
  WORST grade 1 | HOME-B Rs 5,131,654 borrowed + Rs 0 liquidated, 120m, EMI Rs 64,728, raw 0.475

## Customer 12
- income Rs 209,540/mo, expenses Rs 106,718, existing EMI Rs 11,202, disposable Rs 91,621
- appetite MODERATE, credit score 857, portfolio Rs 3,151,816 (liquid Rs 2,558,864 / volatile Rs 592,952)
- needs Rs 4,274,973; 30 candidates generated

  BEST  grade 2 | HOME-A Rs 2,564,984 borrowed + Rs 1,709,989 liquidated, 120m, EMI Rs 31,460, interest Rs 1,210,240, raw 0.522
  WORST grade 0 | VEH-A Rs 1,709,989 borrowed + Rs 2,564,984 liquidated, 36m, EMI Rs 54,696, raw 0.301

## Customer 13
- income Rs 100,206/mo, expenses Rs 38,667, existing EMI Rs 15,936, disposable Rs 45,603
- appetite MODERATE, credit score 551, portfolio Rs 4,047,685 (liquid Rs 1,965,094 / volatile Rs 2,082,591)
- needs Rs 1,646,530; 71 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 1,646,530 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.726
  WORST grade 0 | PERS-B Rs 987,918 borrowed + Rs 658,612 liquidated, 48m, EMI Rs 26,873, raw 0.456

## Customer 14
- income Rs 89,095/mo, expenses Rs 56,950, existing EMI Rs 16,169, disposable Rs 15,975
- appetite AGGRESSIVE, credit score 547, portfolio Rs 3,558,468 (liquid Rs 2,323,680 / volatile Rs 1,234,788)
- needs Rs 1,630,476; 18 candidates generated

  BEST  grade 2 | NO_LOAN Rs 0 borrowed + Rs 1,630,476 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.720, DEMOTED (stress 34%)
  WORST grade 0 | PERS-B Rs 326,095 borrowed + Rs 1,304,381 liquidated, 48m, EMI Rs 8,870, raw 0.501

## Customer 15
- income Rs 474,941/mo, expenses Rs 175,028, existing EMI Rs 52,305, disposable Rs 247,609
- appetite AGGRESSIVE, credit score 672, portfolio Rs 25,406,703 (liquid Rs 13,003,343 / volatile Rs 12,403,360)
- needs Rs 6,061,667; 68 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 6,061,667 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.803
  WORST grade 0 | BUS-A Rs 4,849,333 borrowed + Rs 1,212,333 liquidated, 48m, EMI Rs 128,298, raw 0.568

## Customer 16
- income Rs 497,004/mo, expenses Rs 343,384, existing EMI Rs 17,668, disposable Rs 135,952
- appetite AGGRESSIVE, credit score 577, portfolio Rs 18,884,762 (liquid Rs 10,521,579 / volatile Rs 8,363,183)
- needs Rs 18,256,719; 8 candidates generated

  BEST  grade 2 | NO_LOAN Rs 0 borrowed + Rs 18,256,719 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.594
  WORST grade 0 | HOME-B Rs 3,651,344 borrowed + Rs 14,605,375 liquidated, 60m, EMI Rs 75,619, raw 0.358

## Customer 17
- income Rs 82,039/mo, expenses Rs 31,490, existing EMI Rs 1,317, disposable Rs 49,232
- appetite AGGRESSIVE, credit score 624, portfolio Rs 2,273,769 (liquid Rs 1,081,944 / volatile Rs 1,191,825)
- needs Rs 892,973; 98 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 892,973 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.802
  WORST grade 0 | PERS-B Rs 535,784 borrowed + Rs 357,189 liquidated, 24m, EMI Rs 25,661, raw 0.576

## Customer 18
- income Rs 587,571/mo, expenses Rs 166,502, existing EMI Rs 60,216, disposable Rs 360,852
- appetite CONSERVATIVE, credit score 802, portfolio Rs 16,876,005 (liquid Rs 2,262,170 / volatile Rs 14,613,835)
- needs Rs 18,863,714; 17 candidates generated

  BEST  grade 1 | HOME-A Rs 3,772,743 borrowed + Rs 15,090,971 liquidated, 120m, EMI Rs 46,274, interest Rs 1,780,099, raw 0.338
  WORST grade 0 | BUS-A Rs 3,772,743 borrowed + Rs 15,090,971 liquidated, 24m, EMI Rs 178,037, raw 0.223

## Customer 19
- income Rs 41,997/mo, expenses Rs 13,611, existing EMI Rs 20, disposable Rs 28,367
- appetite AGGRESSIVE, credit score 666, portfolio Rs 2,156,544 (liquid Rs 1,167,342 / volatile Rs 989,203)
- needs Rs 1,618,951; 44 candidates generated

  BEST  grade 3 | NO_LOAN Rs 0 borrowed + Rs 1,618,951 liquidated, 1m, EMI Rs 0, interest Rs 0, raw 0.626
  WORST grade 0 | PERS-B Rs 323,790 borrowed + Rs 1,295,161 liquidated, 24m, EMI Rs 15,508, raw 0.310

## Customer 20
- income Rs 258,373/mo, expenses Rs 81,233, existing EMI Rs 26,213, disposable Rs 150,927
- appetite AGGRESSIVE, credit score 758, portfolio Rs 2,051,930 (liquid Rs 1,979,089 / volatile Rs 72,841)
- needs Rs 6,351,939; 6 candidates generated

  BEST  grade 2 | HOME-A Rs 6,351,939 borrowed + Rs 0 liquidated, 120m, EMI Rs 77,908, interest Rs 2,997,045, raw 0.520
  WORST grade 0 | HOME-B Rs 5,081,551 borrowed + Rs 1,270,388 liquidated, 84m, EMI Rs 81,500, raw 0.385
