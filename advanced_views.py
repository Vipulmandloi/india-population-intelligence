"""Shared advanced analysis panel, chart views and exports."""

import json
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

from advanced_analytics import (
    DIMENSIONS, FAMILIES, INCOME_ORDER, MEASURES, TABLE_LABELS,
    ADVANCED_STATE_METRICS, advanced_state_series, available_dimensions, available_measures, distribution, query,
)
from advanced_data import GRAINS
from analytics import describe, display
from reports import export_csv
from ui import AGE_ORDER, PALETTE, bars, chart

LIMIT = 24
ORDERS = {"age_cohort": AGE_ORDER + ["Unknown"], "income_band": INCOME_ORDER}
DEFAULTS = {
    "education_gender": ("Gender", "education"),
    "education_age": ("age_cohort", "education"),
    "education_settlement": ("settlement", "education"),
    "employment_age_gender": ("age_cohort", "Gender"),
    "occupation_gender": ("Gender", "Occupation"),
    "income_bands_state": ("State", "income_band"),
    "income_bands_gender": ("Gender", "income_band"),
    "income_bands_settlement": ("settlement", "income_band"),
    "household_sizes": ("household_size", None),
    "digital_age_gender": ("age_cohort", "internet"),
    "financial_education_gender": ("education", "bank"),
    "financial_employment": ("employment_status", "insurance"),
}


def format_dimension(name):
    return DIMENSIONS[name] if name else "None"


def ordered_values(dimension, values):
    order = ORDERS.get(dimension)
    return sorted(values, key=lambda value: (order.index(value) if value in order else len(order), str(value))) if order else sorted(values)


def add_benchmark(release, table, dims, measure, filters, mode, frame):
    if "State" not in dims:
        return frame
    national_dims = tuple(dim for dim in dims if dim != "State")
    base = query(release, table, national_dims, measure, tuple(pair for pair in filters if pair[0] != "State"))
    if mode != "Value":
        base = distribution(base, national_dims, "Total %")
    if national_dims:
        output = frame.merge(base[[*national_dims, "value"]].rename(columns={"value": "all_india"}),
                             on=list(national_dims), how="left", validate="many_to_one")
    else:
        output = frame.assign(all_india=base.value.iloc[0])
    output["gap"] = output.value - output.all_india
    return output


def insights(frame, dims, unit, is_rate):
    ranked = frame.dropna(subset=["value"]).copy()
    if ranked.empty:
        return
    ranked["cell"] = ranked[list(dims)].astype(str).agg(" / ".join, axis=1)
    for note in describe(ranked, "cell", "value", unit):
        st.write(note)
    if "gap" in ranked and ranked.gap.notna().any():
        ranked = ranked.dropna(subset=["gap"])
        widest = ranked.loc[ranked.gap.abs() == ranked.gap.abs().max()].sort_values("cell")
        row = widest.iloc[0]
        gap = f"{row.gap:+.2f} pp" if is_rate else f"{row.gap:+,.2f} {unit}"
        advice = "One of the tied largest benchmark gaps" if len(widest) > 1 else "Largest absolute benchmark gap"
        st.caption(f"{advice}: {row.cell} at {gap} versus all India.")


