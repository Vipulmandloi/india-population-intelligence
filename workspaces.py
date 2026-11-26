"""Analytical workspaces composed from validated aggregate measures."""

from dataclasses import replace

import pandas as pd
import plotly.express as px
import streamlit as st

from analytics import BREAKDOWNS, METRICS, display, explore, extent, metric_series, state_metric, table
from intelligence import metric_catalogue
from reports import export_csv, printable_report
from ui import AGE_ORDER, bars, chart, grouped, insight_panel, kpis, state_map


def summary(scope):
    national = table(scope.dataset, "national_summary").iloc[0]
    if not scope.focus:
        return national.total_population, national.distinct_households, national.average_age, national.median_age
    state = scope.states.loc[scope.states.State == scope.focus].iloc[0]
    age = table(scope.dataset, "state_age_summary", scope.focus)
    return state.population, state.households, state.average_age, age.iloc[0].median_age if len(age) else None


def metric_tile(scope, label, series=None):
    frame, national = series[label] if series is not None else state_metric(scope, label)
    metric = METRICS[label]
    value = frame.set_index("State").Value.get(scope.focus) if scope.focus else national
    return label, display(value, metric.unit), metric.definition


def comparison(scope, frame, label, benchmark):
    metric = METRICS[label]
    selected = frame.loc[frame.State.isin(scope.comparison)].sort_values("Value", ascending=False).copy()
    if selected.empty:
        return
    st.subheader("Selected State/UT comparison")
    if benchmark is not None and metric.unit not in {"people", "households"}:
        selected["National benchmark"] = benchmark
        selected["Gap (pp)" if metric.unit == "%" else "Gap from benchmark"] = selected.Value - benchmark
    if len(selected) > 1:
        reference = selected.iloc[0]
        selected["Gap to leader (pp)" if metric.unit == "%" else "Gap to leader"] = selected.Value - reference.Value
    st.dataframe(selected, hide_index=True, width="stretch")
    insight_panel(selected, "State", "Value", metric.unit, benchmark if metric.unit not in {"people", "households"} else None)


def composition(scope, base, column, title, compare=True, exclude=None):
    frame = scope.frame(base)
    if exclude:
        frame = frame.loc[frame[column] != exclude]
    with st.container(border=True):
        st.markdown(f"**{title}**")
        bars(frame, column, height=310)
        if compare and scope.comparison:
            detail = table(scope.dataset, f"state_{base}_summary")
            detail = detail.loc[detail.State.isin(scope.comparison)].copy()
            if exclude:
                detail = detail.loc[detail[column] != exclude]
            if len(detail):
                detail["Share"] = detail.population / detail.groupby("State").population.transform("sum") * 100
                with st.expander(f"Compare {title.lower()} by state"):
                    grouped(detail, column, "State", "Share")
                    st.caption("Share within each selected state and displayed category universe (%).")


def benchmark_view(scope, options, key):
    label = st.selectbox("Ranking metric", options, key=key)
    frame, bench = state_metric(scope, label)
    metric = METRICS[label]
    st.caption(metric.definition)
    ranking = frame.dropna().sort_values("Value", ascending=False)
    left, right = st.columns([3, 2])
    with left:
        bars(ranking.head(10), "State", "Value", "Leading State/UTs", metric.unit)
    with right:
        insight_panel(ranking, "State", "Value", metric.unit, bench if metric.unit not in {"people", "households"} else None)
    comparison(scope, frame, label, bench)


