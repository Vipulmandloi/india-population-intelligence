"""Read-only queries, metric definitions, and deterministic comparisons."""

from dataclasses import dataclass
import pandas as pd
import streamlit as st
from dashboard_data import connect, validate_artifact

OPTIONAL = {
    "age_value_summary": ("Age", "population"),
    "state_age_value_summary": ("State", "Age", "population"),
}

@st.cache_data(ttl=1800, show_spinner=False)
def dataset_for(mode, path, revision):
    return validate_artifact(mode, path, revision)

def read_table(con, dataset, name, state=None):
    columns = dataset.projections.get(name) or OPTIONAL[name]
    projection = ", ".join(f'"{column}"' for column in columns)
    sql = f'SELECT {projection} FROM main."{name}"'
    if name in OPTIONAL and not con.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_schema = 'main' AND table_name = ?", [name]
    ).fetchone()[0]:
        return pd.DataFrame(columns=columns)
    frame = con.execute(sql + (' WHERE "State" = ?' if state else ""), [state] if state else []).fetchdf()
    category = name.removeprefix("state_").removesuffix("_summary")
    if "category" in frame and category not in frame:
        frame = frame.rename(columns={"category": "Religion" if category == "religion" else category})
    return frame


@st.cache_data(ttl=1800, max_entries=360, show_spinner=False)
def table(dataset, name, state=None):
    with connect(dataset.path) as con:
        return read_table(con, dataset, name, state)


@st.cache_data(ttl=1800, max_entries=48, show_spinner=False)
def tables(dataset, names, state=None):
    """Read a related set of aggregates with one short-lived connection."""
    with connect(dataset.path) as con:
        return {name: read_table(con, dataset, name, state) for name in names}


@dataclass
class Scope:
    dataset: object
    focus: str
    comparison: list
    states: pd.DataFrame
    advanced: object = None

    @property
    def label(self):
        return self.focus or "All India"

    def frame(self, base):
        return table(self.dataset, f"{'state_' if self.focus else ''}{base}_summary", self.focus)


@dataclass(frozen=True)
class Metric:
    column: str
    unit: str
    definition: str
    table_name: str = ""
    category: str = ""
    value: str = ""

METRICS = {
    "Population": Metric("population", "people", "Number of generated people in the selected geography."),
    "Households": Metric("households", "households", "Distinct generated household IDs."),
    "Mean household size": Metric("household_size", "people / household", "Generated people divided by distinct generated households."),
    "Mean age": Metric("average_age", "years", "Arithmetic mean age of generated people."),
    "Mean annual income": Metric("average_income", "INR / person", "Generated annual income per person, including assigned zeros. The national benchmark is weighted by state population using published rounded state means.", "income_summary"),
    "Urban share": Metric("rate", "%", "Urban-labelled people divided by all people.", "state_settlement_summary", "settlement", "Urban"),
    "Employed share": Metric("rate", "%", "People assigned employed status divided by all people, including children.", "state_main_activity_summary", "main_activity", "Employed"),
    "Bank account coverage": Metric("rate", "%", "People assigned a bank account divided by all people.", "state_bank_summary", "bank", "Yes"),
    "Health insurance coverage": Metric("rate", "%", "People assigned health insurance divided by all people.", "state_insurance_summary", "insurance", "Yes"),
    "Disability prevalence": Metric("rate", "%", "People assigned disability status divided by all people.", "state_disability_summary", "disability", "Yes"),
    "Internet access": Metric("rate", "%", "People assigned internet access divided by all people.", "state_digital_summary", "internet_access", "Yes"),
    "Smartphone ownership": Metric("rate", "%", "People assigned smartphone ownership divided by all people.", "state_digital_summary", "smartphone_ownership", "Yes"),
}

def state_metric(scope, label, aggregates=None):
    metric = METRICS[label]
    states = scope.states.copy()

    def get(name):
        return aggregates[name] if aggregates is not None else table(scope.dataset, name)

    if metric.column == "household_size":
        states[metric.column] = states.population / states.households.where(states.households > 0)
        national = states.population.sum() / states.households.sum() if states.households.sum() else None
    elif metric.category:
        detail = get(metric.table_name)
        counts = detail.loc[detail[metric.category] == metric.value].groupby("State").population.sum()
        eligible = detail.groupby("State").population.sum().reindex(states.State)
        numerators = counts.reindex(states.State).fillna(0)
        states[metric.column] = (numerators / eligible.where(eligible > 0) * 100).to_numpy()
        national = numerators.sum() / eligible.sum() * 100 if eligible.sum() else None
    elif metric.table_name:
        states = states.merge(get(metric.table_name), on="State", how="left", validate="one_to_one")
        known = states.dropna(subset=[metric.column])
        national = (known[metric.column] * known.population).sum() / known.population.sum() if known.population.sum() else None
    elif metric.column == "average_age":
        national = float(get("national_summary").iloc[0].average_age)
    else:
        national = states[metric.column].sum()
    return states[["State", metric.column]].rename(columns={metric.column: "Value"}), national

