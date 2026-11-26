"""P4D independent reference audit. Only checksum-pinned DuckDB aggregates are read."""

import argparse
from collections import defaultdict
from fractions import Fraction
from hashlib import sha256
from itertools import permutations
import json
import math
from pathlib import Path
from unicodedata import normalize

import duckdb

PINS = {
    "production": "bb8453a00ff5e832ecb1ee98ff286c81f2410d4f6a481a955a6786c0ad822e2c",
    "snapshot": "e0f491fe2a9b42af228324a786142106826e129bd8af5b394fd696e4a6138939",
    "advanced": "05053a452415186c4d29a1b4d03c21734cbc492cc4f989890a0683829fb443ac",
}
POPULATION = 1_500_000_000
HOUSEHOLDS = 397_105_805
ABS = 1e-9
REL = 1e-12

# Independent business inventory. Axes are deliberately declared separately
# from the application's allowlist and arithmetic implementation.
GRAINS = {
    "person_counts": ("Gender", "age_cohort"),
    "education_gender": ("Gender", "education"),
    "education_age": ("age_cohort", "education"),
    "education_settlement": ("settlement", "education"),
    "employment_age_gender": ("age_cohort", "Gender", "employment_status"),
    "employment_settlement": ("settlement", "employment_status"),
    "occupation_gender": ("Gender", "employment_status", "Occupation"),
    "employment_education": ("education", "employment_status"),
    "income_bands_state": ("income_band",),
    "income_bands_gender": ("Gender", "income_band"),
    "income_bands_settlement": ("settlement", "income_band"),
    "income_education": ("education",),
    "income_occupation": ("Occupation",),
    "income_age": ("age_cohort",),
    "income_gender": ("Gender",),
    "household_sizes": ("settlement", "household_size"),
    "digital_age_gender": ("age_cohort", "Gender", "smartphone", "internet"),
    "financial_education_gender": ("education", "Gender", "bank", "insurance"),
    "financial_employment": ("employment_status", "bank", "insurance"),
}
COUNTS = {"People": ("people", None, 1)}
WORK = {
    **COUNTS,
    "Employed share ages 15-64": ("employed_working_age", "working_age_known_status", 100),
    "Employed share ages 15+": ("employed_15_plus", "eligible_15_plus_known_status", 100),
}
INCOME = {
    **COUNTS,
    "Valid recorded incomes": ("income_valid", None, 1),
    "Valid employed incomes": ("employed_income_valid", None, 1),
    "Recorded zero incomes": ("income_zero", None, 1),
    "Recorded income sum": ("income_sum", None, 1),
    "Mean recorded income": ("income_sum", "income_valid", 1),
    "Mean employed income": ("employed_income_sum", "employed_income_valid", 1),
}
HOME = {
    "Households": ("households", None, 1),
    "Household members": ("members", None, 1),
    "Mean household size": ("members", "households", 1),
}


def open_read(path):
    return duckdb.connect(str(path), read_only=True, config={
        "threads": 2, "memory_limit": "512MB", "enable_external_access": "false",
        "max_temp_directory_size": "0bytes",
    })


def checksum(path):
    with Path(path).open("rb") as f:
        digest = sha256()
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


class Audit:
    def __init__(self):
        self.groups = defaultdict(lambda: {"passed": 0, "failed": 0})
        self.failures = []

    def check(self, family, label, condition):
        if condition:
            self.groups[family]["passed"] += 1
        else:
            self.groups[family]["failed"] += 1
            self.failures.append(f"{family}: {label}")


def reference_measures(table):
    if table.startswith("income_"):
        return INCOME
    if table == "household_sizes":
        return HOME
    if table in ("employment_age_gender", "employment_settlement", "employment_education"):
        return WORK
    return COUNTS


def quote(name):
    return '"' + name.replace('"', '""') + '"'


def grouped(conn, table, dims, expression):
    keys = ",".join(quote(x) for x in dims)
    return conn.execute(f"SELECT {keys+', ' if keys else ''}{expression} FROM {quote(table)}"
                        + (f" GROUP BY {keys} ORDER BY {keys}" if keys else "")).fetchall()