def executive(scope):
    population, households, mean, median = summary(scope)
    kpis([
        ("Population", display(population, "people"), METRICS["Population"].definition),
        ("Households", display(households, "households"), METRICS["Households"].definition),
        ("Median age", f"{median:g} years" if pd.notna(median) else "Unavailable", "Median exact age in the selected geography."),
        ("States / UTs", str(1 if scope.focus else len(scope.states)), "Geographies in the current focus."),
    ])
    st.caption(f"Mean age in {scope.label} is {display(mean, 'years')}.")
    shortcut_a, shortcut_b, _ = st.columns([1, 1, 2])
    shortcut_a.button("Open Population Explorer", on_click=lambda: st.session_state.update(workspace="Population Explorer"))
    shortcut_b.button("Open Geographic Intelligence", on_click=lambda: st.session_state.update(workspace="Geographic Intelligence"))
    frame, _ = state_metric(scope, "Population")
    map_col, rank_col = st.columns([3, 2])
    with map_col.container(border=True):
        st.subheader("Population footprint")
        state_map(scope, frame, "people", "overview_map")
    with rank_col.container(border=True):
        st.subheader("State / UT rankings")
        ranking = st.radio("Show ranking", ("Largest", "Smallest"), horizontal=True, key="home_rank")
        sample = frame.nlargest(7, "Value") if ranking != "Smallest" else frame.nsmallest(7, "Value")
        bars(sample, "State", "Value", height=315)
        insight_panel(frame, "State", "Value", "people")
    with st.expander("Population share and complete ranking"):
        shares = frame.assign(Share=frame.Value / frame.Value.sum() * 100)
        st.dataframe(shares.sort_values("Value", ascending=False), width="stretch", hide_index=True)
        chart(px.treemap(shares, path=["State"], values="Value", color="Value",
                         color_continuous_scale=["#243A64", "#62DDCB"]), 320)
    st.subheader("Inclusion and economy")
    rows = (("Urban share", "Employed share", "Internet access", "Bank account coverage"),
            ("Mean annual income", "Smartphone ownership", "Health insurance coverage"))
    series = metric_series(scope, [label for row in rows for label in row])
    for row in rows:
        kpis([metric_tile(scope, label, series) for label in row])
    gender = (scope.frame("age_gender").groupby("Gender", as_index=False).population.sum()
              if scope.focus else table(scope.dataset, "gender_summary"))
    c1, c2 = st.columns(2)
    with c1:
        bars(gender, "Gender", title="Gender composition", height=240)
    with c2:
        bars(scope.frame("settlement"), "settlement", title="Rural and urban composition", height=240)


def geography(scope):
    label = st.selectbox("Map and comparison metric", list(METRICS), key="geo_metric")
    metric = METRICS[label]
    frame, national = state_metric(scope, label)
    st.caption(metric.definition)
    kpis([metric_tile(scope, name) for name in ("Population", "Urban share", "Mean household size")])
    left, right = st.columns([3, 2])
    with left.container(border=True):
        state_map(scope, frame, metric.unit, "geography_map")
    with right.container(border=True):
        bars(frame.nlargest(10, "Value"), "State", "Value", label, metric.unit, height=395)
    if scope.focus:
        st.button(f"Open {scope.focus} profile", on_click=lambda: st.session_state.update(workspace="State Intelligence"))
    if scope.comparison:
        st.button("Open advanced comparison", on_click=lambda: st.session_state.update(workspace="State Comparison"))
    comparison(scope, frame, label, national)
    with st.expander("Complete ranking and geography coverage", expanded=True):
        st.dataframe(frame.sort_values("Value", ascending=False), hide_index=True, width="stretch")
        if scope.focus:
            locality = table(scope.dataset, "city_summary", scope.focus)
            if locality.City.nunique() > 1:
                bars(locality, "City", title="Generated locality labels")
            else:
                st.caption("City is a generated State/UT placeholder. District and verified city statistics are unavailable.")
        bars(scope.frame("settlement"), "settlement", title="Settlement counts for the current focus", height=230)


