"""State profiles, unit-safe comparisons, and searchable metric discovery."""

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from advanced_analytics import ADVANCED_STATE_METRICS, MEASURES, advanced_state_series, query
from analytics import METRICS, display, extent, metric_series, tables
from reports import export_csv, printable_report
from ui import PALETTE, bars, chart, kpis

PROFILE_TABLES = {
    "Age and gender": ("age_gender", ("age_group", "Gender")),
    "Settlement": ("settlement", ("settlement",)),
    "Education attainment": ("education", ("education_level",)),
    "Literacy": ("literacy", ("literacy",)),
    "Employment type": ("employment_type", ("employment_type",)),
    "Work status": ("main_activity", ("main_activity",)),
    "Occupation": ("occupation", ("Occupation",)),
    "Religion": ("religion", ("Religion",)),
    "Social group": ("social_group", ("social_group",)),
    "Smartphone and internet": ("digital", ("smartphone_ownership", "internet_access")),
    "Bank account": ("bank", ("bank",)),
    "Health insurance": ("insurance", ("insurance",)),
    "Disability": ("disability", ("disability",)),
    "Generated wealth label": ("wealth", ("wealth",)),
}
SECTIONS = {
    "Demography": ["Age and gender", "Settlement"],
    "Education and work": ["Education attainment", "Literacy", "Employment type", "Work status", "Occupation"],
    "Social composition": ["Religion", "Social group"],
    "Inclusion and wellbeing": ["Smartphone and internet", "Bank account", "Health insurance",
                                "Disability", "Generated wealth label"],
}
DEFAULT_METRICS = ["Urban share", "Internet access", "Mean annual income"]


def state_definitions(scope):
    return {**METRICS, **ADVANCED_STATE_METRICS} if scope.advanced else METRICS


def benchmark_rows(scope, labels, selected):
    definitions = state_definitions(scope)
    data = metric_series(scope, [label for label in labels if label in METRICS])
    if scope.advanced:
        data.update(advanced_state_series(scope.advanced, [label for label in labels if label in ADVANCED_STATE_METRICS]))
    rows = []
    for label, (frame, benchmark) in data.items():
        metric = definitions[label]
        ranked = frame.assign(Rank=frame.Value.rank(method="min", ascending=False).astype("Int64"))
        for row in ranked.loc[ranked.State.isin(selected)].itertuples(index=False):
            gap = row.Value - benchmark if pd.notna(benchmark) and pd.notna(row.Value) else None
            rows.append({
                "State": row.State, "Metric": label, "Value": row.Value, "Unit": metric.unit,
                "All-India benchmark": benchmark,
                "Absolute gap": gap if metric.unit != "%" else None,
                "Percentage-point gap": gap if metric.unit == "%" else None,
                "Relative gap (%)": 100 * gap / abs(benchmark) if gap is not None and benchmark else None,
                "National rank": row.Rank, "Definition / denominator": metric.definition,
            })
    return pd.DataFrame(rows)


def profile_sections(scope, state):
    names = tuple(f"state_{base}_summary" for base, _ in PROFILE_TABLES.values())
    sources = tables(scope.dataset, names + ("state_age_summary", "income_summary"), state)
    sections = []
    for title, (base, dimensions) in PROFILE_TABLES.items():
        data = sources[f"state_{base}_summary"].copy()
        data["Share of state people (%)"] = 100 * data.population / data.population.sum()
        sections.append((title, data[[*dimensions, "population", "Share of state people (%)"]]))
    return sections, sources["state_age_summary"], sources["income_summary"]


def profile_summary(scope, state):
    benchmarks = benchmark_rows(scope, list(state_definitions(scope)), [state])
    population = benchmarks.loc[benchmarks.Metric == "Population", "Value"].item()
    benchmarks.loc[benchmarks.Metric == "Population", "Share of all-India population (%)"] = 100 * population / scope.dataset.records
    return benchmarks


