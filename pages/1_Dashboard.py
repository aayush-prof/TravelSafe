"""
TravelSafe - Dashboard
======================

Main dashboard page showing:
- City & Persona selection (synced via session_state)
- Top metrics: Safety Index, Base Index, Events Count, Pos/Neutral
- Summary bar with status interpretation
- Dynamic clickable cards → navigate to relevant pages
- Updated timestamp
- PDF report download
"""

import streamlit as st
import plotly.graph_objects as go
from datetime import datetime
from collections import Counter

# Import from core modules (reusing existing business logic)
from core.config import SUPPORTED_CITIES, DEFAULT_CITY, DEFAULT_PERSONA, USE_LIVE_NEWS, check_api_keys, get_api_status_for_module
from core.personas import get_all_personas
from core.data_cache import get_city_data
from core.scoring import get_index_interpretation

# Import services for PDF and logging
try:
    from core.services.pdf_report import generate_safety_report, create_download_button
    from core.services.logger import log_info
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False
    def log_info(msg, module="home"): pass


def get_selected_city() -> str:
    """Read city from session_state (consistent across pages)."""
    return st.session_state.get('selected_city', DEFAULT_CITY)


def get_selected_persona() -> str:
    """Read persona from session_state (consistent across pages)."""
    return st.session_state.get('selected_persona', DEFAULT_PERSONA)


def set_selected_city(city: str):
    """Update city in session_state."""
    st.session_state['selected_city'] = city


def set_selected_persona(persona: str):
    """Update persona in session_state."""
    st.session_state['selected_persona'] = persona


def get_safety_status(index: float) -> tuple:
    """
    Return (status_text, color, card_class, icon) based on safety index.
    Aligned with scoring.py thresholds.
    """
    if index >= 6:
        return "VERY SAFE", "#10b981", "metric-card-safe", "✅"
    elif index >= 2:
        return "SAFE", "#34d399", "metric-card-safe", "👍"
    elif index >= 0:
        return "LOW RISK", "#a3e635", "metric-card-warning", "🟢"
    elif index >= -3:
        return "MODERATE", "#f59e0b", "metric-card-warning", "⚠️"
    elif index >= -6:
        return "RISKY", "#f97316", "metric-card-danger", "🟠"
    elif index >= -8:
        return "HIGH RISK", "#ef4444", "metric-card-danger", "🚨"
    else:
        return "SEVERE / DANGEROUS", "#b91c1c", "metric-card-danger", "⛔"


EVENT_COLORS = {
    "crime": "#ef4444",
    "protest": "#f97316",
    "accident": "#eab308",
    "disaster": "#dc2626",
    "weather": "#3b82f6",
    "positive": "#10b981",
    "neutral": "#6b7280",
}

EVENT_ICONS = {
    "crime": "🚔",
    "protest": "📢",
    "accident": "🚗",
    "disaster": "🌪️",
    "weather": "⛈️",
    "positive": "🎉",
    "neutral": "📰",
}

PERSONA_LABELS = {
    "student": "🎓 Student",
    "solo_female": "👩 Solo Female",
    "family": "👨‍👩‍👧‍👦 Family",
    "backpacker": "🎒 Backpacker",
    "elderly": "👴 Senior",
}


