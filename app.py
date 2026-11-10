import re
import streamlit as st
import duckdb
import pandas as pd
import plotly.express as px
import os
from pathlib import Path

# Set INDIA_DB_PATH when deploying or moving the project to another machine.
DEPLOYMENT_DB = Path(__file__).resolve().parent.parent / "database" / "india_population.duckdb"
DEFAULT_DB = Path(r"C:\India_Population_Dashboard\india_population_v34_pilot_retry.duckdb")
REPO_DB = Path(__file__).parent / "data" / "india_population_v34_pilot.duckdb"

# Production: set INDIA_DB_PATH explicitly. Local fallback supports the deployment folder.
if os.environ.get("INDIA_DB_PATH"):
    DB_PATH = Path(os.environ["INDIA_DB_PATH"]).expanduser()
elif DEPLOYMENT_DB.exists():
    DB_PATH = DEPLOYMENT_DB
elif DEFAULT_DB.exists():
    DB_PATH = DEFAULT_DB
else:
    DB_PATH = REPO_DB

st.set_page_config(
    page_title="India Population Intelligence",
    page_icon="🇮🇳",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ---------- Visual system ----------
st.markdown("""
<style>
:root { color-scheme: dark; }
.stApp { background: #090d12; color: #e7edf2; }
[data-testid="stSidebar"] { background: #10171d; border-right: 1px solid #26343b; }
.block-container { padding-top: 1.15rem; padding-bottom: 3rem; max-width: 1680px; }
.hero { padding: 30px 34px; border-radius: 20px; background: radial-gradient(circle at 85% 20%,rgba(34,211,187,.17),transparent 28%), linear-gradient(115deg,#17232a 0%,#111a20 58%,#17251f 100%); border: 1px solid #30433f; margin-bottom: 20px; box-shadow: 0 16px 48px rgba(0,0,0,.22); }
.hero-kicker { color:#5eead4; letter-spacing:2.3px; font-size:10px; font-weight:800; }
.hero-title { color:#f4f8f8; font-size:34px; font-weight:780; margin:7px 0 5px; letter-spacing:-.8px; }
.hero-sub { color:#aab9bd; font-size:14px; }
.section-label { color:#5eead4; font-size:10px; letter-spacing:1.8px; font-weight:800; margin: 6px 0 10px; }
h1,h2,h3 { letter-spacing:-.35px; }
div[data-testid="stMetric"] { background: linear-gradient(145deg,#172329,#111a20); border: 1px solid #2b3d42; padding: 17px 19px; border-radius: 15px; box-shadow: 0 8px 24px rgba(0,0,0,.13); }
div[data-testid="stMetricLabel"] { color:#9fb2b5; }
div[data-testid="stMetricValue"] { color:#f3f7f7; }
div[data-testid="stMetricDelta"] { color:#5eead4; }
div[data-testid="stDataFrame"] { border:1px solid #26383d; border-radius:12px; }
.stSelectbox label,.stMultiSelect label,.stRadio label { color:#b8c8c9 !important; }
[data-testid="stAlert"] { border-radius:12px; }
hr { border-color:#26363b; }
footer {visibility:hidden;}
</style>
""", unsafe_allow_html=True)

@st.cache_resource
def db():
    if not DB_PATH.exists():
        st.error(f"Database not found: {DB_PATH}. Set INDIA_DB_PATH to the location of the DuckDB analytics database.")
        st.stop()
    return duckdb.connect(str(DB_PATH), read_only=True)

con = db()

ALLOWED = {
    "national_summary", "state_summary", "city_summary", "age_summary",
    "gender_summary", "settlement_summary", "education_summary",
    "occupation_summary", "digital_summary", "income_summary",
    "literacy_summary", "employment_type_summary", "main_activity_summary",
    "marital_summary", "religion_summary", "social_group_summary",
    "mother_tongue_summary", "bank_summary", "insurance_summary",
    "disability_summary", "wealth_summary", "age_gender_summary",
    "state_settlement_summary", "state_education_summary",
    "state_occupation_summary", "state_digital_summary",
    "state_age_summary", "state_age_gender_summary", "state_marital_summary",
    "state_literacy_summary", "state_employment_type_summary",
    "state_main_activity_summary", "state_religion_summary",
    "state_social_group_summary", "state_mother_tongue_summary",
    "state_bank_summary", "state_insurance_summary",
    "state_disability_summary", "state_wealth_summary"
}

# Normalize single-dimension summary columns for chart consistency.
# The incremental builder retains descriptive source column names (e.g. marital,
# literacy, Religion, wealth); the dashboard uses the common alias "category".
CATEGORY_SOURCE_COLUMNS = {
    "marital_summary": "marital", "state_marital_summary": "marital",
    "literacy_summary": "literacy", "state_literacy_summary": "literacy",
    "religion_summary": "Religion", "state_religion_summary": "Religion",
    "social_group_summary": "social_group", "state_social_group_summary": "social_group",
    "mother_tongue_summary": "mother_tongue", "state_mother_tongue_summary": "mother_tongue",
    "bank_summary": "bank", "state_bank_summary": "bank",
    "insurance_summary": "insurance", "state_insurance_summary": "insurance",
    "disability_summary": "disability", "state_disability_summary": "disability",
    "wealth_summary": "wealth", "state_wealth_summary": "wealth",
    "employment_type_summary": "employment_type", "state_employment_type_summary": "employment_type",
    "main_activity_summary": "main_activity", "state_main_activity_summary": "main_activity",
}

@st.cache_data(ttl=1800)
def table(name):
    if name not in ALLOWED:
        raise ValueError("Unknown summary table")
    df = con.execute(f'SELECT * FROM "{name}"').fetchdf()
    source_col = CATEGORY_SOURCE_COLUMNS.get(name)
    if source_col and "category" not in df.columns and source_col in df.columns:
        df["category"] = df[source_col]
    return df

@st.cache_data(ttl=1800)
def state_occupation_data(state):
    """Fetch only the selected state's occupation rows from DuckDB."""
    return con.execute(
        "SELECT State, Occupation, population, average_income "
        "FROM state_occupation_summary WHERE State = ?",
        [state]
    ).fetchdf()

def fmt(n):
    return f"{int(round(float(n))):,}"

def chart_theme(fig, height=390):
    fig.update_layout(
        template="plotly_dark", height=height,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(family="Inter, Segoe UI, sans-serif", color="#dce7e7", size=12),
        colorway=["#2dd4bf", "#f5b942", "#a78bfa", "#60a5fa", "#fb7185", "#a3e635"],
        margin=dict(l=12,r=12,t=48,b=12), legend_title_text=""
    )
    fig.update_xaxes(showgrid=False, zeroline=False)
    fig.update_yaxes(gridcolor="rgba(148,163,184,.13)", zeroline=False)
    fig.update_layout(title_font=dict(size=15, color="#edf5f4"))
    return fig

def show_chart(fig, height=390):
    st.plotly_chart(chart_theme(fig, height), use_container_width=True)

def locality_panel(state):
    """Show locality detail only when the source contains meaningful locality variation."""
    city_data = table("city_summary")
    city_data = city_data[city_data.State == state].copy()
    if not city_data.empty and city_data["City"].nunique(dropna=True) > 1:
        city_data = city_data.sort_values("population", ascending=False)
        st.markdown(f"#### Locality distribution · {state}")
        show_chart(px.bar(city_data.head(15).sort_values("population"),
                          x="population", y="City", orientation="h",
                          color="population", title=f"Synthetic locality distribution · {state}"), 480)
        st.dataframe(city_data, use_container_width=True, hide_index=True)
        return

    st.markdown(f"#### Geographic detail · {state}")
    with st.expander("Data coverage note · why city-level detail is unavailable", expanded=False):
        st.caption(
            "Verified real-city breakdowns are not available in this dataset. The City field is a "
            "synthetic state-level placeholder, not a list of real cities. The rural/urban "
            "chart is a separate generated dimension and should not be read as verified locality geography."
        )
    settlement = table("state_settlement_summary")
    settlement = settlement[settlement.State == state].copy()
    if not settlement.empty:
        show_chart(px.pie(settlement, names="settlement", values="population", hole=.62,
                          title=f"Rural / urban composition · {state}"), 360)
    st.caption("The rural / urban split is a separate generated dimension; it should not be interpreted as verified locality geography.")

def scoped(base_name, state_name=None):
    """Return national aggregate or state-specific aggregate according to the global selector."""
    if selected_state == "All India":
        return table(base_name)
    if not state_name:
        raise ValueError(f"No state-level summary configured for {base_name}")
    df = table(state_name)
    return df[df["State"] == selected_state].copy()

def compare_scoped(state_table, value_col="population", category_col=None):
    df = table(state_table)
    df = df[df["State"].isin(comparison_states)].copy()
    if category_col and category_col in df.columns:
        return df
    return df

def comparison_panel(title, df, value_col="population", category_col=None):
    if len(comparison_states) < 2:
        return
    st.markdown(f"#### {title} · selected-state comparison")
    d = compare_scoped(df, value_col, category_col) if isinstance(df, str) else df
    if d.empty:
        st.info("No comparison data available for this selection.")
        return
    if category_col and category_col in d.columns:
        fig = px.bar(d, x="State", y=value_col, color=category_col,
                     barmode="group", title=title)
    else:
        fig = px.bar(d, x="State", y=value_col, color="State", title=title)
    show_chart(fig, 360)

# Approximate state/UT centroid coordinates for a clickable analytical locator map.
# Markers represent state-level aggregates; they are not boundary polygons.
STATE_CENTROIDS = {
 "Andhra Pradesh":(15.9,79.7),"Arunachal Pradesh":(28.1,94.5),"Assam":(26.2,92.9),
 "Bihar":(25.9,85.6),"Chhattisgarh":(21.3,82.0),"Goa":(15.4,74.0),
 "Gujarat":(22.7,71.7),"Haryana":(29.0,76.1),"Himachal Pradesh":(31.8,77.2),
 "Jharkhand":(23.6,85.3),"Karnataka":(15.0,76.0),"Kerala":(10.5,76.3),
 "Madhya Pradesh":(23.5,78.5),"Maharashtra":(19.4,75.3),"Manipur":(24.7,93.9),
 "Meghalaya":(25.5,91.3),"Mizoram":(23.2,92.8),"Nagaland":(26.0,94.5),
 "Odisha":(20.5,84.4),"Punjab":(31.0,75.3),"Rajasthan":(26.8,73.8),
 "Sikkim":(27.5,88.5),"Tamil Nadu":(11.0,78.4),"Telangana":(17.9,79.0),
 "Tripura":(23.8,91.5),"Uttar Pradesh":(27.1,80.8),"Uttarakhand":(30.1,79.0),
 "West Bengal":(23.2,87.8),"Andaman and Nicobar Islands":(11.7,92.7),
 "Chandigarh":(30.7,76.8),"Dadra and Nagar Haveli and Daman and Diu":(20.2,72.9),
 "Delhi":(28.6,77.2),"Jammu and Kashmir":(33.7,76.0),"Ladakh":(34.2,77.6),
 "Lakshadweep":(10.0,72.6),"Puducherry":(11.9,79.8)
}

def _state_key(value):
    """Normalize state/UT labels so punctuation and common naming variants still match."""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

_STATE_CENTROID_KEYS = {_state_key(name): coords for name, coords in STATE_CENTROIDS.items()}
_STATE_CENTROID_KEYS.update({
    _state_key("Jammu & Kashmir"): STATE_CENTROIDS["Jammu and Kashmir"],
    _state_key("Jammu and Kashmir (UT)"): STATE_CENTROIDS["Jammu and Kashmir"],
    _state_key("J&K"): STATE_CENTROIDS["Jammu and Kashmir"],
    _state_key("Andaman & Nicobar Islands"): STATE_CENTROIDS["Andaman and Nicobar Islands"],
    _state_key("Andaman and Nicobar"): STATE_CENTROIDS["Andaman and Nicobar Islands"],
    _state_key("A&N Islands"): STATE_CENTROIDS["Andaman and Nicobar Islands"],
})

def state_locator_map(state_frame):
    m = state_frame.copy()
    # Normalize labels before lookup: source tables may use "&", "and", or UT suffixes.
    coords = m["State"].map(lambda name: _STATE_CENTROID_KEYS.get(_state_key(name)))
    def coord_part(value, index):
        if isinstance(value, (tuple, list)) and len(value) > index:
            return value[index]
        return None
    m["lat"] = coords.map(lambda value: coord_part(value, 0))
    m["lon"] = coords.map(lambda value: coord_part(value, 1))
    m = m.dropna(subset=["lat", "lon"])
    fig = px.scatter_geo(m, lat="lat", lon="lon", size="population", color="population",
        hover_name="State", custom_data=["State", "population", "households"],
        color_continuous_scale=[[0,"#164e4a"],[.45,"#2dd4bf"],[1,"#f5b942"]],
        size_max=34, title="India state locator · select a marker to focus")
    fig.update_geos(scope="asia", projection_type="mercator", center={"lat":22,"lon":82},
        lataxis_range=[5,38], lonaxis_range=[66,99], showland=True, landcolor="#172329",
        showcountries=True, countrycolor="#526267", showocean=True, oceancolor="#0b1217",
        showcoastlines=True, coastlinecolor="#526267", showframe=False, bgcolor="rgba(0,0,0,0)")
    fig.update_traces(marker=dict(line=dict(width=1,color="#d6e5e2"), opacity=.9, sizemin=8),
        hovertemplate="<b>%{hovertext}</b><br>Population: %{customdata[1]:,.0f}<br>Households: %{customdata[2]:,.0f}<extra></extra>")
    return fig

# ---------- Base summaries ----------
national = table("national_summary").iloc[0]
states = table("state_summary").sort_values("population", ascending=False)
state_options = ["All India"] + states["State"].tolist()

# Apply map selections on the next rerun, before the sidebar selectbox is created.
# Streamlit does not allow changing a widget's keyed session state after instantiation.
pending_state = st.session_state.pop("pending_map_state", None)
if pending_state in state_options:
    st.session_state["global_state"] = pending_state

# ---------- Sidebar controls ----------
st.sidebar.markdown("## 🇮🇳 India PI")
st.sidebar.caption("POPULATION INTELLIGENCE PLATFORM")
page = st.sidebar.radio(
    "WORKSPACE",
    ["Executive Overview","Geography","Demographics","Education",
     "Employment & Income","Social Composition","Digital & Financial",
     "Households & Wellbeing"]
)
st.sidebar.divider()
if st.sidebar.button("↺ Reset geographic filters", use_container_width=True):
    st.session_state["global_state"] = "All India"
    st.session_state["comparison_states"] = []
    st.rerun()
selected_state = st.sidebar.selectbox("Geographic focus · main KPIs", state_options, key="global_state")
comparison_states = st.sidebar.multiselect(
    "Compare states · side-by-side (optional)",
    options=states["State"].tolist(),
    default=[],
    key="comparison_states",
    help="Choose two or more states. Their side-by-side comparison appears separately; this does not change the main Geographic focus KPIs."
)
if selected_state != "All India" and selected_state in comparison_states:
    st.sidebar.caption("The selected focus state is also in the comparison set.")
st.sidebar.divider()
st.sidebar.caption("DATASET PROFILE")
st.sidebar.markdown(f"**{fmt(national.total_population)}** records")
st.sidebar.markdown("29 attributes · 36 States/UTs")
st.sidebar.caption("Synthetic scenario data — not official statistics.")

# ---------- Header ----------
st.markdown("""
<div class="hero">
  <div class="hero-kicker">INDIA • SYNTHETIC POPULATION DATASET</div>
  <div class="hero-title">Population Intelligence</div>
  <div class="hero-sub">A multidimensional view of synthetic people, households, geography and socio-economic indicators.</div>
</div>
""", unsafe_allow_html=True)
st.warning("All figures are generated synthetic data for analytical demonstration. They are not official population estimates and do not describe real individuals.")
if selected_state != "All India":
    st.info(f"Main geographic focus: **{selected_state}**. Main KPIs and state-detail visuals follow this selection; the separate comparison section follows Compare states.")
if len(comparison_states) >= 2:
    st.caption("Multi-state comparison is enabled for: " + " · ".join(comparison_states))
    st.markdown("### State comparison · selected states")
    st.caption(
        "The Geographic focus selector controls the main KPIs and state detail. "
        "This comparison section uses only the states selected in Compare states."
    )
    comparison_overview = states[states["State"].isin(comparison_states)].copy()
    metric_cols = [c for c in ["population", "average_age", "households", "population_share_pct"]
                   if c in comparison_overview.columns]
    if not comparison_overview.empty and metric_cols:
        comparison_overview = comparison_overview[["State"] + metric_cols].sort_values(
            "population", ascending=False
        )
        st.dataframe(
            comparison_overview,
            use_container_width=True,
            hide_index=True,
            column_config={
                "population": st.column_config.NumberColumn("Population", format="%d"),
                "average_age": st.column_config.NumberColumn("Average age", format="%.2f"),
                "households": st.column_config.NumberColumn("Households", format="%d"),
                "population_share_pct": st.column_config.NumberColumn("Share of dataset", format="%.2f%%"),
            },
        )
        if "population" in comparison_overview.columns:
            comparison_fig = px.bar(
                comparison_overview.sort_values("population"),
                x="population", y="State", orientation="h", color="State",
                title="Population across selected states",
                text="population",
            )
            comparison_fig.update_traces(texttemplate="%{text:,.0f}", textposition="outside")
            show_chart(comparison_fig, 360)

# ---------- Executive overview ----------
if page == "Executive Overview":
    st.markdown('<div class="section-label">01 / POPULATION SNAPSHOT</div>', unsafe_allow_html=True)
    if selected_state == "All India":
        pop = int(national["total_population"])
        avg_age = float(national["average_age"])
        med_age = float(national["median_age"])
        households = int(national["distinct_households"])
    else:
        r = states[states.State == selected_state].iloc[0]
        pop, avg_age, households = int(r.population), float(r.average_age), int(r.households)
        age_stats = table("state_age_summary")
        age_stats = age_stats[age_stats.State == selected_state].iloc[0]
        med_age = float(age_stats.median_age)
        avg_age = float(age_stats.average_age)
    k = st.columns(4)
    k[0].metric("Population", fmt(pop))
    k[1].metric("Average age", f"{avg_age:.1f} years")
    k[2].metric("Median age", f"{med_age:.0f} years")
    k[3].metric("Households", fmt(households))

    state_view = states if selected_state == "All India" else states[states.State == selected_state]
    if selected_state == "All India":
        st.markdown("### Geographic footprint")
        map_col, rank_col = st.columns([1.35,1])
        with map_col:
            st.markdown("#### Explore India")
            try:
                map_event = st.plotly_chart(chart_theme(state_locator_map(state_view), 520),
                    use_container_width=True, key="india_locator_map", on_select="rerun", selection_mode="points")
                picked = map_event.selection.points
                if picked:
                    chosen = picked[0].get("customdata", [None])[0]
                    if chosen in state_options and chosen != st.session_state.get("global_state"):
                        st.session_state["pending_map_state"] = chosen
                        st.rerun()
            except TypeError:
                show_chart(state_locator_map(state_view), 520)
                st.caption("Your Streamlit version does not support click-to-filter on charts. Use Geographic focus in the sidebar.")
            st.caption("State markers are approximate centroids, sized by synthetic population; this is a locator view, not an administrative boundary map.")
        with rank_col:
            d = state_view.head(12).sort_values("population")
            show_chart(px.bar(d, x="population", y="State", orientation="h",
                              color="population", color_continuous_scale=[[0,"#164e4a"],[1,"#2dd4bf"]],
                              title="Largest 12 States / UTs"), 520)
        show_chart(px.treemap(state_view, path=["State"], values="population",
                              color="population", color_continuous_scale="Teal",
                              title="Population share by State / UT"), 330)
    else:
        locality_panel(selected_state)

    gender = scoped("gender_summary", None) if selected_state == "All India" else None
    settlement = scoped("settlement_summary", "state_settlement_summary") if selected_state == "All India" else scoped("settlement_summary", "state_settlement_summary")
    ages = table("age_summary")
    if selected_state != "All India":
        # The state-level age/gender table provides age cohorts for the selected state.
        ag = scoped("age_gender_summary", "state_age_gender_summary")
        age_only = ag.groupby("age_group", as_index=False).population.sum()
        g = ag.groupby("Gender", as_index=False).population.sum()
        sett = settlement.groupby("settlement", as_index=False).population.sum()
    else:
        ag = table("age_gender_summary")
        age_only = ages
        g = table("gender_summary")
        sett = table("settlement_summary")
    st.markdown("### Population structure")
    a,b,c = st.columns(3)
    with a:
        show_chart(px.pie(g, names="Gender", values="population", hole=.62, title="Gender composition"), 330)
    with b:
        show_chart(px.pie(sett, names="settlement", values="population", hole=.62, title="Rural / urban composition"), 330)
    with c:
        show_chart(px.bar(age_only, x="age_group", y="population", color="age_group", title="Age cohorts"), 330)
    st.markdown("### State comparison")
    show = state_view.copy()
    total_for_share = int(national["total_population"])
    show["population_share_pct"] = show.population / total_for_share * 100
    st.dataframe(show, use_container_width=True, hide_index=True)
    if len(comparison_states) >= 2:
        comp = states[states.State.isin(comparison_states)]
        st.markdown("### Selected-state comparison")
        show_chart(px.bar(comp, x="State", y="population", color="State", title="Population comparison"), 360)

# ---------- Geography ----------
elif page == "Geography":
    st.markdown("### Geographic intelligence")
    if selected_state == "All India":
        state_view = states
        l,r = st.columns([1.1,1])
        with l:
            show_chart(px.bar(state_view.head(20).sort_values("population"),
                              x="population", y="State", orientation="h",
                              color="population", title="Top 20 States / UTs"), 650)
        with r:
            ss = table("state_settlement_summary")
            if len(comparison_states) >= 2:
                ss = ss[ss.State.isin(comparison_states)]
            show_chart(px.bar(ss, x="State", y="population", color="settlement",
                              barmode="stack", title="Rural / urban mix by State"), 650)
        st.dataframe(state_view, use_container_width=True, hide_index=True)
    else:
        row = states[states.State == selected_state].iloc[0]
        st.metric(f"{selected_state} population", fmt(row.population))
        locality_panel(selected_state)
    if len(comparison_states) >= 2:
        comp = states[states.State.isin(comparison_states)]
        st.markdown("#### Selected-state comparison")
        show_chart(px.bar(comp, x="State", y="population", color="State", title="Population by selected state"), 360)

# ---------- Demographics ----------
elif page == "Demographics":
    st.markdown("### Demographic structure")
    ag = scoped("age_gender_summary", "state_age_gender_summary")
    marital = scoped("marital_summary", "state_marital_summary")
    l,r = st.columns(2)
    with l:
        show_chart(px.bar(ag, x="age_group", y="population", color="Gender",
                          barmode="group", title="Age profile by gender"), 430)
    with r:
        show_chart(px.pie(marital, names="category", values="population", hole=.55,
                          title="Marital status"), 430)
    st.markdown("### Age cohort detail")
    st.dataframe(ag, use_container_width=True, hide_index=True)
    if len(comparison_states) >= 2:
        comp = table("state_age_gender_summary")
        comp = comp[comp.State.isin(comparison_states)]
        st.markdown("#### Age and gender comparison across selected states")
        show_chart(px.bar(comp, x="age_group", y="population", color="State",
                          barmode="group", facet_col="Gender", title="Age cohorts by state and gender"), 440)

# ---------- Education ----------
elif page == "Education":
    st.markdown("### Education & literacy")
    education = scoped("education_summary", "state_education_summary")
    literacy = scoped("literacy_summary", "state_literacy_summary")
    l,r = st.columns(2)
    with l:
        show_chart(px.bar(education.sort_values("population"), x="population",
                          y="education_level", orientation="h", color="population",
                          title="Education attainment"), 460)
    with r:
        show_chart(px.pie(literacy, names="category", values="population", hole=.55,
                          title="Literacy status"), 460)
    st.markdown("### Education breakdown")
    st.dataframe(education, use_container_width=True, hide_index=True)
    if len(comparison_states) >= 2:
        comp = table("state_education_summary")
        comp = comp[comp.State.isin(comparison_states)]
        st.markdown("#### Education comparison across selected states")
        show_chart(px.bar(comp, x="education_level", y="population", color="State",
                          barmode="group", title="Education attainment by state"), 440)

# ---------- Employment ----------
elif page == "Employment & Income":
    st.markdown("### Employment and income")
    if selected_state == "All India":
        occupation = table("occupation_summary")
        employment = table("employment_type_summary")
        activity = table("main_activity_summary")
        income = table("income_summary")
    else:
        occupation = state_occupation_data(selected_state)
        employment = scoped("employment_type_summary", "state_employment_type_summary")
        activity = scoped("main_activity_summary", "state_main_activity_summary")
        income = table("income_summary")
        income = income[income.State == selected_state]
    # "Not applicable" represents people without an assigned occupation;
    # exclude it from this chart so actual occupation categories remain readable.
    occupation_chart = occupation[
        occupation["Occupation"].astype(str).str.strip().str.casefold() != "not applicable"
    ].copy()

    l,r = st.columns(2)
    with l:
        ycol = "Occupation"
        if occupation_chart.empty:
            st.info(f"No applicable occupation categories found for {selected_state}.")
        else:
            show_chart(px.bar(occupation_chart.sort_values("population"), x="population", y=ycol,
                              orientation="h", color="population",
                              title=f"Occupation distribution — {selected_state} (excluding Not applicable)"), 480)
    with r:
        show_chart(px.pie(employment, names="category", values="population", hole=.55,
                          title="Employment type"), 420)
    l,r = st.columns(2)
    with l:
        show_chart(px.bar(activity, x="population", y="category", orientation="h",
                          color="population", title="Main activity"), 420)
    with r:
        inc = income.sort_values("average_income", ascending=False)
        show_chart(px.bar(inc, x="State" if selected_state == "All India" else "average_income",
                          y="average_income" if selected_state == "All India" else "State",
                          orientation="v" if selected_state == "All India" else "h",
                          color="average_income", title="Average annual income"), 420)
    st.dataframe(income, use_container_width=True, hide_index=True)
    if len(comparison_states) >= 2:
        comp = table("state_occupation_summary")
        comp = comp[comp.State.isin(comparison_states)]
        st.markdown("#### Occupation comparison across selected states")
        show_chart(px.bar(comp, x="State", y="population", color="Occupation",
                          barmode="stack", title="Occupation mix by selected state"), 440)

# ---------- Social composition ----------
elif page == "Social Composition":
    st.markdown("### Social and language composition")
    rel = scoped("religion_summary", "state_religion_summary")
    sg = scoped("social_group_summary", "state_social_group_summary")
    mt = scoped("mother_tongue_summary", "state_mother_tongue_summary")
    a,b,c = st.columns(3)
    for col,df,title in [(a,rel,"Religion"),(b,sg,"Social group"),(c,mt,"Mother tongue")]:
        with col:
            show_chart(px.pie(df, names="category", values="population", hole=.5, title=title), 390)
    st.caption("These are synthetic attributes generated from model assumptions; do not interpret them as measured social composition.")
    if len(comparison_states) >= 2:
        comp = table("state_religion_summary")
        comp = comp[comp.State.isin(comparison_states)]
        st.markdown("#### Religion-category comparison across selected states")
        show_chart(px.bar(comp, x="State", y="population", color="category",
                          barmode="group", title="Synthetic religion categories by state"), 440)

# ---------- Digital and financial ----------
elif page == "Digital & Financial":
    st.markdown("### Digital and financial inclusion")
    bank = scoped("bank_summary", "state_bank_summary")
    insurance = scoped("insurance_summary", "state_insurance_summary")
    disability = scoped("disability_summary", "state_disability_summary")
    if selected_state == "All India":
        digital = table("digital_summary")
    else:
        digital = table("state_digital_summary")
        digital = digital[digital.State == selected_state]
        digital = digital.groupby(["smartphone_ownership","internet_access"], as_index=False).population.sum()
    a,b,c = st.columns(3)
    for col,df,title in [(a,bank,"Bank account status"),(b,insurance,"Health insurance"),(c,disability,"Disability status")]:
        with col:
            show_chart(px.pie(df, names="category", values="population", hole=.5, title=title), 370)
    l,r = st.columns(2)
    with l:
        sm = digital.groupby("smartphone_ownership", as_index=False).population.sum()
        show_chart(px.pie(sm, names="smartphone_ownership", values="population",
                          hole=.55, title="Smartphone ownership"), 400)
    with r:
        internet = digital.groupby("internet_access", as_index=False).population.sum()
        show_chart(px.pie(internet, names="internet_access", values="population",
                          hole=.55, title="Internet access"), 400)
    if len(comparison_states) >= 2:
        comp = table("state_digital_summary")
        comp = comp[comp.State.isin(comparison_states)]
        comp = comp.groupby(["State","smartphone_ownership"], as_index=False).population.sum()
        st.markdown("#### Smartphone ownership comparison")
        show_chart(px.bar(comp, x="State", y="population", color="smartphone_ownership",
                          barmode="group", title="Smartphone ownership by selected state"), 420)

# ---------- Households ----------
elif page == "Households & Wellbeing":
    st.markdown("### Household profile and wellbeing")
    if selected_state == "All India":
        wealth = table("wealth_summary")
        household_view = states[["State","households","population"]].sort_values("households", ascending=False)
    else:
        wealth = scoped("wealth_summary", "state_wealth_summary")
        household_view = states.loc[states.State == selected_state, ["State","households","population"]]
    show_chart(px.bar(wealth, x="category", y="households", color="households",
                      title="Households by synthetic wealth quintile"), 420)
    st.caption("Wealth quintiles are synthetic labels from the generator, not survey-derived wealth estimates.")
    st.markdown("### Household counts by State / UT")
    st.dataframe(household_view, use_container_width=True, hide_index=True)
    if len(comparison_states) >= 2:
        comp = states[states.State.isin(comparison_states)]
        st.markdown("#### Household comparison across selected states")
        show_chart(px.bar(comp, x="State", y="households", color="State",
                          title="Households by selected state"), 360)

st.divider()
with st.expander("About this dataset · methodology & limitations"):
    st.markdown("""
    **Build:** v3.4 synthetic dataset · 1.5 billion generated records · 29 attributes.

    **Calibration inputs:** selected geography and demographic dimensions use Census 2011 aggregates where available; employment participation uses the configured PLFS 2025 reference. These inputs do not make the generated records official statistics.

    **Synthetic assumptions / limitations:** income, education, occupation/industry mix, household composition, wealth, digital access, insurance and disability are generated assumptions. Mother tongue is a placeholder in this build. City/locality labels are synthetic, not verified real cities. Social-group residuals must not be interpreted as OBC.

    **Interpretation:** all dashboard values describe this generated synthetic dataset only. They are not estimates of India's actual population and must not be used for policy, eligibility, financial or individual-level decisions.
    """)
st.caption(f"India Population Intelligence • Synthetic dataset v3.4 • {fmt(national.total_population)} records • 29 attributes")


# v3.4 data-quality notes:
# City is a synthetic state-level locality label, not a real city.
# Mother Tongue is a placeholder ("Not calibrated in this build").
# Income, education, occupation, wealth, digital, insurance and disability
# are synthetic assumptions and must not be presented as official estimates.
