# Fraud-alert review under a capacity constraint

Reproducibility package | SEEM3410 | Group 15

Can a digital bank prioritize urgent alerts without leaving low-risk alerts in the queue too long? Open **results/decision_table.csv** for the original 17 configurations, **results/capacity_followup_levels.csv** for the fixed-four follow-up, and **results/peak_staffing_B_levels.csv** for the six-hour peak-shift trial. All alerts are synthetic. No bank records, trained fraud model, or external service is needed.

## Reproduce the evidence

Run these commands in this directory with Python 3.12.14 and NumPy 2.5.3 (the tested versions). If needed, install the single runtime dependency with `python -m pip install -r requirements.txt` in a virtual environment.

```sh
python -m unittest -v test_engine test_analysis test_peak_staffing
python validation.py
python run_experiments.py all --workers 8
python check_warmup.py --workers 8
python confirm_capacity.py --workers 8
python peak_staffing.py --workers 8
python export_trace.py
python check_results.py
```

Outputs are already included in `results/`. To keep the supplied files unchanged, pass `--out my_results` to each experiment, validation and check command; the trace exporter takes a **file** path: `python export_trace.py --out my_results/example_alerts.csv`. Use `--workers 1` for sequential experiments. Workers change scheduling, not random streams. The recorded eight-worker run took about 13 seconds for the 1,700 main simulations on the original machine; timings are machine-dependent. For separate stages use `python run_experiments.py pilot` and then `python run_experiments.py main`; the latter reads the pilot freeze file. No charts require an internet connection.

## What was simulated

The system runs continuously, including overnight. Identical analysts serve one alert to completion. The peak rate applies 10:00-13:00 and 18:00-21:00 every day; segmented Poisson arrivals are uniform within each segment conditional on its count. Baseline hourly rates are 18 off-peak and 36 peak. H/M/L risk probabilities are 0.20/0.30/0.50. Conditional service time is lognormal, with means 12/8/4 minutes and a common coefficient of variation (CV) of 0.60. For a class mean m, log variance is log(1+CV^2) and log mean is log(m) minus half the log variance. These values are study assumptions, not fitted banking data.

| Label | Single change from baseline | Seats | Policies |
| --- | --- | ---: | --- |
| B | None | 3 | FCFS, STATIC, DYNAMIC |
| D | Multiply both arrival rates by 1.10 | 3 | Same three |
| C | Add one seat throughout the day | 4 | Same three |
| V | Increase CV to 1.20; keep class means | 3 | Same three |
| R | H/M/L probabilities 0.30/0.30/0.40 | 3 | Same three |
| B_DYNAMIC_A10, B_DYNAMIC_A40 | Ageing interval 10 or 40 minutes instead of 20 | 3 | DYNAMIC only |

FCFS chooses the oldest waiting alert. STATIC chooses H before M before L, oldest first within class. DYNAMIC selects the largest base score (H=2,M=1,L=0) plus floor(wait / A), with earliest arrival and then lowest alert ID breaking ties. Main A=20 minutes; A10/A40 are sensitivity analyses, not a tuning grid for picking a winner. At a common timestamp, completions release seats and all arrivals join before the next dispatch. No preemption, abandonment or service-time lookahead. Staffing is constant in the original matrix; only the separate peak-shift trial below introduces shift openings and closings.

**Cohort and common random numbers.** For each root, replication, day and stream, NumPy PCG64 draws arrivals, positions, risks and service shocks separately. Alert identity fixes arrival, risk and service *before* scheduling. Policies share the same records within environment, C and ageing variants reuse B, and V/R transform shared primitive draws. D's rate change can alter counts and alert identities; no paired cross-demand effect is reported. Inter-replication seeds are separate. In the main study, the system starts empty, burns in for seven days, then measures arrivals in [day 7, day 21). The system is never reset at midnight. Newly arriving alerts continue competing after the endpoint until the entire measurement cohort is served; service is followed to completion. Seven days of exogenous follow-up are available initially and extended in seven-day increments if necessary. None required extension in the reported runs.

## Why there are 100 replications

