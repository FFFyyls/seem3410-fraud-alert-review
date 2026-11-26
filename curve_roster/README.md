# Place six extra review hours on a long busy period

**Decision.** If six extra seat-hours are available, scheduling against predicted *arrivals* alone misses a crucial feature: cases left in the queue are still there in the next hour. We used the first transaction day's hourly shape to choose a fixed roster and kept it unchanged when testing the second day's shape. Against the original split, the selected roster cut both risks. A simpler continuous shift was competitive, and neither came close to the 5% low-risk target.

### What a manager can decide in advance

Start from the existing three always-available seats and the A20 rule: risk gives the initial priority, and every completed 20 minutes of waiting adds one priority point. Allocate **one extra seat for six scheduled hours per day**. Search all 190 combinations of two nonoverlapping three-hour blocks on the hourly grid, wholly inside the relative day. Touching blocks form one six-hour shift (19 possibilities). Half-hour starts, other block lengths and shifts crossing the relative-day boundary are outside this search. A reviewer finishes an active case after scheduled closing: paid time can exceed six hours.

For each training roster, estimate two rates: the percentage of H cases taking over 30 minutes from arrival to completion, and the percentage of L cases waiting over 60 minutes to start. If any roster's upper 95% limit for L is at most 5%, prefer the smallest H rate within that set. Otherwise minimise **(H rate + L rate)/2**. Here a one-percentage-point reduction carries equal weight in either class, regardless of class size. It is a decision preference, not a financial loss estimate. The complete rule and tie-breaks are in [design.json](design.json).

### Learn on one curve, evaluate on another

* **Observed:** 144,786 upstream card transactions in relative day 1; 140,021 in day 2 ([Worldline / ULB v3](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud/versions/3)). The [hourly source aggregates](../repro/data/hourly_profile.csv) include observed exposure; the last bin spans 3,592 seconds rather than 3,600. Within each day, divide hourly count by exposure, then rescale the resulting 24 rates to **540 expected alerts/day**. Local civil times, manual alert volumes, risk labels, service times and rosters are not observed in these data. [Data preparation and licence](../repro/data/README.md).
* **Training:** repeat only the first curve as the simulated daily intensity. Reuse the original marked-arrival generator, with H/M/L probabilities 20/30/50% and mean active service 12/8/4 minutes (class-specific lognormal, CV 0.6). Within each of 16 replications, all 190 schedules face the same cases and work. No schedule passes the 5% training screen. The balanced choice is **11–14 and 16–19** on the *relative* clock. Optimising H alone selects the same roster; L alone selects **11–14 and 17–20**. Lock all choices before loading the second curve.
* **Test:** keep the start times fixed, replace the training curve with the second day's independently normalised curve and use 80 fresh paired replications. For both phases each replication has 14 warm-up days, 14 measured days, and continued arrivals for follow-up. The replicated days share the one curve for that phase, with fresh synthetic arrivals every day. Thus 80 replications quantify simulation uncertainty conditional on **one** held-out timing curve, not variation across 80 real days.

### Results on the second curve

All rosters in this table use A20. Numbers are mean class-specific percentages across independent simulation replications; paid hours include any overrun.

| How the roster was chosen on day 1 | Extra seat, relative hours | H finish >30 min | L wait >60 min | Paid extra h/day |
|---|---|---:|---:|---:|
| Original two-peak baseline | 10–13, 18–21 | 44.15% | 34.65% | 6.17 |
| Maximum first-day incoming volume within the blocks | 09–12, 20–23 | 51.69% | 44.46% | 6.17 |
| Best continuous shift under the training rule | 11–17 | 36.39% | 26.14% | 6.08 |
| Best of all 190 under the training rule | **11–14, 16–19** | **37.43%** | **25.40%** | **6.16** |
| Lowest L rate alone on day 1 | 11–14, 17–20 | 40.37% | 28.75% | 6.16 |

Against the original roster, the balanced choice reduced H by **6.71 pp** (paired 95% interval **6.12 to 7.31**) and L by **9.25 pp** (**8.51 to 10.00**). Its held-out L level was **25.40% [24.11, 26.68]**. Equal scheduled time did not guarantee identical overtime; the difference in paid time versus original was −0.007 h/day [−0.019, +0.005].

The balanced choice and the best continuous shift traded places depending on what mattered: splitting increased H by **1.04 pp [0.43, 1.65]** and decreased L by **0.74 pp [0.05, 1.43]**. For the equal-class score, split minus continuous was **+0.15 pp [−0.47, +0.77]**. The split also required **0.083 h/day** more paid time. Where handovers or staffing a split shift are costly, the continuous shift merits consideration. These are pointwise conditional intervals; held-out comparisons do not identify the universally optimal shift.

The highest-volume approach covered an expected 195.94 incoming alerts during its six first-day hours, versus 179.43 for the balanced choice, but left hours 12–20 with **no** extra cover. Over those eight hours, mean work on the first curve was 2.82 seat-hours above three-seat supply; on the second curve it was 4.70 hours above. On the second curve, all 13 hours from 09 to 22 were above the three-seat average processing rate (180/6.8 ≈ 26.47 alerts per hour). Expected work over the interval was **46.27 seat-hours**, versus **45 scheduled seat-hours** even with all six extra hours there. This explains why shifting available hours helps without promising the low-risk standard. Actual service-tail rates in the table come from the discrete-event model, not the mean-work approximation.

For an actual desk, replace transaction counts by de-identified **alert-entry** logs aligned to the real roster clock, estimate active work and class mix, and test fixed schedules on later days and days of the week. Repeatedly simulating one held-out transaction shape does not establish whether either actual local shift should start at 11:00.

### Reproduce offline

Requires the sibling `repro/` directory, Python and NumPy as in [the project instructions](../repro/README.md). From this directory:

```sh
python -B -m unittest -v test_curve
python -B run_study.py --workers 4 --out my_results
```

The 3,040 training replays use root seed 34102641. The 480 held-out replays use root 34102642 (five distinct A20 rosters plus same-roster FCFS). No new engine or optimiser dependency is required. Inspect [training grid](results/training_grid.csv), [locked rosters](results/locked_rosters.json), [hourly inputs](results/profiles.csv), [test levels](results/test_levels.csv), [paired differences](results/test_paired.csv), and [test replications with class denominators](results/test_replications.csv). The same-roster FCFS diagnostic changes the rule rather than the schedule; it is kept outside the schedule comparison above.
