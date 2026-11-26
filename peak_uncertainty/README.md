# Posting tomorrow's fourth-seat roster when peak starts are uncertain

**Keep the 10:00–13:00 and 18:00–21:00 roster as the default under symmetric timing errors.** We selected it before seeing the validation workload. On the independent test set, 11.27% of high-risk cases finished after 30 minutes and 4.31% of low-risk cases waited over an hour (95% interval 3.84%–4.77%). Delaying both shifts by half an hour increased high-risk lateness by 0.37 percentage points, with no clear reduction in low-risk long waits. Moving *only* lunch by half an hour remained competitive. These are model-clock hours for this synthetic two-peak setting.

## What the manager knows

Tomorrow's lunch peak can start anywhere from 09:00 to 11:00, and the evening one from 17:00 to 19:00. A fresh, continuous, uniform start is drawn independently for each peak and day. Both last three hours. Those error bounds and independence are **assumptions**, not estimated forecast errors. Planners know the distribution but cannot see tomorrow's draws. They post one recurring roster rather than adjust retrospectively. The earlier fixed one-hour delay case illustrates what an error can do; it cannot select tomorrow's roster.

The two baseline rates (18/36 alerts per hour), expected daily total (540), risk mix and service times stay the same. We transform the within-day arrival clock using cumulative intensities; conditional on the peak starts this gives the specified piecewise Poisson process. For every competing calendar within a replication, alert timestamps, risk labels and work are identical. The three permanent seats and ageing rule (A20) are fixed. A fourth seat opens in two three-hour blocks, each starting at a nominal peak time plus −60, −30, 0, +30 or +60 minutes: 25 possible fixed calendars, each with six scheduled seat-hours. The fourth seat finishes an active case after its window closes. Its paid hours include that overrun.

## How the roster was selected and tested

1. **Search.** In 32 independent 14-day replications (root 34102611), the 25 candidates replayed the same workload per replication. Four passed the low-risk screen: the upper endpoint of a two-sided 95% interval on the all-day long-wait rate was at most 5%. Among these four, the nominal calendar had the lowest mean high-risk lateness (11.15%). The grid, selection rule, seeds and comparators are in [design.json](design.json); [the locked selection](results/selection.json) was written before generating test results.
2. **Test.** Keep the selected schedule fixed. On 80 independent new replications (root 34102612), compare it with posting both shifts earlier or later; also check the original high-risk target against oldest-first on the same calendar. The simulation runs continuously through 14 warm-up days, 14 measured arrival days and sufficient subsequent arrivals to follow the measured cohort to review. Intervals below are pointwise Student intervals over the 80 replications; difference intervals are computed within paired workloads. The estimates concern rates across the measured days, not a maximum-day guarantee.

| Preposted calendar; uncertain peaks | High-risk completion >30 min | Low-risk wait >60 min | Extra paid seat-h/day |
|---|---:|---:|---:|
| 09:30–12:30 / 17:30–20:30 | 12.88% | 6.03% | 6.16 |
| **10:00–13:00 / 18:00–21:00** | **11.27%** | **4.31%** | **6.15** |
| 10:30–13:30 / 18:30–21:30 | 11.64% | 4.13% | 6.14 |

* Comparing **late versus nominal coverage** on unknown peak days, H changed by +0.37 pp [0.16, 0.58]; L changed by −0.17 pp [−0.37, +0.03]. Keeping the original starts is supported when urgent completion is the priority subject to the all-day L guardrail.
* Comparing **uncertain versus on-time peaks** with the nominal calendar and the same daily work, H rose from 9.30% to 11.27% (+1.97 pp [1.66, 2.28]); L rose from 2.98% to 4.31% (+1.33 pp [1.07, 1.59]). That isolates the cost of timing uncertainty without changing the roster.
* Changing **only dispatch** on the selected roster, A20 reduced H lateness by 9.89 pp versus FCFS (95% interval for the reduction 9.58–10.20), exceeding the original 2 pp improvement target. L long waits rose by 3.02 pp [2.70, 3.35]. The A20 daily rate clears the 5% guardrail, but L arrivals between 13:00–14:00 and 21:00–22:00 still had long waits in 17.26% and 15.27% of cases, respectively.
* **How distinct is the winner?** On training data, moving *only lunch* 30 minutes later had H lateness just 0.044 pp above the nominal calendar. A secondary, independently seeded comparison (root 34102613; 80 fresh replications) found H +0.17 pp [−0.01, +0.34] and L −0.08 pp [−0.22, +0.06] versus nominal. It would be misleading to call nominal uniquely best. This diagnostic did not reselect the posted calendar. See [its separate design](finalist_design.md).

This search does not price fraud losses, fit a bank's peak-error distribution or optimize a dispatch that can change after the day starts. Estimate the error range and any systematic bias from actual **alert** arrivals before deciding whether the nominal roster transfers to another desk.

## Reproduce or inspect the result

Use the project's Python/NumPy environment. Keep this directory beside the unmodified `repro/` folder so it can import the verified event engine and staff calendar. Run these commands from this directory; output goes to a fresh folder.

~~~sh
python -B -m unittest discover -v
python -B experiment.py --workers 4 --out my_results
python -B check_runner_up.py --workers 4 --out my_results
python -B check_results.py my_results
~~~

[screening.csv](results/screening.csv) gives all 25 training estimates. [holdout_levels.csv](results/holdout_levels.csv) contains absolute validation rates, intervals, fixed-hour diagnostics and paid hours; [holdout_paired.csv](results/holdout_paired.csv) contains policy and input contrasts. [finalist_paired.csv](results/finalist_paired.csv) contains the separate near-tie check. The accompanying `*_reps.csv` files contain each replication's rates and event counts. All percentage denominators refer to arrivals of that risk class, not all arrivals.
