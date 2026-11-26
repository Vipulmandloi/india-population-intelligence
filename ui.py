"""Shared Streamlit layout, chart styles, and geographic interaction."""

import json
from pathlib import Path
import re
import unicodedata

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from analytics import describe, display

ASSETS = Path(__file__).resolve().parent / "assets"
PALETTE = ["#50DCC7", "#78A8FF", "#F3C879", "#B8A2FC", "#F59B9D", "#8DBCE0"]
AGE_ORDER = ["0-17", "18-25", "26-35", "36-50", "51-65", "66+"]

def styles():
    st.markdown("""
    <style>
    .block-container { padding-top: 2.4rem; max-width: 1460px; }
    div[data-testid="stMetricValue"] > div { font-size: clamp(1.15rem, 1.65vw, 1.65rem); }
    div[data-testid="stMetricLabel"] { color: #B7C8DE; }
    @media (max-width: 1100px) {
        div[class*="st-key-kpi_"] [data-testid="stHorizontalBlock"] {
            display: grid; grid-template-columns: repeat(2, minmax(0, 1fr));
        }
        div[class*="st-key-kpi_"] [data-testid="stColumn"] { width: auto !important; min-width: 0 !important; }
        div[data-testid="stMetricValue"] > div { white-space: normal; overflow-wrap: anywhere; }
    }
    :is(button, a, input, [tabindex]):focus-visible { outline: 2px solid #49DCC5; outline-offset: 2px; }
    h1 { letter-spacing: -.032em; }
    h2, h3 { letter-spacing: -.018em; }
    </style>
    """, unsafe_allow_html=True)

def chart(fig, height=350, **kwargs):
    fig.update_layout(
        template="plotly_dark", height=height, colorway=PALETTE,
        font=dict(color="#C7D7EA", size=12),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=13, t=34 if fig.layout.title.text else 12, b=15),
        legend=dict(orientation="h", y=-.18, title_text=""),
        hoverlabel=dict(bgcolor="#18263C", font_color="#EDF4FF"),
    )
    fig.update_xaxes(gridcolor="#233249", automargin=True, zerolinecolor="#344760")
    fig.update_yaxes(gridcolor="#233249", automargin=True, zerolinecolor="#344760")
    return st.plotly_chart(fig, config={"displaylogo": False}, **kwargs)

def kpis(items):
    key = "kpi_" + re.sub(r"[^a-z0-9]+", "_", items[0][0].lower())
    with st.container(key=key):
        for col, (label, value, help_text) in zip(st.columns(len(items)), items):
            col.metric(label, value, help=help_text, border=True)

def bars(frame, category, value="population", title=None, unit="people", height=330, benchmark=None):
    if frame.empty:
        st.info("No aggregate rows for this selection.")
        return
    ordered = frame.sort_values(value, ascending=True)
    x = ordered[value]
    fig = go.Figure(go.Bar(
        x=x.tolist(), y=ordered[category].astype(str).tolist(), orientation="h",
        marker_color=PALETTE[0], customdata=[display(v, unit) for v in x],
        hovertemplate="%{y}<br>%{customdata}<extra></extra>",
    ))
    fig.update_layout(title_text=title or "", xaxis_title=unit)
    if benchmark is not None:
        fig.add_vline(x=benchmark, line_dash="dash", line_color="#F3C879",
                      annotation_text="All India", annotation_position="top left")
    chart(fig, height)

def insight_panel(frame, dim, value="population", unit="people", benchmark=None):
    notes = describe(frame, dim, value, unit, benchmark)
    if notes:
        with st.container(border=True):
            st.markdown("**What this view shows**")
            for note in notes:
                st.write(note)

def normalize(label):
    ascii_name = unicodedata.normalize("NFKD", label).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]", "", ascii_name.lower().replace("&", " and "))

def plotly_geometry(geometry):
    """D3 geographic paths use clockwise exteriors for polygons under a hemisphere."""
    polygons = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    oriented = []
    for polygon in polygons:
        rings = []
        for index, ring in enumerate(polygon):
            area = sum(a[0] * b[1] - b[0] * a[1] for a, b in zip(ring, ring[1:]))
            rings.append(list(reversed(ring)) if (area > 0) == (index == 0) else ring)
        oriented.append(rings)
    coordinates = oriented[0] if geometry["type"] == "Polygon" else oriented
    return {"type": geometry["type"], "coordinates": coordinates}