def main():
    st.markdown("""
    <style>
        /* Hide default Streamlit elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        header[data-testid="stHeader"] {background: transparent;}
        
        /* Reduce default padding */
        .main .block-container {
            padding-top: 0 !important;
            padding-bottom: 1rem;
            max-width: 1400px;
        }
        
        /* Top Navigation Bar */
        .top-navbar {
            background: linear-gradient(135deg, #0f0f1a 0%, #1a1a2e 100%);
            border-bottom: 1px solid rgba(102, 126, 234, 0.2);
            padding: 0.75rem 2rem;
            margin: -1rem -1rem 1.5rem -1rem;
            display: flex;
            align-items: center;
            justify-content: space-between;
            flex-wrap: wrap;
            gap: 1rem;
        }
        
        .nav-brand {
            display: flex;
            align-items: center;
            gap: 0.75rem;
        }
        
        .nav-brand-icon {
            font-size: 1.8rem;
        }
        
        .nav-brand-text {
            font-size: 1.4rem;
            font-weight: 700;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
        }
        
        .nav-links {
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        .nav-link {
            color: #888;
            text-decoration: none;
            padding: 0.5rem 1rem;
            border-radius: 8px;
            font-size: 0.85rem;
            font-weight: 500;
            transition: all 0.2s ease;
            cursor: pointer;
        }
        
        .nav-link:hover {
            color: #fff;
            background: rgba(102, 126, 234, 0.15);
        }
        
        .nav-link.active {
            color: #fff;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        
        .nav-selectors {
            display: flex;
            gap: 0.75rem;
            align-items: center;
        }
        
        /* Hero Section */
        .hero-section {
            text-align: center;
            padding: 2rem 1rem 1.5rem 1rem;
            background: linear-gradient(180deg, rgba(102,126,234,0.08) 0%, transparent 100%);
            border-radius: 20px;
            margin-bottom: 1.5rem;
        }
        
        .hero-title {
            font-size: 2.8rem;
            font-weight: 800;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 50%, #f093fb 100%);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            background-clip: text;
            margin-bottom: 0.5rem;
            letter-spacing: -1px;
        }
        
        .hero-subtitle {
            color: #9ca3af;
            font-size: 1.1rem;
            font-weight: 400;
            margin-bottom: 1rem;
        }
        
        .hero-chips {
            display: flex;
            justify-content: center;
            gap: 0.75rem;
            flex-wrap: wrap;
        }
        
        .hero-chip {
            padding: 0.5rem 1.25rem;
            border-radius: 25px;
            font-size: 0.9rem;
            font-weight: 500;
            display: inline-flex;
            align-items: center;
            gap: 0.4rem;
        }
        
        .chip-city {
            background: linear-gradient(135deg, rgba(59,130,246,0.2) 0%, rgba(59,130,246,0.1) 100%);
            border: 1px solid rgba(59,130,246,0.4);
            color: #60a5fa;
        }
        
        .chip-persona {
            background: linear-gradient(135deg, rgba(139,92,246,0.2) 0%, rgba(139,92,246,0.1) 100%);
            border: 1px solid rgba(139,92,246,0.4);
            color: #a78bfa;
        }
        
        /* Metric Cards with Glow */
        .metric-card-glow {
            background: linear-gradient(135deg, #12121f 0%, #1a1a2e 100%);
            border-radius: 16px;
            padding: 1.25rem 1rem;
            border: 1px solid rgba(255,255,255,0.08);
            text-align: center;
            transition: all 0.3s ease;
            position: relative;
            overflow: hidden;
        }
        
        .metric-card-glow::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 2px;
            background: linear-gradient(90deg, transparent, rgba(102,126,234,0.5), transparent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }
        
        .metric-card-glow:hover {
            transform: translateY(-4px);
            border-color: rgba(102,126,234,0.3);
            box-shadow: 0 20px 40px rgba(102,126,234,0.15), 0 0 30px rgba(102,126,234,0.1);
        }
        
        .metric-card-glow:hover::before {
            opacity: 1;
        }
        
        .metric-label {
            color: #6b7280;
            font-size: 0.75rem;
            font-weight: 500;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 0.5rem;
        }
        
        .metric-value {
            font-size: 2rem;
            font-weight: 700;
            line-height: 1.2;
        }
        
        .metric-sublabel {
            color: #4b5563;
            font-size: 0.7rem;
            margin-top: 0.25rem;
        }
        
        /* Status Colors */
        .status-safe { color: #10b981; }
        .status-warning { color: #f59e0b; }
        .status-danger { color: #ef4444; }
        .status-info { color: #3b82f6; }
        .status-neutral { color: #6b7280; }
        
        /* Section Title */
        .section-title {
            font-size: 1rem;
            font-weight: 600;
            color: #9ca3af;
            margin-bottom: 1rem;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* Footer */
        .footer-minimal {
            text-align: center;
            padding: 1rem 0;
            color: #4b5563;
            font-size: 0.75rem;
            border-top: 1px solid rgba(255,255,255,0.05);
            margin-top: 2rem;
        }
    </style>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    spacer_l, sel_col1, sel_col2, spacer_r = st.columns([1.5, 1, 1, 1.5])
    
    with sel_col1:
        current_city = get_selected_city()
        city_index = SUPPORTED_CITIES.index(current_city) if current_city in SUPPORTED_CITIES else 0
        selected_city = st.selectbox(
            "📍 City",
            options=SUPPORTED_CITIES,
            index=city_index,
            key="home_city_selector",
            label_visibility="collapsed"
        )
        if selected_city != current_city:
            set_selected_city(selected_city)
            st.rerun()
    
    with sel_col2:
        personas = get_all_personas()
        persona_names = [p.name for p in personas.values()]
        current_persona = get_selected_persona()
        persona_index = persona_names.index(current_persona) if current_persona in persona_names else 0
        selected_persona = st.selectbox(
            "👤 Profile",
            options=persona_names,
            index=persona_index,
            format_func=lambda x: PERSONA_LABELS.get(x, x.replace('_', ' ').title()),
            key="home_persona_selector",
            label_visibility="collapsed"
        )
        if selected_persona != current_persona:
            set_selected_persona(selected_persona)
            st.rerun()
    
    st.markdown("<div style='height: 0.5rem;'></div>", unsafe_allow_html=True)
    
    city = get_selected_city()
    persona = get_selected_persona()

    with st.spinner(""):
        cached_data = get_city_data(city, persona)
        st.session_state["unified_events"] = cached_data.get("events", [])

    st.toast(f"✅ Data loaded for {city}", icon="🛡️")
    log_info(f"Dashboard loaded for {city} ({persona})", module="home")

    scores = {
        "index": cached_data.get("safety_index", 0.0),
        "base_index": cached_data.get("base_index", 0.0),
        "total_events": cached_data.get("total_events", 0),
        "category_counts": cached_data.get("category_counts", {}),
    }
    last_updated = cached_data.get("last_updated", datetime.now())

    m1, m2, m3, m4 = st.columns(4)
    
    status_text, status_color, card_class, status_icon = get_safety_status(scores["index"])
    interpretation = get_index_interpretation(scores["index"])
    event_counts = scores["category_counts"]
    positive_count = event_counts.get('positive', 0)
    neutral_count = event_counts.get('neutral', 0)

    with m1:
        st.markdown(f"""
        <div class="metric-card-glow">
            <div class="metric-label">Safety Index</div>
            <div class="metric-value" style="color: {status_color};">{scores["index"]:+.1f}</div>
            <div class="metric-sublabel">{status_text}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with m2:
        base_color = "#ef4444" if scores["base_index"] < -2 else "#f59e0b" if scores["base_index"] < 0 else "#10b981"
        st.markdown(f"""
        <div class="metric-card-glow">
            <div class="metric-label">Base Index</div>
            <div class="metric-value" style="color: {base_color};">{scores["base_index"]:+.1f}</div>
            <div class="metric-sublabel">Raw Score</div>
        </div>
        """, unsafe_allow_html=True)
    
    with m3:
        st.markdown(f"""
        <div class="metric-card-glow">
            <div class="metric-label">Events Count</div>
            <div class="metric-value status-info">{scores["total_events"]}</div>
            <div class="metric-sublabel">Total Analyzed</div>
        </div>
        """, unsafe_allow_html=True)
    
    with m4:
        pos_neu = positive_count + neutral_count
        st.markdown(f"""
        <div class="metric-card-glow">
            <div class="metric-label">Positive/Neutral</div>
            <div class="metric-value status-safe">{pos_neu}</div>
            <div class="metric-sublabel">{positive_count} good · {neutral_count} neutral</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(118,75,162,0.1) 100%); 
                border: 1px solid rgba(102,126,234,0.2); border-radius: 12px; padding: 1rem 1.5rem;
                display: flex; align-items: center; gap: 1rem; flex-wrap: wrap;">
        <div style="font-size: 2.5rem;">{status_icon}</div>
        <div style="flex: 1; min-width: 200px;">
            <div style="font-size: 1.1rem; font-weight: 600; color: {status_color}; margin-bottom: 0.25rem;">
                {city} — {status_text}
            </div>
            <div style="color: #9ca3af; font-size: 0.85rem;">{interpretation}</div>
        </div>
            <div style="text-align: right; color: #6b7280; font-size: 0.75rem;">
            <div>Updated: {last_updated.strftime("%H:%M")}</div>
            <div>{scores["total_events"]} events analyzed</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown('<div class="section-title">📈 Event Categories</div>', unsafe_allow_html=True)
    
    cat_cols = st.columns(7)
    for idx, event_type in enumerate(EVENT_COLORS.keys()):
        count = event_counts.get(event_type, 0)
        color = EVENT_COLORS.get(event_type, "#6b7280")
        icon = EVENT_ICONS.get(event_type, "📰")
        with cat_cols[idx]:
            st.markdown(f"""
            <div class="metric-card-glow" style="padding: 0.75rem;">
                <div style="font-size: 1.3rem;">{icon}</div>
                <div style="font-size: 1.25rem; font-weight: 700; color: {color};">{count}</div>
                <div style="color: #6b7280; font-size: 0.65rem; text-transform: capitalize;">{event_type}</div>
            </div>
            """, unsafe_allow_html=True)
    
    is_live, status_text, status_color = get_api_status_for_module("news")
    status_icon = "🟢" if is_live else "🟡"
    
    st.markdown(f"""
    <div class="footer-minimal">
        🛡️ TravelSafe — Data refreshes every 5 min · 
        <span style="color: {status_color};">{status_icon} {status_text}</span> · 
        {datetime.now().strftime("%b %d, %Y %H:%M")}
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
else:
    main()