def records(conn, table):
    cur = conn.execute(f"SELECT * FROM {quote(table)}")
    columns = [entry[0] for entry in cur.description]
    return [dict(zip(columns, row)) for row in cur.fetchall()]


def ratio(num, den, scale):
    return Fraction(num * scale, den) if den else None


def comparable(actual, expected):
    if expected is None:
        return actual is None or math.isnan(actual)
    return not math.isnan(actual) and math.isclose(actual, float(expected), abs_tol=ABS, rel_tol=REL)


def reconcile(audit, prod, snap, adv):
    national = prod.execute("SELECT total_population,distinct_households FROM national_summary").fetchone()
    audit.check("reconciliation", "authoritative national totals", national == (POPULATION, HOUSEHOLDS))
    state = grouped(prod, "state_summary", ("State",), "SUM(population), SUM(households)")
    audit.check("reconciliation", "36 unique states", len(state) == 36)
    audit.check("reconciliation", "national equals state sum", tuple(map(sum, zip(*[r[1:] for r in state]))) == national)
    for table, dims in GRAINS.items():
        units = "members" if table == "household_sizes" else "people"
        rows = grouped(adv, table, ("State",), f"SUM({units})")
        audit.check("reconciliation", f"{table} state people", rows == [r[:2] for r in state])
        unique = grouped(adv, table, ("State", *dims), "COUNT(*)")
        audit.check("reconciliation", f"{table} unique grain", all(r[-1] == 1 for r in unique))
        audit.check("reconciliation", f"{table} no unlabeled dimensions",
                    all(all(value is not None and value != "" for value in r[:-1]) for r in unique))
    audit.check("reconciliation", "all state households", grouped(adv, "household_sizes", ("State",), "SUM(members),SUM(households)") == state)
    household = records(adv, "household_sizes")
    audit.check("reconciliation", "size times households equals people in each cell",
                all(row["household_size"] * row["households"] == row["members"] for row in household))
    margins = [
        ("person_counts", ("State", "Gender", "age_cohort"), "state_age_gender_summary", ("State", "Gender", "age_group")),
        ("education_settlement", ("State", "settlement"), "state_settlement_summary", ("State", "settlement")),
        ("education_gender", ("State", "education"), "state_education_summary", ("State", "education_level")),
        ("education_age", ("State", "education"), "state_education_summary", ("State", "education_level")),
        ("education_settlement", ("State", "education"), "state_education_summary", ("State", "education_level")),
        ("occupation_gender", ("State", "Occupation"), "state_occupation_summary", ("State", "Occupation")),
        ("digital_age_gender", ("State", "smartphone", "internet"), "state_digital_summary", ("State", "smartphone_ownership", "internet_access")),
    ]
    margins.extend((table, ("State", dim), f"state_{dim}_summary", ("State", dim))
                   for table in ("financial_education_gender", "financial_employment") for dim in ("bank","insurance"))
    for actual, dims, expected, refdims in margins:
        audit.check("reconciliation", f"{actual} against {expected}",
                    grouped(adv, actual, dims, "SUM(people)") == grouped(prod, expected, refdims, "SUM(population)"))
    activity = prod.execute("""
        SELECT State, CASE WHEN main_activity IN ('Child','Student/Other') THEN 'Not applicable'
          ELSE main_activity END AS status, SUM(population)
        FROM state_main_activity_summary GROUP BY 1,2 ORDER BY 1,2
    """).fetchall()
    age_eligibility = grouped(prod, "state_age_value_summary", ("State",),
        'SUM(population) FILTER(WHERE Age>=15), SUM(population) FILTER(WHERE Age BETWEEN 15 AND 64)')
    for t in ("employment_age_gender", "employment_education", "employment_settlement"):
        audit.check("reconciliation", f"{t} employment labels", grouped(adv,t,("State","employment_status"),"SUM(people)") == activity)
        audit.check("reconciliation", f"{t} exact-age eligibility",
                    grouped(adv,t,("State",),"SUM(eligible_15_plus),SUM(working_age_15_64)") == age_eligibility)
    income = grouped(prod, "_partial_income_summary", ("State",), "SUM(income_n),SUM(income_sum)")
    for name in GRAINS:
        if name.startswith("income_"):
            audit.check("reconciliation", f"{name} valid counts and annual sums",
                        grouped(adv,name,("State",),"SUM(income_valid),SUM(income_sum)") == income)
    edges = {"Zero":(0,1), "1-49,999":(1,50_000), "50,000-99,999":(50_000,100_000),
             "100,000-249,999":(100_000,250_000), "250,000-499,999":(250_000,500_000),
             "500,000-999,999":(500_000,1_000_000), "1,000,000+":(1_000_000,None)}
    state_band = grouped(adv,"income_bands_state",("State","income_band"),"SUM(people),SUM(income_valid),SUM(income_zero),SUM(income_sum)")
    for _, label, people, valid, zeros, total in state_band:
        missing = label == "Missing or invalid"
        lo,hi = edges.get(label,(0,None))
        audit.check("income bands", f"{label} bounds and counts",
                    (valid == zeros == total == 0 if missing else
                     label in edges and valid == people and zeros == (people if label=="Zero" else 0)
                     and total >= lo*valid and (hi is None or total < hi*valid)))
    for table in ("income_bands_gender","income_bands_settlement"):
        audit.check("reconciliation", f"{table} band/state totals",
                    grouped(adv,table,("State","income_band"),"SUM(people),SUM(income_valid),SUM(income_zero),SUM(income_sum)") == state_band)
    for name, in snap.execute("SELECT table_name FROM information_schema.tables WHERE table_schema='main' ORDER BY 1").fetchall():
        fields = ", ".join(quote(row[0]) for row in snap.execute(f"DESCRIBE {quote(name)}").fetchall())
        audit.check("snapshot parity", name,
                    prod.execute(f"SELECT {fields} FROM {quote(name)} ORDER BY ALL").fetchall()
                    == snap.execute(f"SELECT {fields} FROM {quote(name)} ORDER BY ALL").fetchall())
    def canonical(value):
        text = normalize("NFKD", value).encode("ascii","ignore").decode().lower().replace("&"," and ")
        return "".join(char for char in text if char.isalnum())
    assets = Path(__file__).resolve().parent / "assets"
    geometries = json.loads((assets/"india-states.geojson").read_text(encoding="utf-8-sig"))
    names = [canonical(feature["properties"]["shapeName"]) for feature in geometries["features"]]
    audit.check("reconciliation", "36 unique exact canonical map joins",
                len(names) == len(set(names)) == 36 and set(names) == {canonical(row[0]) for row in state})
    return {"records": national[0], "households": national[1], "states":len(state),
            "valid_income": sum(row[1] for row in income), "income_sum_inr": sum(row[2] for row in income),
            "zero_income": sum(row[4] for row in state_band)}, state