def state_profile(scope):
    state_options = sorted(scope.states.State)
    current = scope.focus or None
    if st.session_state.get("profile_state") != current:
        st.session_state.profile_state = current

    def select_state():
        st.session_state.global_state = st.session_state.profile_state or "All India"

    st.selectbox("State / UT profile", state_options, index=None, placeholder="Choose a State/UT",
                 key="profile_state", on_change=select_state)
    if not scope.focus:
        st.info("Choose a State/UT in Geographic focus or select a map marker, then open State Intelligence.")
        st.button("Open geographic map", on_click=lambda: st.session_state.update(workspace="Geographic Intelligence"))
        return
    state = scope.focus
    st.subheader(state)
    benchmarks = profile_summary(scope, state)
    metrics = benchmarks.set_index("Metric")
    comp, age, income = profile_sections(scope, state)
    mean = age.average_age.iloc[0] if len(age) else None
    med = age.median_age.iloc[0] if len(age) else None
    kpis([
        ("Population", display(metrics.loc["Population", "Value"], "people"), METRICS["Population"].definition),
        ("National population share", f"{metrics.loc['Population', 'Share of all-India population (%)']:.2f}%", "State population divided by all synthetic records."),
        ("Households", display(metrics.loc["Households", "Value"], "households"), METRICS["Households"].definition),
        ("Median age", display(med, "years"), "Median recorded exact age among generated people."),
    ])
    st.caption(f"Mean age {display(mean, 'years')} | Mean household size {display(metrics.loc['Mean household size', 'Value'], 'people / household')}.")
    highlights = benchmarks[benchmarks.Unit == "%"].dropna(subset=["Percentage-point gap"])
    if len(highlights):
        largest = highlights.loc[highlights["Percentage-point gap"].abs().idxmax()]
        st.write(f"{largest.Metric} has the widest rate gap here at {largest['Percentage-point gap']:+.1f} pp versus all India.")
    st.write(f"{state} ranks {metrics.loc['Population', 'National rank']} of {len(scope.states)} by represented population.")
    st.subheader("National benchmarks and ranks")
    st.dataframe(benchmarks, hide_index=True, width="stretch")
    section = st.radio("Profile topic", list(SECTIONS), horizontal=True, key="profile_topic")
    ordered = [(title, frame) for title, frame in comp if title in SECTIONS[section]]
    columns = st.columns(2)
    for index, (title, frame) in enumerate(ordered):
        with columns[index % 2].container(border=True):
            st.markdown(f"**{title}**")
            fields = [column for column in frame.columns if column not in ("population", "Share of state people (%)")]
            plotted = frame.assign(Category=frame[fields].astype(str).agg(" / ".join, axis=1))
            bars(plotted, "Category", height=285)
            for note in extent(plotted, "Category", "population", "people"):
                st.caption(note)
    age_report = age.rename(columns={"average_age": "Mean age (years)", "median_age": "Median age (years)"})
    income_report = income.rename(columns={"average_income": "Mean annual income (INR/person)",
                                           "average_monthly_earnings": "Mean monthly earnings (INR/person)"})
    if section == "Education and work":
        st.dataframe(income_report, hide_index=True, width="stretch")
        st.caption("Income means include generated zeros. Earnings are generated annual income divided by 12 and rounded down per person.")
    advanced_sections = []
    if scope.advanced:
        for title, name, dimensions, measure in (
            ("Education by gender", "education_gender", ("Gender", "education"), "People"),
            ("Working-age employed share by gender", "employment_age_gender", ("Gender",), "Employed share ages 15-64"),
            ("Annual income bands", "income_bands_state", ("income_band",), "Valid recorded incomes"),
            ("Household sizes", "household_sizes", ("household_size",), "Households"),
            ("Smartphone and internet by gender", "digital_age_gender", ("Gender", "smartphone", "internet"), "People"),
            ("Bank account and insurance", "financial_employment", ("bank", "insurance"), "People"),
        ):
            data = query(scope.advanced, name, dimensions, measure, (("State", (state,)),))
            advanced_sections.append((title, data.assign(Metric=measure, Unit=MEASURES[measure].unit,
                                                         **{"Definition / denominator": MEASURES[measure].definition})))
        with st.expander("Advanced profile breakdowns"):
            topic = st.selectbox("Advanced profile topic", [title for title, _ in advanced_sections])
            st.dataframe(dict(advanced_sections)[topic], hide_index=True, width="stretch")
    detail_rows = pd.concat([
        frame.rename(columns={"population": "Value"}).assign(
            Topic=title, Unit="people", **{"Definition / denominator": "Synthetic people in this category. Shares divide by all people in the selected State/UT."})
        for title, frame in comp
    ], ignore_index=True)
    supplemental = pd.DataFrame([
        {"State": state, "Topic": "Age", "Metric": "Median age", "Value": med, "Unit": "years",
         "Definition / denominator": "Median exact age among generated people in this State/UT."},
        {"State": state, "Topic": "Income", "Metric": "Mean monthly earnings",
         "Value": income.average_monthly_earnings.iloc[0] if len(income) else None, "Unit": "INR / person",
         "Definition / denominator": "Mean of generated annual income divided by 12 and rounded down per person. Includes recorded zeros."},
    ])
    advanced_csv = [data.rename(columns={"value": "Value"}).assign(Topic=title) for title, data in advanced_sections]
    profile_csv = pd.concat([benchmarks.assign(Topic="National benchmarks"), supplemental, detail_rows, *advanced_csv], ignore_index=True)
    html = printable_report(f"{state} intelligence profile", state, scope.dataset.version,
                            [("National benchmarks", benchmarks), ("Age", age_report), ("Income", income_report), *comp, *advanced_sections])
    c1, c2 = st.columns(2)
    c1.download_button("Download profile CSV", export_csv(profile_csv, "State profile", state, scope.dataset.version),
                       "state-profile.csv", "text/csv", on_click="ignore")
    c2.download_button("Download printable profile", html, "state-profile.html", "text/html", on_click="ignore")
    st.caption("National ranks are ordered from highest value, with equal values sharing rank. Rankings are descriptive.")


