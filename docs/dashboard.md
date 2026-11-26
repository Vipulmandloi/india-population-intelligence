# P2 dashboard guide

The application still uses the validated v3.4 aggregate contract. `app.py` owns startup, routing and the persistent geography controls. `analytics.py` owns read-only cached queries, metric definitions, denominators, and the controlled Explorer registry. `workspaces.py` composes the ten workspace views. `ui.py` supplies charts, map interactions, and shared KPI components. Streamlit theme settings live in `.streamlit/config.toml`.

## Geography and filters

The geographic focus changes the detail views. Rankings and maps retain national context. The comparison control is independent of focus and affects the explicitly labelled comparison views. Map polygons are shaded by the current metric. Select a State/UT marker to focus, or use the keyboard-accessible geographic selector. The geographic reset also clears remembered map selections. Explorer controls define their own geographic scope and remain selected while navigating between workspaces.

The geometry contains 36 simplified State/UT features. Names are matched after folding accents and normalizing ampersands. Ring winding is adapted at render time for Plotly. The data is attributed to DataMeet via geoBoundaries, distributed through GeoDataViewer under CC BY 2.5 India. This community layer is for analytical orientation and carries its source boundary conventions. [Hosted asset and attribution](https://geodataviewer.com/datasets/boundaries/india-states-boundaries/) [License](https://creativecommons.org/licenses/by/2.5/in/)

## Definitions and available detail

- A national rate aggregates its numerator and denominator across states. Comparison gaps between rates are percentage points.
- The national mean annual income is reconstructed from state population weights and rounded state means. Recorded zeros remain in the denominator.
- The age dependency ratio is people aged 0 to 14 and 65 or older per 100 people aged 15 to 64. Generated employed share among people aged 15 and over uses the exact-age denominator and the generator's minimum employment age. These are descriptive synthetic indicators.
- The Explorer exposes a State/UT metric registry and documented joint grains. State-scoped age cohorts use the age-by-gender aggregate summed over gender. Each geography's category shares use its own population denominator.
- Wealth labels are person-level. Mean household size uses distinct household counts. Household-size distributions are unavailable.
- District measures, geographic time series, cross-tabulated education, income distribution or gender pay gaps, and joint banking and insurance measures require additional aggregates. Mother tongue is a coverage placeholder.
- Narrative insights are deterministic comparisons of displayed aggregate values. They carry no significance tests or causal inference.

See [release and provenance](release.md) for production and snapshot validation.