def reference_cell(rows, dimensions, numerator, denominator, filters):
    result = defaultdict(lambda: [0, 0])
    for row in rows:
        if any(row[key] not in values for key, values in filters):
            continue
        key = tuple(row[d] for d in dimensions)
        result[key][0] += row[numerator]
        if denominator:
            result[key][1] += row[denominator]
    return result


def explorer_matrix(audit, adv, release):
    from advanced_analytics import available_dimensions, available_measures, distribution, query
    for name, keys in GRAINS.items():
        rows = records(adv, name)
        measures = reference_measures(name)
        audit.check("registry", name, set(available_measures(name)) == set(measures))
        for label, (numerator, denominator, scale) in measures.items():
            axes = ("State", *(d for d in keys if not (label.startswith("Employed share") and d == "employment_status")))
            audit.check("registry", f"{name} {label} dimensions", tuple(available_dimensions(name,label)) == axes)
            for dims in [*((d,) for d in axes), *permutations(axes, 2)]:
                category = axes[1]
                category_value = next(row[category] for row in rows if row["State"] == "Delhi")
                for filters in [(), (("State", ("Delhi","Kerala")), (category, (category_value,)))]:
                    wanted = reference_cell(rows,dims,numerator,denominator,filters)
                    actual = query(release,name,dims,label,filters)
                    def key(row):
                        return tuple(getattr(row,d) for d in dims)
                    def read(actual, field):
                        return {key(row): getattr(row, field) for row in actual.itertuples(index=False)}
                    ident = f"{name} | {label} | {dims} | {filters}"
                    audit.check("explorer cells", ident, read(actual,"numerator") == {k:n for k,(n,_) in wanted.items()})
                    if denominator:
                        values = read(actual,"value")
                        audit.check("explorer weighted metrics", ident,
                                    read(actual,"denominator") == {k:d for k,(_,d) in wanted.items()}
                                    and all(comparable(values.get(k,float("nan")),ratio(n,d,scale)) for k,(n,d) in wanted.items()))
                    else:
                        modes = [("Total %", None)]
                        if len(dims)==2:
                            modes.extend([("Row %",0),("Column %",1)])
                        for mode, index in modes:
                            totals = defaultdict(int)
                            for k,(n,_) in wanted.items():
                                totals[k[index] if index is not None else None] += n
                            computed = distribution(actual,dims,mode)
                            observed = read(computed,"value")
                            audit.check("explorer normalization", f"{ident} {mode}",
                                        len(observed)==len(wanted) and all(comparable(observed[k],ratio(n,totals[k[index] if index is not None else None],100)) for k,(n,_) in wanted.items()))


