"""
TravelSafe - Weather Alerts
============================

Real-time weather monitoring and alerts:
- Automatic fetch on page load for selected city
- Hero section with current conditions
- Weather charts and trends
- Risk interpretation statements
- Download PDF report option
"""

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime
from collections import Counter
import base64
from io import BytesIO

# Import from core modules
from core.config import SUPPORTED_CITIES, DEFAULT_CITY, DEFAULT_PERSONA
from core.api_services import fetch_weather_data, WeatherData, CITY_COORDINATES
from core.data_cache import get_city_data
from core.ui_components import render_footer

# Import services for PDF and logging
try:
    from core.services.pdf_report import generate_weather_report, create_download_button
    from core.services.logger import log_info
    SERVICES_AVAILABLE = True
except ImportError:
    SERVICES_AVAILABLE = False
    def log_info(msg, module="weather"): pass


def get_selected_city() -> str:
    """Read city from session_state."""
    return st.session_state.get('selected_city', DEFAULT_CITY)


def get_selected_persona() -> str:
    """Read persona from session_state."""
    return st.session_state.get('selected_persona', DEFAULT_PERSONA)


def get_weather_risk_level(weather: WeatherData) -> tuple:
    """
    Analyze weather conditions and return risk level.
    Returns (level, color, icon, description)
    """
    risk_score = 0
    risk_factors = []
    
    # Temperature extremes
    if weather.temperature > 40:
        risk_score += 3
        risk_factors.append("Extreme heat warning")
    elif weather.temperature > 35:
        risk_score += 2
        risk_factors.append("High temperature")
    elif weather.temperature < 5:
        risk_score += 2
        risk_factors.append("Cold conditions")
    elif weather.temperature < 0:
        risk_score += 3
        risk_factors.append("Freezing temperatures")
    
    # Humidity
    if weather.humidity > 85:
        risk_score += 1
        risk_factors.append("High humidity")
    
    # Wind
    if weather.wind_speed > 50:
        risk_score += 3
        risk_factors.append("Strong winds")
    elif weather.wind_speed > 30:
        risk_score += 1
        risk_factors.append("Moderate winds")
    
    # Visibility
    if weather.visibility < 2:
        risk_score += 2
        risk_factors.append("Low visibility")
    
    # Weather alerts
    if weather.alerts:
        risk_score += len(weather.alerts) * 2
        risk_factors.append(f"{len(weather.alerts)} active alert(s)")
    
    # Determine level
    if risk_score >= 5:
        return "HIGH RISK", "#ef4444", "🚨", risk_factors
    elif risk_score >= 3:
        return "MODERATE", "#f59e0b", "⚠️", risk_factors
    elif risk_score >= 1:
        return "LOW RISK", "#fbbf24", "📢", risk_factors
    else:
        return "SAFE", "#10b981", "✅", ["No significant weather concerns"]


def get_uv_index_info(hour: int) -> tuple:
    """Estimate UV index based on time of day."""
    if 10 <= hour <= 16:
        return 8, "Very High", "#ef4444"
    elif 8 <= hour <= 18:
        return 5, "Moderate", "#f59e0b"
    else:
        return 1, "Low", "#10b981"


