# Real transaction timing for a demand-shape scenario

`hourly_profile.csv` contains the counts of **all 284,807 real card transactions**, grouped into two relative 24-hour periods. It is an input for testing the review queue under a different arrival shape. Alert volume, risk mix, service requirements and staffing remain separate scenario assumptions.

## Source, access and attribution

- **Original publisher:** Worldline and the Machine Learning Group of Université libre de Bruxelles (ULB), [Credit Card Fraud Detection, version 3](https://www.kaggle.com/datasets/mlg-ulb/creditcardfraud/versions/3). The publisher describes two days of European cardholders' transactions in September 2013.
- **Field definition and licence:** the [publisher's metadata endpoint](https://www.kaggle.com/api/v1/datasets/view/mlg-ulb/creditcardfraud) defines `Time` as seconds elapsed since the first transaction. It lists **Database: Open Database, Contents: Database Contents**. Follow [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/) and [DbCL 1.0](https://opendatacommons.org/licenses/dbcl/1-0/), including attribution; retain these notices with the derived aggregate. The data are not described as CC0.
- **Independent catalogue check:** [OpenML 1597](https://www.openml.org/d/1597), [metadata](https://www.openml.org/api/v1/json/data/1597), names Andrea Dal Pozzolo, Olivier Caelen and Gianluca Bontempi as creators. Its broad `Public` licence label is less specific than the original publisher's terms and is not treated as a public-domain grant.
- **Documented mirror:** the official [TensorFlow imbalanced-data tutorial](https://www.tensorflow.org/tutorials/structured_data/imbalanced_data) attributes the same Worldline/ULB dataset and explicitly loads [this original-column CSV](https://storage.googleapis.com/download.tensorflow.org/data/creditcard.csv). The tutorial later drops `Time` for classification; **this aggregation retains the original `Time` column** and performs no classifier preprocessing.

The delivered aggregate was rebuilt from the project's existing original Kaggle v3 `source.zip`. Catalogue metadata and the TensorFlow mirror reference were checked on 24 November 2026. The source archive and individual transaction records are not included in this directory.

Suggested scholarly citation: Andrea Dal Pozzolo, Olivier Caelen, Reid A. Johnson and Gianluca Bontempi (2015), *Calibrating Probability with Undersampling for Unbalanced Classification*, IEEE Symposium on Computational Intelligence and Data Mining. Dataset attribution should additionally name Worldline/ULB and link to the dataset above.

## Interface and exact transformation

| Column | Meaning |
|---|---|
| `day` | `floor(Time / 86400)`, either 0 or 1; a relative period, not a known calendar date |
| `hour` | `floor(Time / 3600) mod 24`, 0–23; relative hour, not local clock hour |
| `count` | Integer number of source transaction rows in that bin |
| `exposure_seconds` | Overlap of the bin with the observed extent from minimum to maximum `Time`; see the endpoint convention below |

Hourly intervals are left-closed/right-open. Every source row is counted once; different transactions at the same second remain distinct. All fraud and non-fraud rows are retained. `Class` is used only to reconcile the published total of 492 fraud labels; it does not select alerts, determine risk tiers or infer review demand. `Amount` and the PCA columns are not used.

### Endpoint convention: 8 seconds short of 48 hours

Observed `Time` ranges from **0 to 172,792 seconds**. The last observed event lies 8 seconds before 48 hours. This does not establish the source's precise collection cutoff: the dataset might simply contain no transaction in the final seconds. To make the chosen exposure transparent, the primary proxy conservatively uses the observed extent. The last event is included; day 1/hour 23 receives **3,592 seconds** exposure and the other 47 bins receive 3,600 seconds. No count is imputed or multiplied inside the CSV.

For each relative hour `h`, pool the two days as:

```text
r_h = 3600 * sum(count[d,h]) / sum(exposure_seconds[d,h])
w_h = r_h / sum(r_0, ..., r_23)
lambda_h = assumed_daily_alert_total * w_h
```

Thus a scenario with 540 expected alerts/day uses `lambda_h = 540 * w_h`. **540 is the queue study's assumption**, not a conversion rate estimated from this dataset. This fixes expected volume; a Poisson realization need not contain exactly 540 alerts. The queue engine determines its own sampling and common-random-number coupling.

Treating the final bin as a full hour instead changes the largest normalized hourly weight by only **0.00004108** (0.004108 percentage points); at 540 expected alerts/day, that is at most **0.0222 expected alerts in any hour**. This is an endpoint-convention sensitivity calculation, not evidence about the unknown collection cutoff. The previous project exploratory summary instead used day 0 alone for hour 23; do not mix that template's statistics with this pooled-exposure template.

## Observed descriptive results

| Statistic | Result |
|---|---:|
| Source rows / fraud-label identity check | 284,807 / 492 |
| Relative day 0 / day 1 rows | 144,786 / 140,021 |
| Observed extent / nominal 48 hours | 172,792 / 172,800 seconds (99.99537%) |
| Peak relative hour | 21; 8,851.5 transactions per observed hour |
| Trough relative hour | 4; 1,104.5 transactions per observed hour |
| Peak-to-trough rate ratio | 8.0140 |
| Six highest-rate relative hours | 21, 18, 11, 20, 10, 14 |
| Share assigned to those six hours after normalization | 35.6444% |

The six hours above are not necessarily contiguous. Full counts, exposures and the 24 normalized weights are in `profile_summary.json`. They describe this two-day sample, not the population of banks or a contemporary digital bank.

## Reproduce and validate

Python 3 standard-library `csv`, `zipfile` and `urllib` are sufficient. No TensorFlow installation, account credentials, model training or third-party Python dependency is needed.

From the `repro` directory, use an original local ZIP or CSV:

```powershell
python data/build_hourly_profile.py --input "C:\path\to\source.zip"
python -m unittest discover -s data -p test_profile.py -v
```

To obtain the original archive, use the publisher's download endpoint and keep it outside any submission/package directory:

```powershell
curl.exe -fL "https://api.kaggle.com/v1/datasets/download/mlg-ulb/creditcardfraud?datasetVersionNumber=3" -o "C:\path\to\source.zip"
```

Alternatively, run `python data/build_hourly_profile.py` to stream the documented TensorFlow mirror directly to the CSV reader without saving raw rows. If the network source is unavailable, the command fails visibly; the `--input` route can reproduce the aggregate offline. The local-archive route was executed for this release. Metadata in `source_metadata.json` records the checked source identities and read route; regenerating the aggregate does not silently refresh or depend on online catalogue metadata.

The script checks the 31-column source schema, finite integer seconds within the two relative days, valid binary labels, 284,807 records, 492 positive labels and a zero relative-time origin before publishing outputs. Tests exercise hourly/day boundaries, repeated timestamps, unsorted input, invalid values, the endpoint convention, all 48 keys, source totals and reconciliation of the exported summary. All 48 counts were also reconciled against the existing project's independent aggregation of the same original archive.

## Scope for the queue study

Use this as a **real-transaction-derived timing proxy**. Comparing phase 0 with a 12-hour rotation tests sensitivity to unknown alignment with the synthetic staffing clock. Keep aggregate alert volume and the risk/service assumptions unchanged when isolating the effect of shape.

This source cannot estimate the fraction of transactions sent to review, actual alert creation times, H/M/L proportions, manual service times, analyst shifts or queue abandonment. Real alerts may batch, cluster or combine several transactions into one case. Only two relative days are observed, so weekly patterns and between-day uncertainty are not estimated. In particular, relative hour 21 must not be relabelled as a verified 21:00 local peak.
