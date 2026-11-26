"""Contract and metric registry for the separate advanced aggregate artifact."""

from pathlib import Path

from dashboard_data import connect

SCHEMA_VERSION = 1
COUNT = ("people",)
EMPLOYMENT = ("people", "age_known", "eligible_15_plus", "working_age_15_64", "status_known",
              "eligible_15_plus_known_status", "working_age_known_status",
              "employed", "employed_15_plus", "employed_working_age")
INCOME = ("people", "income_valid", "income_zero", "income_sum", "employed_people",
          "employed_income_valid", "employed_income_sum")
HOUSEHOLD = ("households", "members")

# All grains retain State so national views use additive rollups of stored numerators.
GRAINS = {
    "person_counts": (("State", "Gender", "age_cohort"), COUNT),
    "education_gender": (("State", "Gender", "education"), COUNT),
    "education_age": (("State", "age_cohort", "education"), COUNT),
    "education_settlement": (("State", "settlement", "education"), COUNT),
    "employment_age_gender": (("State", "age_cohort", "Gender", "employment_status"), EMPLOYMENT),
    "employment_settlement": (("State", "settlement", "employment_status"), EMPLOYMENT),
    "occupation_gender": (("State", "Gender", "employment_status", "Occupation"), COUNT),
    "employment_education": (("State", "education", "employment_status"), EMPLOYMENT),
    "income_bands_state": (("State", "income_band"), INCOME),
    "income_bands_gender": (("State", "Gender", "income_band"), INCOME),
    "income_bands_settlement": (("State", "settlement", "income_band"), INCOME),
    "income_education": (("State", "education"), INCOME),
    "income_occupation": (("State", "Occupation"), INCOME),
    "income_age": (("State", "age_cohort"), INCOME),
    "income_gender": (("State", "Gender"), INCOME),
    "household_sizes": (("State", "settlement", "household_size"), HOUSEHOLD),
    "digital_age_gender": (("State", "age_cohort", "Gender", "smartphone", "internet"), COUNT),
    "financial_education_gender": (("State", "education", "Gender", "bank", "insurance"), COUNT),
    "financial_employment": (("State", "employment_status", "bank", "insurance"), COUNT),
}

METRIC_REGISTRY = {
    "people": ("row count", "", "synthetic people"),
    "age_known": ("rows with known age", "", "synthetic people"),
    "eligible_15_plus": ("rows with age >= 15", "", "synthetic people"),
    "working_age_15_64": ("rows with age between 15 and 64", "", "synthetic people"),
    "status_known": ("rows with generated status other than Unknown", "", "synthetic people"),
    "eligible_15_plus_known_status": ("age >= 15 and known status", "", "synthetic people"),
    "working_age_known_status": ("age 15-64 and known status", "", "synthetic people"),
    "employed": ("status = Employed", "", "synthetic people"),
    "employed_15_plus": ("status = Employed and age >= 15", "", "synthetic people"),
    "employed_working_age": ("status = Employed and age 15-64", "", "synthetic people"),
    "employed_share_15_plus": ("employed_15_plus", "eligible_15_plus_known_status", "proportion"),
    "employed_share_15_64": ("employed_working_age", "working_age_known_status", "proportion"),
    "income_valid": ("rows with nonnegative recorded annual income", "", "synthetic people"),
    "income_zero": ("rows with recorded zero annual income", "", "synthetic people"),
    "income_sum": ("sum of nonnegative recorded annual income", "", "generated INR/year"),
    "mean_income": ("income_sum", "income_valid", "generated INR/year per person with valid income"),
    "employed_people": ("status = Employed", "", "synthetic people"),
    "employed_income_valid": ("rows with status = Employed and valid income", "", "synthetic people"),
    "employed_income_sum": ("sum of annual income for employed people with valid income", "", "generated INR/year"),
    "employed_mean_income": ("employed_income_sum", "employed_income_valid", "generated INR/year per employed person with valid income"),
    "households": ("verified distinct generated household IDs", "", "synthetic households"),
    "members": ("sum of observed household members", "", "synthetic people"),
    "persons_per_household": ("members", "households", "synthetic people per household"),
}


