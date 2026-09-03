"""
TravelSafe - Crime Watch
=========================

Real-time crime monitoring and safety analysis:
- Automatic fetch on page load for selected city
- Hero section with crime risk status
- Crime news from GNews/Google News RSS
- Plotly charts and trends
- Risk interpretation statements
- Download PDF report option
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from collections import Counter
import base64
import pandas as pd

# Import from core modules
from core.config import SUPPORTED_CITIES, DEFAULT_CITY, DEFAULT_PERSONA
from core.api_services import CrimeData, CrimeNewsItem
from core.data_cache import get_city_data
from core.ui_components import render_footer

# Import services for PDF and logging
try:
    from core.services.pdf_report import generate_crime_report, create_download_button
    from core.services.logger import log_info
    SERVICES_AVAILABLE = True
except ImportError:
    SERVICES_AVAILABLE = False
    def log_info(msg, module="crime"): pass


def get_selected_city() -> str:
    """Read city from session_state."""
    return st.session_state.get('selected_city', DEFAULT_CITY)


def get_selected_persona() -> str:
    """Read persona from session_state."""
    return st.session_state.get('selected_persona', DEFAULT_PERSONA)


CRIME_CATEGORIES = {
    "murder": ("🔪", "Homicide", "#dc2626"),
    "kill": ("🔪", "Homicide", "#dc2626"),
    "death": ("💀", "Fatal Incident", "#b91c1c"),
    "robbery": ("💰", "Robbery", "#f97316"),
    "theft": ("🏃", "Theft", "#f59e0b"),
    "steal": ("🏃", "Theft", "#f59e0b"),
    "burglary": ("🏠", "Burglary", "#f97316"),
    "assault": ("👊", "Assault", "#ef4444"),
    "attack": ("👊", "Attack", "#ef4444"),
    "kidnap": ("🚗", "Kidnapping", "#b91c1c"),
    "abduct": ("🚗", "Abduction", "#b91c1c"),
    "fraud": ("💳", "Fraud", "#8b5cf6"),
    "scam": ("💳", "Scam", "#8b5cf6"),
    "drug": ("💊", "Drug Crime", "#6366f1"),
    "narcotics": ("💊", "Narcotics", "#6366f1"),
    "arrest": ("🚔", "Arrest", "#3b82f6"),
    "police": ("🚔", "Police Activity", "#3b82f6"),
    "shooting": ("🔫", "Shooting", "#b91c1c"),
    "gang": ("👥", "Gang Activity", "#7c3aed"),
    "cyber": ("💻", "Cybercrime", "#3b82f6"),
    "violence": ("⚠️", "Violence", "#ef4444"),
}


def categorize_crime(title: str) -> tuple:
    """Categorize crime by keywords in title."""
    text = title.lower()
    
    for keyword, (icon, label, color) in CRIME_CATEGORIES.items():
        if keyword in text:
            return icon, label, color
    
    return "🚔", "Crime Report", "#ef4444"


def get_crime_risk_level(crime_data: CrimeData) -> tuple:
    """
    Analyze crime data and return risk level.
    Returns (level, color, icon, factors)
    """
    count = crime_data.total_count
    risk_factors = []
    
    # Count serious crimes
    serious_keywords = ["murder", "kill", "shooting", "kidnap", "assault", "robbery"]
    serious_count = 0
    
    for item in crime_data.news_items:
        title_lower = item.title.lower()
        if any(kw in title_lower for kw in serious_keywords):
            serious_count += 1
    
    # Build risk factors
    if serious_count > 0:
        risk_factors.append(f"{serious_count} serious incident(s) reported")
    
    if count > 10:
        risk_factors.append(f"High volume of reports ({count} items)")
    elif count > 5:
        risk_factors.append(f"Moderate volume of reports ({count} items)")
    elif count > 0:
        risk_factors.append(f"{count} crime report(s) found")
    
    # Determine level
    if serious_count >= 3 or count >= 15:
        return "HIGH RISK", "#ef4444", "🚨", risk_factors
    elif serious_count >= 1 or count >= 8:
        return "ELEVATED", "#f97316", "⚠️", risk_factors
    elif count >= 3:
        return "MODERATE", "#fbbf24", "📢", risk_factors
    else:
        if not risk_factors:
            risk_factors.append("No significant crime activity detected")
        return "LOW RISK", "#10b981", "✅", risk_factors


def generate_crime_pdf_content(city: str, crime_data: CrimeData, risk_level: str, risk_factors: list) -> str:
    """Generate HTML content for PDF download."""
    factors_html = "".join([f"<li>{f}</li>" for f in risk_factors])
    
    news_html = ""
    if crime_data.news_items:
        news_html = "<h3>Recent Crime Reports</h3><table style='width:100%; border-collapse: collapse;'>"
        news_html += "<tr style='background:#f3f4f6;'><th style='padding:10px; text-align:left;'>Title</th><th style='padding:10px;'>Source</th><th style='padding:10px;'>Date</th></tr>"
        for item in crime_data.news_items[:10]:
            news_html += f"<tr style='border-bottom:1px solid #e5e7eb;'><td style='padding:10px;'>{item.title[:60]}...</td><td style='padding:10px; text-align:center;'>{item.source}</td><td style='padding:10px; text-align:center;'>{item.published_at}</td></tr>"
        news_html += "</table>"
    
    risk_class = 'risk-high' if 'HIGH' in risk_level else 'risk-elevated' if 'ELEVATED' in risk_level else 'risk-moderate' if 'MODERATE' in risk_level else 'risk-low'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>TravelSafe Crime Report - {city}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 40px; color: #333; }}
            h1 {{ color: #1e3a5f; border-bottom: 2px solid #ef4444; padding-bottom: 10px; }}
            h2 {{ color: #ef4444; margin-top: 30px; }}
            h3 {{ color: #6b7280; }}
            .header {{ background: #fef2f2; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
            .metric-value {{ font-size: 24px; font-weight: bold; color: #1e3a5f; }}
            .metric-label {{ font-size: 12px; color: #6b7280; }}
            .risk-box {{ padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .risk-high {{ background: #fef2f2; border-left: 4px solid #ef4444; }}
            .risk-elevated {{ background: #fff7ed; border-left: 4px solid #f97316; }}
            .risk-moderate {{ background: #fffbeb; border-left: 4px solid #fbbf24; }}
            .risk-low {{ background: #f0fdf4; border-left: 4px solid #10b981; }}
            ul {{ line-height: 1.8; }}
            table {{ margin-top: 15px; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; }}
        </style>
    </head>
    <body>
        <h1>🚔 TravelSafe Crime Report</h1>
        
        <div class="header">
            <h2>📍 {city}</h2>
            <p>Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
            <p>Data Source: {crime_data.source}</p>
        </div>
        
        <h2>Crime Statistics</h2>
        <div class="metric">
            <div class="metric-value">{crime_data.total_count}</div>
            <div class="metric-label">Total Reports</div>
        </div>
        
        <h2>Risk Assessment</h2>
        <div class="risk-box {risk_class}">
            <strong>Risk Level: {risk_level}</strong>
            <ul>
                {factors_html}
            </ul>
        </div>
        
        {news_html}
        
        <h2>Safety Recommendations</h2>
        <ul>
            <li>Stay aware of your surroundings at all times</li>
            <li>Avoid isolated areas, especially at night</li>
            <li>Keep valuables secure and out of sight</li>
            <li>Save local emergency numbers on your phone</li>
            <li>Share your itinerary with trusted contacts</li>
            <li>Trust your instincts - if something feels wrong, leave</li>
        </ul>
        
        <h2>Emergency Contacts</h2>
        <ul>
            <li>Police: 100 (India) / 911 (USA) / 999 (UK)</li>
            <li>Ambulance: 102 (India) / 911 (USA) / 999 (UK)</li>
            <li>Women Helpline: 181 (India)</li>
        </ul>
        
        <div class="footer">
            <p>This report was generated by TravelSafe - Your AI-powered travel safety companion.</p>
            <p>Data refreshes every 15 minutes. For real-time updates, visit the app.</p>
        </div>
    </body>
    </html>
    """
    return html


