"""
TravelSafe PDF Report Generator
================================

Auto-generates downloadable PDF/HTML reports for all pages:
- Safety Dashboard Report
- Weather Alerts Report
- Crime Watch Report
- City Insights Report

Reports are generated as HTML (for rich formatting) and can be
printed to PDF using browser's print function.
"""

import base64
from datetime import datetime
from typing import List, Dict, Any, Optional
import streamlit as st

from .logger import log_info, log_error


def _get_base_template() -> str:
    """Get base HTML template with styling."""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>
            * {{ box-sizing: border-box; }}
            body {{ 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                padding: 40px; 
                color: #333;
                max-width: 900px;
                margin: 0 auto;
                line-height: 1.6;
            }}
            h1 {{ 
                color: #1e3a5f; 
                border-bottom: 3px solid {accent_color}; 
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            h2 {{ color: {accent_color}; margin-top: 30px; }}
            h3 {{ color: #4b5563; margin-top: 25px; }}
            .header {{ 
                background: linear-gradient(135deg, #f8fafc 0%, #e2e8f0 100%);
                padding: 25px; 
                border-radius: 12px; 
                margin-bottom: 25px;
                border-left: 5px solid {accent_color};
            }}
            .metric-box {{
                display: inline-block;
                background: #fff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 15px 25px;
                margin: 8px;
                text-align: center;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
            }}
            .metric-value {{ 
                font-size: 28px; 
                font-weight: bold; 
                color: {accent_color}; 
            }}
            .metric-label {{ 
                font-size: 12px; 
                color: #6b7280;
                text-transform: uppercase;
                letter-spacing: 0.5px;
            }}
            .status-safe {{ background: #dcfce7; border-color: #10b981; color: #166534; }}
            .status-warning {{ background: #fef3c7; border-color: #f59e0b; color: #92400e; }}
            .status-danger {{ background: #fee2e2; border-color: #ef4444; color: #991b1b; }}
            .status-box {{
                padding: 15px 20px;
                border-radius: 8px;
                border-left: 5px solid;
                margin: 15px 0;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin: 15px 0;
            }}
            th, td {{
                padding: 12px;
                text-align: left;
                border-bottom: 1px solid #e5e7eb;
            }}
            th {{
                background: #f9fafb;
                font-weight: 600;
                color: #374151;
            }}
            tr:hover {{ background: #f9fafb; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 8px; }}
            .footer {{
                margin-top: 40px;
                padding-top: 20px;
                border-top: 2px solid #e5e7eb;
                font-size: 12px;
                color: #9ca3af;
                text-align: center;
            }}
            .grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 15px; }}
            .card {{
                background: #fff;
                border: 1px solid #e5e7eb;
                border-radius: 8px;
                padding: 15px;
            }}
            @media print {{
                body {{ padding: 20px; }}
                .no-print {{ display: none; }}
            }}
        </style>
    </head>
    <body>
        {content}
        <div class="footer">
            <p>🛡️ <strong>TravelSafe</strong> — Your AI-powered travel safety companion</p>
            <p>Generated on {timestamp} • Data refreshes every 5-15 minutes</p>
        </div>
    </body>
    </html>
    """


def generate_safety_report(
    city: str,
    safety_index: float,
    base_index: float,
    total_events: int,
    event_counts: Dict[str, int],
    persona: str,
    events: List[Dict[str, Any]] = None,
) -> str:
    """
    Generate comprehensive safety dashboard report.
    
    Args:
        city: City name
        safety_index: Persona-adjusted safety index
        base_index: Raw safety index
        total_events: Total number of events
        event_counts: Event counts by type
        persona: Selected persona name
        events: Optional list of event dicts
        
    Returns:
        HTML string for the report
    """
    try:
        # Determine status
        if safety_index >= 5:
            status = ("VERY SAFE", "status-safe", "#10b981")
        elif safety_index >= 2:
            status = ("SAFE", "status-safe", "#10b981")
        elif safety_index >= -2:
            status = ("MODERATE", "status-warning", "#f59e0b")
        elif safety_index >= -5:
            status = ("CAUTION", "status-warning", "#f59e0b")
        else:
            status = ("HIGH RISK", "status-danger", "#ef4444")
        
        status_text, status_class, accent_color = status
        
        # Build metrics HTML
        metrics_html = f"""
        <div class="metric-box">
            <div class="metric-value">{safety_index:+.1f}</div>
            <div class="metric-label">Safety Index</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{base_index:+.1f}</div>
            <div class="metric-label">Base Index</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{total_events}</div>
            <div class="metric-label">Total Events</div>
        </div>
        """
        
        # Build event breakdown HTML
        events_html = "<h2>📊 Event Breakdown</h2><div class='grid'>"
        event_icons = {
            "crime": "🚔", "protest": "📢", "accident": "🚗",
            "disaster": "🌪️", "weather": "⛈️", "positive": "🎉", "neutral": "📰"
        }
        for event_type, count in event_counts.items():
            icon = event_icons.get(event_type, "📰")
            events_html += f"""
            <div class="card">
                <strong>{icon} {event_type.title()}</strong>: {count} events
            </div>
            """
        events_html += "</div>"
        
        # Build events table if provided
        events_table_html = ""
        if events:
            events_table_html = """
            <h2>📰 Recent Events</h2>
            <table>
                <tr><th>Event</th><th>Type</th><th>Severity</th></tr>
            """
            for event in events[:15]:
                events_table_html += f"""
                <tr>
                    <td>{event.get('title', 'N/A')[:60]}...</td>
                    <td>{event.get('type', 'N/A').title()}</td>
                    <td>{event.get('severity', 0):+d}</td>
                </tr>
                """
            events_table_html += "</table>"
        
        # Build full content
        content = f"""
        <h1>🛡️ TravelSafe Safety Report</h1>
        
        <div class="header">
            <h2 style="margin: 0 0 10px 0;">📍 {city}</h2>
            <p style="margin: 0; color: #6b7280;">Persona: {persona.replace('_', ' ').title()}</p>
        </div>
        
        <h2>📈 Safety Metrics</h2>
        {metrics_html}
        
        <div class="status-box {status_class}">
            <strong>Overall Status: {status_text}</strong>
            <p style="margin: 5px 0 0 0;">
                Based on analysis of {total_events} recent events in {city}.
            </p>
        </div>
        
        {events_html}
        
        {events_table_html}
        
        <h2>💡 Recommendations</h2>
        <ul>
            <li>Stay informed about local news and updates</li>
            <li>Keep emergency contacts readily available</li>
            <li>Follow local guidelines and regulations</li>
            <li>Register with your embassy if traveling internationally</li>
        </ul>
        """
        
        html = _get_base_template().format(
            title=f"Safety Report - {city}",
            accent_color=accent_color,
            content=content,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p")
        )
        
        log_info(f"Generated safety report for {city}", module="pdf")
        return html
        
    except Exception as e:
        log_error(f"Failed to generate safety report for {city}", module="pdf", exc=e)
        return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"


def generate_weather_report(
    city: str,
    temperature: float,
    feels_like: float,
    humidity: int,
    description: str,
    wind_speed: float,
    alerts: List[Dict[str, Any]] = None,
    risk_level: str = "Low",
    recommendations: List[str] = None,
) -> str:
    """Generate weather alerts report."""
    try:
        # Determine accent color based on risk
        accent_colors = {
            "LOW": "#10b981",
            "MODERATE": "#f59e0b", 
            "ELEVATED": "#f97316",
            "HIGH": "#ef4444",
        }
        accent_color = accent_colors.get(risk_level.upper().split()[0], "#3b82f6")
        
        # Build alerts HTML
        alerts_html = ""
        if alerts:
            alerts_html = "<h2>⚠️ Active Alerts</h2>"
            for alert in alerts:
                alerts_html += f"""
                <div class="status-box status-warning">
                    <strong>{alert.get('event', 'Alert')}</strong>
                    <p style="margin: 5px 0 0 0;">{alert.get('description', '')[:200]}</p>
                </div>
                """
        else:
            alerts_html = """
            <div class="status-box status-safe">
                <strong>✅ No Active Weather Alerts</strong>
                <p style="margin: 5px 0 0 0;">Weather conditions are favorable for travel.</p>
            </div>
            """
        
        # Build recommendations HTML
        recs_html = ""
        if recommendations:
            recs_html = "<h2>💡 Recommendations</h2><ul>"
            for rec in recommendations:
                recs_html += f"<li>{rec}</li>"
            recs_html += "</ul>"
        
        content = f"""
        <h1>🌤️ Weather Report</h1>
        
        <div class="header">
            <h2 style="margin: 0 0 10px 0;">📍 {city}</h2>
            <p style="margin: 0; color: #6b7280;">{description}</p>
        </div>
        
        <h2>🌡️ Current Conditions</h2>
        <div class="metric-box">
            <div class="metric-value">{temperature}°C</div>
            <div class="metric-label">Temperature</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{feels_like}°C</div>
            <div class="metric-label">Feels Like</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{humidity}%</div>
            <div class="metric-label">Humidity</div>
        </div>
        <div class="metric-box">
            <div class="metric-value">{wind_speed}</div>
            <div class="metric-label">Wind (km/h)</div>
        </div>
        
        {alerts_html}
        
        {recs_html}
        """
        
        html = _get_base_template().format(
            title=f"Weather Report - {city}",
            accent_color=accent_color,
            content=content,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p")
        )
        
        log_info(f"Generated weather report for {city}", module="pdf")
        return html
        
    except Exception as e:
        log_error(f"Failed to generate weather report for {city}", module="pdf", exc=e)
        return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"


def generate_crime_report(
    city: str,
    total_count: int,
    risk_level: str,
    risk_factors: List[str],
    news_items: List[Dict[str, Any]] = None,
    recommendations: List[str] = None,
) -> str:
    """Generate crime watch report."""
    try:
        # Determine accent color
        accent_colors = {
            "LOW": "#10b981",
            "MODERATE": "#f59e0b",
            "ELEVATED": "#f97316", 
            "HIGH": "#ef4444",
        }
        risk_key = risk_level.upper().split()[0]
        accent_color = accent_colors.get(risk_key, "#ef4444")
        status_class = "status-safe" if risk_key == "LOW" else "status-warning" if risk_key in ["MODERATE", "ELEVATED"] else "status-danger"
        
        # Build risk factors HTML
        factors_html = "<ul>"
        for factor in risk_factors:
            factors_html += f"<li>{factor}</li>"
        factors_html += "</ul>"
        
        # Build news table
        news_html = ""
        if news_items:
            news_html = """
            <h2>📰 Recent Crime Reports</h2>
            <table>
                <tr><th>Report</th><th>Source</th><th>Date</th></tr>
            """
            for item in news_items[:10]:
                title = item.get('title', 'N/A')
                if len(title) > 60:
                    title = title[:60] + "..."
                news_html += f"""
                <tr>
                    <td>{title}</td>
                    <td>{item.get('source', 'N/A')}</td>
                    <td>{item.get('date', 'N/A')}</td>
                </tr>
                """
            news_html += "</table>"
        
        content = f"""
        <h1>🚔 Crime Watch Report</h1>
        
        <div class="header">
            <h2 style="margin: 0 0 10px 0;">📍 {city}</h2>
            <p style="margin: 0; color: #6b7280;">{total_count} crime reports analyzed</p>
        </div>
        
        <h2>⚠️ Risk Assessment</h2>
        <div class="status-box {status_class}">
            <strong>Risk Level: {risk_level}</strong>
        </div>
        
        <h3>Risk Factors</h3>
        {factors_html}
        
        {news_html}
        
        <h2>🛡️ Safety Recommendations</h2>
        <ul>
            <li>Stay aware of your surroundings at all times</li>
            <li>Avoid isolated areas, especially at night</li>
            <li>Keep valuables secure and out of sight</li>
            <li>Save local emergency numbers on your phone</li>
            <li>Share your itinerary with trusted contacts</li>
        </ul>
        
        <h2>📞 Emergency Contacts</h2>
        <ul>
            <li><strong>Police:</strong> 100 (India) / 911 (USA) / 999 (UK)</li>
            <li><strong>Ambulance:</strong> 102 (India) / 911 (USA) / 999 (UK)</li>
            <li><strong>Women Helpline:</strong> 181 (India)</li>
        </ul>
        """
        
        html = _get_base_template().format(
            title=f"Crime Report - {city}",
            accent_color=accent_color,
            content=content,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p")
        )
        
        log_info(f"Generated crime report for {city}", module="pdf")
        return html
        
    except Exception as e:
        log_error(f"Failed to generate crime report for {city}", module="pdf", exc=e)
        return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"


def generate_city_report(
    city: str,
    country: str,
    population: str,
    summary: str,
    tourism_info: str,
    notable_facts: List[str],
    safety_index: float,
    dos: List[str] = None,
    donts: List[str] = None,
    persona_tips: List[str] = None,
) -> str:
    """Generate city insights report."""
    try:
        # Determine accent color based on safety
        if safety_index >= 2:
            accent_color = "#10b981"
        elif safety_index >= -2:
            accent_color = "#f59e0b"
        else:
            accent_color = "#ef4444"
        
        # Build facts HTML
        facts_html = "<ul>"
        for fact in notable_facts:
            facts_html += f"<li>{fact}</li>"
        facts_html += "</ul>"
        
        # Build tips HTML
        tips_html = ""
        if persona_tips:
            tips_html = "<h2>🎯 Personalized Tips</h2><ul>"
            for tip in persona_tips:
                tips_html += f"<li>{tip}</li>"
            tips_html += "</ul>"
        
        # Build safety planner HTML
        planner_html = ""
        if dos or donts:
            planner_html = "<h2>🗓️ Safety Planner</h2><div class='grid'>"
            if dos:
                planner_html += "<div class='card' style='border-left: 4px solid #10b981;'><h3>✅ DO's</h3><ul>"
                for do in dos[:8]:
                    planner_html += f"<li>{do.replace('✅ ', '')}</li>"
                planner_html += "</ul></div>"
            if donts:
                planner_html += "<div class='card' style='border-left: 4px solid #ef4444;'><h3>❌ DON'Ts</h3><ul>"
                for dont in donts[:8]:
                    planner_html += f"<li>{dont.replace('❌ ', '')}</li>"
                planner_html += "</ul></div>"
            planner_html += "</div>"
        
        content = f"""
        <h1>🏙️ City Insights Report</h1>
        
        <div class="header">
            <h2 style="margin: 0 0 10px 0;">📍 {city}</h2>
            <p style="margin: 0; color: #6b7280;">{country} • Population: {population}</p>
        </div>
        
        <h2>📖 About {city}</h2>
        <p>{summary}</p>
        
        <h2>🎯 Tourism Information</h2>
        <p>{tourism_info}</p>
        
        <h2>📚 Notable Facts</h2>
        {facts_html}
        
        <h2>📈 Safety Score</h2>
        <div class="metric-box">
            <div class="metric-value">{safety_index:+.1f}</div>
            <div class="metric-label">Safety Index</div>
        </div>
        
        {tips_html}
        
        {planner_html}
        """
        
        html = _get_base_template().format(
            title=f"City Insights - {city}",
            accent_color=accent_color,
            content=content,
            timestamp=datetime.now().strftime("%B %d, %Y at %I:%M %p")
        )
        
        log_info(f"Generated city report for {city}", module="pdf")
        return html
        
    except Exception as e:
        log_error(f"Failed to generate city report for {city}", module="pdf", exc=e)
        return f"<html><body><h1>Error generating report</h1><p>{str(e)}</p></body></html>"


def create_download_button(
    html_content: str,
    filename: str,
    button_text: str = "📥 Download Report",
    button_color: str = "#3b82f6",
) -> None:
    """
    Create a styled download button in Streamlit.
    
    Args:
        html_content: HTML content to download
        filename: Filename for download
        button_text: Button label
        button_color: Button background color
    """
    try:
        b64 = base64.b64encode(html_content.encode()).decode()
        
        st.markdown(f"""
        <a href="data:text/html;base64,{b64}" download="{filename}" style="text-decoration: none;">
            <button style="
                background: {button_color};
                color: white;
                padding: 12px 24px;
                border: none;
                border-radius: 8px;
                cursor: pointer;
                font-weight: 600;
                font-size: 14px;
                display: inline-flex;
                align-items: center;
                gap: 8px;
                transition: all 0.2s;
            "
            onmouseover="this.style.transform='translateY(-2px)'; this.style.boxShadow='0 4px 12px rgba(0,0,0,0.2)';"
            onmouseout="this.style.transform='translateY(0)'; this.style.boxShadow='none';"
            >
                {button_text}
            </button>
        </a>
        """, unsafe_allow_html=True)
        
    except Exception as e:
        log_error(f"Failed to create download button", module="pdf", exc=e)
        st.error("Could not create download button")