def inspect_artifact(path, expected_records=None):
    """Fail closed for an incomplete or incompatible separate aggregate artifact."""
    path = Path(path)
    with connect(path) as con:
        catalog = dict(con.execute(
            "SELECT table_name, table_type FROM information_schema.tables WHERE table_schema='main'"
        ).fetchall())
        if catalog != dict.fromkeys([*GRAINS, "advanced_metadata"], "BASE TABLE"):
            raise ValueError("Advanced artifact catalogue does not match the schema")
        rows = con.execute("SELECT * FROM advanced_metadata LIMIT 2").fetchall()
        if len(rows) != 1:
            raise ValueError("Advanced metadata must contain one validated release row")
        version, count, files, scope, notice = rows[0]
        if (version != SCHEMA_VERSION or count <= 0 or files <= 0
                or scope not in ("pilot", "production") or (scope == "production" and count != 1_500_000_000)
                or "synthetic" not in notice.lower() or (expected_records is not None and count != expected_records)):
            raise ValueError("Incompatible advanced artifact metadata")
        state_counts = con.execute('SELECT "State", SUM(people) FROM person_counts GROUP BY 1 ORDER BY 1').fetchall()
        if sum(n for _, n in state_counts) != count or (scope == "production" and len(state_counts) != 36):
            raise ValueError("Advanced artifact does not reconcile to its declared scope")
        income_state = None
        for name, (dims, metrics) in GRAINS.items():
            schema = con.execute(f"DESCRIBE {name}").fetchall()
            expected_types = ["VARCHAR" if dim != "household_size" else "INTEGER" for dim in dims] + [
                "HUGEINT" if metric.endswith("income_sum") or metric == "income_sum" else "BIGINT" for metric in metrics]
            if [(row[0], row[1]) for row in schema] != list(zip((*dims, *metrics), expected_types)):
                raise ValueError(f"Incompatible columns in {name}")
            amount = "members" if name == "household_sizes" else "people"
            counts = con.execute(f'SELECT "State", SUM({amount}) FROM {name} GROUP BY 1 ORDER BY 1').fetchall()
            if counts != state_counts:
                raise ValueError(f"Non-reconciling state counts in {name}")
            fields = ", ".join('"' + dim + '"' for dim in dims)
            if con.execute(f"SELECT EXISTS (SELECT 1 FROM {name} GROUP BY {fields} HAVING COUNT(*) <> 1)").fetchone()[0]:
                raise ValueError(f"Duplicate aggregate grain in {name}")
            if metrics == EMPLOYMENT:
                invalid = "employed > status_known OR status_known > people OR eligible_15_plus > age_known OR age_known > people OR working_age_15_64 > eligible_15_plus OR eligible_15_plus_known_status > eligible_15_plus OR working_age_known_status > working_age_15_64 OR employed_15_plus > eligible_15_plus_known_status OR employed_working_age > working_age_known_status"
            elif metrics == INCOME:
                invalid = "income_zero > income_valid OR income_valid > people OR employed_people > people OR employed_income_valid > least(employed_people, income_valid) OR employed_income_sum > income_sum"
                expressions = ", ".join(f"SUM({metric})" for metric in INCOME)
                summary = con.execute(f'SELECT "State", {expressions} FROM {name} GROUP BY 1 ORDER BY 1').fetchall()
                if income_state is None:
                    income_state = summary
                elif summary != income_state:
                    raise ValueError(f"Income measures differ across rollups in {name}")
            elif metrics == HOUSEHOLD:
                invalid = "household_size < 1 OR members <> household_size * households"
            else:
                invalid = "false"
            negative = " OR ".join(f"{metric} IS NULL OR {metric} < 0" for metric in metrics)
            if con.execute(f"SELECT EXISTS (SELECT 1 FROM {name} WHERE {invalid} OR {negative})").fetchone()[0]:
                raise ValueError(f"Invalid measures or denominators in {name}")
        return {"schema_version": version, "records": count, "files": files, "scope": scope,
                "states": len(state_counts), "tables": tuple(GRAINS)}


def reconcile_baseline(path, baseline):
    """Require identical State/UT person and distinct-household coverage."""
    with connect(path) as advanced, connect(baseline) as base:
        reference = base.execute('SELECT "State", population, households FROM state_summary ORDER BY 1').fetchall()
        candidate = advanced.execute("""
            SELECT "State", SUM(members), SUM(households) FROM household_sizes GROUP BY 1 ORDER BY 1
        """).fetchall()
    if reference != candidate:
        raise ValueError("Advanced State/UT population or household counts differ from the baseline")


def load_advanced_table(path, table, state=None, expected_records=1_500_000_000, baseline=None):
    """Future dashboard entry point. Pilot artifacts cannot serve production views."""
    if table not in GRAINS:
        raise ValueError("Unknown advanced aggregate")
    meta = inspect_artifact(path, expected_records)
    if expected_records == 1_500_000_000:
        if meta["scope"] != "production" or baseline is None:
            raise ValueError("Production views require a production advanced artifact and baseline")
        reconcile_baseline(path, baseline)
    with connect(path) as con:
        where = ' WHERE "State" = ?' if state is not None else ""
        return con.execute(f"SELECT * FROM {table}" + where, [state] if state is not None else []).fetchdf()


