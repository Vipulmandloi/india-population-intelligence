# Proposed release — India Population Intelligence V2

Target tag after production approval is v2.0.0. Scope is a production-scale synthetic analytics portfolio dashboard with twelve workspaces, State/UT profiles and comparisons, nineteen advanced aggregate tables, a multidimensional Explorer and documented CSV/HTML exports.

The release preserves 1,500,000,000 synthetic people, 397,105,805 distinct synthetic households and all 36 States and UTs. The P5 baseline passed 53 regression tests, 4,049 aggregate audit checks and seven independent one-shard checks. Local single-session AppTest Advanced Explorer median was 109 ms. At five sessions the median was 700 ms and process peak working set was 219 MiB.

| Serving artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| Baseline snapshot | 11284480 | e0f491fe2a9b42af228324a786142106826e129bd8af5b394fd696e4a6138939 |
| Advanced aggregates | 5779456 | 05053a452415186c4d29a1b4d03c21734cbc492cc4f989890a0683829fb443ac |

The P5 candidate ZIP has SHA-256 53f6fae27f71b1a60518fb2e34842f94f0282c2d745340914ec9189e57efb0b2. Its manifest enumerates the original candidate files; the staging branch can add reviewed release documentation. The app uses validated aggregate files. Outputs are synthetic and contain no official population estimates. District analytics, household wealth and exact income percentiles are outside this release.

## Hosting and rollback

Deploy the reviewed staging ref as a separate Community Cloud app with root app.py and Python 3.12. Staging production-mode settings are INDIA_APP_MODE=production and INDIA_DB_PATH=data/india_population_release.duckdb. The advanced artifact resolves automatically.
Before any approved cutover, record the production runtime, secrets names and routing details from the account. Compare the hosted staging UI with independent references and verify actual saved exports. Preserve the original deployment and its URL throughout P6A. If a later cutover is reversed, route users back to the unchanged original deployment. If a later same-branch rollout is expressly approved, restore the prior configuration and revert its release commit without rewriting history.

[Original public app](https://india-population-intelligence-zqswauvqgeangeb7sgs6tw.streamlit.app/)
