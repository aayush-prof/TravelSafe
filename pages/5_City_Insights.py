"""
TravelSafe - City Insights
===========================

Comprehensive city information and safety planning:
- City profile from Wikipedia API (population, tourism, facts)
- Live travel alerts and advisories
- Persona-based travel tips
- Interactive Safety Planner (DO's and DON'Ts)
- Color-coded safety meter gauge
"""

import streamlit as st
import plotly.graph_objects as go
import requests
from datetime import datetime
from collections import Counter
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

# Import from core modules - reuse existing backend
from core.ui_components import (
    get_selected_city,
    get_selected_persona,
    render_metric_card,
    render_footer,
    get_safety_status,
    get_dark_chart_layout,
    get_event_color_map,
    get_event_icon_map,
)
from core.config import SUPPORTED_CITIES, SUPPORTED_CITIES_INTERNATIONAL
from core.data_cache import get_city_data

# Import services for PDF and logging
try:
    from core.services.pdf_report import generate_city_report, create_download_button
    from core.services.logger import log_info
    SERVICES_AVAILABLE = True
except ImportError:
    SERVICES_AVAILABLE = False
    def log_info(msg, module="city"): pass


@dataclass
class CityProfile:
    """City profile data structure."""
    name: str
    summary: str
    population: str
    country: str
    region: str
    tourism_info: str
    notable_facts: List[str]
    image_url: Optional[str]
    wiki_url: str
    fetched_at: str
    source: str