def demographics(scope):
    age = scope.frame("age_value")
    _, _, mean, median = summary(scope)
    tiles = [
        ("Mean age", display(mean, "years"), METRICS["Mean age"].definition),
        ("Median age", f"{median:g} years" if pd.notna(median) else "Unavailable", "Median age of generated people."),
    ]
    if not age.empty:
        working = age.loc[age.Age.between(15, 64), "population"].sum()
        dependent = age.population.sum() - working
        tiles += [
            ("Population aged 15-64", display(working, "people"), "Count of synthetic people aged 15 through 64."),
            ("Age dependency ratio", f"{100 * dependent / working:.1f}" if working else "Unavailable",
             "People aged 0-14 or 65+ per 100 people aged 15-64. This is a demographic measure."),
        ]
    kpis(tiles)
    cohort = scope.frame("age_gender").copy()
    with st.container(border=True):
        st.subheader("Population pyramid")
        for gender in cohort.Gender.unique():
            if gender not in {"Female", "Male"}:
                st.caption("Additional gender categories appear on the positive side.")
                break
        cohort["Signed count"] = cohort.population.where(cohort.Gender != "Female", -cohort.population)
        fig = px.bar(cohort, x="Signed count", y="age_group", color="Gender", orientation="h",
                     category_orders={"age_group": AGE_ORDER, "Gender": ["Female", "Male"]}, custom_data=["population"])
        fig.update_traces(hovertemplate="%{y}<br>%{customdata[0]:,} synthetic people<extra>%{fullData.name}</extra>")
        fig.update_layout(barmode="relative", xaxis_title="Female (left) and other categories (right)", yaxis_title="Age cohort")
        chart(fig, 360)
    if not age.empty:
        with st.container(border=True):
            st.subheader("Exact-age distribution")
            chart(px.line(age.sort_values("Age"), x="Age", y="population", labels={"population": "Synthetic people"}), 300)
            insight_panel(age, "Age")
    else:
        st.info("Exact-age frequencies are unavailable in this artifact.")
    c1, c2 = st.columns(2)
    with c1:
        composition(scope, "marital", "marital", "Marital status")
    with c2:
        composition(scope, "settlement", "settlement", "Settlement")
    if scope.comparison:
        detail = table(scope.dataset, "state_age_gender_summary")
        detail = detail.loc[detail.State.isin(scope.comparison)]
        choice = st.selectbox("Gender for cohort comparison", sorted(detail.Gender.unique()))
        grouped(detail.loc[detail.Gender == choice], "age_group", "State")
    st.caption("Age by settlement requires a joint aggregate. The settlement chart displays its own population breakdown.")


def education(scope):
    c1, c2 = st.columns(2)
    with c1:
        composition(scope, "education", "education_level", "Education attainment")
    with c2:
        composition(scope, "literacy", "literacy", "Literacy status")
    st.caption("Literacy and education attainment are separate generated attributes. Literacy includes an explicit not-applicable category.")
    attainment = table(scope.dataset, "state_education_summary")
    category = st.selectbox("Attainment level for ranking", sorted(attainment.education_level.unique()))
    totals = attainment.groupby("State").population.sum()
    counts = attainment.loc[attainment.education_level == category].groupby("State").population.sum()
    result = (counts.reindex(totals.index, fill_value=0) / totals * 100).rename("Value").reset_index()
    bars(result.nlargest(10, "Value"), "State", "Value", f"Share with {category}", "%")
    benchmark = (counts.sum() / totals.sum() * 100) if totals.sum() else None
    chosen = result.loc[result.State.isin(scope.comparison)] if scope.comparison else result
    insight_panel(chosen, "State", "Value", "%", benchmark)
    st.caption("Education by gender, age, or rural/urban residence requires new joint aggregates.")


def employment(scope):
    age = scope.frame("age_value")
    activity = scope.frame("main_activity")
    employed = activity.loc[activity.main_activity == "Employed", "population"].sum()
    tiles = [metric_tile(scope, label) for label in ("Employed share", "Mean annual income")]
    adults = age.loc[age.Age >= 15, "population"].sum()
    if adults and scope.dataset.version == "v3.4":
        tiles.append(("Employed among ages 15+", f"{employed / adults:.1%}",
                      "Generated employed count divided by people aged 15+. The generator assigns employment at ages 15 and over."))
    kpis(tiles)
    st.caption("The 'Not employed' label includes people outside generated employment. It cannot establish unemployment or labour-force participation.")
    c1, c2 = st.columns(2)
    with c1:
        composition(scope, "occupation", "Occupation", "Assigned occupations", exclude="Not applicable")
        composition(scope, "main_activity", "main_activity", "Work status")
    with c2:
        composition(scope, "employment_type", "employment_type", "Employment type")
        income = table(scope.dataset, "income_summary", scope.focus)
        with st.container(border=True):
            bars(income.nlargest(10, "average_income"), "State", "average_income", "Mean annual income per synthetic person", "INR / person")
            st.caption("Includes generated zero income. Monthly earnings use annual income divided by 12, rounded down per person.")
            with st.expander("Annual and monthly income table"):
                st.dataframe(income, hide_index=True, width="stretch")
    benchmark_view(scope, ["Mean annual income", "Employed share"], "employment_rank")
    st.caption("Income bands, medians and gender differences require additional aggregates.")


