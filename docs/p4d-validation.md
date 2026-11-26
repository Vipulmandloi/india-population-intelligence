# P4D independent statistical validation

Audited 26 November 2026 from the P4C checkpoint `6e8184f` on `feature/india-population-v2`. The data release is v3.4 synthetic with P4B advanced aggregate schema v1. All figures describe generated people and households. The audit establishes internal consistency for the pinned artifacts. It does not establish real-world representativeness, official benchmark accuracy, or sampling uncertainty.

## Results

| Evidence | Passed | Failed | Scope |
| --- | ---: | ---: | --- |
| Independent aggregate audit | 4,049 | 0 | Three pinned DuckDB databases and the state geometry catalogue |
| Independent bounded raw-shard check | 7 | 0 | 100,000 records from one existing Parquet file against its one-file pilot aggregate |
| Automated regression and application tests | 52 | 0 | 10 new P4D tests and 42 existing tests, including release-backed paths |
| Browser smoke and responsive checks | Qualitative | Qualitative | Local in-app browser only. Details below |

The automated and independent suites executed **4,108 checks and test cases**. Browser observations are recorded separately. A check can cover an entire table projection, a set of aggregate cells, or a benchmark row with several fields.

| Measure | Independent reference | Observed result |
| --- | --- | --- |
| People | Sum of production State/UT counts; the same state totals in every advanced grain | 1,500,000,000 |
| Geography | Unique State/UT names plus exact canonical geometry joins | 36 |
| Distinct households | Sum of production state household counts; sum of advanced size-frequency cells | 397,105,805 |
| Household size | Sum of size × households divided by distinct households | 3.77733 people per household |
| Valid recorded annual income | Production partial count sums reconciled to all seven advanced income grains | 1,500,000,000 |
| Recorded annual income sum | Production partial integer income sums reconciled by State/UT | INR 229,298,948,601,272 |
| Recorded zero income | Exact zero-band count, validated across gender and settlement bands | 897,451,870 |
| Recorded annual income per person | Exact recorded income sum divided by valid recorded-income count | INR 152,865.96573 |

## Validation matrix

| Area | Independent calculation and acceptance |
| --- | --- |
| Geography and population | Compare exact State/UT population vectors for all 19 tables and the baseline. Enforce a unique, labeled grain, match geometry keys one-to-one, compare age × gender and settlement margins, and validate the 42 published snapshot projections against production. |
| Education | Reconcile attainment margins to production by State/UT. Reconstruct gender, age and settlement cross-tabs from joint cells and independently normalize rows, columns and totals. Graduate-share benchmarks use an all-people denominator. Literacy remains a separate concept. |
| Employment and occupation | Compare labels to the baseline activity rollup using the documented Child and Student/Other mapping. Reconcile eligibility against exact ages for 15+ and 15–64, and compare occupation margins. Employed shares use eligible people with a known status. These fields support descriptive employed shares. Official LFPR, WPR and unemployment rates are outside the advanced metric registry. |
| Income | Reconcile exact counts and sums in all income grains. For each of 216 observed State/UT × band cells, check counts and sum bounds. Zero has its own band and counts as valid. Positive bands use consecutive lower-inclusive, upper-exclusive edges of 1, 50,000, 100,000, 250,000, 500,000 and 1,000,000 INR. Null and negative values are missing or invalid. Aggregate bounds assess stored consistency. The one-file check and builder fixtures provide separate raw and boundary evidence. The advanced national benchmark sums integer incomes and counts before dividing. The baseline mean separately weights the published rounded state means by state population. |
| Households and wealth | Compare state household totals, then require size × household count = member count in every size/settlement cell. Validate household-frequency and member denominators separately. Wealth labels remain person-level synthetic attributes. |
| Digital and finance | Compare the stored joint smartphone × internet margin and the banking and insurance margins with the baseline. Validate advanced cross-tabs on stored joint aggregates only. The separate shard check reconciles joint digital and financial counts directly from person rows. |
| Explorer | Enumerate every registered advanced metric and supported ordered one- and two-axis combination. Compare application cells to Python integer rollups of independently read joint tables for national scope and a Delhi/Kerala plus category filter. Verify ratio numerators and denominators, and applicable total, row and column shares. Shares use the corresponding filtered total before Top/Bottom-N display limits. Automated UI tests cover representative ranking, pivot and export paths. |
| State Intelligence and Comparison | Recompute 21 metrics for each of 36 jurisdictions using independent SQL. Check values, units, national benchmarks, competition rankings, percentage-point gaps, absolute gaps and relative gaps. Relative gaps divide the signed difference by the absolute benchmark. A missing or zero denominator leaves a ratio unavailable. All 36 profile navigation choices were also exercised through Streamlit AppTest. |
| Insights | Exercise tied leaders and trailing categories, tied comparisons, unavailable benchmarks and missing or zero values. Insights describe filtered synthetic aggregates and differences. |
| Exports | Capture the actual bytes registered with Streamlit. Compare a Delhi profile CSV and printable HTML, household size rows, five-state comparison CSV and HTML, P3 Top-N Explorer CSV, and advanced normalized cross-tab and Bottom-N ranking exports to independent references. Check synthetic notices, scope and sampled metadata. Fixtures exercise spreadsheet formula prefixes and escaped HTML text. |
| Adversarial | Use isolated copies and synthetic fixtures for invalid dimensions and filters, zero denominators, missing and invalid values, incompatible, corrupt, duplicate or scope-mismatched artifacts, fallback, and a changed file revision after caching. |

