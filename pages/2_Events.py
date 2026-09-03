"""
TravelSafe - Events
===================

Detailed breakdown and analysis of all safety-related events:
- Filterable event categories
- Severity analysis
- Interactive charts and tables
- Export functionality
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
from collections import Counter
from datetime import datetime

# Import shared components
from core.ui_components import (
    get_selected_city,
    get_selected_persona,
    render_footer,
    get_dark_chart_layout,
    get_event_color_map,
    get_event_icon_map,
)
from core.data_cache import get_city_data

# Import services for logging
try:
    from core.services.logger import log_info
except ImportError:
    def log_info(msg, module="events"): pass


def inject_page_styles():
    """Inject enhanced SaaS dashboard styles."""
    st.markdown("""
    <style>
    /* Section Headers */
    .section-header {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        margin: 2rem 0 1rem 0;
        padding-bottom: 0.75rem;
        border-bottom: 1px solid rgba(255,255,255,0.1);
    }
    .section-header h3 {
        margin: 0;
        color: #fff;
        font-size: 1.25rem;
        font-weight: 600;
    }
    .section-icon { font-size: 1.5rem; }
    
    /* Stat Cards */
    .stat-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.8) 0%, rgba(15,23,42,0.9) 100%);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 12px;
        padding: 1.25rem;
        text-align: center;
        transition: all 0.3s ease;
    }
    .stat-card:hover {
        border-color: rgba(139,92,246,0.5);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(139,92,246,0.15);
    }
    .stat-card .icon { font-size: 1.75rem; margin-bottom: 0.5rem; }
    .stat-card .label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-card .value { font-size: 1.75rem; font-weight: 700; color: #fff; margin: 0.25rem 0; }
    
    /* Chart Container */
    .chart-container {
        background: linear-gradient(135deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0.8) 100%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 1.25rem;
        margin-bottom: 1rem;
    }
    .chart-title {
        color: #e2e8f0;
        font-size: 1rem;
        font-weight: 600;
        margin-bottom: 1rem;
        display: flex;
        align-items: center;
        gap: 0.5rem;
    }
    
    /* Category Cards */
    .category-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.85) 100%);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 1rem;
        text-align: center;
        transition: all 0.2s ease;
    }
    .category-card:hover {
        border-color: rgba(255,255,255,0.2);
        transform: scale(1.02);
    }
    
    /* Data Footer */
    .data-footer {
        display: flex;
        justify-content: center;
        align-items: center;
        gap: 0.75rem;
        padding: 1rem;
        margin-top: 2rem;
        color: #64748b;
        font-size: 0.8rem;
        border-top: 1px solid rgba(255,255,255,0.08);
    }
    .data-footer .dot {
        width: 6px;
        height: 6px;
        background: #10b981;
        border-radius: 50%;
        animation: pulse 2s infinite;
    }
    @keyframes pulse {
        0%, 100% { opacity: 1; }
        50% { opacity: 0.5; }
    }
    </style>
    """, unsafe_allow_html=True)


def main():
    inject_page_styles()
    
    # Get current selections
    city = get_selected_city()
    persona = get_selected_persona()
    
    st.markdown("""
    <div style="text-align: center; padding: 1.5rem 0 1rem 0;">
        <h1 style="color: #fff; margin: 0; font-size: 2.25rem; font-weight: 700;">
            📊 Events
        </h1>
        <p style="color: #94a3b8; margin: 0.5rem 0 0 0; font-size: 1rem;">
            Detailed analysis and breakdown of all safety-related events
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # City badge
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <span style="background: linear-gradient(135deg, rgba(139,92,246,0.2), rgba(59,130,246,0.2)); 
                     border: 1px solid rgba(139,92,246,0.4); padding: 0.5rem 1.25rem; 
                     border-radius: 25px; color: #a78bfa; font-weight: 500;">
            📍 {city}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    cached_data = get_city_data(city, persona)
    events = cached_data.get("events", [])
    total_events_shared = cached_data.get("total_events", len(events))

    if not events:
        st.warning("No events loaded yet. Please load data from the Home Dashboard.")
        render_footer(module="news")
        return

    st.session_state["unified_events"] = events

    st.toast(f"📊 Loaded {total_events_shared} events for {city}", icon="📊")
    log_info(f"Events page loaded for {city} ({total_events_shared} events)", module="events")
    
    color_map = get_event_color_map()
    icon_map = get_event_icon_map()
    
    if not events:
        st.warning("No events found for this city. Try selecting a different city.")
        render_footer(module="news")
        return
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🔍</span>
        <h3>Filters</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    with col1:
        all_types = list(set(e.event_type for e in events))
        selected_types = st.multiselect(
            "Event Categories",
            options=all_types,
            default=all_types,
            key="event_type_filter"
        )
    with col2:
        severity_range = st.slider(
            "Severity Range",
            min_value=-5,
            max_value=5,
            value=(-5, 5),
            key="severity_filter"
        )
    
    # Apply filters
    filtered_events = [
        e for e in events
        if e.event_type in selected_types
        and severity_range[0] <= e.severity <= severity_range[1]
    ]
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📈</span>
        <h3>Overview Metrics</h3>
    </div>
    """, unsafe_allow_html=True)
    
    total_events = len(filtered_events)
    avg_severity = sum(e.severity for e in filtered_events) / total_events if total_events > 0 else 0
    negative_count = sum(1 for e in filtered_events if e.severity < 0)
    positive_count = sum(1 for e in filtered_events if e.severity > 0)
    neutral_count = sum(1 for e in filtered_events if e.severity == 0)
    
    cols = st.columns(5)
    metrics_data = [
        ("📰", "Total Events", str(total_events), "#a78bfa"),
        ("📊", "Avg Severity", f"{avg_severity:+.1f}", "#f59e0b" if avg_severity < 0 else "#10b981"),
        ("⚠️", "Negative", str(negative_count), "#ef4444"),
        ("✅", "Positive", str(positive_count), "#10b981"),
        ("➖", "Neutral", str(neutral_count), "#6b7280"),
    ]
    
    for idx, (icon, label, value, color) in enumerate(metrics_data):
        with cols[idx]:
            st.markdown(f"""
            <div class="stat-card">
                <div class="icon">{icon}</div>
                <div class="label">{label}</div>
                <div class="value" style="color: {color};">{value}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📊</span>
        <h3>Analytics</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    # PIE CHART
    with col1:
        st.markdown('<div class="chart-container"><div class="chart-title">🥧 Event Distribution</div>', unsafe_allow_html=True)
        
        if filtered_events:
            type_counts = Counter(e.event_type for e in filtered_events)
            fig_pie = go.Figure(data=[go.Pie(
                labels=[t.replace('_', ' ').title() for t in type_counts.keys()],
                values=list(type_counts.values()),
                hole=0.45,
                marker=dict(colors=[color_map.get(t, "#6b7280") for t in type_counts.keys()]),
                textinfo='label+percent',
                textfont=dict(color='#fff', size=11),
                hovertemplate='%{label}<br>Count: %{value}<br>%{percent}<extra></extra>'
            )])
            fig_pie.update_layout(
                **get_dark_chart_layout(height=320),
                showlegend=False
            )
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No events to display")
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # HISTOGRAM
    with col2:
        st.markdown('<div class="chart-container"><div class="chart-title">📊 Severity Distribution</div>', unsafe_allow_html=True)
        
        if filtered_events:
            severities = [e.severity for e in filtered_events]
            fig_hist = go.Figure(data=[go.Histogram(
                x=severities,
                nbinsx=7,
                marker=dict(
                    color='rgba(139,92,246,0.7)',
                    line=dict(color='rgba(139,92,246,1)', width=1)
                ),
                hovertemplate='Severity: %{x}<br>Count: %{y}<extra></extra>'
            )])
            fig_hist.update_layout(
                **get_dark_chart_layout(height=320),
                xaxis_title="Severity",
                yaxis_title="Count",
                bargap=0.1
            )
            st.plotly_chart(fig_hist, use_container_width=True)
        else:
            st.info("No events to display")
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🏷️</span>
        <h3>Category Breakdown</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if filtered_events:
        type_counts = Counter(e.event_type for e in filtered_events)
        categories = list(type_counts.items())
        
        for i in range(0, len(categories), 4):
            cols = st.columns(4)
            for j, col in enumerate(cols):
                if i + j < len(categories):
                    cat, count = categories[i + j]
                    icon = icon_map.get(cat, "📰")
                    color = color_map.get(cat, "#6b7280")
                    pct = (count / total_events * 100) if total_events > 0 else 0
                    
                    with col:
                        st.markdown(f"""
                        <div class="category-card">
                            <div style="font-size: 2rem; margin-bottom: 0.25rem;">{icon}</div>
                            <div style="color: #94a3b8; font-size: 0.8rem; text-transform: capitalize;">{cat.replace('_', ' ')}</div>
                            <div style="font-size: 1.5rem; font-weight: 700; color: {color};">{count}</div>
                            <div style="color: #64748b; font-size: 0.75rem;">{pct:.1f}% of total</div>
                        </div>
                        """, unsafe_allow_html=True)
    else:
        st.info("No events found for the selected filters.")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📋</span>
        <h3>Events Table</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if filtered_events:
        df = pd.DataFrame([
            {
                "Type": f"{icon_map.get(e.event_type, '📰')} {e.event_type.replace('_', ' ').title()}",
                "Title": e.news_item.title[:60] + "..." if len(e.news_item.title) > 60 else e.news_item.title,
                "Severity": e.severity,
                "Date": e.news_item.published_at.strftime('%Y-%m-%d') if e.news_item.published_at else 'N/A',
                "Source": e.news_item.source,
            }
            for e in filtered_events
        ])
        
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            sort_by = st.selectbox("Sort by", ["Severity", "Type", "Date"], key="sort_col")
        with col2:
            sort_order = st.radio("Order", ["Descending", "Ascending"], horizontal=True, key="sort_order")
        with col3:
            csv = df.to_csv(index=False)
            st.download_button(
                "📥 Export CSV",
                csv,
                f"events_{city}_{datetime.now().strftime('%Y%m%d')}.csv",
                "text/csv",
                use_container_width=True
            )
        
        ascending = sort_order == "Ascending"
        df = df.sort_values(sort_by, ascending=ascending)
        
        st.dataframe(df, use_container_width=True, hide_index=True, height=400)
    else:
        st.info("No events to display in table.")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📄</span>
        <h3>Event Details</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if filtered_events:
        for event in filtered_events[:10]:
            icon = icon_map.get(event.event_type, "📰")
            color = color_map.get(event.event_type, "#6b7280")
            title = event.news_item.title
            
            with st.expander(f"{icon} {title[:70]}{'...' if len(title) > 70 else ''}", expanded=False):
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.markdown(f"**Type:** <span style='color:{color}'>{event.event_type.replace('_', ' ').title()}</span>", unsafe_allow_html=True)
                with col2:
                    sev_color = "#ef4444" if event.severity < 0 else "#10b981" if event.severity > 0 else "#6b7280"
                    st.markdown(f"**Severity:** <span style='color:{sev_color};'>{event.severity:+d}</span>", unsafe_allow_html=True)
                with col3:
                    date_str = event.news_item.published_at.strftime('%Y-%m-%d') if event.news_item.published_at else 'N/A'
                    st.markdown(f"**Date:** {date_str}")
                
                st.markdown(f"**Source:** {event.news_item.source}")
                st.markdown("---")
                st.markdown(f"**Full Title:**  \n{title}")
                
                if event.news_item.description:
                    st.markdown(f"**Description:**  \n{event.news_item.description}")
        
        if len(filtered_events) > 10:
            st.caption(f"Showing 10 of {len(filtered_events)} events. Use the table above to see all events.")
    else:
        st.info("No event details to display.")
    
    st.markdown(f"""
    <div class="data-footer">
        <span class="dot"></span>
        <span>Updated {datetime.now().strftime('%I:%M %p')} • {len(events)} total events • Shared data</span>
    </div>
    """, unsafe_allow_html=True)
    
    render_footer(module="news")


# Run main
if __name__ == "__main__":
    main()
else:
    main()
