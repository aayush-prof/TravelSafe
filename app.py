"""
TravelSafe - Home
==================

Home page for the TravelSafe multi-page Streamlit app.
This file handles:
- Page configuration
- Shared CSS styling
- Shared sidebar (session state for city/persona selection)
- Top navigation dropdown

Pages are located in the /pages directory:
1. Dashboard - Main safety overview
2. Events - Event distribution analysis
3. Weather & Alerts - Weather and environment insights
4. Crime Watch - Crime news and trends
5. City Insights - City profiles and travel tips
"""

import streamlit as st
from datetime import datetime

# Import core modules for shared state
from core.config import SUPPORTED_CITIES, DEFAULT_CITY, DEFAULT_PERSONA
from core.personas import get_all_personas
from core.news_client import get_data_source_info


st.set_page_config(
    page_title="TravelSafe | Home",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="expanded"
)


def apply_custom_css():
    """Apply premium CSS styling across all pages."""
    st.markdown("""
    <style>
        /* Import Google Font */
        @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
        
        /* Global Styles */
        .stApp {
            font-family: 'Inter', sans-serif;
        }
        
        /* Hide Streamlit branding */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        
        /* Hide default header */
        header[data-testid="stHeader"] {
            background: transparent;
        }
        
        /* Main container */
        .main .block-container {
            padding-top: 1rem;
            padding-bottom: 2rem;
            max-width: 1200px;
        }
        
        /* Sidebar Styling */
        [data-testid="stSidebar"] {
            background: linear-gradient(180deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
            padding-top: 0;
        }
        
        [data-testid="stSidebar"] > div:first-child {
            padding-top: 0;
        }
        
        [data-testid="stSidebar"] .stMarkdown {
            color: #e8e8e8;
        }
        
        [data-testid="stSidebar"] .stSelectbox label {
            color: #a8d8ff !important;
            font-weight: 500;
        }
        
        [data-testid="stSidebar"] hr {
            border-color: rgba(255,255,255,0.1);
            margin: 1rem 0;
        }
        
        /* Top Navigation Bar */
        .top-nav-bar {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            z-index: 1000;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            padding: 0.5rem 1rem;
            border-bottom: 1px solid rgba(255,255,255,0.1);
            display: flex;
            align-items: center;
            gap: 1rem;
        }
        
        .nav-logo {
            font-size: 1.3rem;
            font-weight: 700;
            color: #fff;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* Header Styling */
        .main-header {
            text-align: center;
            padding: 0.5rem 0 1rem 0;
        }
        
        .main-title {
            font-size: 2.5rem;
            font-weight: 700;
            color: #ffffff;
            margin-bottom: 0.3rem;
            letter-spacing: -1px;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        
        .main-subtitle {
            color: #888;
            font-size: 1rem;
            font-weight: 400;
        }
        
        .header-divider {
            width: 80px;
            height: 3px;
            background: linear-gradient(90deg, #3b82f6, #60a5fa);
            margin: 0.8rem auto;
            border-radius: 2px;
        }
        
        /* Metric Cards */
        .metric-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            transition: transform 0.3s ease, box-shadow 0.3s ease;
            margin-bottom: 1rem;
        }
        
        .metric-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 20px 60px rgba(102, 126, 234, 0.2);
        }
        
        /* Clickable Nav Cards */
        .nav-card {
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            border-radius: 16px;
            padding: 1.5rem;
            box-shadow: 0 10px 40px rgba(0,0,0,0.3);
            border: 1px solid rgba(255,255,255,0.1);
            transition: all 0.3s ease;
            margin-bottom: 1rem;
            cursor: pointer;
            text-align: center;
        }
        
        .nav-card:hover {
            transform: translateY(-8px) scale(1.02);
            box-shadow: 0 25px 70px rgba(102, 126, 234, 0.3);
            border-color: rgba(102, 126, 234, 0.5);
            background: linear-gradient(135deg, #1f1f3a 0%, #1a2847 100%);
        }
        
        .metric-card-safe {
            background: linear-gradient(135deg, #0d4f3c 0%, #1a5d4a 100%);
            border: 1px solid rgba(16, 185, 129, 0.3);
        }
        
        .metric-card-warning {
            background: linear-gradient(135deg, #5c4813 0%, #6b5a1e 100%);
            border: 1px solid rgba(245, 158, 11, 0.3);
        }
        
        .metric-card-danger {
            background: linear-gradient(135deg, #5c1313 0%, #6b1e1e 100%);
            border: 1px solid rgba(239, 68, 68, 0.3);
        }
        
        .metric-value {
            font-size: 3rem;
            font-weight: 700;
            margin: 0.5rem 0;
        }
        
        .metric-label {
            font-size: 0.85rem;
            text-transform: uppercase;
            letter-spacing: 1.5px;
            color: #a0aec0;
            font-weight: 500;
        }
        
        .metric-delta {
            font-size: 0.9rem;
            padding: 0.25rem 0.75rem;
            border-radius: 20px;
            display: inline-block;
            margin-top: 0.5rem;
        }
        
        .delta-positive {
            background: rgba(16, 185, 129, 0.2);
            color: #10b981;
        }
        
        .delta-negative {
            background: rgba(239, 68, 68, 0.2);
            color: #ef4444;
        }
        
        /* Section Headers */
        .section-header {
            font-size: 1.4rem;
            font-weight: 600;
            color: #e8e8e8;
            margin: 2rem 0 1rem 0;
            display: flex;
            align-items: center;
            gap: 0.5rem;
        }
        
        /* City Badge */
        .city-badge {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 0.5rem 1.5rem;
            border-radius: 25px;
            font-weight: 600;
            font-size: 1.1rem;
            display: inline-block;
            margin-bottom: 1rem;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.4);
        }
        
        /* Persona Badge */
        .persona-badge {
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
            color: white;
            padding: 0.4rem 1rem;
            border-radius: 20px;
            font-weight: 500;
            font-size: 0.9rem;
            display: inline-block;
            box-shadow: 0 4px 15px rgba(240, 147, 251, 0.3);
        }
        
        /* Info Box */
        .info-box {
            background: rgba(102, 126, 234, 0.1);
            border: 1px solid rgba(102, 126, 234, 0.3);
            border-radius: 12px;
            padding: 1rem 1.5rem;
            margin: 1rem 0;
            color: #a8d8ff;
        }
        
        /* Page Header */
        .page-header {
            font-size: 2rem;
            font-weight: 700;
            color: #fff;
            margin-bottom: 0.5rem;
        }
        
        .page-subheader {
            color: #888;
            font-size: 1rem;
            margin-bottom: 2rem;
        }
        
        /* Responsive Design */
        @media (max-width: 768px) {
            .main-title {
                font-size: 2rem;
            }
            .metric-value {
                font-size: 2rem;
            }
            .metric-card {
                padding: 1rem;
            }
        }
        
        /* Scrollbar Styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        
        ::-webkit-scrollbar-track {
            background: #1a1a2e;
        }
        
        ::-webkit-scrollbar-thumb {
            background: linear-gradient(180deg, #667eea, #764ba2);
            border-radius: 4px;
        }
        
        /* Animation */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(20px); }
            to { opacity: 1; transform: translateY(0); }
        }
        
        .animate-fade-in {
            animation: fadeIn 0.6s ease-out;
        }
    </style>
    """, unsafe_allow_html=True)


