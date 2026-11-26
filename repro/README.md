# Revision v2 — timing uncertainty and equal-duration staffing

This is a self-contained experiment package. It retains the original verified, nonpreemptive fraud-alert review engine, and asks a narrower operational question: **does moving the same six hours of extra coverage 30 minutes later protect the original closing-hour cohorts, and does that survive a one-hour demand timing error?**

## Main finding: delayed coverage helps under mistiming, but does not protect both windows

| Scenario | Original peak A20: overall L long wait | Delayed A20: overall L long wait | Fixed four A20: overall L long wait |
|---|---:|---:|---:|
| Prespecified synthetic baseline | 2.88% [2.59, 3.18] | 2.83% [2.52, 3.14] | 1.19% [1.00, 1.38] |
| Prespecified demand peaks delayed 60 min | 7.74% [7.29, 8.18] | 4.55% [4.21, 4.89] | 1.23% [1.06, 1.40] |
| Exploratory transaction shape, phase 0 | 29.54% [28.43, 30.66] | 29.32% [28.20, 30.45] | 1.15% [0.87, 1.42] |
| Exploratory transaction shape, phase +12 h | 59.90% [58.87, 60.93] | 58.56% [57.55, 59.56] | 1.14% [0.87, 1.40] |

Under baseline timing, delayed coverage changes H lateness by **+0.60 pp [0.48, 0.73]** and overall L long waits by **−0.05 pp [−0.14, 0.03]** relative to original coverage. It reduces the two original closing-hour L rates to **7.75% and 6.26%**, still above the new 5% diagnostic.

When demand is one hour late, the same delayed staffing improves H lateness by **3.80 pp [3.63, 3.97]** and overall L long waits by **3.19 pp [3.00, 3.37]**. Paid extra capacity is essentially unchanged: **+0.0025 seat-h/day [−0.0074, 0.0124]** versus the original schedule. The aggregate L gate passes, but the two fixed-window rates remain **19.78% and 16.43%**. No peak-only candidate satisfies all three frozen gates. This is a trade-off, not evidence that a 30-minute shift is universally better.

The exploratory shapes show that a short schedule tied to assumed peak times can perform poorly even with unchanged daily workload. Fixed four passes the aggregate L criterion in all four tested shapes, but even it does not pass both fixed-window diagnostics under delayed synthetic demand. No tested plan establishes a universal hourly service guarantee.

## Reproduce

Python 3.12 and NumPy are sufficient. The supplied environment uses the version in `requirements.txt`; no classifier or banking service is needed.

```powershell
python -B -m unittest discover -v
python -B study.py --include-proxy --check-warmup --workers 8
python -B check_revision.py
```

Run these from this directory. To preserve the included results, add `--out my_results` to both the study and audit commands. Omit `--include-proxy` to run only the two prespecified synthetic scenarios. The proxy input preparation, source identity and observed-extent caveat are documented in `data/README.md`. Reproduction reads the included 48-row count/exposure table; it does not need the raw transaction archive or a network connection.

## Frozen comparison

`study_design.json` is the design frozen before outcomes. A new root seed, **34101600**, generates **100 independent paired replications**, with **14 warm-up days**, **14 measurement days**, and initially seven days of continued external arrivals for follow-up. The system runs continuously across midnight and does not clear the queue at the measurement endpoint. If necessary, external arrivals extend in seven-day blocks until all measurement-cohort alerts complete.

Each replication evaluates six plans:

| Plan | Policy | Fourth-seat daily start windows |
|---|---|---|
| `fixed3_A20` | Dynamic ageing, A=20 min | None |
| `peak_A20` | Dynamic ageing, A=20 min | [10:00,13:00), [18:00,21:00) |
| `shift30_A20` | Dynamic ageing, A=20 min | [10:30,13:30), [18:30,21:30) |
| `fixed4_A20` | Dynamic ageing, A=20 min | All day |
| `peak_FCFS` | FCFS | Original peak windows |
| `shift30_FCFS` | FCFS | Shifted windows |

Three permanent **concurrent seats**, not three employees, are always available. The extra seat may start only inside its window and finishes an active review after closing. Scheduled idle time is paid; extra paid time is scheduled time plus actual fourth-seat work outside every scheduled window, clipped to the measurement period. These are seat-hours, not wages or headcount.

The primary comparison is `shift30_A20 − peak_A20`, separately under each prespecified synthetic scenario. Fixed three and fixed four bound the staffing alternatives. Same-schedule FCFS comparisons isolate the ordering-policy effect from the staffing effect. No windows, ageing interval or replication count were selected after observing results.

## What changes in the input, and what stays synthetic

Baseline arrivals have piecewise Poisson rates of 18 alerts/hour off peak and 36 during [10:00,13:00) and [18:00,21:00). Expected volume is **540 alerts/day**. H/M/L proportions are 20/30/50%; service is class-conditional lognormal, mean 12/8/4 minutes and CV 0.6. Risk and service are synthetic assumptions in every scenario.