def social(scope):
    c1, c2 = st.columns(2)
    with c1:
        composition(scope, "religion", "Religion", "Religion")
    with c2:
        composition(scope, "social_group", "social_group", "Social group")
    with st.container(border=True):
        st.subheader("Language coverage")
        st.dataframe(scope.frame("mother_tongue"), hide_index=True, width="stretch")
        st.caption("Mother tongue is a placeholder in v3.4. Other/Unclassified in the social group distribution is a residual category.")
    st.caption("Religion and selected social group inputs use historical calibration where available. Generated counts do not describe actual communities.")


def digital(scope):
    kpis([metric_tile(scope, label) for label in ("Internet access", "Smartphone ownership", "Bank account coverage", "Health insurance coverage")])
    with st.container(border=True):
        st.subheader("Smartphone and internet segments")
        joint = scope.frame("digital").copy()
        joint["Segment"] = "Phone " + joint.smartphone_ownership.astype(str) + " / Internet " + joint.internet_access.astype(str)
        bars(joint, "Segment", height=270)
        insight_panel(joint, "Segment")
    c1, c2 = st.columns(2)
    with c1:
        composition(scope, "bank", "bank", "Bank account status")
    with c2:
        composition(scope, "insurance", "insurance", "Health insurance status")
    benchmark_view(scope, ["Internet access", "Smartphone ownership", "Bank account coverage",
                           "Health insurance coverage"], "digital_rank")
    st.caption("Banking and insurance totals are separate margins. Joint segmentation is available for smartphone ownership and internet access.")


def households(scope):
    kpis([metric_tile(scope, label) for label in ("Households", "Mean household size", "Disability prevalence")])
    left, right = st.columns(2)
    with left.container(border=True):
        wealth = scope.frame("wealth").sort_values("wealth")
        fig = px.bar(wealth, x=wealth.wealth.astype(str).tolist(), y=wealth.population.tolist(),
                     title="Synthetic people by generated wealth label",
                     labels={"x": "Generated wealth label", "y": "Synthetic people"})
        chart(fig, 330)
        st.caption("The generator assigns these labels to people. Members of a household may have different labels.")
    with right:
        composition(scope, "disability", "disability", "Disability status")
    with st.expander("Household counts by State/UT"):
        st.dataframe(scope.states[["State", "population", "households"]].sort_values("households", ascending=False),
                     hide_index=True, width="stretch")
    benchmark_view(scope, ["Households", "Mean household size", "Disability prevalence"], "household_rank")
    st.caption("Mean household size divides people by distinct households. Household-size distributions are unavailable.")


