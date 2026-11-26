# How much fourth-seat coverage is enough on a long busy curve?

**Fund 13 scheduled fourth-seat hours if the held-out curve repeats and the daily low-risk target is firm.** Keep the fourth seat continuously open from relative hour 10 to 23. Thirteen was the first of 25 locked budgets to pass the second-day screen. A subsequent 1,200-replication study resolved the operational choice: 11 hours exceeded the limit, 12 hours had too little margin to verify it, and 13 hours cleared it comfortably. These are hours from the start of the transaction record, not local clock times in a bank.

### Where the threshold lies

The first day's curve suggested that 12 hours would suffice: its selected roster (10–16 and 17–23) had an estimated L rate of 2.97%, with upper 95% limit 3.47%; none of the shorter budgets passed the training gate. The original **80-replication screen** on the second day's shape gave:

| Fourth-seat budget | Preselected relative-hour shift | H finishes >30 min, % [95% CI] | L waits >60 min, % [95% CI] | Extra paid seat-h/day |
|---:|---|---:|---:|---:|
| 0 | None | 71.19 [70.46, 71.93] | 66.65 [65.70, 67.60] | 0.00 |
| 6 | 11–14 and 16–19 | 37.43 [36.18, 38.68] | 25.40 [24.11, 26.68] | 6.16 |
| 11 | 10–16 and 17–22 | 14.63 [13.84, 15.43] | 5.52 [4.89, 6.15] | 11.16 |
| 12 | 10–16 and 17–23 | 13.83 [13.05, 14.61] | 4.97 [4.37, **5.56**] | 12.14 |
| **13** | **10–23** | **10.10 [9.44, 10.76]** | **2.44 [2.01, 2.86]** | **13.06** |
| 14 | 09–23 | 8.43 [7.89, 8.96] | 1.76 [1.40, 2.11] | 14.06 |
| 24 | All day | 8.19 [7.67, 8.71] | 1.67 [1.33, 2.01] | 24.00 |

At 12 hours, the estimate was below 5% but its upper limit exceeded 5%. At 13 hours, the upper limit was 2.86%; even adjusting for all 25 comparisons gave 3.12%, whereas the adjusted limit at 12 hours was 5.92%. Thirteen was also the first budget to meet both original daily decision criteria: on that roster, A20 reduced H by **10.19 pp [9.77, 10.61]** versus same-roster first-come, first-served.

In a fresh **80-replication confirmation**, at 12 hours L was **4.22% [3.65, 4.78]**, which passed the original pointwise rule, unlike the first batch. At 13 hours it was **2.13% [1.70, 2.55]**, passing both times. [Original paired threshold contrasts](results/threshold_contrast.csv).

### A separate precision study at the boundary

To distinguish a genuine shortfall from Monte Carlo variation at 12 hours, we locked an additional [precision study](precision_design.json) with **1,200 new independent replications** shared across the already selected 11-, 12- and 13-hour rosters on the same second-day curve. We kept its results separate from both earlier 80-run estimates and fixed the sample size in advance.

| Budget | H finish >30 min, % [pointwise 95%] | L wait >60 min, % [simultaneous 95% across 3 budgets] | Paid extra h/day |
|---:|---:|---:|---:|
| 11 | 14.40 [14.17, 14.63] | 5.38 [5.17, 5.60] | 11.16 |
| 12 | 13.61 [13.39, 13.83] | 4.85 [4.65, **5.05**] | 12.14 |
| **13** | **9.91 [9.73, 10.10]** | **2.55 [2.40, 2.70]** | **13.06** |

At 11 hours even the simultaneous lower bound exceeds 5%. At 12 the mean lies below 5%, but both the simultaneous upper bound (**5.049%**) and original pointwise upper bound (**5.013%**) exceed 5%. Thus 12 hours could suffice; the agreed standard does not certify it. At 13 hours the simultaneous upper bound is **2.695%** and H declines **10.18 pp [10.07, 10.29]** versus same-roster FCFS.

The change from 12 to 13 fills the single 16–17 gap. In the precision study those additional 60 scheduled minutes reduced H by **3.70 pp [3.62, 3.77]** and L by **2.30 pp [2.23, 2.37]**. Paid cover increased by **0.916 h/day**: the continuous shift has one fewer closing at which a reviewer could work overtime. [Fresh levels](results/precision_levels.csv) and [paired budget changes](results/precision_paired.csv). This validates the choice against one held-out timing curve under the stated workload and shift family; special-purpose testing of other 12-hour patterns would be a different search.