Pilot root **34101590**, independent of the main root **341015**. Ten pilot replications per B/D/R policy retained full 28-day trajectories. On each trajectory compare the same statistics over the two 14-day arrival windows [day 7,21) and [day 14,28). Adopt 14 days of warm-up if a change in high-risk lateness exceeds 1 percentage point or low-risk p95 wait changes by more than 2 minutes *and* its two-sided paired 95% interval excludes zero. None triggered; these short pilot intervals are broad in stressed environments.

A supplementary cleaner diagnostic compares the **same days 15-28 arrivals** after starting empty on day 0 versus day 7. It fixes the post-day-7 arrivals and services exactly. In all 90 paired pilot configurations (10 seeds x 3 environments x 3 policies) the measurement-cohort start times matched, supporting seven days for the tested paths. The diagnostic does not prove stationarity. See `results/pilot_diagnostics.html` for the observed daily trajectories.

Before running the main sample, use the more demanding of four baseline targets: STATIC and DYNAMIC versus FCFS, each for the high-risk late-rate difference (2 pp half-width) and low-risk p95-wait difference (5 min). Estimate R=(1.96 s/target)^2 from paired pilot differences, round up to a multiple of 10, with floor 40 and cap 100. STATIC minus FCFS for low-risk p95 gave 134.68, so all configurations used the cap of **100**. Its attained main half-width was 4.15 minutes; the other three also met their targets. This final-sample precision was checked, not used for optional stopping.

## How to read the numbers

* H lateness = completion more than 30 minutes after arrival. Analogous M/L completion targets are 60/120 minutes. H start-by-15 is an auxiliary *start* target. The low-risk guardrail is the proportion **waiting to start** more than 60 minutes, not low-risk completion lateness. Equality with a target is timely.
* Work in independent replication units, not individual alerts. Each replication contributes one class-specific mean, proportion or linearly interpolated p95. A reported p95 is **the mean of within-replication p95s**. A class with no arrivals has n=0 and unavailable conditional metrics, not a zero miss rate; no empty class occurred in the main or follow-up runs.
* Absolute probability estimates in summary CSVs are **percent (%)**. Signed probability differences are **percentage points (pp)** and always alternative minus reference within replication. Raw replication probability columns are **fractions**. Times are minutes and counts are alerts. Intervals are pointwise, two-sided Student 95% intervals across replication estimates or CRN-paired differences. They describe Monte Carlo variation conditional on assumptions; they do not include model uncertainty or guarantee joint coverage over all configurations. A guardrail is classified as meets when the upper endpoint is at most 5%, exceeds when the lower endpoint is above 5%, and uncertain if the interval crosses 5%.
* Time-average queue and seat utilization integrate only over the measurement window. End states are taken immediately before endpoint events. Waiting, busy and total unfinished are separate; end-of-window cohort unfinished does not mean the alert was dropped. Maximum queue means maximum number waiting during the window after same-time dispatch.

## Which files answer which question?

| Question | File(s) in results/ |
| --- | --- |
| What was frozen, and what actually ran? | design_freeze.json, run_manifest.json |
| Which of the 17 configurations crosses the guardrail? | decision_table.csv |
| Are high-risk gains and low-risk harm explained by ordering or staffing? | paired_effects_ci.csv, levels_ci.csv. Filter comparison for within-environment, four-minus-three seat, or ageing effects. |
| How can I recompute intervals or check the 24-hour queue? | replication_metrics.csv (one row per config/rep), daily_backlog.csv (one per config/rep/measurement day). |
| Where are the pilot values and warm-up checks? | pilot_windows.csv, pilot_warmup_contrasts.csv (14 minus 7), pilot_precision.csv, pilot_daily.csv, pilot_daily_means.csv, pilot_matched_calendar.csv, pilot_diagnostics.html |
| Can I inspect individual synthetic alerts? | example_alerts.csv: 550 alerts from main B/rep 0/first measurement day, with fixed class/service and all three start/finish times. Use export_trace.py --day 1..14 --rep 0..99 to select another cohort day. |
| Does the event model reproduce textbook or hand calculations? | validation_summary.csv, validation_replications.csv, validation_hand_trace.csv. validation_synthetic_inputs.csv checks generated inputs against their configured assumptions. |
| Does the four-seat result survive higher stress? | capacity_followup_levels.csv (%), capacity_followup_paired.csv (pp), capacity_followup_replications.csv (raw fractions), capacity_followup_manifest.json |
| Does adding a seat only during peaks work? What does it cost? | peak_staffing_design.json (frozen inputs and decision rules); peak_staffing_{B,D,R}_levels.csv, _paired.csv, _replications.csv and _manifest.json (one set per environment). |

