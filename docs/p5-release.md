# Version 2.0.0-rc.1

## Changes

The release brings twelve analytics workspaces, optional multidimensional tables, checksum-validated artifact discovery, read-only connections, accessible tables, and CSV and printable HTML reports into one portable deployment tree. P5 pins the resolved Python 3.12 environment, updates Streamlit and Pillow to advisory-fixed versions, limits browser-facing error details, improves visible keyboard focus, and avoids redundant defaults when the state comparison widget is restored.

## Release gates

| Gate | Status | Evidence |
| --- | --- | --- |
| Clean isolated Windows CPython 3.12.16 install | PASS | Fresh standalone runtime and virtual environment, with compatible pinned dependencies |
| Linux x86-64 compatible wheels | PASS | Resolved and populated a manylinux 2.31 target with 37 binary packages |
| Actual Linux execution and Community Cloud execution | UNVERIFIED | WSL and Docker unavailable locally. Environment and app settings require P6 verification. |
| Navigation and application startup | PASS | Final browser startup with both files, all 12 workspaces at 1366 × 768 and representative workspaces at 1920 × 1080, 768 × 1024 and 390 × 844 |
| Statistical regression and bounded raw shard | PASS | 4,049 independent aggregate checks and all 7 one-file comparisons passed |
| Application regression suite | PASS | 53 tests passed on the final lock, including fallback and saved-payload parity checks |
| Portable archive | PASS | Allowlisted ZIP with per-file SHA-256 and standalone extraction smoke check |
| Protected source artifacts | PASS | Gross population, state and household reconciliation plus pinned SHA-256 values |
| Actual locally saved browser exports | UNVERIFIED | Download controls initiated. The in-app browser produced no newly saved file for inspection in the accessible Downloads folder. Automated payload checks are independent evidence. |
| Accessible controls, keyboard path and tested layouts | PASS | Keyboard skip link focused main, visible control labels, chart table alternatives, and no page-level horizontal overflow in sampled views |
| Screen reader, full contrast/interaction and cross-engine matrix | UNVERIFIED | Tested in-app browser only. No confirmed end-to-end screen-reader session. |
| Dependency advisory audit | PASS | pip-audit checked all 37 final installed packages and returned zero known vulnerabilities at the time of testing |
| Public hosting configuration and release | UNVERIFIED | Remote Git HEAD inspected read-only. Hosted application settings and P6 deployment are separate. |

## Security

Review covered application inputs, exports, database opening, public archive contents and tracked history. Interactive SQL is built from allowlisted tables, metrics and dimensions with bound filter values. Serving disables DuckDB external access and spill. No user uploads or user-supplied SQL are exposed. HTML escapes interpolated report content and CSV neutralizes formula-like text. Local geometry serves the map without a tile API. The application uses static CSS and disables Streamlit usage telemetry. Framework and browser asset requests can still occur.

Targeted secret-signature scans of local text history returned no matching credentials for the searched key patterns. This is a bounded scan. History includes machine-specific paths and a historical Git LFS object whose SHA-256 matches the original analytics database. Keep the prior deployment branch intact during P6. Promote a curated fresh deployment tree to keep historical paths and the historical database out of the release. The current two compact DuckDB artifacts are ordinary Git blobs by explicit path rules and do not require LFS materialization.

The original dependency set returned 61 package advisories across Streamlit and Pillow, including a Windows Streamlit server-side request vulnerability. Raising Streamlit from 1.50.0 to 1.67.0 and Pillow from the original resolution of 11.3.0 to 13.0.0 cleared the advisory scan. No application-level critical security defect remains identified in the reviewed serving flows. Re-run the dependency audit before deployment.

## Performance

Windows on an AMD Ryzen 7 4800H laptop with 16 GB RAM. Python 3.12.16, Streamlit 1.67.0 and DuckDB 1.4.5 served both validated artifacts. One process ran independent AppTest sessions concurrently from a barrier, repeated the same interaction sequence three times per session, timed with a monotonic clock and recorded process working-set values. A fresh process was used for each session count. Timings include Streamlit script execution and chart serialization. Browser painting and network transport are outside these measurements.

| Local concurrent sessions | First Overview median | Geography median | State selector median | Comparison report median | Advanced Explorer median | Peak working set |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1 | 5,678 ms | 366 ms | 363 ms | 114 ms | 109 ms | 192 MiB |
| 3 | 6,810 ms | 1,013 ms | 1,001 ms | 299 ms | 362 ms | 207 MiB |
| 5 | 7,700 ms | 1,545 ms | 1,695 ms | 654 ms | 700 ms | 219 MiB |
| 10 | 12,081 ms | 3,636 ms | 3,687 ms | 1,265 ms | 1,373 ms | 244 MiB |

