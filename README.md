# Fraud-alert review under a capacity constraint

Reproducibility package | SEEM3410 | Group 15

Can a digital bank prioritize urgent alerts without leaving low-risk alerts in the queue too long? Open **results/decision_table.csv** for the original 17 configurations; the four-seat follow-up is in **results/capacity_followup_levels.csv**. All alerts are synthetic. No bank records, trained fraud model, or external service is needed.

## Reproduce the evidence

Run these commands in this directory with Python 3.12.14 and NumPy 2.5.3 (the tested versions). If needed, install the single runtime dependency with `python -m pip install -r requirements.txt` in a virtual environment.

```sh
python -m unittest -v test_engine test_analysis
python validation.py
python run_experiments.py all --workers 8
python check_warmup.py --workers 8
python confirm_capacity.py --workers 8
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

FCFS chooses the oldest waiting alert. STATIC chooses H before M before L, oldest first within class. DYNAMIC selects the largest base score (H=2,M=1,L=0) plus floor(wait / A), with earliest arrival and then lowest alert ID breaking ties. Main A=20 minutes; A10/A40 are sensitivity analyses, not a tuning grid for picking a winner. At a common timestamp, completions release seats and all arrivals join before the next dispatch. No preemption, abandonment, shift change or service-time lookahead.

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

**Decision.** In the main study, all three-seat policies exceeded the low-risk guardrail. With four seats under baseline inputs, A20 lowered high-risk lateness by 6.38 pp (95% CI: 6.15-6.60 pp reduction) versus four-seat FCFS, while 1.07% of low-risk alerts waited over 60 minutes (0.90-1.23%). Strict priority missed the guardrail even with four seats.

**Separate capacity follow-up:** `python confirm_capacity.py --workers 8` fixes four seats and compares only FCFS versus A20 under B, D, V and R. It uses **independent root 34101593**, 100 replications per configuration, the same 7+14-day windows, and 800 runs separate from the main 1,700. No parameter was retuned. A20's low-risk rate met the target in B and V, was uncertain at +10% demand (4.71%, 4.35-5.08%), and exceeded it when the H share rose to 30% (7.51%, 7.07-7.96%). One-factor scenarios do not establish performance under combined stresses. No saved time is translated into fraud losses or monetary savings.