def generate_weather_pdf_content(city: str, weather: WeatherData, risk_level: str, risk_factors: list) -> str:
    """Generate HTML content for PDF download."""
    factors_html = "".join([f"<li>{f}</li>" for f in risk_factors])
    alerts_html = ""
    
    if weather.alerts:
        alerts_html = "<h3>Active Alerts</h3><ul>"
        for alert in weather.alerts:
            alerts_html += f"<li><strong>{alert.get('event', 'Alert')}</strong>: {alert.get('description', '')[:100]}</li>"
        alerts_html += "</ul>"
    
    risk_class = 'risk-high' if 'HIGH' in risk_level else 'risk-moderate' if 'MODERATE' in risk_level else 'risk-low'
    
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>TravelSafe Weather Report - {city}</title>
        <style>
            body {{ font-family: Arial, sans-serif; padding: 40px; color: #333; }}
            h1 {{ color: #1e3a5f; border-bottom: 2px solid #3b82f6; padding-bottom: 10px; }}
            h2 {{ color: #3b82f6; margin-top: 30px; }}
            h3 {{ color: #6b7280; }}
            .header {{ background: #f0f9ff; padding: 20px; border-radius: 8px; margin-bottom: 20px; }}
            .metric {{ display: inline-block; margin: 10px 20px 10px 0; }}
            .metric-value {{ font-size: 24px; font-weight: bold; color: #1e3a5f; }}
            .metric-label {{ font-size: 12px; color: #6b7280; }}
            .risk-box {{ padding: 15px; border-radius: 8px; margin: 20px 0; }}
            .risk-high {{ background: #fef2f2; border-left: 4px solid #ef4444; }}
            .risk-moderate {{ background: #fffbeb; border-left: 4px solid #f59e0b; }}
            .risk-low {{ background: #f0fdf4; border-left: 4px solid #10b981; }}
            ul {{ line-height: 1.8; }}
            .footer {{ margin-top: 40px; padding-top: 20px; border-top: 1px solid #e5e7eb; font-size: 12px; color: #9ca3af; }}
        </style>
    </head>
    <body>
        <h1>🌤️ TravelSafe Weather Report</h1>
        
        <div class="header">
            <h2>📍 {city}</h2>
            <p>Generated: {datetime.now().strftime("%B %d, %Y at %I:%M %p")}</p>
            <p>Data Source: {weather.source}</p>
        </div>
        
        <h2>Current Conditions</h2>
        <div class="metric">
            <div class="metric-value">{weather.temperature}°C</div>
            <div class="metric-label">Temperature</div>
        </div>
        <div class="metric">
            <div class="metric-value">{weather.feels_like}°C</div>
            <div class="metric-label">Feels Like</div>
        </div>
        <div class="metric">
            <div class="metric-value">{weather.humidity}%</div>
            <div class="metric-label">Humidity</div>
        </div>
        <div class="metric">
            <div class="metric-value">{weather.wind_speed} km/h</div>
            <div class="metric-label">Wind Speed</div>
        </div>
        <div class="metric">
            <div class="metric-value">{weather.visibility} km</div>
            <div class="metric-label">Visibility</div>
        </div>
        <p><strong>Conditions:</strong> {weather.icon} {weather.description}</p>
        <p><strong>Sunrise:</strong> {weather.sunrise} | <strong>Sunset:</strong> {weather.sunset}</p>
        
        <h2>Risk Assessment</h2>
        <div class="risk-box {risk_class}">
            <strong>Risk Level: {risk_level}</strong>
            <ul>
                {factors_html}
            </ul>
        </div>
        
        {alerts_html}
        
        <h2>Travel Recommendations</h2>
        <ul>
            <li>Check weather updates before outdoor activities</li>
            <li>Carry appropriate clothing for the conditions</li>
            <li>Stay hydrated in hot weather</li>
            <li>Follow local authority advisories</li>
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
    return f'<a href="data:text/html;base64,{b64}" download="{filename}" style="text-decoration: none;"><button style="background: #3b82f6; color: white; padding: 10px 20px; border: none; border-radius: 8px; cursor: pointer; font-weight: 600;">📥 Download PDF Report</button></a>'


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
        border-color: rgba(59,130,246,0.5);
        transform: translateY(-2px);
        box-shadow: 0 8px 25px rgba(59,130,246,0.15);
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
        background: #3b82f6;
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
            🌤️ Weather Alerts
        </h1>
        <p style="color: #94a3b8; margin: 0.5rem 0 0 0; font-size: 1rem;">
            Real-time weather conditions and environmental safety
        </p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get selected city
    city = get_selected_city()
    persona = get_selected_persona()
    
    # City badge
    st.markdown(f"""
    <div style="text-align: center; margin-bottom: 1.5rem;">
        <span style="background: linear-gradient(135deg, rgba(59,130,246,0.2), rgba(6,182,212,0.2)); 
                     border: 1px solid rgba(59,130,246,0.4); padding: 0.5rem 1.25rem; 
                     border-radius: 25px; color: #60a5fa; font-weight: 500;">
            📍 {city}
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Ensure shared events/scores are loaded once per city/persona
    cached_data = get_city_data(city, persona)
    st.session_state["unified_events"] = cached_data.get("events", [])
    
    with st.spinner("Fetching weather data..."):
        weather = fetch_weather_data(city)
    
    if "API" in weather.source:
        st.toast(f"✅ Live weather data loaded for {city}", icon="🌤️")
    else:
        st.toast(f"ℹ️ Using cached weather data for {city}", icon="🌤️")
    
    log_info(f"Weather page loaded for {city}", module="weather")
    
    # Get risk assessment
    risk_level, risk_color, risk_icon, risk_factors = get_weather_risk_level(weather)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🌡️</span>
        <h3>Current Conditions</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"""
        <div class="hero-card">
            <div style="font-size: 4rem; margin-bottom: 0.5rem;">{weather.icon}</div>
            <div style="font-size: 3.5rem; font-weight: 700; color: #fff;">{weather.temperature}°C</div>
            <div style="font-size: 1.2rem; color: #94a3b8; margin: 0.5rem 0 1rem 0; text-transform: capitalize;">{weather.description}</div>
            <div style="font-size: 0.9rem; color: #64748b;">
                Feels like <strong style="color: #fff;">{weather.feels_like}°C</strong>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        card_class = "metric-card-danger" if "HIGH" in risk_level else "metric-card-warning" if "MODERATE" in risk_level else "metric-card-safe"
        st.markdown(f"""
        <div class="metric-card {card_class}" style="padding: 2rem; text-align: center; height: 100%; display: flex; flex-direction: column; justify-content: center;">
            <div style="font-size: 3.5rem; margin-bottom: 0.5rem;">{risk_icon}</div>
            <div style="font-size: 1.5rem; font-weight: 700; color: {risk_color};">{risk_level}</div>
            <div style="font-size: 0.85rem; color: #94a3b8; margin-top: 0.5rem;">Weather Risk Level</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📊</span>
        <h3>Weather Details</h3>
    </div>
    """, unsafe_allow_html=True)
    
    cols = st.columns(6)
    
    metrics = [
        ("💧", "Humidity", f"{weather.humidity}%", "#3b82f6"),
        ("💨", "Wind", f"{weather.wind_speed} km/h", "#8b5cf6"),
        ("👁️", "Visibility", f"{weather.visibility} km", "#06b6d4"),
        ("📊", "Pressure", f"{weather.pressure} hPa", "#f59e0b"),
        ("☁️", "Clouds", f"{weather.clouds}%", "#6b7280"),
        ("🌅", "Sunrise", weather.sunrise, "#f97316"),
    ]
    
    for idx, (icon, label, value, color) in enumerate(metrics):
        with cols[idx]:
            st.markdown(f"""
            <div class="stat-card">
                <div class="icon">{icon}</div>
                <div class="label">{label}</div>
                <div class="value" style="color: {color}; font-size: 1.3rem;">{value}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">📈</span>
        <h3>Weather Analysis</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    # Comfort Index Gauge
    with col1:
        st.markdown('<div class="chart-container"><div class="chart-title">🎯 Comfort Index</div>', unsafe_allow_html=True)
        
        comfort = 100 - abs(weather.temperature - 24) * 3 - abs(weather.humidity - 50) * 0.5
        comfort = max(0, min(100, comfort))
        
        fig_comfort = go.Figure(go.Indicator(
            mode="gauge+number",
            value=comfort,
            domain={'x': [0, 1], 'y': [0, 1]},
            number={'font': {'color': '#fff', 'size': 36}, 'suffix': '%'},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': '#666', 'tickfont': {'color': '#888'}},
                'bar': {'color': '#10b981' if comfort > 70 else '#f59e0b' if comfort > 40 else '#ef4444'},
                'bgcolor': 'rgba(255,255,255,0.1)',
                'borderwidth': 2,
                'bordercolor': '#333',
                'steps': [
                    {'range': [0, 40], 'color': 'rgba(239,68,68,0.2)'},
                    {'range': [40, 70], 'color': 'rgba(245,158,11,0.2)'},
                    {'range': [70, 100], 'color': 'rgba(16,185,129,0.2)'},
                ],
            }
        ))
        
        fig_comfort.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': '#fff'},
            height=280,
            margin=dict(l=20, r=20, t=30, b=20)
        )
        
        st.plotly_chart(fig_comfort, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    # Weather Radar
    with col2:
        st.markdown('<div class="chart-container"><div class="chart-title">📡 Weather Parameters</div>', unsafe_allow_html=True)
        
        temp_norm = min(100, max(0, (weather.temperature + 10) / 50 * 100))
        humidity_norm = weather.humidity
        wind_norm = min(100, weather.wind_speed / 60 * 100)
        visibility_norm = min(100, weather.visibility * 10)
        clouds_norm = weather.clouds
        
        fig_radar = go.Figure()
        
        fig_radar.add_trace(go.Scatterpolar(
            r=[temp_norm, humidity_norm, wind_norm, visibility_norm, clouds_norm],
            theta=['Temperature', 'Humidity', 'Wind', 'Visibility', 'Clouds'],
            fill='toself',
            fillcolor='rgba(59,130,246,0.3)',
            line=dict(color='#3b82f6', width=2),
            name='Current'
        ))
        
        fig_radar.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], gridcolor='rgba(255,255,255,0.1)'),
                angularaxis=dict(gridcolor='rgba(255,255,255,0.1)')
            ),
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': '#fff'},
            height=280,
            margin=dict(l=60, r=60, t=30, b=40),
            showlegend=False
        )
        
        st.plotly_chart(fig_radar, use_container_width=True)
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<br>", unsafe_allow_html=True)
    
    st.markdown("""
    <div class="section-header">
        <span class="section-icon">🚨</span>
        <h3>Weather Alerts</h3>
    </div>
    """, unsafe_allow_html=True)
    
    if weather.alerts:
        for alert in weather.alerts:
            st.markdown(f"""
            <div class="metric-card metric-card-danger" style="margin-bottom: 1rem; border-left: 4px solid #ef4444;">
                <div style="display: flex; align-items: flex-start; gap: 1rem;">
                    <div style="font-size: 2rem;">⚠️</div>
                    <div style="flex: 1;">
                        <div style="font-weight: 700; color: #ef4444; margin-bottom: 0.3rem;">
                            {alert.get('event', 'Weather Alert')}
                        </div>
                        <div style="color: #aaa; font-size: 0.9rem; margin-bottom: 0.5rem;">
                            {alert.get('description', 'No details available')[:200]}
                        </div>
                        <div style="color: #666; font-size: 0.8rem;">
                            📅 {alert.get('start', 'N/A')} → {alert.get('end', 'N/A')}
                        </div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div class="metric-card metric-card-safe" style="text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 0.5rem;">✅</div>
            <div style="font-size: 1.2rem; font-weight: 600; color: #10b981;">No Active Weather Alerts</div>
            <div style="color: #94a3b8; margin-top: 0.5rem;">Current conditions are normal for this area.</div>
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
                <div style="color: #94a3b8;">Current weather risk for {city}</div>
            </div>
        </div>
        <div style="border-top: 1px solid rgba(255,255,255,0.1); padding-top: 1rem;">
            <div style="font-weight: 600; color: #fff; margin-bottom: 0.5rem;">Contributing Factors:</div>
    """, unsafe_allow_html=True)
    
    for factor in risk_factors:
        factor_color = "#ef4444" if any(w in factor.lower() for w in ["extreme", "strong", "high", "alert"]) else "#f59e0b" if any(w in factor.lower() for w in ["moderate", "low"]) else "#10b981"
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
        <span class="section-icon">💡</span>
        <h3>Travel Recommendations</h3>
    </div>
    """, unsafe_allow_html=True)
    
    recommendations = []
    
    if weather.temperature > 35:
        recommendations.append(("🌡️", "Stay hydrated and avoid prolonged sun exposure"))
        recommendations.append(("👕", "Wear light, breathable clothing"))
    elif weather.temperature < 10:
        recommendations.append(("🧥", "Dress in warm layers"))
        recommendations.append(("☕", "Carry warm beverages"))
    
    if weather.humidity > 80:
        recommendations.append(("💧", "High humidity - stay in air-conditioned spaces"))
    
    if weather.wind_speed > 30:
        recommendations.append(("💨", "Strong winds expected - secure loose items"))
    
    if weather.visibility < 5:
        recommendations.append(("👁️", "Reduced visibility - drive carefully"))
    
    if "rain" in weather.description.lower():
        recommendations.append(("🌂", "Carry an umbrella or raincoat"))
    
    if not recommendations:
        recommendations.append(("✅", "Weather conditions are favorable for travel"))
        recommendations.append(("📱", "Keep checking for updates"))
    
    cols = st.columns(2)
    for idx, (icon, tip) in enumerate(recommendations):
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
        <span class="section-icon">📥</span>
        <h3>Report & Data</h3>
    </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div class="stat-card" style="padding: 1rem;">
            <div class="label">Data Source</div>
            <div style="color: #fff; font-weight: 600; font-size: 0.95rem; margin-top: 0.25rem;">{weather.source}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div class="stat-card" style="padding: 1rem;">
            <div class="label">Last Updated</div>
            <div style="color: #fff; font-weight: 600; font-size: 0.95rem; margin-top: 0.25rem;">{weather.fetched_at}</div>
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
    pdf_content = generate_weather_pdf_content(city, weather, risk_level, risk_factors)
    filename = f"TravelSafe_Weather_{city.replace(' ', '_')}_{datetime.now().strftime('%Y%m%d')}.html"
    
    st.markdown(create_download_link(pdf_content, filename), unsafe_allow_html=True)
    st.caption("*Report downloads as HTML file. Open in browser and print to PDF for best results.")
    
    st.markdown(f"""
    <div class="data-footer">
        <span class="dot"></span>
        <span>Updated {datetime.now().strftime('%I:%M %p')} • {weather.source} • Live data</span>
    </div>
    """, unsafe_allow_html=True)
    
    render_footer(module="weather")


if __name__ == "__main__":
    main()
else:
    main()