Counts and integer sums require exact equality. Independent ratios use exact rational arithmetic before comparison to application floats. Aggregate comparisons use absolute tolerance 1e-9 and relative tolerance 1e-12 for binary arithmetic. Printable report numeric assertions allow 0.000051 for four-decimal display formatting.

## Browser and accessibility

Launched Streamlit locally with the bundled baseline and pinned advanced artifact. Opened all 12 workspaces. Checked a map with 36 shapes and markers, clicked the Uttar Pradesh marker, and cleared its geographic selection. Checked the comparison empty state and selected Delhi and Kerala. Used the keyboard to select Female in the Education chart’s highlight control. Inspected the advanced heatmap and its aggregate table at 1440, 900 and 420 pixels with no page-level horizontal overflow in that view. Confirmed that the Methodology workspace displays the 4,049 passing checks and frozen scope. Comparison metric definitions and accessible table rows were present.

Browser delivery of the downloaded file remains unverified. The browser download event did not return a saved file for inspection. The automated tests verified the actual downloadable payloads. Screen-reader compatibility, a cross-browser or physical-device matrix, Cloud execution, and exhaustive interactive rendering for every metric/filter combination remain unverified. Full raw-record recertification and official calibration are outside this audit. The grouped release does not establish exact income percentiles, analytics below State/UT, mother tongue, or intersections absent from stored aggregates.

## Corrected defects

- Working-age employment shares could be grouped or filtered by employment status, yielding tautological percentages. The registry, UI and query validation now exclude the outcome axis for these rates.
- A cache hit could bypass a changed advanced-file revision. The revision is now checked before cache lookup as well as on cache misses.
- Insight descriptions could select one arbitrary leader from a tie. They now describe ties and handle unavailable benchmarks.
- CSV text beginning with spreadsheet formula characters could be interpreted on open. Spreadsheet-facing text is now neutralized, including formula markers after leading whitespace, while typed numeric values retain numeric form. HTML content remains escaped.
- Data Quality & Methodology now presents the frozen P4D results, reconciliation and limits, alongside the advanced metric and grain catalogue.

## Artifact integrity

SHA-256 matched at the start and finish. The audit opened production, snapshot, pilot and advanced databases read-only. It did not run a production-scale scan or aggregation.

| Protected artifact | SHA-256 |
| --- | --- |
| Original production analytics DuckDB | `bb8453a00ff5e832ecb1ee98ff286c81f2410d4f6a481a955a6786c0ad822e2c` |
| Bundled sanitized baseline snapshot | `e0f491fe2a9b42af228324a786142106826e129bd8af5b394fd696e4a6138939` |
| P4B v1 advanced DuckDB | `05053a452415186c4d29a1b4d03c21734cbc492cc4f989890a0683829fb443ac` |
| Parquet manifest | `e97fc968277d486d78f0ac87d27f9507aab327ac95eab468be17aec74cc23bdb` |
| Deployment bundle DuckDB copy | `bb8453a00ff5e832ecb1ee98ff286c81f2410d4f6a481a955a6786c0ad822e2c` |
| Deployment bundle app entry point | `0f909f54bc96dd6551d6f9a575c9589dd7acfa90e87961b091496bcdf4b2ad83f` |

## Reproduction

Use the repository's environment with the pinned dependencies. Run from the repository root. Set the two test environment variables to your validated local files. Choose an unused report path. The runner refuses to overwrite reports or accept a different artifact hash. For another release, review and update the pins and expected scope intentionally.

```powershell
$env:INDIA_TEST_PRODUCTION_DB = 'path/to/production.duckdb'
$env:INDIA_TEST_ADVANCED_DB = 'path/to/advanced-v1.duckdb'

python -B validate_p4d.py --production $env:INDIA_TEST_PRODUCTION_DB --snapshot data/india_population_release.duckdb --advanced $env:INDIA_TEST_ADVANCED_DB --report pilots/p4d-local-audit.json
python -B validate_p4d_sample.py path/to/part-07501.parquet pilots/run-100k/advanced.duckdb
python -B -m unittest discover -s tests
```

The sample requires the existing P4A one-file pilot. It is a bounded provenance check and does not represent a randomly selected sample or a row-level audit of P4B. The [machine-readable aggregate summary](p4d-validation.json) is the published output of the reference runner.

## Suggested P5 acceptance

Review the approved release files and SHA-256 manifest independently. Reproduce a clean local install and privately test a Cloud-compatible baseline and optional-advanced configuration. Measure cold start and concurrent memory use. Confirm real-browser downloads and run cross-browser, mobile and screen-reader checks. Obtain separate approval before distributing artifacts or deploying.