No scenario errors at these loads. At ten sessions, 30 repeated observations yielded p95 of 4,449 ms for Geography and 2,803 ms for Advanced Explorer. Advancing from five to ten sessions materially increased latency. Some restored advanced selector defaults logged a Streamlit warning during the load test without affecting the result. At five sessions, 15 observations per repeated operation yielded p95 of 1,709 ms for Geography, 1,761 ms for state selection, 1,104 ms for comparison and 810 ms for advanced Explorer. The one-session warm return to Overview was 516 ms median. The observed local browser-serving process reached around 189 MiB peak working set. These results are bounded local measurements. Production capacity, long-duration retention and isolated browser map, rendering and download latency remain unverified.

A separate 15-run microbenchmark over a 252-row filtered education rollup measured 36.78 ms median uncached and 1.22 ms cached. CSV generation took 5.19 ms median for 45,169 bytes. HTML generation took 10.39 ms for 30,933 bytes. Times cover payload generation and exclude browser saving.

Reproduce from the engineering checkout with `python -B benchmark_release.py --sessions 5 --repetitions 3`. The P3 report records the historical baseline. P4A and P4B builder benchmarks measure offline data production separately.

## Files and verification

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| Baseline aggregate `data/india_population_release.duckdb` | 11,284,480 | `e0f491fe2a9b42af228324a786142106826e129bd8af5b394fd696e4a6138939` |
| Advanced aggregate `data/advanced-v1.duckdb` | 5,779,456 | `05053a452415186c4d29a1b4d03c21734cbc492cc4f989890a0683829fb443ac` |

Use `python -B package_release.py pilots/india-population-intelligence-2.0.0-rc.1.zip` in the engineering repository for a new ZIP. The tool refuses an existing destination. The ZIP contains its own SHA-256 file manifest and is validated entry by entry. It includes source, lock, Streamlit config, two serving files, geometry, docs and real dashboard screenshots. Raw Parquet, private work databases, LFS history, credentials and local build logs are outside the deployable tree.

For tests from the engineering checkout, set `INDIA_TEST_PRODUCTION_DB` to the independent production baseline and `INDIA_TEST_ADVANCED_DB` to the pinned advanced file, then run `python -B -m unittest discover -s tests`. Reproduce the independent SQL suite using the commands in [P4D validation](p4d-validation.md). Run `uv pip compile requirements.in --universal --python-version 3.12 --output-file requirements.txt` when intentionally refreshing the lock.

## P6 deployment and rollback

1. Before any remote changes, record the current app's Git revision, branch, Python version, URL, and names of required settings. Preserve the running baseline. The read-only Git remote query returned `main` at `6f369ab`; the hosted dashboard settings could not be inspected.
2. On approval, use only the curated tree and SHA-256 manifest in a fresh staged deployment target. Use repository-root `app.py`, the pinned lock and Python 3.12. The two artifacts resolve from `data/` with no machine-specific environment settings. Confirm Linux startup and resource use on the target, then rerun the workspace and export smoke checks.
3. Open Executive, Geography, all advanced families, Population Explorer and Methodology. Confirm advanced-ready status, exactly 1,500,000,000 people and 397,105,805 households. Select Delhi and Kerala and compare their published scopes and units. Check the baseline fallback in a staging configuration with the advanced file absent.
4. In Chrome or Firefox, save the profile CSV and HTML, comparison CSV and HTML, baseline Explorer aggregate CSV and advanced CSVs for Education, Employment, Income and Households. Confirm the browser's Downloads list and open the new files. Verify UTF-8, scope, denominator, synthetic notice and values against the P4D independent SQL using the selected State/UT and columns.
5. Run keyboard and screen-reader walkthroughs, check recent dependency advisories, and verify the public code/data distribution terms. Promote only after passing the review and obtaining the release approval.
6. Roll back by retaining the prior live app and routing users back to it. If a separate staging revision fails, restore the previous approved Git ref and artifact hashes on the staging target. If a future live update uses the same branch, revert the release commit and restore its previous environment configuration. A Community Cloud Python change requires a separate redeploy. [Community Cloud deploy settings](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) · [Python version changes](https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-python)