def benchmark_chart(rows, label, height=320):
    sub = rows.loc[rows.Metric == label].dropna(subset=["Value"])
    if sub.empty:
        st.info("No observations for the selected metric and geography.")
        return
    unit = sub.Unit.iloc[0]
    fig = go.Figure()
    fig.add_bar(name="State/UT", x=sub.State.tolist(), y=sub.Value.tolist(), marker_color=PALETTE[0],
                customdata=[display(value, unit) for value in sub.Value],
                hovertemplate="%{x}<br>%{customdata}<extra>State/UT</extra>")
    if unit not in {"people", "households"} and len(sub) and pd.notna(sub["All-India benchmark"].iloc[0]):
        fig.add_bar(name="All India", x=sub.State.tolist(), y=sub["All-India benchmark"].tolist(),
                    marker_color=PALETTE[1], hovertemplate="%{y:,.2f}<extra>All India</extra>")
    fig.update_layout(title_text=label, yaxis_title=unit, barmode="group")
    chart(fig, height)


def compare_states(scope):
    if not scope.comparison:
        st.info("Choose up to five State/UTs in the comparison control to begin.")
        return
    if "compare_metrics" not in st.session_state:
        st.session_state.compare_metrics = list(DEFAULT_METRICS)
    labels = st.multiselect("Comparison metrics", list(state_definitions(scope)),
                            max_selections=6, key="compare_metrics")
    if not labels:
        st.info("Select at least one metric.")
        return
    rows = benchmark_rows(scope, labels, scope.comparison)
    if st.session_state.get("compare_chart_metric") not in labels:
        st.session_state.compare_chart_metric = labels[0]
    selected_metric = st.selectbox("Metric for grouped bars", labels, key="compare_chart_metric")
    view = st.radio("Comparison visualization", ["Grouped bars", "Relative-gap heatmap", "Small multiples"],
                    horizontal=True, key="compare_view")
    if view == "Grouped bars":
        benchmark_chart(rows, selected_metric)
        st.caption("All-India totals appear in the table for additive counts. The bar chart compares selected State/UT counts on a shared scale.")
    elif view == "Relative-gap heatmap":
        pivot = rows.pivot(index="Metric", columns="State", values="Relative gap (%)").reindex(index=labels, columns=scope.comparison)
        if pivot.isna().all().all():
            st.info("No relative gaps are available for these metrics.")
        else:
            chart(px.imshow(pivot, color_continuous_scale="RdBu", color_continuous_midpoint=0,
                            text_auto=".1f", aspect="auto", labels={"color": "Relative gap (%)"}), 340)
            st.caption("Every cell is a relative percentage difference from its own all-India benchmark. Blank cells have an unavailable or zero benchmark.")
    else:
        columns = st.columns(2)
        for index, label in enumerate(labels):
            with columns[index % 2]:
                benchmark_chart(rows, label, 300)
        st.caption("Each chart has its own unit and scale.")
    sub = rows.loc[rows.Metric == selected_metric].dropna(subset=["Value"])
    for note in extent(sub, "State", "Value", state_definitions(scope)[selected_metric].unit):
        st.write(note)
    gaps = sub.dropna(subset=["Relative gap (%)"])
    if len(gaps):
        widest = gaps.loc[gaps["Relative gap (%)"].abs().idxmax()]
        st.caption(f"{widest.State} has the largest relative gap for {selected_metric.lower()} at {widest['Relative gap (%)']:+.1f}% versus all India.")
    st.dataframe(rows, hide_index=True, width="stretch")
    st.caption("Sort by a column header. Absolute gaps use metric units. Rate gaps use percentage points. Relative gaps divide the signed gap by the absolute benchmark.")
    geography = ", ".join(scope.comparison)
    c1, c2 = st.columns(2)
    c1.download_button("Download benchmark CSV", export_csv(rows, "State comparison", geography, scope.dataset.version),
                       "state-comparison.csv", "text/csv", on_click="ignore")
    c2.download_button("Download printable comparison",
                       printable_report("State comparison", geography, scope.dataset.version, [("Selected metrics", rows)]),
                       "state-comparison.html", "text/html", on_click="ignore")


def metric_catalogue():
    query = st.text_input("Search metric catalogue", placeholder="Try income, age, or banking").strip().casefold()
    rows = [{"Metric": label, "Unit": metric.unit, "Definition / denominator": metric.definition}
            for label, metric in METRICS.items()
            if query in f"{label} {metric.unit} {metric.definition}".casefold()]
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No metric matches that search.")