* `synthetic_base`: the original two-peak intensity.
* `synthetic_delay60`: demand peaks [11:00,14:00) and [19:00,22:00), while all staffing windows stay as listed above. This deliberately breaks the exact demand/staffing alignment.
* `proxy_phase0`, `proxy_phase12`: exploratory transaction-time-shape stresses. For each of 24 relative hours, divide summed source transaction count by summed observed exposure, then normalize the 24 intensities to the assumed 540 alerts/day. The second phase rotates the shape by 12 hours. Source time is relative to the first recorded transaction; neither phase identifies a real bank's local clock. The two observed transaction days do not supply a calibrated alert process, risk mix or review-time distribution.

All scenarios share the same replication's daily alert counts, chronological alert IDs, risk labels and service durations. The time transformation is monotone and matches integrated daily intensities:

`Lambda_target(new arrival minute) = Lambda_baseline(original arrival minute)`.

Thus timing alone changes across scenarios. This is not a blind shift of every timestamp: such a shift would move cases between days. Within each scenario, all plans replay exactly the same arrivals and marks. The fixed clock-window cohorts can contain different IDs across timing scenarios, but contain exactly the same IDs across staffing/policy plans within a scenario.

## Metrics and separate decision gates

* H lateness: completion takes more than 30 minutes after arrival.
* L long wait: service starts more than 60 minutes after arrival.
* Fixed diagnostic cohorts: L arrivals in [13:00,14:00) and [21:00,22:00). These are the **original scheduled closing-hour cohorts**. Under shifted demand they are not necessarily post-demand-peak cohorts.
* L p95: average of the within-replication 95th percentiles, not a percentile pooled across all alerts.

Decisions retain three separate columns:

1. **Original aggregate gate:** upper 95% CI for overall L long-wait rate is at most 5%.
2. **New prespecified fixed-window diagnostic:** both original closing-hour cohort upper CIs are at most 5%. This is stricter than, and does not replace, the original aggregate gate.
3. **Same-schedule H benefit:** the upper endpoint of A20-minus-FCFS H lateness is at most −2 percentage points.

`protected_candidate` requires all three. It identifies a candidate under these inputs, not an optimal schedule or a guaranteed service level in every hour. Both proxy phases are exploratory pressure tests, even though their phases were specified before the runs.

Every level and effect is summarized across independent replication-level statistics. Intervals are pointwise two-sided Student 95% intervals. Common random numbers support paired differences. These intervals capture Monte Carlo variation conditional on the chosen profiles and service model; they do not include uncertainty in real-bank parameters or provide simultaneous coverage across all gates. Individual queueing alerts are not treated as independent statistical samples.

For very rare outcomes the untruncated Student interval may extend slightly below zero. In the fixed-four, phase-12, [13:00,14:00) subset, all 100 simulated replication rates are zero, yielding the descriptive Monte Carlo interval [0,0]; this does not establish a structural zero risk or an exact probability bound. Such rare subset results do not determine the peak-plan recommendations.

## Evidence and limits

`results/replications.csv` is the raw one-row-per-scenario/plan/replication table. `levels.csv` contains levels, `paired.csv` signed differences, and `decisions.csv` the separate gates. `input_profiles.csv` records the effective intensity profiles, `frozen_design.json` the effective design, and `manifest.json` the executed matrix and environment.

`warmup_checks.csv` compares exact days 15–28 arrivals after starting empty on day 0 versus day 7. This checks initialization sensitivity on 10 paired paths per configuration without changing the design. It is a finite-path diagnostic, not proof of stationarity. `check_revision.py` independently recalculates all reported means and confidence intervals, checks count and seat-hour consistency, and exactly replays replication 0 from the saved profiles.

The executed release contains **2,400 simulation runs**, **560 independently recomputed level/effect intervals**, **24 exactly replayed configurations**, and **240 matched-calendar initialization checks** with no changed measurement start time. All **29 engine/staffing/statistics/new-contract tests** passed. Data-source tests are documented separately in `data/README.md`. No run required external-input follow-up beyond the initial seven days.

The inherited tests cover hand traces, priority ties, nonpreemption, cohort boundaries, follow-up competition, independent full-scan scheduling, and exact shift/overtime accounting. New tests cover intensity mapping, shared marks, exposure-weighted proxy normalization, fixed arrival-window denominators and separate gates. Passing implementation checks does not calibrate the model to a bank.

The study excludes employee breaks, absenteeism, heterogeneous skills, escalation/rework, correlated attack bursts, alert-model errors and monetary fraud losses. None of the experiments estimates a fraud classifier, true-fraud discovery rate or avoided loss. Extra detail should be added only when a relevant observed input or decision need justifies it.