**Decision.** In the main study, all three-seat policies exceeded the low-risk guardrail. With four seats under baseline inputs, A20 lowered high-risk lateness by 6.38 pp (95% CI: 6.15-6.60 pp reduction) versus four-seat FCFS, while 1.07% of low-risk alerts waited over 60 minutes (0.90-1.23%). Strict priority missed the guardrail even with four seats.

**Separate capacity follow-up:** `python confirm_capacity.py --workers 8` fixes four seats and compares only FCFS versus A20 under B, D, V and R. It uses **independent root 34101593**, 100 replications per configuration, the same 7+14-day windows, and 800 runs separate from the main 1,700. No parameter was retuned. A20's low-risk rate met the target in B and V, was uncertain at +10% demand (4.71%, 4.35-5.08%), and exceeded it when the H share rose to 30% (7.51%, 7.07-7.96%). One-factor scenarios do not establish performance under combined stresses. No saved time is translated into fraud losses or monetary savings.

## Six hours of peak coverage: sufficient at baseline, not under either stress

`python peak_staffing.py --env B --workers 8` replays the same baseline alert IDs for three A20 staffing plans on 100 new replication sets (root 34101594). Three seats are always present. The flexible fourth seat starts work only during [10:00,13:00) and [18:00,21:00); when both can take an alert, use a permanent seat first. A job already in service at closing finishes without interruption. Extra paid time includes idle scheduled coverage and only actual fourth-seat work outside *all* its windows, clipped to the 14 measured days. These are seat-hours, not numbers of employees or monetary costs.

| Baseline plan (A20 throughout) | H completion >30 min, % [95% CI] | L wait >60 min, % [95% CI] | Extra paid seat-h/day |
| --- | ---: | ---: | ---: |
| Fixed three | 38.75 [37.79, 39.70] | 30.35 [29.40, 31.31] | 0 |
| Fourth seat during peaks | 9.36 [8.90, 9.82] | 2.98 [2.65, 3.31] | 6.171 [6.165, 6.178] |
| Fixed four | 6.67 [6.36, 6.99] | 1.29 [1.09, 1.49] | 24 |

The peak plan uses six scheduled hours plus 0.171 hours of overtime per day. It saves 17.829 paid seat-hours/day versus fixed four (74.3% of the **fourth seat's incremental hours**, 18.6% of **all** seat-hours). In exchange, H lateness rises 2.68 pp [2.49, 2.88] and L long waits rise 1.69 pp [1.53, 1.85] versus fixed four. It passes the **overall** L guardrail, not an hourly one: among L arrivals in [13:00,14:00) and [21:00,22:00), long-wait rates are 10.68% and 9.27% on peaks-only coverage, compared with 1.77% and 1.49% for the same arrival subsets on fixed four.

Because the peak plan met the aggregate B guardrail, a prespecified secondary comparison replayed the same 100 input tables under **FCFS on those identical shifts**. A20 reduced H lateness by 8.76 pp [8.49, 9.02] from FCFS's 18.11%, comfortably above the 2 pp practical benchmark. A20 increased L long waits by 2.20 pp [1.98, 2.42] versus that same-schedule FCFS comparator, while keeping the aggregate level below 5%.

Run `--env D` (+10% arrivals; root 34101595) and `--env R` (H/M/L=30/30/40%; root 34101596) for separate stress tests, or omit `--env` for all three studies. Both used 100 matched replications, no combined stress and no search over shift windows. Peak coverage missed the L guardrail in **D: 11.68% [10.91, 12.46]** and **R: 18.53% [17.53, 19.54]**. Fixed four also missed it in R (7.99% [7.51, 8.47]). In D, fixed four met it in this sample (4.55% [4.21, 4.89]); the earlier independent fixed-four study straddled 5%, so treat that case as near the boundary rather than reliably safe.