def profile_matrix(audit, prod, adv, release, scope, states):
    from intelligence import benchmark_rows
    # Expected values are constructed with separate SQL expressions and rational arithmetic.
    specs = {
        "Population": (prod,"state_summary","SUM(population)",None,1,"people"),
        "Households": (prod,"state_summary","SUM(households)",None,1,"households"),
        "Mean household size": (prod,"state_summary","SUM(population)","SUM(households)",1,"people / household"),
        "Mean age": (prod,"state_summary","MAX(average_age)",None,1,"years"),
        "Mean annual income": (prod,"income_summary","MAX(average_income)",None,1,"INR / person"),
        "Urban share": (prod,"state_settlement_summary","SUM(CASE WHEN settlement='Urban' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Employed share": (prod,"state_main_activity_summary","SUM(CASE WHEN main_activity='Employed' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Bank account coverage": (prod,"state_bank_summary","SUM(CASE WHEN bank='Yes' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Health insurance coverage": (prod,"state_insurance_summary","SUM(CASE WHEN insurance='Yes' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Disability prevalence": (prod,"state_disability_summary","SUM(CASE WHEN disability='Yes' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Internet access": (prod,"state_digital_summary","SUM(CASE WHEN internet_access='Yes' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Smartphone ownership": (prod,"state_digital_summary","SUM(CASE WHEN smartphone_ownership='Yes' THEN population ELSE 0 END)","SUM(population)",100,"%"),
        "Recorded income per person": (adv,"income_bands_state","SUM(income_sum)","SUM(income_valid)",1,"INR / person / year"),
        "Recorded income among employed": (adv,"income_bands_state","SUM(employed_income_sum)","SUM(employed_income_valid)",1,"INR / employed person / year"),
        "Employed share ages 15-64": (adv,"employment_age_gender","SUM(employed_working_age)","SUM(working_age_known_status)",100,"%"),
        "Employed share ages 15+": (adv,"employment_age_gender","SUM(employed_15_plus)","SUM(eligible_15_plus_known_status)",100,"%"),
        "Recorded zero income share": (adv,"income_bands_state","SUM(income_zero)","SUM(income_valid)",100,"%"),
        "One-person household share": (adv,"household_sizes","SUM(CASE WHEN household_size=1 THEN households ELSE 0 END)","SUM(households)",100,"%"),
        "Graduate share": (adv,"education_gender","SUM(CASE WHEN education='Graduate' THEN people ELSE 0 END)","SUM(people)",100,"%"),
        "Smartphone and internet share": (adv,"digital_age_gender","SUM(CASE WHEN smartphone='Yes' AND internet='Yes' THEN people ELSE 0 END)","SUM(people)",100,"%"),
        "Bank account and insurance share": (adv,"financial_employment","SUM(CASE WHEN bank='Yes' AND insurance='Yes' THEN people ELSE 0 END)","SUM(people)",100,"%"),
    }
    names = [state[0] for state in states]
    got = benchmark_rows(scope,list(specs),names).set_index(["Metric","State"])
    for metric, (con, table, num, den, scale, unit) in specs.items():
        if den:
            pairs = grouped(con,table,("State",),f"{num},{den}")
            values = {state:ratio(n,d,scale) for state,n,d in pairs}
            bench = ratio(sum(r[1] for r in pairs),sum(r[2] for r in pairs),scale)
        else:
            values = dict(grouped(con,table,("State",),num))
            if metric=="Mean age":
                bench=prod.execute("SELECT average_age FROM national_summary").fetchone()[0]
            elif metric=="Mean annual income":
                bench=sum(values[state]*pop for state,pop,_ in states)/POPULATION
            else:
                bench=sum(values.values())
        for state in names:
            row=got.loc[(metric,state)]
            value=values[state]
            gap=value-bench if value is not None and bench is not None else None
            rank=1+sum(other>value for other in values.values() if other is not None) if value is not None else None
            ok=(comparable(row.Value,value) and comparable(row["All-India benchmark"],bench)
                and comparable(row["Percentage-point gap"],gap if unit=="%" else None)
                and comparable(row["Absolute gap"],gap if unit!="%" else None)
                and comparable(row["Relative gap (%)"],float(gap)*100/abs(float(bench)) if gap is not None and bench else None)
                and row["National rank"]==rank and row.Unit==unit)
            audit.check("state profile and comparison",f"{metric} {state}",ok)


def run(paths):
    from advanced_analytics import Release, file_revision
    from analytics import Scope
    from dashboard_data import validate_artifact
    audit = Audit()
    hashes = {name:checksum(path) for name,path in paths.items()}
    for name, digest in hashes.items():
        audit.check("integrity",name,digest==PINS[name])
    if audit.failures:
        raise ValueError("Frozen artifact checksum mismatch: " + ", ".join(audit.failures))
    with open_read(paths["production"]) as prod, open_read(paths["snapshot"]) as snap, open_read(paths["advanced"]) as adv:
        verified, states = reconcile(audit,prod,snap,adv)
        release=Release(paths["advanced"],file_revision(paths["advanced"]),1,POPULATION,15000,36,hashes["advanced"],HOUSEHOLDS)
        dataset=validate_artifact("development",paths["snapshot"],file_revision(paths["snapshot"]))
        scope=Scope(dataset,"",[],snap.execute("SELECT * FROM state_summary").fetchdf(),release)
        explorer_matrix(audit,adv,release)
        profile_matrix(audit,prod,adv,release,scope,states)
    for name,path in paths.items():
        audit.check("integrity", f"{name} after audit", checksum(path)==hashes[name])
    return {"release":"P4B-v1 / v3.4 synthetic", "hashes":hashes, "verified":verified,
            "tolerance":{"absolute":ABS,"relative":REL}, "groups":dict(audit.groups),
            "totals":{key:sum(group[key] for group in audit.groups.values()) for key in ("passed","failed")},
            "failures":audit.failures}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in PINS:
        parser.add_argument("--"+name,required=True,type=Path)
    parser.add_argument("--report",required=True,type=Path)
    args=parser.parse_args()
    report=run({name:getattr(args,name).resolve(strict=True) for name in PINS})
    with args.report.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2)
    print(json.dumps({"verified":report["verified"],"totals":report["totals"],"failures":report["failures"][:10]}))
    raise SystemExit(bool(report["failures"]))


if __name__ == "__main__":
    main()