@st.cache_data(ttl=3600, show_spinner=False)  # Cache for 1 hour
def _fetch_city_profile_data(city: str) -> Dict[str, Any]:
    """
    Fetch city profile information from Wikipedia API.
    Returns a dict (pickle-serializable) for caching.
    
    Uses Wikipedia's REST API for summary and extract.
    Falls back to local data if API fails.
    """
    try:
        # Wikipedia REST API endpoint
        api_url = f"https://en.wikipedia.org/api/rest_v1/page/summary/{city.replace(' ', '_')}"
        
        headers = {
            "User-Agent": "TravelSafe/2.0 (Educational Travel Safety App)"
        }
        
        response = requests.get(api_url, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        # Extract summary
        summary = data.get("extract", "")
        
        # Parse population and other details from summary
        population = _extract_population(summary)
        tourism_info = _extract_tourism_info(city, summary)
        notable_facts = _extract_notable_facts(summary)
        
        # Get image if available
        image_url = None
        if "thumbnail" in data:
            image_url = data["thumbnail"].get("source")
        elif "originalimage" in data:
            image_url = data["originalimage"].get("source")
        
        return {
            "name": data.get("title", city),
            "summary": summary[:500] + "..." if len(summary) > 500 else summary,
            "population": population,
            "country": _get_country(city),
            "region": _get_region(city),
            "tourism_info": tourism_info,
            "notable_facts": notable_facts,
            "image_url": image_url,
            "wiki_url": data.get("content_urls", {}).get("desktop", {}).get("page", f"https://en.wikipedia.org/wiki/{city}"),
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "source": "Wikipedia API"
        }
        
    except Exception as e:
        return _generate_fallback_profile_data(city, str(e))


def fetch_city_profile_from_wikipedia(city: str) -> CityProfile:
    """Wrapper that converts cached dict to CityProfile dataclass."""
    data = _fetch_city_profile_data(city)
    return CityProfile(**data)


def _extract_population(text: str) -> str:
    """Extract population information from text."""
    import re
    
    # Common population patterns
    patterns = [
        r'population[^\d]*(\d[\d,\.]+\s*(million|billion|lakh|crore)?)',
        r'(\d[\d,\.]+\s*(million|billion))\s*people',
        r'(\d[\d,\.]+)\s*inhabitants',
    ]
    
    text_lower = text.lower()
    
    for pattern in patterns:
        match = re.search(pattern, text_lower)
        if match:
            return match.group(1).strip().title()
    
    return "Data not available"


def _extract_tourism_info(city: str, text: str) -> str:
    """Extract or generate tourism information."""
    tourism_keywords = ["tourist", "tourism", "attraction", "visit", "destination", "landmark"]
    
    # Check if text mentions tourism
    if any(kw in text.lower() for kw in tourism_keywords):
        # Find sentences about tourism
        sentences = text.split('.')
        for sent in sentences:
            if any(kw in sent.lower() for kw in tourism_keywords):
                return sent.strip() + "."
    
    # Fallback based on city
    return CITY_TOURISM_INFO.get(city, f"{city} offers diverse cultural experiences and attractions for visitors.")


def _extract_notable_facts(text: str) -> List[str]:
    """Extract notable facts from summary."""
    facts = []
    sentences = text.split('.')
    
    # Keywords that indicate interesting facts
    fact_keywords = ["known for", "famous", "largest", "oldest", "first", "capital", "major", "important"]
    
    for sent in sentences[:5]:  # Check first 5 sentences
        if any(kw in sent.lower() for kw in fact_keywords) and len(sent) > 30:
            facts.append(sent.strip() + ".")
            if len(facts) >= 3:
                break
    
    return facts if facts else ["A vibrant city with rich history", "Popular tourist destination", "Cultural and economic hub"]


def _get_country(city: str) -> str:
    """Get country for a city."""
    return CITY_COUNTRIES.get(city, "Various")


def _get_region(city: str) -> str:
    """Get region for a city."""
    return CITY_REGIONS.get(city, "Regional")


def _generate_fallback_profile_data(city: str, error: str) -> Dict[str, Any]:
    """Generate fallback profile data (dict) when Wikipedia API fails."""
    return {
        "name": city,
        "summary": CITY_SUMMARIES.get(city, f"{city} is a popular destination known for its unique culture and attractions."),
        "population": CITY_POPULATIONS.get(city, "Data unavailable"),
        "country": _get_country(city),
        "region": _get_region(city),
        "tourism_info": CITY_TOURISM_INFO.get(city, f"{city} offers diverse experiences for travelers."),
        "notable_facts": CITY_FACTS.get(city, ["Historic city", "Cultural center", "Tourist attraction"]),
        "image_url": None,
        "wiki_url": f"https://en.wikipedia.org/wiki/{city.replace(' ', '_')}",
        "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "source": f"Fallback Data ({error[:30]})"
    }


CITY_COUNTRIES = {
    "Delhi": "India", "Mumbai": "India", "Bangalore": "India", "Chennai": "India",
    "Kolkata": "India", "Hyderabad": "India", "Pune": "India", "Ahmedabad": "India",
    "Jaipur": "India", "Lucknow": "India", "Chandigarh": "India", "Goa": "India",
    "Kochi": "India", "Varanasi": "India", "Amritsar": "India", "Udaipur": "India",
    "Shimla": "India", "Darjeeling": "India", "Rishikesh": "India", "Mysore": "India",
    "New York": "USA", "Los Angeles": "USA", "San Francisco": "USA",
    "London": "United Kingdom", "Paris": "France", "Berlin": "Germany",
    "Tokyo": "Japan", "Singapore": "Singapore", "Dubai": "UAE",
    "Sydney": "Australia", "Toronto": "Canada", "Amsterdam": "Netherlands",
    "Bangkok": "Thailand", "Hong Kong": "China", "Rome": "Italy",
}

CITY_REGIONS = {
    "Delhi": "North India", "Mumbai": "West India", "Bangalore": "South India",
    "Chennai": "South India", "Kolkata": "East India", "Hyderabad": "South India",
    "Pune": "West India", "Ahmedabad": "West India", "Jaipur": "North India",
    "Lucknow": "North India", "Chandigarh": "North India", "Goa": "West India",
    "Kochi": "South India", "Varanasi": "North India", "Amritsar": "North India",
    "Udaipur": "North India", "Shimla": "North India", "Darjeeling": "East India",
    "Rishikesh": "North India", "Mysore": "South India",
    "New York": "North America", "Los Angeles": "North America", "San Francisco": "North America",
    "London": "Europe", "Paris": "Europe", "Berlin": "Europe",
    "Tokyo": "East Asia", "Singapore": "Southeast Asia", "Dubai": "Middle East",
    "Sydney": "Oceania", "Toronto": "North America", "Amsterdam": "Europe",
    "Bangkok": "Southeast Asia", "Hong Kong": "East Asia", "Rome": "Europe",
}

CITY_POPULATIONS = {
    "Delhi": "32 Million", "Mumbai": "21 Million", "Bangalore": "13 Million",
    "Chennai": "11 Million", "Kolkata": "15 Million", "Hyderabad": "10 Million",
    "Pune": "7 Million", "Ahmedabad": "8 Million", "Jaipur": "4 Million",
    "New York": "8.3 Million", "London": "9 Million", "Tokyo": "14 Million",
    "Singapore": "5.9 Million", "Dubai": "3.4 Million", "Paris": "2.2 Million",
    "Sydney": "5.3 Million", "Toronto": "2.9 Million", "Bangkok": "10.7 Million",
}

CITY_SUMMARIES = {
    "Delhi": "Delhi, India's capital territory, is a massive metropolitan area in the country's north. It's a city with a rich blend of ancient history and modernity, featuring Mughal-era monuments alongside contemporary architecture.",
    "Mumbai": "Mumbai is the financial capital of India and home to Bollywood. This coastal city is known for its colonial architecture, vibrant nightlife, and diverse culture.",
    "Bangalore": "Bangalore, officially Bengaluru, is the Silicon Valley of India. Known for its pleasant climate, gardens, and thriving tech industry.",
    "Tokyo": "Tokyo is Japan's busy capital, mixing ultramodern and traditional, from neon-lit skyscrapers to historic temples.",
    "Singapore": "Singapore is a global financial hub with a tropical climate and multicultural population.",
    "London": "London is England's capital and a 21st-century city with history stretching back to Roman times.",
}

CITY_TOURISM_INFO = {
    "Delhi": "Home to UNESCO World Heritage sites like Red Fort, Qutub Minar, and Humayun's Tomb. The city attracts millions of tourists annually.",
    "Mumbai": "Gateway of India, Marine Drive, and Elephanta Caves make Mumbai a top tourist destination with vibrant street food culture.",
    "Bangalore": "Known for Lalbagh Gardens, Bangalore Palace, and its thriving café culture. A hub for tech tourism.",
    "Jaipur": "The Pink City is famous for Amber Fort, Hawa Mahal, and City Palace. Part of the Golden Triangle tourist circuit.",
    "Goa": "India's beach paradise with Portuguese heritage, known for nightlife, water sports, and churches.",
    "Tokyo": "Ancient temples, cutting-edge technology, and world-class cuisine make Tokyo a unique destination.",
    "Singapore": "Gardens by the Bay, Marina Bay Sands, and diverse food scene attract millions yearly.",
    "Dubai": "Known for Burj Khalifa, luxury shopping, and desert safaris. A modern architectural marvel.",
}

CITY_FACTS = {
    "Delhi": ["Capital of India since 1911", "Has 3 UNESCO World Heritage Sites", "Home to one of the world's largest spice markets"],
    "Mumbai": ["Financial capital of India", "Largest film industry (Bollywood)", "Has Asia's oldest stock exchange"],
    "Tokyo": ["World's most populous metropolitan area", "Hosted 2020 Summer Olympics", "Home to over 200 Michelin-starred restaurants"],
    "Singapore": ["One of the world's cleanest cities", "Has the world's best airport", "A leading global financial center"],
}


@st.cache_data(ttl=1800, show_spinner=False)  # Cache for 30 minutes
def fetch_travel_alerts(city: str, country: str) -> List[Dict[str, Any]]:
    """
    Fetch travel alerts for a city/country.
    Uses a combination of sources and local knowledge.
    """
    alerts = []
    
    # Check for known advisories (simulated - would connect to real API in production)
    country_advisories = TRAVEL_ADVISORIES.get(country, [])
    alerts.extend(country_advisories)
    
    # Add city-specific alerts
    city_alerts = CITY_ALERTS.get(city, [])
    alerts.extend(city_alerts)
    
    return alerts


TRAVEL_ADVISORIES = {
    "India": [
        {"type": "health", "level": "info", "title": "Health Advisory", "message": "Ensure routine vaccinations are up to date. Drink only bottled water."},
    ],
    "Thailand": [
        {"type": "safety", "level": "caution", "title": "Monsoon Season", "message": "Heavy rainfall expected June-October. Check weather updates."},
    ],
    "UAE": [
        {"type": "culture", "level": "info", "title": "Cultural Guidelines", "message": "Dress modestly in public areas. Respect local customs during Ramadan."},
    ],
}

CITY_ALERTS = {
    "Delhi": [
        {"type": "air", "level": "warning", "title": "Air Quality Alert", "message": "Air quality may be poor during winter months (Nov-Feb). Consider carrying masks."},
    ],
    "Mumbai": [
        {"type": "weather", "level": "info", "title": "Monsoon Advisory", "message": "Heavy rains June-September may cause flooding. Plan accordingly."},
    ],
    "Goa": [
        {"type": "safety", "level": "info", "title": "Beach Safety", "message": "Swim only in designated areas with lifeguards. Watch for strong currents."},
    ],
}


PERSONA_TIPS = {
    "student": {
        "icon": "🎓",
        "name": "Student Traveler",
        "tips": [
            "🎫 Always carry your student ID for discounts at museums and attractions",
            "🏨 Consider hostels or budget accommodations for affordable stays",
            "🚌 Use public transport - it's cheaper and authentic",
            "📱 Download offline maps and translation apps",
            "🍜 Try street food for budget-friendly local cuisine",
            "👥 Join free walking tours to explore the city",
            "📚 Visit university campuses for cultural exchange",
        ],
        "priority": "Budget-friendly experiences",
    },
    "solo_female": {
        "icon": "👩",
        "name": "Solo Female Traveler",
        "tips": [
            "📍 Share your live location with family/friends",
            "🏨 Book accommodations in well-lit, central areas",
            "🚕 Use verified taxi apps rather than street hails",
            "👗 Research and respect local dress codes",
            "📱 Keep emergency numbers saved offline",
            "🌙 Avoid isolated areas after dark",
            "💬 Trust your instincts - if something feels wrong, leave",
            "👭 Connect with local women's groups or travel communities",
        ],
        "priority": "Safety and security first",
    },
    "family": {
        "icon": "👨‍👩‍👧‍👦",
        "name": "Family Traveler",
        "tips": [
            "🏨 Book family-friendly hotels with child amenities",
            "🎢 Plan activities suitable for all age groups",
            "🧸 Pack snacks and entertainment for kids",
            "🏥 Identify nearby hospitals and pharmacies",
            "⏰ Plan for rest time - avoid over-packed schedules",
            "🎟️ Book skip-the-line tickets for popular attractions",
            "🚗 Consider private transport for convenience",
        ],
        "priority": "Comfort and convenience",
    },
    "backpacker": {
        "icon": "🎒",
        "name": "Backpacker",
        "tips": [
            "🎒 Pack light - you'll thank yourself later",
            "🏨 Stay in hostels for social experiences and tips",
            "🚆 Use overnight trains/buses to save on accommodation",
            "🍜 Eat where locals eat for authentic cheap food",
            "📱 Have digital copies of all documents",
            "🔄 Stay flexible with your itinerary",
            "💵 Carry some cash for places without cards",
        ],
        "priority": "Authentic local experiences",
    },
    "elderly": {
        "icon": "👴",
        "name": "Senior Traveler",
        "tips": [
            "🏨 Choose accommodations with easy accessibility",
            "⏰ Avoid over-packed itineraries - take it slow",
            "💊 Keep all medications in carry-on luggage",
            "📋 Carry medical information card in local language",
            "🚶 Choose guided tours for comfort and safety",
            "🏥 Research medical facilities at destination",
            "📞 Get comprehensive travel insurance",
        ],
        "priority": "Comfort and health safety",
    },
}


def generate_safety_dos(event_counts: Dict[str, int], city: str, persona: str) -> List[str]:
    """Generate DO's based on event categories and persona."""
    dos = []
    
    # Base DO's for everyone
    dos.append("✅ Keep copies of important documents (passport, ID) separately")
    dos.append("✅ Register with your country's embassy if traveling internationally")
    dos.append("✅ Learn basic phrases in the local language")
    
    # Crime-related DO's
    if event_counts.get("crime", 0) > 0:
        dos.append("✅ Stay alert in crowded areas and tourist spots")
        dos.append("✅ Use hotel safes for valuables")
        dos.append("✅ Stick to well-lit, populated areas at night")
    
    # Weather-related DO's
    if event_counts.get("weather", 0) > 0:
        dos.append("✅ Check weather forecasts daily before going out")
        dos.append("✅ Carry appropriate gear (umbrella, jacket, sunscreen)")
        dos.append("✅ Have a backup indoor plan for bad weather days")
    
    # Accident/disaster DO's
    if event_counts.get("accident", 0) > 0 or event_counts.get("disaster", 0) > 0:
        dos.append("✅ Know emergency exit routes at your accommodation")
        dos.append("✅ Keep emergency numbers saved on your phone")
        dos.append("✅ Carry a basic first-aid kit")
    
    # Protest-related DO's
    if event_counts.get("protest", 0) > 0:
        dos.append("✅ Stay informed about local events and gatherings")
        dos.append("✅ Have alternative routes planned for your destinations")
    
    # Persona-specific DO's
    if persona == "solo_female":
        dos.append("✅ Share your itinerary with trusted contacts")
        dos.append("✅ Use women-friendly transport options when available")
    elif persona == "family":
        dos.append("✅ Establish a meeting point in case family gets separated")
        dos.append("✅ Keep children's identification on them at all times")
    elif persona == "elderly":
        dos.append("✅ Take regular breaks during sightseeing")
        dos.append("✅ Inform travel companions about medical conditions")
    
    return dos[:10]  # Limit to 10 items


def generate_safety_donts(event_counts: Dict[str, int], city: str, persona: str) -> List[str]:
    """Generate DON'Ts based on event categories and persona."""
    donts = []
    
    # Base DON'Ts for everyone
    donts.append("❌ Don't flash expensive jewelry or electronics")
    donts.append("❌ Don't leave bags unattended in public")
    donts.append("❌ Don't share travel plans with strangers")
    
    # Crime-related DON'Ts
    if event_counts.get("crime", 0) > 0:
        donts.append("❌ Don't walk alone in unfamiliar areas after dark")
        donts.append("❌ Don't carry large amounts of cash")
        donts.append("❌ Don't accept drinks from strangers")
    
    # Weather-related DON'Ts
    if event_counts.get("weather", 0) > 0:
        donts.append("❌ Don't ignore weather warnings or advisories")
        donts.append("❌ Don't venture outdoors during severe weather")
    
    # Accident/disaster DON'Ts
    if event_counts.get("accident", 0) > 0 or event_counts.get("disaster", 0) > 0:
        donts.append("❌ Don't ignore safety instructions at venues")
        donts.append("❌ Don't take unnecessary risks for photos")
    
    # Protest-related DON'Ts
    if event_counts.get("protest", 0) > 0:
        donts.append("❌ Don't get involved in local political demonstrations")
        donts.append("❌ Don't photograph protests or police activity")
    
    # Persona-specific DON'Ts
    if persona == "solo_female":
        donts.append("❌ Don't share your hotel room number with strangers")
        donts.append("❌ Don't take unlicensed taxis late at night")
    elif persona == "family":
        donts.append("❌ Don't let children wander unsupervised")
        donts.append("❌ Don't overpack the daily schedule")
    elif persona == "elderly":
        donts.append("❌ Don't skip meals or hydration while sightseeing")
        donts.append("❌ Don't forget to take prescribed medications")
    
    return donts[:10]


def main():
    st.markdown("""
    <div style="text-align: center; padding: 2rem 0 1.5rem 0;">
        <h1 style="color: #fff; margin: 0; font-size: 2.5rem; font-weight: 700;">🏙️ City Insights</h1>
        <p style="color: #9ca3af; margin: 0.75rem 0 0 0; font-size: 1.1rem;">Comprehensive city profile and personalized safety planning</p>
    </div>
    """, unsafe_allow_html=True)
    
    # Get selected city and persona from session state
    city = get_selected_city()
    persona = get_selected_persona()
    
    # Display current selection badges
    persona_labels = {
        "student": "🎓 Student",
        "solo_female": "👩 Solo Female",
        "family": "👨‍👩‍👧‍👦 Family",
        "backpacker": "🎒 Backpacker",
        "elderly": "👴 Senior",
    }
    
    st.markdown(f"""
    <div style="display: flex; justify-content: center; gap: 1rem; margin-bottom: 2rem; flex-wrap: wrap;">
        <span style="background: linear-gradient(135deg, rgba(139,92,246,0.15), rgba(139,92,246,0.25)); border: 1px solid rgba(139,92,246,0.4); padding: 0.6rem 1.25rem; border-radius: 25px; color: #a78bfa; font-weight: 500;">
            📍 {city}
        </span>
        <span style="background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(59,130,246,0.25)); border: 1px solid rgba(59,130,246,0.4); padding: 0.6rem 1.25rem; border-radius: 25px; color: #60a5fa; font-weight: 500;">
            {persona_labels.get(persona, persona)}
        </span>
    </div>
    """, unsafe_allow_html=True)
    
    cached_data = get_city_data(city, persona)
    events = cached_data.get("events", [])
    result = cached_data.get("result")

    if not events or result is None:
        st.warning("No events loaded yet. Please load data from the Home Dashboard.")
        render_footer(module="city")
        return

    st.session_state["unified_events"] = events

    with st.spinner("🔍 Loading city data..."):
        # Fetch city profile from Wikipedia
        city_profile = fetch_city_profile_from_wikipedia(city)
        
        # Fetch travel alerts
        alerts = fetch_travel_alerts(city, city_profile.country)
    
    # Show toast notification
    if "Wikipedia" in city_profile.source:
        st.toast(f"✅ City profile loaded from Wikipedia", icon="🏙️")
    else:
        st.toast(f"ℹ️ Using cached city data", icon="🏙️")
    
    log_info(f"City insights loaded for {city}", module="city")
    
    # Get safety status
    status_text, status_color, card_class, status_icon = get_safety_status(result.persona_index)
    
    # Event counts for Safety Planner
    event_counts = Counter(e.event_type for e in result.events)
    
    st.markdown("### 📖 City Profile")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Overview and key information about your destination</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns([2, 1])
    
    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 16px; padding: 1.75rem;">
            <h2 style="color: #fff; margin: 0 0 1rem 0; font-size: 1.8rem; font-weight: 700;">
                📍 {city_profile.name}
            </h2>
            <p style="color: #d1d5db; font-size: 0.95rem; line-height: 1.7; margin-bottom: 1.25rem;">
                {city_profile.summary}
            </p>
            <div style="display: grid; grid-template-columns: repeat(2, 1fr); gap: 1.25rem; margin-top: 1.25rem;">
                <div style="background: rgba(255,255,255,0.03); padding: 0.75rem 1rem; border-radius: 10px;">
                    <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">🌍 Country</div>
                    <div style="color: #fff; font-weight: 600; font-size: 1.1rem; margin-top: 0.25rem;">{city_profile.country}</div>
                </div>
                <div style="background: rgba(255,255,255,0.03); padding: 0.75rem 1rem; border-radius: 10px;">
                    <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">📌 Region</div>
                    <div style="color: #fff; font-weight: 600; font-size: 1.1rem; margin-top: 0.25rem;">{city_profile.region}</div>
                </div>
                <div style="background: rgba(255,255,255,0.03); padding: 0.75rem 1rem; border-radius: 10px;">
                    <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">👥 Population</div>
                    <div style="color: #fff; font-weight: 600; font-size: 1.1rem; margin-top: 0.25rem;">{city_profile.population}</div>
                </div>
                <div style="background: rgba(255,255,255,0.03); padding: 0.75rem 1rem; border-radius: 10px;">
                    <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">📊 Source</div>
                    <div style="color: #9ca3af; font-size: 0.95rem; margin-top: 0.25rem;">{city_profile.source}</div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        # Safety Meter Gauge
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 16px; padding: 1rem; text-align: center;">
            <div style="font-size: 1rem; font-weight: 600; color: #e2e8f0; margin-bottom: 0.5rem;">🛡️ Safety Meter</div>
        """, unsafe_allow_html=True)
        
        # Calculate gauge value (convert safety index to 0-100 scale)
        gauge_value = min(100, max(0, (result.persona_index + 10) * 5))
        
        fig_gauge = go.Figure(go.Indicator(
            mode="gauge+number",
            value=gauge_value,
            domain={'x': [0, 1], 'y': [0, 1]},
            title={'text': status_text, 'font': {'color': status_color, 'size': 14}},
            number={'font': {'color': '#fff', 'size': 28}, 'suffix': ''},
            gauge={
                'axis': {'range': [0, 100], 'tickcolor': '#475569', 'tickfont': {'color': '#94a3b8', 'size': 9}},
                'bar': {'color': status_color, 'thickness': 0.8},
                'bgcolor': 'rgba(255,255,255,0.05)',
                'borderwidth': 0,
                'steps': [
                    {'range': [0, 30], 'color': 'rgba(239,68,68,0.2)'},
                    {'range': [30, 60], 'color': 'rgba(249,115,22,0.2)'},
                    {'range': [60, 100], 'color': 'rgba(16,185,129,0.2)'},
                ],
                'threshold': {
                    'line': {'color': '#fff', 'width': 2},
                    'thickness': 0.75,
                    'value': gauge_value
                }
            }
        ))
        
        fig_gauge.update_layout(
            paper_bgcolor='rgba(0,0,0,0)',
            plot_bgcolor='rgba(0,0,0,0)',
            font={'color': '#fff'},
            height=200,
            margin=dict(l=15, r=15, t=25, b=5)
        )
        
        st.plotly_chart(fig_gauge, use_container_width=True)
        
        st.markdown(f"""
            <div style="text-align: center; color: #9ca3af; font-size: 0.8rem; padding-bottom: 0.5rem;">
                Safety Index: <span style="color: {status_color}; font-weight: 700;">{result.persona_index:+.1f}</span>
            </div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### ✨ Tourism & Highlights")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>What makes this destination special</p>", unsafe_allow_html=True)
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 16px; padding: 1.5rem; height: 100%;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;">
                <span style="font-size: 1.5rem;">🎯</span>
                <span style="font-size: 1.1rem; font-weight: 600; color: #e2e8f0;">Tourism Info</span>
            </div>
            <p style="color: #d1d5db; line-height: 1.7; margin: 0;">{city_profile.tourism_info}</p>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        facts_html = "".join([f'<li style="color: #d1d5db; margin-bottom: 0.6rem; line-height: 1.5;">{fact}</li>' for fact in city_profile.notable_facts])
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 16px; padding: 1.5rem; height: 100%;">
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 1rem;">
                <span style="font-size: 1.5rem;">📚</span>
                <span style="font-size: 1.1rem; font-weight: 600; color: #e2e8f0;">Notable Facts</span>
            </div>
            <ul style="padding-left: 1.2rem; margin: 0;">
                {facts_html}
            </ul>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### ⚠️ Travel Alerts & Advisories")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Active advisories for your destination</p>", unsafe_allow_html=True)
    
    if alerts:
        for alert in alerts:
            level_colors = {
                "warning": ("#ef4444", "🚨", "rgba(239,68,68,0.15)"),
                "caution": ("#f97316", "⚠️", "rgba(249,115,22,0.15)"),
                "info": ("#3b82f6", "ℹ️", "rgba(59,130,246,0.15)"),
            }
            color, icon, bg = level_colors.get(alert.get("level", "info"), ("#3b82f6", "ℹ️", "rgba(59,130,246,0.15)"))
            
            st.markdown(f"""
            <div style="background: {bg}; border: 1px solid {color}40; border-left: 4px solid {color}; border-radius: 12px; padding: 1rem 1.25rem; margin-bottom: 0.75rem;">
                <div style="display: flex; align-items: flex-start; gap: 1rem;">
                    <div style="font-size: 1.5rem; flex-shrink: 0;">{icon}</div>
                    <div style="flex: 1;">
                        <div style="color: {color}; font-weight: 600; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">
                            {alert.get('type', 'Alert')} Advisory
                        </div>
                        <div style="color: #fff; font-weight: 600; margin: 0.25rem 0; font-size: 1rem;">{alert.get('title', 'Advisory')}</div>
                        <div style="color: #d1d5db; font-size: 0.9rem; line-height: 1.5;">{alert.get('message', '')}</div>
                    </div>
                </div>
            </div>
            """, unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(16,185,129,0.05)); border: 1px solid rgba(16,185,129,0.3); border-radius: 16px; text-align: center; padding: 2rem;">
            <div style="font-size: 3rem; margin-bottom: 0.75rem;">✅</div>
            <div style="font-size: 1.2rem; font-weight: 600; color: #10b981;">No Active Travel Alerts</div>
            <div style="color: #9ca3af; margin-top: 0.5rem; font-size: 0.95rem;">No significant advisories for this destination at this time.</div>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    persona_info = PERSONA_TIPS.get(persona, PERSONA_TIPS["student"])
    
    st.markdown(f"### {persona_info['icon']} Travel Tips for {persona_info['name']}")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Personalized recommendations for your travel style</p>", unsafe_allow_html=True)
    
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(139,92,246,0.1), rgba(59,130,246,0.1)); border: 1px solid rgba(139,92,246,0.3); border-radius: 16px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem;">
        <div style="display: flex; align-items: center; gap: 1rem;">
            <div style="font-size: 3rem;">{persona_info['icon']}</div>
            <div>
                <div style="font-size: 1.3rem; font-weight: 700; color: #fff;">{persona_info['name']}</div>
                <div style="color: #a78bfa; font-size: 0.9rem;">Priority: {persona_info['priority']}</div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    cols = st.columns(2)
    for idx, tip in enumerate(persona_info['tips']):
        with cols[idx % 2]:
            st.markdown(f"""
            <div style="background: rgba(30,41,59,0.6); border: 1px solid rgba(71,85,105,0.3); border-radius: 10px; padding: 0.75rem 1rem; margin-bottom: 0.5rem;">
                <span style="color: #e2e8f0; font-size: 0.9rem;">{tip}</span>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 🗓️ Safety Planner")
    st.markdown(f"<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Personalized recommendations based on recent events in {city}</p>", unsafe_allow_html=True)
    
    # Generate DO's and DON'Ts
    dos = generate_safety_dos(event_counts, city, persona)
    donts = generate_safety_donts(event_counts, city, persona)
    
    col1, col2 = st.columns(2)
    
    # DO's Card
    with col1:
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(16,185,129,0.1), rgba(16,185,129,0.05)); border: 2px solid rgba(16,185,129,0.3); border-radius: 16px; padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem;">
                <span style="font-size: 2rem;">✅</span>
                <span style="font-size: 1.4rem; font-weight: 700; color: #10b981;">DO's</span>
            </div>
        """, unsafe_allow_html=True)
        
        for do_item in dos:
            st.markdown(f"""
            <div style="display: flex; align-items: flex-start; gap: 0.6rem; margin-bottom: 0.7rem; padding-left: 0.25rem;">
                <span style="color: #10b981; font-weight: bold; font-size: 1rem;">•</span>
                <span style="color: #d1d5db; font-size: 0.9rem; line-height: 1.4;">{do_item.replace('✅ ', '')}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    # DON'Ts Card
    with col2:
        st.markdown("""
        <div style="background: linear-gradient(135deg, rgba(239,68,68,0.1), rgba(239,68,68,0.05)); border: 2px solid rgba(239,68,68,0.3); border-radius: 16px; padding: 1.5rem;">
            <div style="display: flex; align-items: center; gap: 0.75rem; margin-bottom: 1.25rem;">
                <span style="font-size: 2rem;">❌</span>
                <span style="font-size: 1.4rem; font-weight: 700; color: #ef4444;">DON'Ts</span>
            </div>
        """, unsafe_allow_html=True)
        
        for dont_item in donts:
            st.markdown(f"""
            <div style="display: flex; align-items: flex-start; gap: 0.6rem; margin-bottom: 0.7rem; padding-left: 0.25rem;">
                <span style="color: #ef4444; font-weight: bold; font-size: 1rem;">•</span>
                <span style="color: #d1d5db; font-size: 0.9rem; line-height: 1.4;">{dont_item.replace('❌ ', '')}</span>
            </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 📊 Recent Events Summary")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Overview of recent events by category</p>", unsafe_allow_html=True)
    
    color_map = get_event_color_map()
    icon_map = get_event_icon_map()
    
    cols = st.columns(4)
    
    metrics = [
        ("crime", "Crime", event_counts.get("crime", 0)),
        ("weather", "Weather", event_counts.get("weather", 0)),
        ("accident", "Accidents", event_counts.get("accident", 0)),
        ("positive", "Positive", event_counts.get("positive", 0)),
    ]
    
    for idx, (event_type, label, count) in enumerate(metrics):
        with cols[idx]:
            icon = icon_map.get(event_type, "📰")
            color = color_map.get(event_type, "#6b7280")
            
            st.markdown(f"""
            <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 12px; text-align: center; padding: 1.25rem 0.75rem;">
                <div style="font-size: 2rem; margin-bottom: 0.4rem;">{icon}</div>
                <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">{label}</div>
                <div style="font-size: 2rem; font-weight: 700; color: {color}; margin-top: 0.25rem;">{count}</div>
            </div>
            """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 📚 Sources & More Info")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Data attribution and additional resources</p>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 12px; text-align: center; padding: 1.25rem;">
            <div style="font-size: 1.75rem; margin-bottom: 0.5rem;">📖</div>
            <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">City Profile</div>
            <div style="color: #e2e8f0; font-weight: 600; font-size: 0.9rem; margin-top: 0.25rem;">{city_profile.source}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col2:
        st.markdown(f"""
        <div style="background: linear-gradient(135deg, rgba(30,41,59,0.8), rgba(15,23,42,0.9)); border: 1px solid rgba(71,85,105,0.3); border-radius: 12px; text-align: center; padding: 1.25rem;">
            <div style="font-size: 1.75rem; margin-bottom: 0.5rem;">⏱️</div>
            <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">Last Updated</div>
            <div style="color: #e2e8f0; font-weight: 600; font-size: 0.9rem; margin-top: 0.25rem;">{city_profile.fetched_at}</div>
        </div>
        """, unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"""
        <a href="{city_profile.wiki_url}" target="_blank" style="text-decoration: none; display: block;">
            <div style="background: linear-gradient(135deg, rgba(59,130,246,0.15), rgba(59,130,246,0.1)); border: 1px solid rgba(59,130,246,0.3); border-radius: 12px; text-align: center; padding: 1.25rem; transition: all 0.2s;">
                <div style="font-size: 1.75rem; margin-bottom: 0.5rem;">🔗</div>
                <div style="color: #9ca3af; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.5px;">Learn More</div>
                <div style="color: #60a5fa; font-weight: 600; font-size: 0.9rem; margin-top: 0.25rem;">Wikipedia →</div>
            </div>
        </a>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1.5rem;'></div>", unsafe_allow_html=True)
    
    st.markdown("### 📥 Download Report")
    st.markdown("<p style='color: #9ca3af; margin-top: -0.5rem; margin-bottom: 1.25rem;'>Get a comprehensive PDF of your city insights</p>", unsafe_allow_html=True)
    
    if SERVICES_AVAILABLE:
        # Generate DO's and DON'Ts for report
        dos = generate_safety_dos(event_counts, city, persona)
        donts = generate_safety_donts(event_counts, city, persona)
        
        # Get persona tips
        persona_info = PERSONA_TIPS.get(persona, PERSONA_TIPS["student"])
        
        # Generate report
        report_html = generate_city_report(
            city=city,
            country=city_profile.country,
            population=city_profile.population,
            summary=city_profile.summary,
            tourism_info=city_profile.tourism_info,
            notable_facts=city_profile.notable_facts,
            safety_index=result.persona_index,
            dos=dos,
            donts=donts,
            persona_tips=persona_info.get('tips', []),
        )
        
        col1, col2, col3 = st.columns([1, 1, 1])
        with col2:
            create_download_button(
                html_content=report_html,
                filename=f"TravelSafe_CityInsights_{city}_{datetime.now().strftime('%Y%m%d')}.html",
                button_text="📥 Download City Report",
                button_color="#8b5cf6"
            )
        
        st.markdown("<p style='color: #6b7280; font-size: 0.8rem; text-align: center; margin-top: 0.75rem;'>*Report downloads as HTML. Open in browser and print to PDF for best results.</p>", unsafe_allow_html=True)
    else:
        st.markdown("""
        <div style="background: rgba(59,130,246,0.1); border: 1px solid rgba(59,130,246,0.3); border-radius: 12px; padding: 1rem; text-align: center;">
            <span style="color: #60a5fa;">📄 PDF report generation not available.</span>
        </div>
        """, unsafe_allow_html=True)
    
    st.markdown("<div style='height: 1rem;'></div>", unsafe_allow_html=True)
    
    render_footer(module="news")


if __name__ == "__main__":
    main()
else:
    main()
