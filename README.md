# TravelSafe - Comprehensive City Travel Safety Platform

[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/downloads/)
[![Streamlit](https://img.shields.io/badge/Streamlit-1.0+-FF4B4B.svg)](https://streamlit.io/)
[![License: MIT](https://img.shields.io/badge/License-Educational-green.svg)](LICENSE)

## Project Description

**TravelSafe** is a sophisticated multi-page Streamlit application that provides comprehensive safety intelligence for travelers visiting cities worldwide. The platform analyzes multiple data sources including news events, weather conditions, crime reports, and city profiles to deliver actionable safety insights.

The application supports **50+ cities** (both Indian and international) and features a **multi-page dashboard architecture** with specialized modules for different safety aspects. Each analysis is personalized using **5 traveler personas** that adjust risk assessments based on individual travel profiles and safety priorities.

The core innovation is the **Travel Safety Index** (-10 to +10 scale) that combines real-time event classification, severity scoring, and persona-based risk weighting to provide personalized safety recommendations for different types of travelers.

---

## Key Features

### Multi-Page Dashboard Architecture
- **Dashboard (Home)**: Overview metrics, safety index, quick insights with PDF report generation
- **Events**: Detailed event analysis with filterable categories and interactive visualizations
- **Weather Alerts**: Real-time weather monitoring with risk assessments and forecasts
- **Crime Watch**: Crime news aggregation, categorization, and trend analysis
- **City Insights**: Wikipedia-powered city profiles, travel tips, and safety planners

### Comprehensive City Coverage
- **45+ Supported Cities**: 30 Indian cities + 15 international destinations
- **Dynamic City Management**: Add/remove cities programmatically
- **Regional Categorization**: India vs International city classification

### Intelligent Event Classification
- **NLP-Powered Classification**: Rule-based keyword matching for event categorization
- **6 Event Categories**: Crime, Protest, Accident, Disaster, Weather, Neutral/Positive
- **Severity Scoring**: -3 (severe negative) to +3 (positive) impact assessment
- **Confidence Scoring**: Classification reliability metrics

### Persona-Based Risk Assessment
- **5 Traveler Personas**: Student, Solo Female, Family, Backpacker, Elderly
- **Custom Risk Weights**: Event-type specific multipliers per persona
- **Personalized Index**: Adjusted safety scores reflecting individual risk priorities

### Advanced Data Services
- **Intelligent Caching**: TTL-based caching with session state management
- **Error Handling**: Graceful degradation with fallback to sample data
- **PDF Report Generation**: Downloadable safety reports per module
- **Structured Logging**: Comprehensive activity tracking and debugging

### Modern UI/UX
- **Dark Mode Design**: Professional SaaS-style interface
- **Responsive Layout**: Wide layout with collapsible sidebar
- **Interactive Visualizations**: Plotly charts with hover interactions
- **Color-Coded Metrics**: Status indicators with gradient styling

---

## Tech Stack

| Technology | Purpose |
|------------|---------|
| **Python 3.9+** | Core programming language |
| **Streamlit** | Multi-page dashboard framework with session state |
| **Pydantic** | Data validation, models, and type safety |
| **Pandas** | Data manipulation and analysis |
| **NumPy** | Numerical operations and calculations |
| **Scikit-learn** | Machine learning utilities and text processing |
| **Plotly** | Interactive charts (bar, gauge, timeline) |
| **Requests** | HTTP API calls for news, weather, Wikipedia |
| **python-dotenv** | Environment variable management |
| **PyArrow** | Streamlit data serialization |

### External APIs (Optional)
- **NewsAPI** / **GNews API**: News article aggregation
- **OpenWeatherMap API**: Real-time weather data
- **Wikipedia REST API**: City profiles and information

---

## Setup & Installation

### Prerequisites
- **Python 3.9+** (recommended: Python 3.10 or 3.11)
- **pip** package manager
- **(Optional)** API keys for live data sources

### Step-by-Step Setup

1. **Clone or download this repository**
   ```bash
   cd "Travel safe"
   ```

2. **Create a virtual environment**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment**
   
   - **Windows (PowerShell)**:
     ```powershell
     .\venv\Scripts\Activate.ps1
     ```
   
   - **Windows (Command Prompt)**:
     ```cmd
     venv\Scripts\activate.bat
     ```
   
   - **macOS/Linux**:
     ```bash
     source venv/bin/activate
     ```

4. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

5. **(Optional) Configure API keys for live data**
   
   Create a `.env` file in the root directory with:
   ```env
   # News API (get free key from https://newsapi.org/)
   NEWS_API_KEY=your_news_api_key_here
   
   # GNews API (get free key from https://gnews.io/)
   GNEWS_API_KEY=your_gnews_api_key_here
   
   # OpenWeatherMap API (get free key from https://openweathermap.org/)
   WEATHER_API_KEY=your_weather_api_key_here
   ```
   
   **Note**: App works with sample data if API keys are not configured.

6. **Run the application**
   ```bash
   streamlit run app.py
   ```

7. **Open in browser**
   - Streamlit will automatically open at `http://localhost:8501`
   - Use the sidebar to navigate between pages

---

## How the Travel Safety Index Works

### Base Index Calculation

1. **Event Classification**: Each news item is classified into one of 6 categories:
   - `crime` (murders, theft, assault, etc.)
   - `protest` (rallies, strikes, demonstrations)
   - `accident` (road accidents, fires, etc.)
   - `disaster` (earthquakes, floods, etc.)
   - `weather` (storms, heatwaves, etc.)
   - `neutral` (general news, positive events)

2. **Severity Assignment**: Each event gets a severity score from **-3 to +3**:
   - `-3`: Very negative (e.g., murder, major disaster)
   - `-2`: Moderately negative (e.g., robbery, protest)
   - `-1`: Slightly negative (e.g., minor accident)
   - `0`: Neutral
   - `+1` to `+3`: Positive events (rare in news)

3. **Aggregation Formula**:
   ```
   raw_score = sum(severity * confidence) / number_of_events
   base_index = normalize(raw_score, from=[-3, 3], to=[-10, 10])
   ```

4. **Final Index**: Clamped to range **[-10, +10]** and rounded to 2 decimal places.

### Persona Adjustment

Each persona has weight multipliers for event types:

| Persona | Crime | Protest | Accident | Disaster | Weather | Neutral |
|---------|-------|---------|----------|----------|---------|---------|
| Student | 1.2 | 1.0 | 0.8 | 1.0 | 0.8 | 1.0 |
| Solo Female | 1.8 | 1.3 | 1.0 | 1.0 | 0.9 | 1.0 |
| Family | 1.5 | 1.4 | 1.3 | 1.5 | 1.2 | 1.0 |
| Backpacker | 1.0 | 0.8 | 0.9 | 1.2 | 1.1 | 1.0 |
| Elderly | 1.3 | 1.2 | 1.4 | 1.6 | 1.5 | 1.0 |

**Persona Index Formula**:
```
weighted_severity = severity * persona_weight[event_type]
persona_index = normalize(weighted_average, from=[-3, 3], to=[-10, 10])
```

---

## Project Structure

```
Travel safe/
├── README.md                    # Project documentation
├── requirements.txt             # Python dependencies
├── app.py                       # Main entry point (Home page)
│
├── pages/                       # Multi-page dashboard modules
│   ├── 1_Dashboard.py          # Safety overview with metrics
│   ├── 2_Events.py             # Event analysis and filters
│   ├── 3_Weather_Alerts.py     # Real-time weather monitoring
│   ├── 4_Crime_Watch.py        # Crime news aggregation
│   └── 5_City_Insights.py      # City profiles and travel tips
│
├── core/                        # Core business logic
│   ├── __init__.py             # Package initializer
│   ├── config.py               # Configuration (cities, API keys, constants)
│   ├── models.py               # Pydantic data models (Event, Persona, etc.)
│   ├── personas.py             # Traveler persona definitions & weights
│   ├── classifier.py           # NLP event classification engine
│   ├── scoring.py              # Safety index computation algorithms
│   ├── api_services.py         # External API integrations (weather, crime)
│   ├── news_client.py          # News fetching & aggregation
│   ├── data_cache.py           # Session state & TTL caching
│   ├── ui_components.py        # Reusable UI components
│   ├── utils.py                # Helper functions
│   │
│   └── services/               # Advanced services
│       ├── __init__.py         # Service package initializer
│       ├── cache.py            # Advanced caching strategies
│       ├── error_handler.py    # Global error handling
│       ├── logger.py           # Structured logging system
│       └── pdf_report.py       # PDF report generation
│
├── sample_data/                 # Fallback data for offline mode
│   └── sample_news.json        # Sample news articles
│
├── logs/                        # Application logs (auto-generated)
│
└── __pycache__/                 # Python bytecode cache
```

### Architecture Highlights

- **Multi-Page App**: Streamlit's native multi-page architecture with shared session state
- **Modular Core**: Business logic separated from UI for maintainability
- **Service Layer**: PDF generation, logging, and caching as pluggable services
- **Data Models**: Type-safe Pydantic models for all data structures
- **Graceful Degradation**: Falls back to sample data when APIs unavailable

---

## Usage Guide

### Getting Started

1. **Launch the App**: Run `streamlit run app.py` and open `http://localhost:8501`

2. **Select Your Destination**: 
   - Use the sidebar dropdown to choose from 45+ cities
   - Mix of Indian cities (Delhi, Mumbai, Bangalore, etc.) and international (Dubai, Singapore, London, etc.)

3. **Choose Your Traveler Profile**:
   - **Student Traveler**: Budget-conscious, moderate risk tolerance
   - **Solo Female Traveler**: Heightened safety awareness, high crime concern
   - **Family Traveler**: Traveling with children, needs secure environments
   - **Backpacker**: Adventure-oriented, higher risk tolerance
   - **Elderly Traveler**: Health-focused, weather and accessibility concerns

4. **Navigate Through Pages**:
   - **🏠 Home**: Quick overview, safety status, and PDF report download
   - **📊 Dashboard**: Detailed metrics, event breakdown, and visualizations
   - **📰 Events**: Filter and analyze events by category and severity
   - **🌦️ Weather Alerts**: Real-time weather data, forecasts, and risk levels
   - **🚔 Crime Watch**: Latest crime news, categorized and analyzed
   - **🏙️ City Insights**: Wikipedia profiles, travel tips, safety planners

### Key Interactions

- **Safety Index Card**: Click to see detailed interpretation and risk factors
- **Event Charts**: Hover over bars/segments for detailed breakdowns
- **Event Tables**: Sort by date, severity, or category; click to expand details
- **PDF Reports**: Download comprehensive reports for offline reference
- **Filters**: Use category filters to focus on specific event types
- **Real-time Data**: Weather and crime pages auto-fetch on load

---

## API Configuration (Optional)

The application works with sample data out-of-the-box. For real-time data, configure these APIs:

### NewsAPI (News Aggregation)
1. Sign up at [NewsAPI.org](https://newsapi.org/) (free tier: 100 requests/day)
2. Add to `.env`: `NEWS_API_KEY=your_key_here`
3. Used by: Dashboard, Events pages

### GNews API (Alternative News Source)
1. Sign up at [GNews.io](https://gnews.io/) (free tier: 100 requests/day)
2. Add to `.env`: `GNEWS_API_KEY=your_key_here`
3. Used by: Crime Watch page

### OpenWeatherMap API (Weather Data)
1. Sign up at [OpenWeatherMap.org](https://openweathermap.org/) (free tier: 1000 requests/day)
2. Add to `.env`: `WEATHER_API_KEY=your_key_here`
3. Used by: Weather Alerts page

### API Usage Notes
- **Fallback Mode**: App uses sample data when APIs unavailable or rate-limited
- **Caching**: API responses cached with TTL to minimize requests
- **Status Indicators**: UI shows data source (Live API / Sample Data)
- **Error Handling**: Graceful degradation with user notifications

---

## Development & Testing

### Running in Development Mode
```bash
# Enable debug logging
streamlit run app.py --logger.level=debug

# Custom port
streamlit run app.py --server.port=8080
```

### Adding New Cities
```python
from core.config import add_city

# Add Indian city
add_city("Kolkata", is_international=False)

# Add international city
add_city("Dubai", is_international=True)
```

### Customizing Personas
Edit `core/personas.py` to adjust risk weights or add new personas.

### Viewing Logs
Check `logs/` directory for structured application logs with timestamps.

---

##  Deployment

### Streamlit Cloud (Recommended)
1. Push code to GitHub
2. Connect repository on [streamlit.io/cloud](https://streamlit.io/cloud)
3. Add API keys in Secrets management
4. Deploy with one click

### Docker (Alternative)
```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
EXPOSE 8501
CMD ["streamlit", "run", "app.py"]
```

---

## License & Credits

### License
This project is created for **educational purposes** as a college mini-project demonstrating:
- Multi-page Streamlit application development
- NLP-based text classification and sentiment analysis
- Real-time data integration and API consumption
- Persona-based risk modeling
- Professional UI/UX design patterns

### Data Sources
- News: NewsAPI, GNews (with proper attribution)
- Weather: OpenWeatherMap
- City Info: Wikipedia REST API
- Sample data synthesized for demonstration

### Disclaimer
Safety indices are **educational estimates** based on news sentiment analysis and should not be the sole factor in travel decisions. Always consult official travel advisories and local authorities for up-to-date safety information.

---

## Author

**Aayush** - College Mini-Project (2026)

### Technologies Demonstrated
- ✅ Python 3.9+ with type hints and modern patterns
- ✅ Streamlit multi-page architecture with session state
- ✅ Pydantic for data validation and modeling
- ✅ API integration with error handling and caching
- ✅ NLP classification using rule-based systems
- ✅ Machine learning utilities with Scikit-learn
- ✅ Interactive data visualization with Plotly
- ✅ Service-oriented architecture (logging, PDF generation)
- ✅ Professional SaaS-style UI/UX design

---