def display(value, unit):
    if pd.isna(value):
        return "Unavailable"
    if unit in {"people", "households"}:
        return f"{int(value):,}"
    if unit == "%":
        return f"{value:,.1f}%"
    return f"{value:,.2f} {unit}"

def describe(frame, dimension, measure, unit, benchmark=None):
    ordered = frame.dropna(subset=[measure]).sort_values([measure, dimension], ascending=[False, True])
    if ordered.empty:
        return []
    high = ordered.iloc[0]
    low = ordered.iloc[-1]
    def extreme(value, adjective):
        tied = ordered.loc[ordered[measure] == value, dimension].astype(str).tolist()
        labels = ", ".join(tied[:3])
        if len(tied) > 3:
            labels += f" and {len(tied) - 3} others"
        return f"{labels} {'tie for the ' + adjective if len(tied) > 1 else 'has the ' + adjective} value at {display(value, unit)}."

    if len(ordered) > 1 and high[measure] == low[measure]:
        notes = [f"All {len(ordered)} categories tie at {display(high[measure], unit)}."]
    else:
        notes = [extreme(high[measure], "highest")]
    if len(ordered) > 1 and high[measure] != low[measure]:
        gap = high[measure] - low[measure]
        gap_text = f"{gap:,.1f} percentage points" if unit == "%" else display(gap, unit)
        notes.append(f"{extreme(low[measure], 'lowest')} The spread is {gap_text}.")
    if pd.notna(benchmark):
        notes.append(f"The all-India benchmark is {display(benchmark, unit)}.")
    return notes

# A selected breakdown always maps to a stored aggregate grain.
BREAKDOWNS = {
    "Age cohort": ("age", "age_group"),
    "Age cohort and gender": ("age_gender", "age_group", "Gender"),
    "Exact age": ("age_value", "Age"),
    "Settlement": ("settlement", "settlement"),
    "Education attainment": ("education", "education_level"),
    "Literacy": ("literacy", "literacy"),
    "Occupation": ("occupation", "Occupation"),
    "Employment type": ("employment_type", "employment_type"),
    "Work status": ("main_activity", "main_activity"),
    "Marital status": ("marital", "marital"),
    "Religion": ("religion", "Religion"),
    "Social group": ("social_group", "social_group"),
    "Mother tongue coverage": ("mother_tongue", "mother_tongue"),
    "Smartphone and internet": ("digital", "smartphone_ownership", "internet_access"),
    "Bank account": ("bank", "bank"),
    "Health insurance": ("insurance", "insurance"),
    "Disability": ("disability", "disability"),
    "Generated wealth label": ("wealth", "wealth"),
}

def explore(scope, dimension, metric, states):
    if dimension == "State / UT":
        frame, _ = state_metric(scope, metric)
        return frame.loc[frame.State.isin(states)] if states else frame
    if metric not in ("Population", "Share of geographic population"):
        raise ValueError("This metric has no aggregate at the selected breakdown.")
    table_name, *columns = BREAKDOWNS[dimension]
    if states:
        if table_name == "age":
            frame = table(scope.dataset, "state_age_gender_summary").groupby(
                ["State", "age_group"], as_index=False
            ).population.sum()
        else:
            frame = table(scope.dataset, f"state_{table_name}_summary")
        frame = frame.loc[frame.State.isin(states)].copy()
        groups = ["State", *columns]
    else:
        frame = table(scope.dataset, f"{table_name}_summary")
        groups = columns
    result = frame.loc[:, [*groups, "population"]].copy()
    result["Value"] = result.pop("population")
    if metric != "Population":
        totals = result.groupby("State").Value.transform("sum") if states else result.Value.sum()
        result["Value"] = result["Value"] / totals * 100
    return result


def metric_series(scope, labels):
    names = {METRICS[label].table_name for label in labels} - {""}
    if "Mean age" in labels:
        names.add("national_summary")
    aggregates = tables(scope.dataset, tuple(sorted(names))) if names else {}
    return {label: state_metric(scope, label, aggregates) for label in labels}


def extent(frame, dimension, value, unit):
    """Describe the two extremes once, preserving the displayed metric unit."""
    ordered = frame.dropna(subset=[value]).sort_values([value, dimension], ascending=[False, True])
    if len(ordered) < 2:
        return []
    high, low = ordered.iloc[0], ordered.iloc[-1]
    gap = high[value] - low[value]
    if not gap:
        return [f"All {len(ordered)} displayed categories have the same value."]
    magnitude = f"{gap:,.1f} pp" if unit == "%" else display(gap, unit)
    if unit == "people" and ordered[value].sum():
        concentration = high[value] / ordered[value].sum()
        return [f"{high[dimension]} accounts for {concentration:.1%} of the displayed people."]
    return [f"{high[dimension]} leads {low[dimension]} by {magnitude} in this selection."]
