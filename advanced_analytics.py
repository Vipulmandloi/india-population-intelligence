"""Validated optional P4B source and bounded multidimensional aggregate queries."""

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb
import pandas as pd
import streamlit as st

from advanced_data import GRAINS, inspect_artifact, reconcile_baseline
from analytics import Metric
from dashboard_data import connect
from release_snapshot import file_hash

RELEASE_HASH = "05053a452415186c4d29a1b4d03c21734cbc492cc4f989890a0683829fb443ac"
BUNDLED_ADVANCED = Path(__file__).resolve().parent / "data" / "advanced-v1.duckdb"
DIMENSIONS = {
    "State": "State / UT", "Gender": "Gender", "age_cohort": "Age cohort",
    "education": "Education attainment", "settlement": "Settlement",
    "employment_status": "Generated employment status", "Occupation": "Occupation",
    "income_band": "Annual income band", "household_size": "People per household",
    "smartphone": "Smartphone access", "internet": "Internet access", "bank": "Bank account",
    "insurance": "Health insurance",
}
TABLE_LABELS = {name: name.replace("_", " ").capitalize() for name in GRAINS}
FAMILIES = {
    "Education": ["education_gender", "education_age", "education_settlement"],
    "Employment": ["employment_age_gender", "employment_settlement", "employment_education", "occupation_gender"],
    "Income": [name for name in GRAINS if name.startswith("income_")],
    "Households": ["household_sizes"],
    "Inclusion": ["digital_age_gender", "financial_education_gender", "financial_employment"],
}
INCOME_ORDER = ["Missing or invalid", "Zero", "1-49,999", "50,000-99,999", "100,000-249,999",
                "250,000-499,999", "500,000-999,999", "1,000,000+"]


@dataclass(frozen=True)
class Release:
    path: Path
    revision: tuple
    version: int
    records: int
    files: int
    states: int
    digest: str
    households: int


def file_revision(path):
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns


@st.cache_data(ttl=1800, max_entries=6, show_spinner=False)
def validate_release(path, revision, baseline, baseline_revision):
    if file_hash(path) != RELEASE_HASH:
        raise ValueError("The advanced artifact fingerprint does not match the approved P4B release.")
    config = inspect_artifact(path, 1_500_000_000)
    if config["scope"] != "production" or config["files"] != 15_000:
        raise ValueError("The advanced artifact does not represent the approved production scope.")
    reconcile_baseline(path, baseline)
    with connect(path) as con:
        household_count = con.execute("SELECT SUM(households) FROM household_sizes").fetchone()[0]
    if file_revision(path) != revision or file_revision(baseline) != baseline_revision:
        raise ValueError("An artifact changed during validation.")
    return Release(path, revision, config["schema_version"], config["records"], config["files"],
                   config["states"], RELEASE_HASH, int(household_count))


def configured_release(dataset):
    setting = os.getenv("INDIA_ADVANCED_DB_PATH", "").strip()
    if not setting and not BUNDLED_ADVANCED.is_file():
        return None, "Advanced analytics unavailable. The optional aggregate is not installed."
    try:
        path = Path(setting).expanduser().resolve(strict=True) if setting else BUNDLED_ADVANCED
        if not path.is_file():
            return None, "Advanced analytics unavailable. Configure a DuckDB file."
        return validate_release(path, file_revision(path), dataset.path, dataset.revision), ""
    except FileNotFoundError:
        return None, "Advanced analytics unavailable. The configured file was not found."
    except (ValueError, OSError, RuntimeError):
        return None, "Advanced analytics unavailable. The artifact failed integrity or baseline compatibility checks."
    except duckdb.Error:
        return None, "Advanced analytics unavailable. The database could not be read safely."


@dataclass(frozen=True)
class Measure:
    numerator: str
    denominator: str
    unit: str
    definition: str
    scale: int = 1


MEASURES = {
    "People": Measure("people", "", "people", "Count of generated people in the selected cells."),
    "Households": Measure("households", "", "households", "Count of validated distinct household IDs."),
    "Household members": Measure("members", "", "people", "Observed members of the selected households."),
    "Mean household size": Measure("members", "households", "people / household", "Observed members divided by distinct households."),
    "Employed share ages 15-64": Measure("employed_working_age", "working_age_known_status", "%", "Generated employed people aged 15-64 divided by people in that age range with known generated status.", 100),
    "Employed share ages 15+": Measure("employed_15_plus", "eligible_15_plus_known_status", "%", "Generated employed people aged 15+ divided by people aged 15+ with known generated status.", 100),
    "Valid recorded incomes": Measure("income_valid", "", "people", "Number of people with nonnegative annual income. Includes recorded zero and excludes missing or negative values."),
    "Valid employed incomes": Measure("employed_income_valid", "", "people", "Number of people with generated employed status and nonnegative recorded income."),
    "Recorded zero incomes": Measure("income_zero", "", "people", "Number of people with recorded annual income equal to zero."),
    "Recorded income sum": Measure("income_sum", "", "INR / year", "Sum of nonnegative annual income. Recorded zeros contribute zero."),
    "Mean recorded income": Measure("income_sum", "income_valid", "INR / person / year", "Nonnegative recorded income sum divided by valid-income count, including recorded zeros."),
    "Mean employed income": Measure("employed_income_sum", "employed_income_valid", "INR / employed person / year", "Recorded income sum among generated employed people divided by their valid-income count."),
}


def available_measures(table):
    _, fields = GRAINS[table]
    return [name for name, measure in MEASURES.items()
            if measure.numerator in fields and (not measure.denominator or measure.denominator in fields)]