def draw(data, dims, unit, style, highlight, highlight_key, plot_key):
    if len(dims) == 2:
        first, second = dims
        categories = data[second].drop_duplicates().head(12)
        max_groups = 12 if style == "Heatmap" else max(3, LIMIT // max(len(categories), 1))
        groups = data[first].drop_duplicates().head(max_groups)
        visible = data.loc[data[first].isin(groups) & data[second].isin(categories)].copy()
    else:
        visible = data.head(LIMIT).copy()
    visible = visible.assign(**{dim: visible[dim].astype(str) for dim in dims})
    labels = {dim: DIMENSIONS[dim] for dim in dims}
    labels["value"] = unit
    if len(dims) == 1:
        dim = dims[0]
        if style == "Distribution":
            model = px.line(visible, x=dim, y="value", markers=True, labels=labels,
                            category_orders={dim: [str(x) for x in ordered_values(dim, visible[dim].unique())]})
            chart(model, 330)
        else:
            bars(visible, dim, "value", unit=unit, height=370)
        return
    first, second = dims
    if style == "Heatmap":
        matrix = visible.pivot(index=first, columns=second, values="value")
        matrix = matrix.reindex(index=ordered_values(first, matrix.index), columns=ordered_values(second, matrix.columns))
        fig = px.imshow(matrix, aspect="auto", color_continuous_scale="Teal",
                        range_color=(0, 100) if unit == "%" else None,
                        text_auto=".1f" if unit == "%" else ".3s",
                        labels={"x": labels[second], "y": labels[first], "color": unit})
        chart(fig, 365)
        return
    fig = px.bar(visible, x=first, y="value", color=second, labels=labels, color_discrete_sequence=[*PALETTE, "#D3C5E9", "#74B8A3"],
                 category_orders={dim: [str(v) for v in ordered_values(dim, visible[dim].unique())] for dim in dims},
                 barmode="group" if style == "Grouped bars" else "stack",
                 custom_data=[first])
    if highlight:
        for trace in fig.data:
            trace.marker.opacity = [1 if str(value) == highlight else .30 for value in trace.x]

    def select_category():
        points = st.session_state[plot_key].selection.points
        selected = points[0].get("customdata") if points else None
        if selected:
            st.session_state[highlight_key] = str(selected[0])

    chart(fig, 365, key=plot_key, on_select=select_category, selection_mode="points")


def advanced_panel(scope, key, family=None):
    release = scope.advanced
    if release is None:
        st.info("Advanced analysis requires the validated P4B artifact. Existing dashboard views remain available.")
        return
    prefix = f"advanced_{key}_"
    def reset():
        for item in list(st.session_state):
            if item.startswith(prefix):
                # Rotate the widget namespace so browser-held defaults reset too.
                st.session_state.pop(item, None)
        st.session_state[f"p4_reset_{key}"] = st.session_state.get(f"p4_reset_{key}", 0) + 1
    if family is None:
        with st.expander("Search available advanced metrics"):
            metric_catalogue(prefix+"catalogue")
    st.button("Reset advanced analysis", key=f"p4_reset_button_{key}", on_click=reset)
    prefix += f"{st.session_state.get(f'p4_reset_{key}', 0)}_"
    choices = FAMILIES[family] if family else list(GRAINS)
    a, b = st.columns(2)
    table = a.selectbox("Aggregate", choices, format_func=TABLE_LABELS.get, key=prefix+"table")
    pre = prefix + table + "_"
    measures = available_measures(table)
    default = "Households" if table == "household_sizes" else ("Valid recorded incomes" if table.startswith("income_bands") else measures[0])
    measure = b.selectbox("Metric", measures, index=measures.index(default), key=pre+"metric")
    spec = MEASURES[measure]
    supported = available_dimensions(table, measure)
    if measure.startswith("Employed share"):
        st.caption("Employment status is unavailable as an axis or filter for this rate because it is the outcome.")
    first_default, second_default = DEFAULTS.get(table, (supported[0], supported[1]))
    c, d = st.columns(2)
    axes = pre + measure + "_"
    first = c.selectbox("Primary dimension", supported, index=supported.index(first_default) if first_default in supported else 0,
                        format_func=format_dimension, key=axes+"first")
    second_options = [None, *(dim for dim in supported if dim != first)]
    second = d.selectbox("Secondary dimension", second_options,
                         index=second_options.index(second_default) if second_default in second_options else 0,
                         format_func=format_dimension, key=axes+first+"_second")
    dims = (first, second) if second else (first,)

    default_scope = "Geographic focus" if scope.focus else "All India"
    chosen = st.radio("Advanced geographic scope", ["All India", "Geographic focus", "Selected State/UTs"],
                      index=["All India", "Geographic focus", "Selected State/UTs"].index(default_scope),
                      horizontal=True, key=pre+"scope")
    if chosen == "Selected State/UTs":
        states = sorted(st.multiselect("Advanced State/UTs", sorted(scope.states.State),
                                      default=scope.comparison, key=pre+"states"))
        if not states:
            st.info("Select at least one State/UT.")
            return
    else:
        states = [scope.focus] if chosen == "Geographic focus" and scope.focus else []
    filters = [("State", tuple(states))] if states else []
    with st.expander("Category filters"):
        available = query(release, table, tuple(supported), measure, tuple(filters))
        for dim in supported:
            if dim == "State":
                continue
            options = ordered_values(dim, available[dim].dropna().unique())
            filter_key = pre+"filter_"+dim
            current = st.session_state.get(filter_key, [])
            valid = [item for item in current if item in options]
            if current != valid:
                st.session_state[filter_key] = valid
            values = st.multiselect(f"Filter {DIMENSIONS[dim]}", options, key=filter_key)
            if values:
                filters.append((dim, tuple(ordered_values(dim, values))))
    st.caption(spec.definition)
    if measure.startswith("Employed share") and "age_cohort" in dims:
        st.caption("Each cohort is intersected with the selected eligible age range. The 0-17 bucket covers eligible ages 15-17 only. Blank cells have no eligible denominator.")
    if table.startswith("income_bands"):
        st.caption("Annual bands are in generated INR. Positive bands include their lower edge and exclude the next band. Zero is separate. Income bands do not supply exact percentiles.")
    st.caption("Scope: " + (", ".join(states) if states else "All India") +
               (" | " + "; ".join(f"{DIMENSIONS[dim]}: {', '.join(map(str, vals))}" for dim, vals in filters if dim != "State")
                if any(dim != "State" for dim, _ in filters) else " | All categories"))
    raw = query(release, table, dims, measure, tuple(filters))
    if raw.empty:
        st.info("No aggregate cells match these filters.")
        return
    a, b, c = st.columns(3)
    modes = ["Value"] if spec.denominator else ["Value", "Total %", *(["Row %", "Column %"] if second else [])]
    mode = a.selectbox("Display", modes, key=pre+measure+str(dims)+"_display")
    chart_options = ["Grouped bars", "Heatmap"] if second else ["Bar chart", "Distribution"]
    if second and not spec.denominator and mode == "Value":
        chart_options.extend(["Stacked bars", "Normalized stacked bars"])
    style = b.selectbox("Visualization", chart_options, key=pre+str(dims)+mode+"_chart")
    rank = c.selectbox("Order", ["Natural order", "Highest first", "Lowest first", "Top N", "Bottom N"], key=pre+"rank")
    if style == "Normalized stacked bars":
        mode = "Row %"
    frame = distribution(raw, dims, mode)
    unit = spec.unit if mode == "Value" else "%"
    benchmark_available = "State" in dims and (
        bool(spec.denominator) or (mode == "Row %" and first == "State") or (mode == "Column %" and second == "State"))
    if benchmark_available and st.checkbox("Compare with matching all-India benchmark", key=pre+str(dims)+mode+"_benchmark"):
        frame = add_benchmark(release, table, dims, measure, tuple(filters), mode, frame)
    if rank != "Natural order":
        frame = frame.sort_values(["value", *dims], ascending=[rank in {"Lowest first", "Bottom N"}, *([True] * len(dims))])
        if rank in {"Top N", "Bottom N"}:
            n = st.number_input("Ranked cells", min_value=1, max_value=150, value=10, key=pre+"n")
            frame = frame.head(n)
    else:
        def natural_order(series):
            if series.name in ORDERS:
                return series.map(dict(zip(ORDERS[series.name], range(len(ORDERS[series.name])))))
            return series
        frame = frame.sort_values(list(dims), key=natural_order, kind="stable")
    denominator_scope = spec.denominator or "Count or sum in selected cell"
    if mode != "Value":
        verb = {"Row %": "each primary-dimension group", "Column %": "each secondary-dimension group",
                "Total %": "the selected total"}[mode]
        denominator_scope = verb + " after filters and before ranking"
        st.caption(f"Percentages divide by {verb} after filters and before ranking. Truncated selections may sum to less than 100%.")
    highlight_key = pre+str(dims)+"_highlight"
    highlight = st.selectbox("Highlight primary category", ["", *map(str, ordered_values(first, frame[first].unique()))],
                             format_func=lambda value: value or "None", key=highlight_key) if second and style != "Heatmap" else ""
    title = measure if mode == "Value" else f"{measure} ({mode})"
    st.subheader(f"{title} by " + " and ".join(DIMENSIONS[dim] for dim in dims))
    draw(frame, dims, unit, style, highlight, highlight_key, pre+str(dims)+style+"_plot")
    if second and style != "Heatmap":
        st.caption("Click a bar or use the category picker to highlight it in this chart.")
    if second:
        st.caption("The chart limits category groups for readability. The table and download retain the entire selected ranking window.")
    else:
        st.caption(f"Chart shows up to {LIMIT} cells. The table and download retain the entire selected ranking window.")
    insights(frame, dims, unit, unit == "%")
    with st.expander("Aggregate rows and cross-tabulation"):
        st.dataframe(frame, hide_index=True, width="stretch")
        if second:
            pivot = frame.pivot(index=first, columns=second, values="value").reindex(
                index=ordered_values(first, frame[first].unique()), columns=ordered_values(second, frame[second].unique()))
            st.dataframe(pivot, width="stretch")
    exported = frame.assign(Metric=measure, Unit=unit, Display=mode, Aggregate=table, Definition=spec.definition)
    geography = ", ".join(states) if states else "All India"
    filter_summary = " | ".join(f"{DIMENSIONS[dim]}: {', '.join(map(str, items))}" for dim, items in filters if dim != "State")
    exported["Category filters"] = filter_summary or "All categories"
    exported["Denominator scope"] = denominator_scope
    st.download_button("Download advanced aggregate CSV", export_csv(exported, "Advanced aggregate", geography, "v3.4 P4B"),
                       file_name="india-advanced-aggregates.csv", mime="text/csv", on_click="ignore", key=pre+"export")
    if family:
        domain_benchmarks(scope, family, prefix)


FAMILY_METRICS = {
    "Education": ["Graduate share"],
    "Employment": ["Employed share ages 15-64", "Employed share ages 15+"],
    "Income": ["Recorded income per person", "Recorded income among employed", "Recorded zero income share"],
    "Households": ["One-person household share"],
    "Inclusion": ["Smartphone and internet share", "Bank account and insurance share"],
}


def domain_benchmarks(scope, family, prefix):
    with st.expander(f"{family} rankings and national benchmarks"):
        st.caption("Benchmarks below use the full metric universe. Category filters above apply to the cross-tab only.")
        label = st.selectbox("Rank State/UTs by", FAMILY_METRICS[family], key=prefix+"rank_metric")
        rows, benchmark = advanced_state_series(scope.advanced, [label])[label]
        unit = ADVANCED_STATE_METRICS[label].unit
        rows = rows.sort_values(["Value", "State"], ascending=[False, True]).copy()
        rows["Rank"] = rows.Value.rank(ascending=False, method="min").astype("Int64")
        if benchmark is not None:
            rows["All India"] = benchmark
            rows["Gap (pp)" if unit == "%" else "Gap from All India"] = rows.Value - benchmark
        st.caption(ADVANCED_STATE_METRICS[label].definition)
        if scope.focus:
            focus = rows.loc[rows.State == scope.focus].iloc[0]
            st.write(f"{scope.focus} ranks {focus.Rank} at {display(focus.Value, unit)}. All India: {display(benchmark, unit)}.")
        st.dataframe(rows, hide_index=True, width="stretch")
        if family == "Education":
            attainment = st.selectbox("Attainment category for gender gap",
                                      ordered_values("education", query(scope.advanced, "education_gender", ("education",), "People").education),
                                      key=prefix+"edu_gap")
            total = query(scope.advanced, "education_gender", ("State", "Gender"), "People")
            category = query(scope.advanced, "education_gender", ("State", "Gender"), "People", (("education", (attainment,)),))
            merged = total.merge(category[["State", "Gender", "numerator"]], on=["State", "Gender"], how="left", suffixes=("_all", "_cat"))
            merged["share"] = merged.numerator_cat.fillna(0) * 100 / merged.numerator_all
            gaps = merged.pivot(index="State", columns="Gender", values="share")
            if {"Female", "Male"} <= set(gaps):
                gaps["Female minus male (pp)"] = gaps.Female - gaps.Male
                st.caption("Each share divides the selected attainment count by the total for the same generated gender and geography.")
                st.dataframe(gaps.sort_values("Female minus male (pp)", ascending=False), width="stretch")
        if family == "Households":
            where = (("State", (scope.focus,)),) if scope.focus else ()
            household = query(scope.advanced, "household_sizes", (), "Households", where)
            mean = query(scope.advanced, "household_sizes", (), "Mean household size", where)
            st.write(f"{scope.label}: {int(household.value.iloc[0]):,} distinct households and "
                     f"{mean.value.iloc[0]:.2f} members per household.")
        st.download_button("Download benchmark ranking CSV",
                           export_csv(rows.assign(Metric=label, Unit=unit, Definition=ADVANCED_STATE_METRICS[label].definition),
                                      "Advanced benchmark ranking", "All State/UTs", "v3.4 P4B"),
                           file_name="india-advanced-ranking.csv", mime="text/csv", on_click="ignore", key=prefix+"ranking_export")


def validation_summary(release):
    report_path = Path(__file__).resolve().parent / "docs" / "p4d-validation.json"
    with st.expander("Independent statistical validation", expanded=True):
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            st.info("The published validation summary is unavailable.")
            return
        totals = report["totals"]
        st.write(f"{totals['passed']:,} checks passed and {totals['failed']:,} failed for {report['release']}.")
        if release is None or release.digest != report["hashes"]["advanced"]:
            st.info("These results apply to the checksum-pinned release. That advanced release is inactive in this session.")
        st.dataframe(pd.DataFrame([
            {"Check group": group.capitalize(), "Passed": result["passed"], "Failed": result["failed"]}
            for group, result in report["groups"].items()
        ]), hide_index=True, width="stretch")
        verified = report["verified"]
        st.write(f"Reconciled {verified['records']:,} synthetic people and {verified['households']:,} "
                 f"distinct synthetic households across {verified['states']} States and UTs.")
        st.caption("The audit used read-only aggregate reconciliation and independent SQL references. "
                   "Full raw-record verification and real-world calibration were outside its scope.")
        st.caption("Run validate_p4d.py with the three pinned databases to reproduce the report. "
                   "The P4D validation report documents browser and export coverage.")
        st.caption("Unverified in P4D: saved browser downloads, screen-reader and cross-browser behavior, "
                   "and Cloud execution.")


def advanced_methodology(release, status):
    st.subheader("Advanced data quality")
    validation_summary(release)
    if release is None:
        st.info(status)
        return
    st.write(f"Schema v{release.version} | {release.records:,} synthetic records | {release.files:,} Parquet files | "
             f"{release.states} States/UTs | {release.households:,} distinct synthetic households.")
    st.code(release.digest, language=None)
    st.caption("SHA-256 verified against the approved immutable P4B release.")
    st.write("P4B processed five files per transactional batch. It validated the full manifest ledger, exact State/UT population "
             "and household totals, 21 grouped baseline margins plus five employment margins, recorded-income sums and band consistency.")
    st.write("Stored intersections support the dimensions below. Income bands do not establish exact percentiles. "
             "Education attainment and literacy are distinct. District geography and mother tongue remain unsupported. "
             "All figures describe generated records.")
    catalogue = []
    for name, (dimensions, _) in GRAINS.items():
        catalogue.append({"Aggregate": name, "Dimensions": ", ".join(DIMENSIONS[d] for d in dimensions),
                          "Available metrics": ", ".join(available_measures(name))})
    st.dataframe(pd.DataFrame(catalogue), hide_index=True, width="stretch")
    metric_catalogue("methodology")


def metric_catalogue(key):
    term = st.text_input("Search advanced metric definitions", key=key,
                         placeholder="Examples: working age, valid income, household").strip().casefold()
    rows = []
    for label, spec in MEASURES.items():
        tables = ", ".join(TABLE_LABELS[table] for table in GRAINS if label in available_measures(table))
        if term in f"{label} {spec.definition} {tables}".casefold():
            rows.append({"Metric": label, "Unit": spec.unit, "Definition": spec.definition,
                         "Denominator field": spec.denominator or "Count or sum", "Aggregates": tables})
    if rows:
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
    else:
        st.info("No metric matches that search.")
