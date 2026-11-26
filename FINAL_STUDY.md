# SEEM3410 Group 15 · Fraud-alert review, revised study

A bank's fraud-review desk must protect urgent cases and still give lower-risk work a turn. Delayed review can leave less time to stop further harm, so we track **high-risk arrival to review completion >30 minutes**. To detect low-risk cases repeatedly bypassed by medium- and high-risk work, we track **low-risk wait to start >60 minutes**. These are service measures, not estimates of fraud losses. Three permanent seats and a fixed risk-and-wait priority rule anchor the comparisons.

* **When only the range of tomorrow's peak times is known**, screen 25 fixed calendars on uncertain synthetic days and validate the choice on fresh days. The nominal roster was selected; delaying both shifts was not an improvement on both measures. See [uncertain peak starts](peak_uncertainty/README.md).
* **When a past hourly workload shape is available**, learn a roster from the first transaction-day shape, lock it, and use the second shape for testing. The selected split reduced high-risk lateness and low-risk long waits versus the original roster by 6.71 and 9.25 percentage points, respectively. A contiguous shift remained competitive; neither met the 5% daily low-risk target. See [curve-based rostering](curve_roster/README.md).

* **What is the lowest tested budget that protects lower-risk cases on the long curve?** Select one fixed calendar for each 0–24-hour budget on day one. On day two the 80-replication screen first passed at 13 hours, but an independent 80-replication check also passed at 12. A new fixed-size test of the unchanged 11-, 12- and 13-hour rosters used 1,200 fresh paired replications. Its lowest supported budget is **13 hours (10-23, relative hours)**: L 2.55% (three-budget simultaneous 95% interval 2.40–2.70%), H 9.91%. See [budget-based rostering](budget_roster/README.md).

## Where to look

| Question | Reproducibility evidence |
|---|---|
| What is the lowest tested daily budget that meets the 5% L guardrail? | [All 25 budgets](budget_roster/results/budget_frontier.csv), [rosters locked from day one](budget_roster/results/locked_rosters.json), [independent 80-run check](budget_roster/results/confirmation.csv) and [the precision test](budget_roster/results/precision_levels.csv). |
| Which roster is selected under symmetric peak-time errors? | [Selection grid](peak_uncertainty/results/screening.csv), [locked selection](peak_uncertainty/results/selection.json), [held-out levels](peak_uncertainty/results/holdout_levels.csv) and [matched comparisons](peak_uncertainty/results/holdout_paired.csv). |
| Can a roster learned from one shape transfer to another? | [Selection grid](curve_roster/results/training_grid.csv), [locked rosters](curve_roster/results/locked_rosters.json), [relative-hour shapes](curve_roster/results/profiles.csv), [test levels](curve_roster/results/test_levels.csv) and [matched comparisons](curve_roster/results/test_paired.csv). |
| What does a fixed, known one-hour forecast error do in the earlier stress test? | `repro/results/levels.csv` (absolute levels) and `repro/results/paired.csv` (within-replication changes); `repro/results/decisions.csv` applies the stated thresholds. |
| Which inputs are observed, and which are assumed? | `repro/data/README.md`, the 48-row `hourly_profile.csv` and its regeneration script. The only observed model input is the *shape of upstream transactions*. Volume, alert generation, risk, service and staffing are not measured at a bank. Effective scenario intensities are in `repro/results/input_profiles.csv`. |
| What if high priority does not imply longer service? | `mechanism/README.md` and `mechanism/results/coupling_summary.csv`. |
| Where did the figures from the earlier project come from? | See [the original study](README.md#reproduce-the-evidence) for its run commands, original seeds, tests and results. The original scripts remain in the repository root. Do not subtract results from different trials to estimate paired effects. |

## Check the 13-hour result

With Python 3.12 and the dependencies in `requirements.txt`, run these from the repository root:

```sh
cd budget_roster
python -B check_results.py --out results
python -B check_precision.py --out results
```

The first command checks all 25 locked schedules against the 3,271 training candidates. The second rebuilds the boundary estimates and intervals from the 7,200 archived simulation rows: the upper low-risk limit is 5.05% at 12 hours and 2.70% at 13 hours.

## Rerun the simulation offline

Use Python 3.12 and NumPy 2.5.3 (the tested versions). Start in the repository root. Output folders in the commands below are separate from the supplied results. The archived hourly aggregate suffices; the original transaction records are not required.

The following are separate study commands. The seed split and replication counts are specified in each study's `design.json`. The budget always counts **posted** hours; paid time includes finishing an active review after the window ends.

~~~sh
# Start in the repository root
cd peak_uncertainty
python -B -m unittest discover -v
python -B experiment.py --workers 4 --out my_results
python -B check_runner_up.py --workers 4 --out my_results
python -B check_results.py my_results
cd ../curve_roster
python -B -m unittest -v test_curve
python -B run_study.py --workers 4 --out my_results
cd ../budget_roster
python -B -m unittest discover -v
python -B run_budget.py --workers 12 --out my_results
python -B precision.py --locks my_results/locked_rosters.json --workers 12 --out my_results
python -B check_results.py --out my_results
python -B check_precision.py --out my_results
~~~

Earlier fixed-scenario stress tests and risk/service diagnostic (from the repository root):

~~~sh
cd repro
python -B -m unittest discover -v
python -B study.py --include-proxy --check-warmup --workers 4 --out my_results
python -B check_revision.py --out my_results
cd data
python -B -m unittest -v test_profile
cd ../../mechanism
python -B -m unittest -v test_coupling
python -B coupling.py --workers 4 --out my_results
~~~

The timing experiment uses 100 paired replications in each of 4 scenarios × 6 plans, root 34101600. The separate mechanism experiment uses 100 paired replications in 2 coupling conditions × 2 rules, root 34101611. The independent unit is a 14-day replication, not one alert. See the two component READMEs for warm-up, windows and metrics.

The aggregate is derived from [Worldline/ULB, Credit Card Fraud Detection, version 3](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud/versions/3); the derived table is supplied under the source database and content terms ([ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/), [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/)). Attribution, coverage and the alternatives for reproducing it are in `repro/data/README.md`.