def create_download_link(html_content: str, filename: str) -> str:
    """Create a download link for HTML content."""
    b64 = base64.b64encode(html_content.encode()).decode()
    return f'<a href="data:text/html;base64,{b64}" download="{filename}" style="text-decoration: none;"><button style="background: #ef4444; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">📥 Download PDF Report</button></a>'


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
        border-color: rgba(239,68,68,0.5);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(239,68,68,0.15);
    }
    .stat-card .icon { font-size: 1.75rem; margin-bottom: 0.5rem; }
    .stat-card .label { color: #94a3b8; font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.5px; }
    .stat-card .value { font-size: 1.75rem; font-weight: 700; color: #fff; margin: 0.25rem 0; }
    
    /* Hero Card */
    .hero-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.9) 0%, rgba(15,23,42,0.95) 100%);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 16px;
        padding: 2rem;
        text-align: center;
    }
    
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
    
    /* Info Card */
    .info-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.85) 100%);
        border: 1px solid rgba(255,255,255,0.1);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
    }
    
    /* News Card */
    .news-card {
        background: linear-gradient(135deg, rgba(30,41,59,0.6) 0%, rgba(15,23,42,0.8) 100%);
        border: 1px solid rgba(255,255,255,0.08);
        border-radius: 10px;
        padding: 1rem;
        margin-bottom: 0.75rem;
        transition: all 0.2s ease;
    }
    .news-card:hover {
        border-color: rgba(255,255,255,0.15);
        transform: translateX(4px);
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
        background: #ef4444;
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
    
    st.markdown("""
    <div style="text-align: center; padding: 1.5rem 0 1rem 0;">
        <h1 style="color: #fff; margin: 0; font-size: 2.25rem; font-weight: 700;">
            🚔 Crime Watch
        </h1>
        <p style="color: #94a3b8; margin: 0.5rem 0 0 0; font-size: 1rem;">
            Real-time crime monitoring and safety analysis
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get selected city
    city = get_selected_city()
    persona = get_selected_persona()
    
    # City badge
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <span style="background: linear-gradient(135deg, rgba(239,68,68,0.2), rgba(249,115,22,0.2)); 
                     border: 1px solid rgba(239,68,68,0.4); padding: 0.5rem 1.25rem; 
                     border-radius: 25px; color: #f87171; font-weight: 500;">
            📍 {city}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    cached_data = get_city_data(city, persona)
    events = cached_data.get("events", [])

    if not events:
        st.warning("No events loaded yet. Please load data from the Home Dashboard.")
        render_footer(module="crime")
        return

    st.session_state["unified_events"] = events

    crime_events = [e for e in events if e.event_type == "crime"]
    news_items = [
        CrimeNewsItem(
            title=e.news_item.title,
            description=e.news_item.description or "",
            url="",
            source=e.news_item.source,
            published_at=e.news_item.published_at.strftime('%Y-%m-%d') if e.news_item.published_at else "N/A",
            image_url=None,
        )
        for e in crime_events
    ]
    crime_data = CrimeData(
        city=city,
        news_items=news_items,
        total_count=len(crime_events),
        fetched_at=datetime.now().strftime('%Y-%m-%d %H:%M'),
        source="Shared unified events",
    )

    st.toast(f"✅ Crime data loaded for {city} ({crime_data.total_count} reports)", icon="🚔")
    
    log_info(f"Crime page loaded for {city}", module="crime")
    
    # Get risk assessment
    risk_level, risk_color, risk_icon, risk_factors = get_crime_risk_level(crime_data)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🚨</span>
        <h3>Crime Safety Status</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        card_class = "metric-card-danger" if "HIGH" in risk_level else "metric-card-warning" if risk_level in ["ELEVATED", "MODERATE"] else "metric-card-safe"
        st.markdown(f"""
        <div class="hero-card {card_class}">
            <div style="font-size: 4rem; margin-bottom: 0.5rem;">{risk_icon}</div>
            <div style="font-size: 2rem; font-weight: 700; color: {risk_color};">{risk_level}</div>
            <div style="font-size: 1rem; color: #94a3b8; margin-top: 0.5rem;">Crime Risk Level for {city}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card" style="padding: 2rem; height: 100%; display: flex; flex-direction: column; justify-content: center;">
            <div style="font-size: 3.5rem; font-weight: 700; color: #ef4444;">{crime_data.total_count}</div>
            <div style="color: #94a3b8; font-size: 0.9rem; margin-top: 0.25rem;">Reports Found</div>
            <div style="border-top: 1px solid rgba(255,255,255,0.1); margin-top: 1rem; padding-top: 1rem;">
                <div style="color: #64748b; font-size: 0.8rem;">Source</div>
                <div style="color: #fff; font-weight: 600; font-size: 0.9rem;">{crime_data.source}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📊</span>
        <h3>Crime Statistics</h3>
    </div>
    """, unsafe_allow_html=True)
    
    # Categorize all news items
    categories = []
    for item in crime_data.news_items:
        _, label, _ = categorize_crime(item.title)
        categories.append(label)
    
    cat_counts = Counter(categories)
    
    cols = st.columns(4)
    top_categories = cat_counts.most_common(4)
    
    for idx, (cat, count) in enumerate(top_categories):
        with cols[idx]:
            cat_icon = "🚔"
            cat_color = "#ef4444"
            for kw, (icon, label, color) in CRIME_CATEGORIES.items():
                if label == cat:
                    cat_icon = icon
                    cat_color = color
                    break
            
            st.markdown(f"""
            <div class="stat-card">
                <div class="icon">{cat_icon}</div>
                <div class="label">{cat}</div>
                <div class="value" style="color: {cat_color};">{count}</div>
            </div>
            """, unsafe_allow_html=True)
    
    # Fill remaining columns
    if len(top_categories) < 4:
        for idx in range(len(top_categories), 4):
            with cols[idx]:
                st.markdown("""
                <div class="stat-card">
                    <div class="icon">📰</div>
                    <div class="label">Other</div>
                    <div class="value" style="color: #6b7280;">0</div>
                </div>
                """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📈</span>
        <h3>Crime Analysis</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    # Category Pie Chart
    with col1:
        st.markdown('<div class="chart-container"><div class="chart-title">🥧 Crime Categories</div>', unsafe_allow_html=True)
        
        if cat_counts:
            fig_pie = go.Figure(data=[go.Pie(
                labels=list(cat_counts.keys()),
                values=list(cat_counts.values()),
                hole=0.45,
                marker=dict(colors=['#ef4444', '#f97316', '#fbbf24', '#8b5cf6', '#3b82f6', '#10b981']),
                textinfo='label+value',
                textfont=dict(color='#fff', size=11),
                hovertemplate='%{label}<br>Count: %{value}<br>%{percent}<extra></extra>'
            )])
            
            fig_pie.update_layout(
                paper_bgcolor='rgba(0,0,0,0)',
                plot_bgcolor='rgba(0,0,0,0)',
                font=dict(color='#fff'),
                height=300,
                margin=dict(l=20, r=20, t=20, b=20),
                showlegend=False
            )
            
            st.plotly_chart(fig_pie, use_container_width=True)
        else:
            st.info("No crime data available for chart")
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Risk Gauge
    with col2:
        st.markdown('<div class="chart-container"><div class="chart-title">🎯 Risk Score</div>', unsafe_allow_html=True)
        
        risk_value = 80 if "HIGH" in risk_level else 60 if "ELEVATED" in risk_level else 40 if "MODERATE" in risk_level else 20
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=risk_value,
            domain={'x': [0, 1], 'y': [0, 1]},
            number={'font': {'color': '#fff', 'size': 36}},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': '#666', 'tickfont': {'color': '#888'}},
                'bar': {'color': risk_color},
                'bgcolor': 'rgba(255,255,255,0.1)',
                'borderwidth': 2,
                'bordercolor': '#333',
                'steps': [
                    {'range': [0, 30], 'color': 'rgba(16,185,129,0.2)'},
                    {'range': [30, 50], 'color': 'rgba(251,191,36,0.2)'},
                    {'range': [50, 70], 'color': 'rgba(249,115,22,0.2)'},
                    {'range': [70, 100], 'color': 'rgba(239,68,68,0.2)'},
                ],
            }
        ))
        
        fig_gauge.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': '#fff'},
            height=300,
            margin=dict(l=20, r=20, t=20, b=20)
        )
        
        st.plotly_chart(fig_gauge, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📰</span>
        <h3>Recent Crime Reports</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if crime_data.news_items:
        for item in crime_data.news_items[:8]:
            icon, label, color = categorize_crime(item.title)
            
            st.markdown(f"""
            <div class="news-card" style="border-left: 4px solid {color};">
                <div style="display: flex; align-items: flex-start; gap: 1rem;">
                    <div style="font-size: 2rem;">{icon}</div>
                    <div style="flex: 1;">
                        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
                            <span style="color: {color}; font-weight: 600; font-size: 0.8rem; text-transform: uppercase;">{label}</span>
                        </div>
                        <div style="color: #e2e8f0; font-size: 0.95rem; margin-bottom: 0.3rem;">
                            {item.title[:100]}{'...' if len(item.title) > 100 else ''}
                        </div>
                        <div style="color: #64748b; font-size: 0.8rem;">
                            📅 {item.published_at} &nbsp;•&nbsp; 📰 {item.source}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
        
        if len(crime_data.news_items) > 8:
            st.caption(f"Showing 8 of {len(crime_data.news_items)} reports.")
    else:
        st.markdown("""
        <div class="metric-card metric-card-safe" style="text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">✅</div>
            <div style="font-size: 1.2rem; font-weight: 600; color: #10b981;">No Recent Crime Reports</div>
            <div style="color: #94a3b8; margin-top: 0.5rem;">No significant crime activity detected for this city.</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📋</span>
        <h3>Risk Interpretation</h3>
    </div>
    """, unsafe_allow_html=True)
    
    st.markdown(f"""
    <div class="info-card" style="padding: 1.5rem;">
        <div style="display: flex; align-items: center; gap: 1rem; margin-bottom: 1rem;">
            <div style="font-size: 2.5rem;">{risk_icon}</div>
            <div>
                <div style="font-size: 1.3rem; font-weight: 700; color: {risk_color};">{risk_level}</div>
                <div style="color: #94a3b8;">Crime risk assessment for {city}</div>
            </div>
        </div>
        <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
            <div style="font-weight: 600; color: #fff; margin-bottom: 0.5rem;">Risk Factors:</div>
    """, unsafe_allow_html=True)
    
    for factor in risk_factors:
        factor_color = "#ef4444" if any(w in factor.lower() for w in ["serious", "high"]) else "#f97316" if "moderate" in factor.lower() else "#10b981"
        st.markdown(f"""
        <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem;">
            <span style="color: {factor_color};">•</span>
            <span style="color: #cbd5e1;">{factor}</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("</div></div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🛡️</span>
        <h3>Safety Recommendations</h3>
    </div>
    """, unsafe_allow_html=True)
    
    recommendations = [
        ("👁️", "Stay aware of your surroundings at all times"),
        ("🌙", "Avoid isolated areas, especially at night"),
        ("💼", "Keep valuables secure and out of sight"),
        ("📱", "Save local emergency numbers on your phone"),
        ("📍", "Share your location with trusted contacts"),
        ("🚶", "Trust your instincts - if something feels wrong, leave"),
    ]
    
    # Add persona-specific recommendations
    if persona == "solo_female":
        recommendations.insert(0, ("👩", "Consider women-only transport options when available"))
        recommendations.insert(1, ("🏨", "Stay in well-reviewed, secure accommodations"))
    elif persona == "family":
        recommendations.insert(0, ("👨‍👩‍👧‍👦", "Keep children close in crowded areas"))
    elif persona == "elderly":
        recommendations.insert(0, ("👴", "Avoid carrying large amounts of cash"))
    
    cols = st.columns(2)
    for idx, (icon, tip) in enumerate(recommendations[:6]):
        with cols[idx % 2]:
            st.markdown(f"""
            <div class="info-card" style="padding: 0.85rem 1rem; display: flex; align-items: center; gap: 0.75rem;">
                <span style="font-size: 1.3rem;">{icon}</span>
                <span style="color: #e2e8f0;">{tip}</span>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📞</span>
        <h3>Emergency Contacts</h3>
    </div>
    """, unsafe_allow_html=True)
    
    cols = st.columns(4)
    
    emergency_contacts = [
        ("🚔", "Police", "100", "#ef4444"),
        ("🚑", "Ambulance", "102", "#3b82f6"),
        ("🚒", "Fire", "101", "#f97316"),
        ("👩", "Women Helpline", "181", "#8b5cf6"),
    ]
    
    for idx, (icon, label, number, color) in enumerate(emergency_contacts):
        with cols[idx]:
            st.markdown(f"""
            <div class="stat-card">
                <div class="icon">{icon}</div>
                <div class="label">{label}</div>
                <div class="value" style="color: {color};">{number}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.caption("*Emergency numbers shown are for India. Check local numbers for international destinations.")
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📥</span>
        <h3>Report & Data</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card" style="padding: 1rem;">
            <div class="label">Data Source</div>
            <div style="color: #fff; font-weight: 600; font-size: 0.95rem; margin-top: 0.25rem;">{crime_data.source}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card" style="padding: 1rem;">
            <div class="label">Last Updated</div>
            <div style="color: #fff; font-weight: 600; font-size: 0.95rem; margin-top: 0.25rem;">{crime_data.fetched_at}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown("""
        <div class="stat-card" style="padding: 1rem;">
            <div class="label">Cache TTL</div>
            <div style="color: #10b981; font-weight: 600; font-size: 0.95rem; margin-top: 0.25rem;">15 minutes</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    # Download button
    pdf_content = generate_crime_pdf_content(city, crime_data, risk_level, risk_factors)
    filename = f"TravelSafe_Crime_{city.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html"
    
    st.markdown(create_download_link(pdf_content, filename), unsafe_allow_html=True)
    st.caption("*Report downloads as HTML file. Open in browser and print to PDF for best results.")
    
    st.markdown(f"""
    <div class="data-footer">
        <span class="dot"></span>
        <span>Updated {datetime.now().strftime('%I:%M %p')} • {crime_data.total_count} reports • Live data</span>
    </div>
    """, unsafe_allow_html=True)
    
    render_footer(module="crime")


if __name__ == "__main__":
    main()
else:
    main()