@st.cache_data(show_spinner=False)
def boundary_data():
    geometry = json.loads((ASSETS / "india-states.geojson").read_text(encoding="utf-8-sig"))
    for feature in geometry["features"]:
        feature["geometry"] = plotly_geometry(feature["geometry"])
    return geometry, json.loads((ASSETS / "state-centroids.json").read_text())


def map_figure(frame, unit, focus, comparisons):
    geometry, centroids = boundary_data()
    names = {normalize(name): name for name in frame.State}
    features = []
    for feature in geometry["features"]:
        name = names.get(normalize(feature["properties"]["shapeName"]))
        if name:
            features.append({"type": "Feature", "id": name, "properties": {}, "geometry": feature["geometry"]})
    by_name = {normalize(name): point for name, point in centroids.items()}
    points = frame.loc[frame.State.map(lambda name: normalize(name) in by_name)]
    coords = [by_name[normalize(name)] for name in points.State]
    mapped = frame.loc[frame.State.isin([feature["id"] for feature in features])].dropna()
    fig = go.Figure(go.Choropleth(
        geojson={"type": "FeatureCollection", "features": features},
        locations=mapped.State.tolist(), z=mapped.Value.tolist(),
        colorscale=[[0, "#234362"], [.5, "#2C8EAA"], [1, "#6DE1C3"]],
        marker_line_color=["#FFD67F" if s == focus else "#8AB7FF" if s in comparisons else "#A4BDD3" for s in mapped.State],
        marker_line_width=[1.7 if s == focus or s in comparisons else .6 for s in mapped.State],
        colorbar=dict(title=unit, thickness=9, len=.56, orientation="h", y=-.08, x=.5),
        customdata=[display(v, unit) for v in mapped.Value],
        hovertemplate="%{location}<br>%{customdata}<extra></extra>",
    ))
    fig.add_trace(go.Scattergeo(
        lat=[point[0] for point in coords], lon=[point[1] for point in coords],
        customdata=[[name, display(value, unit)] for name, value in points.itertuples(index=False, name=None)],
        mode="markers", marker=dict(
            size=[13 if name == focus else 11 if name in comparisons else 7 for name in points.State],
            color=["#FFE39D" if name == focus else "#82AFFF" if name in comparisons else "#E7F4FA" for name in points.State],
            line=dict(width=1, color="#143049"),
        ),
        hovertemplate="%{customdata[0]}<br>%{customdata[1]}<extra></extra>",
        showlegend=False,
    ))
    fig.update_geos(
        projection_type="mercator", center=dict(lat=22.3, lon=82.5),
        lataxis_range=[6, 37], lonaxis_range=[67, 98],
        visible=False, bgcolor="rgba(0,0,0,0)",
    )
    return fig, len(features)

def state_map(scope, frame, unit, key):
    try:
        fig, coverage = map_figure(frame, unit, scope.focus, scope.comparison)
    except (OSError, ValueError):
        st.info("Boundary geometry is unavailable. Use the geographic filter or state rankings.")
        return
    if not coverage:
        st.info("No State/UT boundaries match this dataset.")
        return
    key = f"{key}_{st.session_state.get('map_revision', 0)}"
    event = chart(fig, 460, key=key, on_select="rerun", selection_mode="points")
    st.caption(f"{coverage}/{len(frame)} geometries matched. Select a marker to focus. Gold marks focus and blue marks comparisons. Simplified community boundaries from DataMeet via geoBoundaries (CC BY 2.5 India).")
    points = event.selection.points
    if points:
        point = points[0]
        custom = point.get("customdata")
        selected = custom[0] if isinstance(custom, list) else point.get("location")
        # A selection survives reruns. Consume it once so filter changes remain independent.
        if [selected, key] != st.session_state.get("last_map_event"):
            st.session_state.last_map_event = [selected, key]
            if selected in set(frame.State) and selected != scope.focus:
                st.session_state.pending_focus = selected
                st.rerun()
    elif st.session_state.get("last_map_event", [None, None])[1] == key:
        st.session_state.pop("last_map_event", None)

def grouped(frame, category, color, value="population", height=350):
    if frame.empty:
        st.info("No aggregate rows for this selection.")
        return
    order = {"age_group": AGE_ORDER}
    chart(px.bar(frame, x=category, y=value, color=color, barmode="group",
                 category_orders=order, color_discrete_sequence=PALETTE,
                 labels={"population": "Synthetic people", "age_group": "Age cohort", "Value": "Value"}), height)
