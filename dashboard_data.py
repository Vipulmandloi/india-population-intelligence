"""Configuration and read-only contract for the dashboard's aggregate database."""

import os
from dataclasses import dataclass
from pathlib import Path

import duckdb


PRODUCTION_RECORDS = 1_500_000_000
BUNDLED_RELEASE = Path(__file__).resolve().parent / "data" / "india_population_release.duckdb"
PROJECTIONS = {
    "national_summary": ("total_population", "average_age", "median_age", "distinct_households"),
    "state_summary": ("State", "population", "average_age", "households"),
    "state_age_summary": ("State", "average_age", "median_age"),
    "city_summary": ("State", "City", "population"),
    "age_summary": ("age_group", "population"),
    "gender_summary": ("Gender", "population"),
    "age_gender_summary": ("age_group", "Gender", "population"),
    "state_age_gender_summary": ("State", "age_group", "Gender", "population"),
    "occupation_summary": ("Occupation", "population"),
    "state_occupation_summary": ("State", "Occupation", "population"),
    "income_summary": ("State", "average_income", "average_monthly_earnings"),
    "dashboard_metadata": ("dataset_version", "expected_records", "data_notice"),
}
for name, columns in {
    "settlement": ("settlement",),
    "education": ("education_level",),
    "digital": ("smartphone_ownership", "internet_access"),
    "literacy": ("literacy",),
    "employment_type": ("employment_type",),
    "main_activity": ("main_activity",),
    "marital": ("marital",),
    "religion": ("Religion",),
    "social_group": ("social_group",),
    "mother_tongue": ("mother_tongue",),
    "bank": ("bank",),
    "insurance": ("insurance",),
    "disability": ("disability",),
    "wealth": ("wealth",),
}.items():
    PROJECTIONS[f"{name}_summary"] = (*columns, "population")
    PROJECTIONS[f"state_{name}_summary"] = ("State", *columns, "population")

COUNTS = {"population", "total_population", "distinct_households", "households", "expected_records"}
MEANS = {"average_age", "median_age", "average_income", "average_monthly_earnings"}
NUMERIC_TYPES = {"SMALLINT", "INTEGER", "BIGINT", "HUGEINT", "FLOAT", "DOUBLE"}


class DashboardDataError(ValueError):
    """Actionable configuration or artifact error safe to show in the UI."""


@dataclass(frozen=True)
class Dataset:
    mode: str
    path: Path
    revision: tuple
    version: str
    records: int
    projections: dict


def dataset_config():
    mode = os.getenv("INDIA_APP_MODE", "development").strip().lower()
    if mode not in {"production", "development"}:
        raise DashboardDataError("Set INDIA_APP_MODE to production or development.")
    configured_path = os.getenv("INDIA_DB_PATH", "").strip()
    if mode == "production" and not configured_path:
        raise DashboardDataError("Production mode requires INDIA_DB_PATH to point to the production DuckDB file.")
    try:
        path = Path(configured_path).expanduser().resolve() if configured_path else BUNDLED_RELEASE
        if not path.is_file():
            raise DashboardDataError("Analytics database is missing. Set INDIA_DB_PATH to a DuckDB file.")
        stat = path.stat()
        with path.open("rb") as artifact:
            if artifact.read(64).startswith(b"version https://git-lfs.github.com/spec/v1"):
                raise DashboardDataError("The analytics file is a Git LFS pointer. Fetch the LFS object or set INDIA_DB_PATH to a materialized database.")
    except (OSError, RuntimeError, ValueError) as error:
        if isinstance(error, DashboardDataError):
            raise
        raise DashboardDataError("The analytics file cannot be read. Check INDIA_DB_PATH and file permissions.") from error
    return mode, path, (stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)


def connect(path):
    return duckdb.connect(str(path), read_only=True, config={
        "threads": "2",
        "memory_limit": "512MB",
        "max_temp_directory_size": "0bytes",
        "enable_external_access": "false",
    })


def validate_artifact(mode, path, revision):
    try:
        with connect(path) as con:
            if mode == "production":
                national = con.execute("SELECT total_population FROM national_summary LIMIT 2").fetchall()
                if national != [(PRODUCTION_RECORDS,)]:
                    raise DashboardDataError("Production mode requires the 1.5 billion-record analytics artifact.")

            schema = {}
            for table, column, data_type in con.execute("""
                SELECT table_name, column_name, data_type
                FROM information_schema.columns WHERE table_schema = 'main'
            """).fetchall():
                schema.setdefault(table, {})[column] = data_type
            projections = {}
            for table, columns in PROJECTIONS.items():
                actual = schema.get(table, {})
                resolved = []
                for column in columns:
                    # Some compatible exports already normalize category column names.
                    category = table.removeprefix("state_").removesuffix("_summary")
                    if column not in actual and column == category and category in {
                        "literacy", "employment_type", "main_activity", "marital",
                        "social_group", "mother_tongue", "bank", "insurance", "disability", "wealth",
                    }:
                        column = "category"
                    if column == "Religion" and column not in actual:
                        column = "category"
                    data_type = actual.get(column)
                    expected = (
                        {"BIGINT"} if column in COUNTS else
                        NUMERIC_TYPES if column in MEANS else
                        {"VARCHAR", "BIGINT"} if column in {"wealth", "category"} else
                        {"VARCHAR"}
                    )
                    if data_type not in expected:
                        raise DashboardDataError(f"Incompatible analytics schema at {table}.{column}. Use a supported DuckDB artifact.")
                    resolved.append(column)
                projections[table] = tuple(resolved)

            meta = con.execute("SELECT dataset_version, expected_records, data_notice FROM dashboard_metadata LIMIT 2").fetchall()
            totals = con.execute("SELECT total_population FROM national_summary LIMIT 2").fetchall()
            state_count, unique_states, state_total = con.execute(
                'SELECT COUNT(*), COUNT(DISTINCT "State"), SUM(population) FROM state_summary'
            ).fetchone()
            if len(meta) != 1 or len(totals) != 1:
                raise DashboardDataError("The analytics artifact must contain one metadata row and one national summary row.")
            version, records, notice = meta[0]
            if not version or not notice or "synthetic" not in notice.lower():
                raise DashboardDataError("The analytics artifact is missing its synthetic dataset identity.")
            if not records or records < 1 or totals[0][0] != records or state_total != records or state_count != unique_states:
                raise DashboardDataError("The analytics artifact failed national and state population reconciliation.")
            if mode == "production" and (version != "v3.4" or state_count != 36):
                raise DashboardDataError("Production mode requires the v3.4 artifact with all 36 States/UTs.")
            return Dataset(mode, path, revision, version, records, projections)
    except duckdb.Error as error:
        raise DashboardDataError(
            "Cannot open or validate the analytics database. Use a readable, compatible DuckDB artifact."
        ) from error