def explorer(scope):
    def reset():
        st.session_state.update({
            "explorer_grain": "State / UT", "explorer_states": [],
            "explorer_order": "Highest first", "explorer_chart": "Bar",
            "explorer_state_metric": "Population", "explorer_people_metric": "Population",
            "explorer_limit_type": "All rows", "explorer_limit": 10, "explorer_benchmark": False,
        })
        for key in list(st.session_state):
            if key.startswith("explorer_categories_"):
                st.session_state[key] = []

    st.button("Reset Explorer", on_click=reset)
    with st.container(border=True):
        first, second = st.columns(2)
        with first:
            grain = st.selectbox("Breakdown", ["State / UT", *BREAKDOWNS], key="explorer_grain")
            choices = list(METRICS) if grain == "State / UT" else ["Population", "Share of geographic population"]
            metric = st.selectbox("Metric", choices, key="explorer_state_metric" if grain == "State / UT" else "explorer_people_metric")
        with second:
            selected = st.multiselect("Explorer State/UT scope", sorted(scope.states.State), key="explorer_states")
            order = st.selectbox("Sort", ["Highest first", "Lowest first", "Label"], key="explorer_order")
        st.caption("Explorer scope is independent of the dashboard focus. Rates and means by State/UT appear on that breakdown. Category filters retain each geography's population denominator.")
        result = explore(scope, grain, metric, selected)
        dim = [name for name in result.columns if name != "Value"]
        for dimension in [column for column in dim if column != "State"]:
            options = sorted(result[dimension].dropna().unique())
            key = f"explorer_categories_{grain}_{dimension}"
            previous = st.session_state.get(key, [])
            cleaned = [value for value in previous if value in options]
            if previous != cleaned:
                st.session_state[key] = cleaned
            categories = st.multiselect(f"Filter {dimension.replace('_', ' ')}", options, key=key)
            if categories:
                result = result.loc[result[dimension].isin(categories)]
        a, b = st.columns(2)
        limit_type = a.selectbox("Rank selection", ["All rows", "Top N", "Bottom N"], key="explorer_limit_type")
        if limit_type != "All rows":
            limit = b.number_input("Number of ranked rows", min_value=1, max_value=100, value=10, key="explorer_limit")
            result = result.sort_values(["Value", *dim], ascending=[limit_type == "Bottom N", *([True] * len(dim))]).head(limit)
    if result.empty:
        st.info("No published aggregates are available for this combination in the active database.")
        return
    order_columns = dim if order == "Label" else ["Value", *dim]
    directions = [True] * len(dim) if order == "Label" else [order == "Lowest first", *([True] * len(dim))]
    result = result.sort_values(order_columns, ascending=directions)
    unit = METRICS[metric].unit if metric in METRICS else "%"
    definition = METRICS[metric].definition if metric in METRICS else "Category population divided by all synthetic people in the matching geography."
    result = result.assign(Unit=unit, **{"Definition / denominator": definition})
    view = st.radio("Visualization", ["Bar", "Table"], horizontal=True, key="explorer_chart")
    shown = result.assign(Segment=result[dim].astype(str).agg(" / ".join, axis=1))
    benchmark = None
    if grain == "State / UT" and unit not in ("people", "households"):
        if st.checkbox("Show all-India benchmark", key="explorer_benchmark"):
            _, benchmark = state_metric(scope, metric)
    if view != "Table":
        bars(shown.head(15), "Segment", "Value", f"{metric} by {grain}", unit, height=420, benchmark=benchmark)
        st.caption("The chart displays up to 15 sorted rows. The table and export include the entire filtered ranking.")
    insight_panel(shown, "Segment", "Value", unit, benchmark)
    for note in extent(shown, "Segment", "Value", unit):
        st.caption(note)
    st.dataframe(result, hide_index=True, width="stretch")
    geography = ", ".join(selected) if selected else ("All State/UTs" if grain == "State / UT" else "All India")
    st.download_button("Download aggregate CSV", export_csv(result, f"{metric} by {grain}", geography, scope.dataset.version),
                       file_name="india-synthetic-aggregates.csv", mime="text/csv", on_click="ignore")
    st.download_button("Download printable results",
                       printable_report(f"{metric} by {grain}", geography, scope.dataset.version, [("Filtered ranking", result)]),
                       file_name="india-synthetic-aggregates.html", mime="text/html", on_click="ignore")


def methodology(scope):
    count, households, _, _ = summary(replace(scope, focus=""))
    kpis([("Synthetic records", display(count, "people"), "National row count."),
          ("Distinct households", display(households, "households"), "National household count."),
          ("States / UTs", str(len(scope.states)), "Geographies in the active artifact.")])
    provenance, dictionary, quality = st.tabs(["Provenance", "Metric dictionary", "Quality and coverage"])
    with provenance:
        st.markdown("""
**Generation.** Version 3.4 used a fixed seed and 15,000 Parquet chunks for the full build. The dashboard reads published aggregate tables.

**Calibration.** The source manifest identifies Census 2011 state, age, gender, settlement and social inputs where available, plus configured PLFS 2025 employment references. Telangana age and religion use an undivided Andhra Pradesh profile as a proxy.

**Generated assumptions.** Household structure, wealth labels, income amounts, occupation mix, education, digital access, insurance, disability and marital status use generated assumptions.

**Geography.** Simplified State/UT boundaries from DataMeet via geoBoundaries and GeoDataViewer, CC BY 2.5 India. The layer is for analytical orientation. City labels are placeholders.
        """)
        st.markdown("[Boundary asset source](https://geodataviewer.com/datasets/boundaries/india-states-boundaries/)")
    with dictionary:
        metric_catalogue()
    with quality:
        st.write(f"Active artifact: {scope.dataset.version} ({scope.dataset.mode}).")
        st.write(f"Startup reconciliation: {int(scope.states.population.sum()):,} state records and {int(count):,} national records.")
        st.write("The v3.4 release verification compared 42 projected tables against the original analytics database. Reproduce it with release_snapshot.py verify and consult docs/release.md.")
        st.write("Unsupported: individual records, district statistics, time series, population estimates, and joins between separate marginal distributions.")
        st.write("Stored Explorer grains: " + ", ".join(BREAKDOWNS) + ".")
