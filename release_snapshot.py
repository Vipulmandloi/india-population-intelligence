"""Build and verify a portable release from explicitly allowlisted aggregates."""

import argparse
import hashlib
import json
import math
from collections import defaultdict
import os
from pathlib import Path
import re
from tempfile import TemporaryDirectory

import duckdb

from dashboard_data import PROJECTIONS, connect, validate_artifact


RELEASE_COLUMNS = {
    **PROJECTIONS,
    "age_value_summary": ("Age", "population"),
    "state_age_value_summary": ("State", "Age", "population"),
    "occupation_summary": (*PROJECTIONS["occupation_summary"], "average_annual_income"),
    "state_occupation_summary": (*PROJECTIONS["state_occupation_summary"], "average_income"),
}
METRICS = {"population", "households", "average_income", "average_annual_income"}
PRIVATE_TEXT = re.compile(
    r'(?:[A-Za-z]:[\\/]|\\\\|/(?:Users|home|mnt|var|tmp)/|https?://|'
    r'[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?:password|api[_ -]?key|secret|token)\s*[:=])',
    re.IGNORECASE,
)


def ident(value):
    return '"' + value.replace('"', '""') + '"'


def file_hash(path):
    with Path(path).open("rb") as source:
        digest = hashlib.sha256()
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_summary(con, table, columns):
    projection = ", ".join(map(ident, columns))
    sql = f"SELECT {projection} FROM main.{ident(table)} ORDER BY ALL"
    cursor = con.execute(sql)
    return tuple((item[0], str(item[1])) for item in cursor.description), cursor.fetchall()


def catalog(con):
    return dict(con.execute("""
        SELECT table_name, table_type
        FROM information_schema.tables WHERE table_schema = 'main'
    """).fetchall())


def check_rows(table, columns, rows):
    dimensions = []
    if table not in {"national_summary", "dashboard_metadata"}:
        dimensions = [i for i, column in enumerate(columns) if column not in METRICS and not column.startswith("average_") and column != "median_age"]
    if not rows or (dimensions and len({tuple(row[i] for i in dimensions) for row in rows}) != len(rows)):
        raise ValueError(f"{table}: empty summary or duplicate grain")
    for row in rows:
        for column, value in zip(columns, row):
            if value is None:
                raise ValueError(f"{table}.{column}: unexpected null")
            if isinstance(value, str) and PRIVATE_TEXT.search(value):
                raise ValueError(f"{table}.{column}: machine path or sensitive text pattern")
            if isinstance(value, (float, int)) and (not math.isfinite(value) or value < 0):
                raise ValueError(f"{table}.{column}: invalid numeric value")


