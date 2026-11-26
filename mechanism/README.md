# Does urgency also mean more work?

On the original peak roster (10:00–13:00 and 18:00–21:00), compare A20 with FCFS. In the **linked** input, high-, medium- and low-risk cases have mean service requirements of 12, 8 and 4 minutes. In the **permuted** input, randomly reassign the same daily inventory of service times across the day's alerts using an independent per-day stream. Arrival times, individual risk labels, daily alert counts, and the full daily distribution of service requirements are identical in both inputs. The destination of each service time changes. This removes systematic duration assignment by risk in expectation; the realised per-class means need not be exactly equal. Each queue rule replays the same resulting case table within a condition. Neither can look ahead to required service.

With Python and NumPy as specified in the sibling `repro` directory, run from this directory:

~~~sh
python -m unittest -v test_coupling
python coupling.py --workers 4 --out my_results
~~~

Independent root 34101611; 100 complete replications; 14 days of warm-up, 14 days of measured arrivals, with arrivals continuing during follow-up until that cohort is resolved. The two primary outcomes are class-specific high-risk completion after 30 min and low-risk wait to start over 60 min. Intervals are pointwise, paired t intervals for differences; the replication is the statistical unit. The interaction is (A20 − FCFS) under permuted times minus (A20 − FCFS) under linked times, paired within each replication. This diagnostic tests an assumption; it does not estimate how a bank actually assigns work.

| Penalty or gain from A20 vs same-roster FCFS | Linked | Permuted |
|---|---:|---:|
| Fewer H late completions, pp [95% CI] | 8.71 [8.43, 8.99] | 8.38 [7.99, 8.76] |
| More L waits over 60 minutes, pp [95% CI] | 2.11 [1.90, 2.33] | 1.20 [1.05, 1.34] |

The ordering trade-off persisted under both assignments. With day-level workloads fixed, removing the systematic link between priority and service time reduced the low-risk penalty by 0.92 pp [0.74, 1.09]. See `results/coupling_reps.csv` for every run and `results/coupling_summary.csv` for estimates and intervals.

## How to use the service-time benchmark

The [2019 CyberSource Global eCommerce Fraud Management Report](https://www.cybersource.com/content/dam/documents/en/global-fraud-report-2019.pdf), section “Less likely to conduct manual review”, reports 10 vs 15 minutes to review an order for two groups of surveyed merchants. These are adjacent-domain benchmarks, not bank alert durations or class means. The [Jesus et al. analyst study, Table 1](https://research.feedzai.com/wp-content/uploads/2022/08/Jesus_Choose_an_Explainer_FAccT2021.pdf) instead timed a decision on a case presented in a study interface (59.50 seconds for the data-only group). The difference in work being timed matters more than an average of these figures.

In `results/capacity_arithmetic.csv`, required seat-hours/day = alerts/day × mean active minutes per alert ÷ 60. The reported gap is required minus scheduled hours; a positive gap cannot be absorbed within scheduled coverage alone. At 540 assumed alerts/day, 78 scheduled hours can absorb at most 8.67 mean minutes per alert even with zero idle time. If the work actually took 10 minutes per case, demand would exceed that budget by 12 hours/day. This is capacity arithmetic, not a DES run or a prediction of overtime; a negative gap does not guarantee timeliness.