def reconcile_production(path, baseline):
    """Validate additional independently built margins before production publication."""
    checks = [
        (name, '"State", education', "state_education_summary", '"State", education_level', "people", "population")
        for name in ("education_gender", "education_age", "education_settlement", "employment_education",
                     "income_education", "financial_education_gender")
    ]
    checks.extend([
        (name, '"State", settlement', "state_settlement_summary", '"State", settlement', amount, "population")
        for name, amount in (("education_settlement", "people"), ("employment_settlement", "people"),
                             ("income_bands_settlement", "people"), ("household_sizes", "members"))
    ])
    checks.extend([
        ("person_counts", '"State", age_cohort, "Gender"', "state_age_gender_summary", '"State", age_group, "Gender"', "people", "population"),
        ("occupation_gender", '"State", "Occupation"', "state_occupation_summary", '"State", "Occupation"', "people", "population"),
        ("income_occupation", '"State", "Occupation"', "state_occupation_summary", '"State", "Occupation"', "people", "population"),
        ("digital_age_gender", '"State", smartphone, internet', "state_digital_summary", '"State", smartphone_ownership, internet_access', "people", "population"),
        ("income_age", '"State", age_cohort', "state_age_gender_summary", '"State", age_group', "people", "population"),
        ("education_age", '"State", age_cohort', "state_age_gender_summary", '"State", age_group', "people", "population"),
        ("employment_age_gender", '"State", age_cohort, "Gender"', "state_age_gender_summary", '"State", age_group, "Gender"', "people", "population"),
    ])
    for name in ("financial_education_gender", "financial_employment"):
        checks.extend((name, f'"State", {dim}', f"state_{dim}_summary", f'"State", {dim}', "people", "population")
                      for dim in ("bank", "insurance"))
    with connect(path) as new, connect(baseline) as old:
        for table, dims, ref, ref_dims, measure, ref_measure in checks:
            actual = new.execute(f"SELECT {dims}, SUM({measure}) FROM {table} GROUP BY ALL ORDER BY ALL").fetchall()
            expected = old.execute(f"SELECT {ref_dims}, SUM({ref_measure}) FROM {ref} GROUP BY ALL ORDER BY ALL").fetchall()
            if actual != expected:
                raise ValueError(f"Production margin mismatch: {table} versus {ref} ({dims})")
        expected = old.execute("""
            SELECT "State", CASE WHEN main_activity IN ('Child', 'Student/Other')
                 THEN 'Not applicable' ELSE main_activity END AS status, SUM(population)
            FROM state_main_activity_summary GROUP BY ALL ORDER BY ALL
        """).fetchall()
        for table in ("employment_age_gender", "employment_settlement", "employment_education",
                      "occupation_gender", "financial_employment"):
            if new.execute(f"""
                SELECT "State", employment_status, SUM(people) FROM {table} GROUP BY ALL ORDER BY ALL
            """).fetchall() != expected:
                raise ValueError(f"Production employment status mismatch: {table}")
        actual_income = new.execute("""
            SELECT "State", SUM(people), SUM(income_valid), SUM(income_sum)
            FROM income_bands_state GROUP BY ALL ORDER BY ALL
        """).fetchall()
        expected_income = old.execute("""
            SELECT "State", SUM(population), SUM(income_n), SUM(income_sum)
            FROM _partial_income_summary GROUP BY ALL ORDER BY ALL
        """).fetchall()
        if actual_income != expected_income:
            raise ValueError("Production recorded-income counts or sums differ")
        band_ranges = {"Missing or invalid": (None, None), "Zero": (0, 1), "1-49,999": (1, 50_000),
                       "50,000-99,999": (50_000, 100_000), "100,000-249,999": (100_000, 250_000),
                       "250,000-499,999": (250_000, 500_000), "500,000-999,999": (500_000, 1_000_000),
                       "1,000,000+": (1_000_000, None)}
        bands = None
        for table in ("income_bands_state", "income_bands_gender", "income_bands_settlement"):
            totals = new.execute(f"""
                SELECT "State", income_band, SUM(people), SUM(income_valid), SUM(income_zero),
                       SUM(income_sum), SUM(employed_income_valid), SUM(employed_income_sum)
                FROM {table} GROUP BY ALL ORDER BY ALL
            """).fetchall()
            if bands is not None and totals != bands:
                raise ValueError(f"Production income-band margins differ in {table}")
            bands = totals
            for _, band, people, valid, zero, income, employed_count, employed_income in totals:
                low, high = band_ranges[band]
                if low is None:
                    if valid or zero or income or employed_count or employed_income:
                        raise ValueError("Invalid-income band contains valid values")
                elif (valid != people or zero != (valid if band == "Zero" else 0)
                      or any(total < low * count or (count and high is not None and total >= high * count)
                             for count, total in ((valid, income), (employed_count, employed_income)))):
                    raise ValueError(f"Income totals outside allowed band: {band}")
    return {"baseline_grouped_margins": len(checks), "baseline_employment_margins": 5,
            "baseline_income_totals": True, "income_band_tables": 3}