## Decision and budget

Three seats are continuously available. A fourth seat can start new cases only in its scheduled hours; a case already in progress is completed and the overrun is paid. Budgets are 0 through 24 **scheduled** extra seat-hours per day in one-hour steps. At each budget we allow a continuous shift or two nonoverlapping shifts whose lengths differ by at most one hour, in either order. All boundaries are on the hour, no shift crosses the relative-day boundary, and adjacent blocks are merged. For example, a seven-hour budget can be one seven-hour shift, 3+4 hours or 4+3 hours. The resulting 3,271 distinct schedules include all 190 schedules in the [six-hour experiment](../curve_roster/README.md).

The dispatch rule is fixed at A20: risk gives initial priority and every complete 20 minutes of waiting earns another point. H is the percentage of high-risk alerts taking over 30 minutes from entry to completion. L is the percentage of low-risk alerts waiting over 60 minutes to start service. The objective was frozen in [design.json](design.json): among training rosters with upper 95% L bound at most 5%, choose the one with the smallest H; if none passes, minimise the equal-weight mean of H and L. The complete search covers only our allowed shift patterns; estimated differences are also subject to finite training noise.

## What was learned, locked and tested

1. Read only the first relative day's 24 observed hourly transaction counts and exposures. Convert counts to rates and then rescale them to **540 expected synthetic alerts/day**. Supply this curve to the existing queue engine and evaluate 16 independent matched replications per roster. Each block's contribution thus includes whatever backlog earlier hours left behind. Reuse the identical archived six-hour training grid.
2. Select **one fixed roster for each of the 25 budgets** and write the complete [locked roster list](results/locked_rosters.json) before evaluating any of the new budgets on the second curve. The two upstream curves are consecutive in the source. The earlier six-hour study used the second curve, but that curve is not read by any budget search.
3. Keep the rosters unchanged and use the second day's separately normalised shape. Use 80 independent replication streams matched across budgets, with arrivals, risk marks and work held constant within each stream. At each budget also replay the same roster using first-come, first-served (FCFS) to check the original H-improvement criterion. The table contains two distinct decisions: **L target** = upper pointwise 95% L limit ≤5%; **both daily targets** additionally require H reduction versus the same-roster FCFS of at least 2 percentage points at its lower paired 95% limit.
4. A minimum found by scanning 25 pointwise intervals is a selection. We preserve the original pointwise rule, then also compute *simultaneous* L bounds across the 25 locked rosters (Bonferroni, two-sided family error 5%, Student t critical value 3.196628436 with 79 degrees of freedom). Finally use genuinely new random streams for 80 paired replications at each first passing budget and its immediate predecessor. If the pointwise L, simultaneous L and joint daily thresholds differ, confirm the union of those neighbours. A fresh replication is not a new observed source day.

All phases use 14 warm-up days followed by 14 measured days; ongoing arrivals after the measurement period preserve competition until every measured case finishes. The roots are 34102641 (training), 34102642 (budget screen), 34102643 (confirmation) and 34102644 (precision). The precision study uses 1,199 degrees of freedom; its two-sided critical values are 1.961944491 for pointwise and 2.397344223 for simultaneous L intervals (Bonferroni over three). Each replication repeats one input shape with new synthetic daily arrivals and active service. Sources, hours' exposure, licence and unit are in the [data README](../repro/data/README.md). The only measured input is the *shape of transactions*. The procedure needs local alert-entry timestamps, active service and effective staffing before its clock times or thresholds can be used by a real review desk.

## Reproduce offline

Use the sibling `repro/` and `curve_roster/` directories preserved in the project package. The script calls the existing NumPy/standard-library event engine. From this directory:

```sh
python -B -m unittest -v test_budget test_precision
python -B run_budget.py --workers 12 --out my_results
python -B check_results.py --out my_results
python -B precision.py --workers 12 --locks my_results/locked_rosters.json --out my_results
python -B check_precision.py --out my_results
```

The [full budget frontier](results/budget_frontier.csv) has one row per budget with relative-time windows, H/L rates and their pointwise 95% limits, familywise L limits, extra paid seat-hours, same-roster FCFS contrast, and the pass/fail decisions. The [confirmation table](results/confirmation.csv) is a fresh test of the locked boundary rosters. The first-day [training grid](results/training_grid.csv) permits independent re-selection; the [held-out replication records](results/test_replications.csv) and [confirmation records](results/confirmation_replications.csv) include event counts and denominators. A positive improvement in the H-vs-FCFS column favours A20.