def render_shared_sidebar():
    """
    Render the shared sidebar across all pages.
    Stores selections in session state for access by all pages.
    """
    with st.sidebar:
        # Initialize session state if not exists
        if 'selected_city' not in st.session_state:
            st.session_state.selected_city = DEFAULT_CITY
        if 'selected_persona' not in st.session_state:
            st.session_state.selected_persona = DEFAULT_PERSONA
        
        # City Selection (moved to top)
        st.markdown("#### 🌍 Destination")
        
        selected_city = st.selectbox(
            "City",
            options=sorted(SUPPORTED_CITIES),
            index=sorted(SUPPORTED_CITIES).index(st.session_state.selected_city) if st.session_state.selected_city in sorted(SUPPORTED_CITIES) else 0,
            key="city_selector",
            label_visibility="collapsed",
        )
        st.session_state.selected_city = selected_city
        
        # Persona Selection
        st.markdown("#### 👤 Traveler Profile")
        personas = get_all_personas()
        persona_options = {
            "student": "🎓 Student Traveler",
            "solo_female": "👩 Solo Female",
            "family": "👨‍👩‍👧‍👦 Family with Kids",
            "backpacker": "🎒 Backpacker",
            "elderly": "👴 Senior Traveler",
        }
        
        selected_persona = st.selectbox(
            "Persona",
            options=list(persona_options.keys()),
            format_func=lambda x: persona_options.get(x, x),
            index=list(persona_options.keys()).index(st.session_state.selected_persona) if st.session_state.selected_persona in persona_options else 0,
            key="persona_selector",
            label_visibility="collapsed",
        )
        st.session_state.selected_persona = selected_persona
        
        st.markdown("---")
        
        # Logo and Title (centered)
        st.markdown("""
        <div style="text-align: center; padding: 1rem 0;">
            <div style="font-size: 3.5rem; margin-bottom: 0.5rem;">🛡️</div>
            <div style="font-size: 1.6rem; font-weight: 700; color: #fff; letter-spacing: -0.5px;">TravelSafe</div>
            <div style="font-size: 0.75rem; color: #888; margin-top: 0.25rem;">Safety Intelligence Platform</div>
        </div>
        """, unsafe_allow_html=True)


