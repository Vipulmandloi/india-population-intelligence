"""India Population Intelligence canonical Streamlit entry point."""

import streamlit as st
from analytics import Scope, dataset_for, table
from dashboard_data import DashboardDataError, dataset_config
from ui import styles
import workspaces
from intelligence import compare_states, state_profile
from advanced_analytics import configured_release
from advanced_views import advanced_panel, advanced_methodology

PAGES = {
    "Executive Overview": (workspaces.executive, "Population scale, geography and headline indicators."),
    "Geographic Intelligence": (workspaces.geography, "Map metrics and compare State/UTs against national benchmarks."),
    "Demographic Intelligence": (workspaces.demographics, "Age structure, gender composition and demographic indicators."),
    "Education Intelligence": (workspaces.education, "Compare generated attainment and literacy."),
    "Employment & Economy": (workspaces.employment, "Explore generated employment, occupations and per-person income."),
    "Social Composition": (workspaces.social, "Explore generated religion and social group composition and language coverage."),
    "Digital & Financial": (workspaces.digital, "Compare digital access, banking and insurance coverage."),
    "Households & Wellbeing": (workspaces.households, "Compare households, disability and person-level wealth labels."),
    "State Intelligence": (state_profile, "Review a State/UT profile, national benchmarks and descriptive highlights."),
    "State Comparison": (compare_states, "Compare up to five State/UTs with unit-aware national benchmarks."),
    "Population Explorer": (workspaces.explorer, "Build, sort and export views from supported aggregate grains."),
    "Data Quality & Methodology": (workspaces.methodology, "Review provenance, metric definitions and coverage."),
}

ADVANCED_VIEWS = {
    "Education Intelligence": ("Education",),
    "Employment & Economy": ("Employment", "Income"),
    "Digital & Financial": ("Inclusion",),
    "Households & Wellbeing": ("Households",),
    "Population Explorer": ("Multidimensional Explorer",),
}


def reset_geography():
    st.session_state.global_state = "All India"
    st.session_state.comparison_states = []
    st.session_state.pop("pending_focus", None)
    st.session_state.pop("last_map_event", None)
    st.session_state.map_revision = st.session_state.get("map_revision", 0) + 1

def main():
    st.set_page_config(page_title="India Population Intelligence", page_icon=":material/monitoring:",
                       layout="wide", initial_sidebar_state="auto")
    styles()
    try:
        with st.spinner("Validating the analytics database..."):
            dataset = dataset_for(*dataset_config())
    except DashboardDataError as error:
        st.error(str(error))
        st.stop()

    advanced, advanced_status = configured_release(dataset)
    states = table(dataset, "state_summary").sort_values("population", ascending=False)
    options = ["All India", *sorted(states.State)]
    pending = st.session_state.pop("pending_focus", None)
    if pending in options:
        st.session_state.global_state = pending
    if st.session_state.get("global_state") not in options:
        st.session_state.global_state = "All India"
    previous = st.session_state.get("comparison_states", [])
    valid_previous = [name for name in previous if name in options[1:]]
    if valid_previous != previous:
        st.session_state.comparison_states = valid_previous

    # Keep workspace settings when Streamlit removes widgets from an inactive page.
    retained = ("explorer_", "geo_metric", "home_rank", "employment_rank", "digital_rank", "household_rank", "compare_", "profile_topic", "advanced_")
    for key in list(st.session_state):
        if key.startswith(retained) and not key.endswith(('_export', '_plot')):
            st.session_state[key] = st.session_state[key]

    with st.sidebar:
        st.markdown("## India Population Intelligence")
        st.caption(f"{dataset.records:,} synthetic records | {dataset.version} | {dataset.mode.title()}")
        st.caption(f"Advanced analytics ready | P4B schema v{advanced.version}" if advanced else advanced_status)
        page = st.radio("Workspace", list(PAGES), key="workspace")
        st.divider()
        focus = st.selectbox("Geographic focus", options, key="global_state")
        compare = st.multiselect("Compare State/UTs", options[1:], max_selections=5, key="comparison_states")
        st.button("Reset geography", on_click=reset_geography, width="stretch")
        st.caption("Focus applies to detail views. Rankings retain national coverage. Comparison is independent.")

    view, description = PAGES[page]
    st.title(page)
    st.caption(description)
    st.warning("Synthetic scenario data: generated records, not official Indian statistics.", icon=":material/info:")
    st.caption(f"Focus: {focus} | Comparison: {', '.join(compare) if compare else 'None'}")
    scope = Scope(dataset, "" if focus == "All India" else focus, compare, states, advanced)
    if advanced and page in ADVANCED_VIEWS:
        selected = st.radio("Analysis view", ["Overview", *ADVANCED_VIEWS[page]], horizontal=True,
                            key=f"advanced_view_{page}")
        if selected == "Overview":
            view(scope)
        else:
            advanced_panel(scope, selected.lower().replace(" ", "_"),
                           None if selected == "Multidimensional Explorer" else selected)
    else:
        view(scope)
        if page == "Data Quality & Methodology":
            advanced_methodology(advanced, advanced_status)
    st.divider()
    st.caption(f"India Population Intelligence | {dataset.version} | {dataset.records:,} synthetic records")

if __name__ == "__main__":
    main()