def available_dimensions(table, measure_name):
    dimensions, _ = GRAINS[table]
    # Conditioning on an employment outcome makes its rate tautological.
    if MEASURES[measure_name].numerator in {"employed_working_age", "employed_15_plus"}:
        return tuple(dim for dim in dimensions if dim != "employment_status")
    return dimensions


def query(release, table, dimensions, measure_name, filters=()):
    if file_revision(release.path) != release.revision:
        raise ValueError("The advanced artifact changed. Reload before running another query.")
    return cached_query(release, table, dimensions, measure_name, filters)


@st.cache_data(ttl=1800, max_entries=192, show_spinner=False)
def cached_query(release, table, dimensions, measure_name, filters):
    if table not in GRAINS or measure_name not in available_measures(table):
        raise ValueError("This measure is unavailable at the requested grain.")
    supported = available_dimensions(table, measure_name)
    if len(set(dimensions)) != len(dimensions) or any(d not in supported for d in dimensions):
        raise ValueError("The selected dimensions do not coexist in this aggregate.")
    measure = MEASURES[measure_name]
    group = ", ".join(f'"{d}"' for d in dimensions)
    fields = f'SUM({measure.numerator})::BIGINT AS numerator'
    if measure.denominator:
        fields += f', SUM({measure.denominator})::BIGINT AS denominator'
    conditions, params = [], []
    for key, values in filters:
        if key not in supported or not values or len(values) > 150:
            raise ValueError("Unsupported category filter.")
        conditions.append(f'"{key}" IN ({", ".join("?" for _ in values)})')
        params.extend(values)
    with connect(release.path) as con:
        if file_revision(release.path) != release.revision:
            raise ValueError("The advanced artifact changed. Reload before running another query.")
        sql = f'SELECT {group + ", " if group else ""}{fields} FROM "{table}"'
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        if group:
            sql += " GROUP BY ALL ORDER BY ALL"
        data = con.execute(sql, params).fetchdf()
    data["value"] = data.numerator
    if measure.denominator:
        data["value"] = data.numerator.div(data.denominator.where(data.denominator > 0)) * measure.scale
    return data


def distribution(data, dimensions, mode):
    """Normalize the full filtered result before applying display ranks."""
    data = data.copy()
    if mode == "Value":
        return data
    if "denominator" in data:
        raise ValueError("Composition percentages require an additive measure.")
    if mode == "Row %" and len(dimensions) == 2:
        denom = data.groupby(dimensions[0], dropna=False).numerator.transform("sum")
    elif mode == "Column %" and len(dimensions) == 2:
        denom = data.groupby(dimensions[1], dropna=False).numerator.transform("sum")
    elif mode == "Total %":
        denom = pd.Series(data.numerator.sum(), index=data.index)
    else:
        raise ValueError("Unsupported normalization for these dimensions.")
    data["denominator"] = denom
    data["value"] = data.numerator.div(denom.where(denom > 0)) * 100
    return data


# Metrics integrated with the State Intelligence and Comparison workspaces.
STATE_MEASURES = {
    "Recorded income per person": ("income_bands_state", "Mean recorded income", ()),
    "Recorded income among employed": ("income_bands_state", "Mean employed income", ()),
    "Employed share ages 15-64": ("employment_age_gender", "Employed share ages 15-64", ()),
    "Employed share ages 15+": ("employment_age_gender", "Employed share ages 15+", ()),
    "Recorded zero income share": ("income_bands_state", "Recorded zero incomes", ("income_valid", "Valid recorded incomes")),
    "One-person household share": ("household_sizes", "Households", ("household_size", 1)),
    "Graduate share": ("education_gender", "People", ("education", "Graduate")),
    "Smartphone and internet share": ("digital_age_gender", "People", (("smartphone", "Yes"), ("internet", "Yes"))),
    "Bank account and insurance share": ("financial_employment", "People", (("bank", "Yes"), ("insurance", "Yes"))),
}
STATE_DEFINITIONS = {
    "Recorded zero income share": "People with recorded zero income divided by people with valid recorded income.",
    "One-person household share": "One-person households divided by all distinct households.",
    "Graduate share": "People assigned the Graduate category divided by all people. Postgraduate is a separate category.",
    "Smartphone and internet share": "People with both assigned smartphone and internet access divided by all people.",
    "Bank account and insurance share": "People with both an assigned bank account and health insurance divided by all people.",
}
ADVANCED_STATE_METRICS = {
    name: Metric("value", "%" if name in STATE_DEFINITIONS else MEASURES[measure].unit,
                 STATE_DEFINITIONS.get(name, MEASURES[measure].definition))
    for name, (_, measure, _) in STATE_MEASURES.items()
}


def advanced_state_series(release, labels):
    series = {}
    for label in labels:
        table, measure, spec = STATE_MEASURES[label]
        if label in STATE_DEFINITIONS:
            denom_measure = "Valid recorded incomes" if label == "Recorded zero income share" else measure
            denominator = query(release, table, ("State",), denom_measure).set_index("State").numerator
            if label == "Recorded zero income share":
                filters = ()
            elif isinstance(spec[0], tuple):
                filters = tuple((dim, (value,)) for dim, value in spec)
            else:
                filters = ((spec[0], (spec[1],)),)
            numerator = query(release, table, ("State",), measure, filters).set_index("State").numerator
            numerator = numerator.reindex(denominator.index, fill_value=0)
            values = numerator.div(denominator.where(denominator > 0)) * 100
            benchmark = numerator.sum() / denominator.sum() * 100 if denominator.sum() else None
            rows = values.rename("Value").reset_index()
        else:
            rows = query(release, table, ("State",), measure).rename(columns={"value": "Value"})[["State", "Value"]]
            overall = query(release, table, (), measure).value.iloc[0]
            benchmark = None if pd.isna(overall) else float(overall)
        series[label] = rows, benchmark
    return series