def check_age(frequencies, average, median, label):
    count = sum(n for _, n in frequencies)
    mean = sum(age * n for age, n in frequencies) / count
    targets = ((count + 1) // 2, (count + 2) // 2)
    medians = []
    cumulative = 0
    for age, n in sorted(frequencies):
        cumulative += n
        while len(medians) < 2 and cumulative >= targets[len(medians)]:
            medians.append(age)
    if abs(mean - average) > 0.00500001 or sum(medians) / 2 != median:
        raise ValueError(f"{label}: age statistics do not match the frequency table")


def verify_snapshot(source, snapshot, mode="production"):
    dataset = validate_artifact(mode, snapshot, ())
    with connect(source) as original, connect(snapshot) as release:
        if catalog(release) != dict.fromkeys(RELEASE_COLUMNS, "BASE TABLE"):
            raise ValueError("Release catalog differs from the aggregate allowlist")
        if release.execute("SELECT COUNT(*) FROM duckdb_schemas() WHERE NOT internal AND schema_name <> 'main'").fetchone()[0]:
            raise ValueError("Release contains a custom schema")
        if any(release.execute(f"SELECT COUNT(*) FROM {function}").fetchone()[0] for function in (
            "duckdb_indexes()", "duckdb_sequences()",
            "duckdb_views() WHERE NOT internal",
            "duckdb_functions() WHERE NOT internal",
        )):
            raise ValueError("Release contains unexpected catalog objects")
        national = release.execute("SELECT * FROM national_summary").fetchone()
        states = dict(release.execute('SELECT "State", population FROM state_summary').fetchall())
        if release.execute("SELECT SUM(households) FROM state_summary").fetchone()[0] != national[3]:
            raise ValueError("State household counts do not reconcile")
        state_plus = set(states)
        aggregate_rows = 0
        population_rollups = {}
        for table, columns in RELEASE_COLUMNS.items():
            if list(columns) != [row[1] for row in release.execute(f"PRAGMA table_info({ident(table)})").fetchall()]:
                raise ValueError(f"{table}: extra, missing, or reordered release columns")
            expected_schema, expected_rows = read_summary(original, table, columns)
            schema, rows = read_summary(release, table, columns)
            if schema != expected_schema or rows != expected_rows:
                raise ValueError(f"{table}: schema, values, or multiplicity differ from source")
            check_rows(table, columns, rows)
            aggregate_rows += len(rows)
            if "State" in columns and {row[columns.index("State")] for row in rows} != state_plus:
                raise ValueError(f"{table}: state coverage differs from state_summary")
            if "population" in columns:
                index = columns.index("population")
                population_rollups[table] = (columns, rows)
                if sum(row[index] for row in rows) != dataset.records:
                    raise ValueError(f"{table}: population does not reconcile")
                if "State" in columns:
                    state_index = columns.index("State")
                    totals = dict.fromkeys(states, 0)
                    for row in rows:
                        totals[row[state_index]] += row[index]
                    if totals != states:
                        raise ValueError(f"{table}: state populations do not reconcile")
        for table, (columns, rows) in population_rollups.items():
            national_table = table.removeprefix("state_")
            if table == national_table or national_table not in population_rollups:
                continue
            national_columns, national_rows = population_rollups[national_table]
            dimensions = [column for column in national_columns if column not in METRICS]
            national_keys = [national_columns.index(column) for column in dimensions]
            state_keys = [columns.index(column) for column in dimensions]
            national_counts = {tuple(row[i] for i in national_keys): row[national_columns.index("population")]
                               for row in national_rows}
            state_counts = defaultdict(int)
            for row in rows:
                state_counts[tuple(row[i] for i in state_keys)] += row[columns.index("population")]
            if state_counts != national_counts:
                raise ValueError(f"{table}: category counts do not reconcile with {national_table}")
        check_age(release.execute('SELECT "Age", population FROM age_value_summary').fetchall(), national[1], national[2], "National")
        for state, mean, median in release.execute("SELECT * FROM state_age_summary").fetchall():
            frequencies = release.execute(
                'SELECT "Age", population FROM state_age_value_summary WHERE "State" = ?', [state]
            ).fetchall()
            check_age(frequencies, mean, median, state)
    return {
        "dataset_version": dataset.version,
        "synthetic_records": dataset.records,
        "states_and_uts": len(states),
        "aggregate_tables": len(RELEASE_COLUMNS),
        "aggregate_rows": aggregate_rows,
        "size_bytes": Path(snapshot).stat().st_size,
        "sha256": file_hash(snapshot),
    }


def create_snapshot(source, output, mode="production"):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise FileExistsError(f"Choose a new release path: {output}")
    # Stage beside the output so publication uses the same filesystem.
    with TemporaryDirectory(prefix=".release-", dir=output.parent) as directory:
        candidate = Path(directory) / "analytics.duckdb"
        with connect(source) as original, duckdb.connect(str(candidate)) as release:
            release.execute("SET threads = 2")
            release.execute("SET memory_limit = '512MB'")
            source_catalog = catalog(original)
            for table, columns in RELEASE_COLUMNS.items():
                if source_catalog.get(table) != "BASE TABLE":
                    raise ValueError(f"Expected a source base table: {table}")
                schema, rows = read_summary(original, table, columns)
                if any(kind not in {"VARCHAR", "SMALLINT", "INTEGER", "BIGINT", "DOUBLE"} for _, kind in schema):
                    raise ValueError(f"{table}: unsupported column type")
                check_rows(table, columns, rows)
                definitions = ", ".join(f"{ident(name)} {kind}" for name, kind in schema)
                placeholders = ", ".join("?" for _ in schema)
                release.execute(f"CREATE TABLE {ident(table)} ({definitions})")
                release.executemany(f"INSERT INTO {ident(table)} VALUES ({placeholders})", rows)
            release.execute("CHECKPOINT")
        result = verify_snapshot(source, candidate, mode)
        # Atomic, no replacement. A concurrent creator wins without being overwritten.
        os.link(candidate, output)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    operation = create_snapshot if args.command == "create" else verify_snapshot
    print(json.dumps(operation(args.source, args.output), indent=2))


if __name__ == "__main__":
    main()