def main():
    """Main app entry point - Home page with navigation."""
    
    # Apply CSS
    apply_custom_css()
    
    # Render shared sidebar
    render_shared_sidebar()
    
  
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Landing Page Content
    st.markdown("""
    <div class="main-header animate-fade-in">
        <div class="main-title">
            <span style="font-size: 3rem; margin-right: 0.5rem;">🛡️</span>
            <span>TravelSafe</span>
        </div>
        <div class="header-divider"></div>
        <div class="main-subtitle">Your AI-powered travel safety companion</div>
    </div>
    """, unsafe_allow_html=True)
    
    # Welcome message
    st.markdown(f"""
    <div style="text-align: center; margin: 1rem 0;">
        <span class="city-badge">📍 {st.session_state.get('selected_city', DEFAULT_CITY)}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # Page Cards - 2 rows layout
    st.markdown('<div class="section-header">🚀 Quick Navigation</div>', unsafe_allow_html=True)
    
    # Row 1: 3 cards
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown("""
        <div class="nav-card">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">🏠</div>
            <div style="font-weight: 600; color: #fff; font-size: 1.1rem;">Dashboard</div>
            <div style="color: #888; font-size: 0.85rem; margin-top: 0.5rem;">
                Main safety overview with index cards
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Dashboard →", key="nav_home", use_container_width=True):
            st.switch_page("pages/1_Dashboard.py")
    
    with col2:
        st.markdown("""
        <div class="nav-card">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">📊</div>
            <div style="font-weight: 600; color: #fff; font-size: 1.1rem;">Events</div>
            <div style="color: #888; font-size: 0.85rem; margin-top: 0.5rem;">
                Full event distribution analysis
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Events →", key="nav_events", use_container_width=True):
            st.switch_page("pages/2_Events.py")
    
    with col3:
        st.markdown("""
        <div class="nav-card">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">🌤️</div>
            <div style="font-weight: 600; color: #fff; font-size: 1.1rem;">Weather Alerts</div>
            <div style="color: #888; font-size: 0.85rem; margin-top: 0.5rem;">
                Weather and environmental safety
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Weather →", key="nav_weather", use_container_width=True):
            st.switch_page("pages/3_Weather_Alerts.py")
    
    # Row 2: 2 cards centered with equal width as row 1
    spacer1, col4, col5, spacer2 = st.columns([1, 2, 2, 1])
    
    with col4:
        st.markdown("""
        <div class="nav-card">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">🚔</div>
            <div style="font-weight: 600; color: #fff; font-size: 1.1rem;">Crime Watch</div>
            <div style="color: #888; font-size: 0.85rem; margin-top: 0.5rem;">
                Crime news and security monitoring
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open Crime →", key="nav_crime", use_container_width=True):
            st.switch_page("pages/4_Crime_Watch.py")
    
    with col5:
        st.markdown("""
        <div class="nav-card">
            <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">🏙️</div>
            <div style="font-weight: 600; color: #fff; font-size: 1.1rem;">City Insights</div>
            <div style="color: #888; font-size: 0.85rem; margin-top: 0.5rem;">
                City profiles and travel tips
            </div>
        </div>
        """, unsafe_allow_html=True)
        if st.button("Open City →", key="nav_city", use_container_width=True):
            st.switch_page("pages/5_City_Insights.py")
    
    # Footer
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; padding: 1rem 0; color: #666;">
        <div style="font-size: 0.9rem; margin-bottom: 0.5rem;">
            🛡️ <strong>TravelSafe</strong> — Your AI-powered travel safety companion
        </div>
        <div style="font-size: 0.75rem;">
            Data refreshes every 5 minutes • Powered by real-time news analysis
        </div>
    </div>
    """, unsafe_allow_html=True)


if __name__ == "__main__":
    main()
