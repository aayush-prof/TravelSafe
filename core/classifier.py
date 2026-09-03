"""
TravelSafe Classifier Module - Hybrid ML Edition
=================================================

This module implements a HYBRID classification pipeline combining:

1. KEYWORD-BASED RULES: Fast, explainable pattern matching
2. ML MODEL (TF-IDF + Logistic Regression): Better generalization

Classification Pipeline:
------------------------
1. Preprocess text (lowercase, clean)
2. Run keyword matching for initial classification
3. Run ML model for confidence boosting
4. Combine results with weighted averaging
5. Apply severity mapping with calibration

Severity Scale:
--------------
-3: Severe negative (murder, terrorist attack, major disaster)
-2: Significant negative (robbery, major accident, riot)
-1: Minor negative (theft, minor accident, traffic disruption)
 0: Neutral (general news, civic announcements)
+1: Slightly positive (infrastructure improvement, tourism)
+2: Moderately positive (festival, cultural event)
+3: Very positive (achievement, award, celebration)

The hybrid approach provides:
- High accuracy from ML model
- Explainability from keyword rules
- Robustness through ensemble
"""

import re
import pickle
import os
from pathlib import Path
from typing import List, Tuple, Optional, Dict
import numpy as np

# ML imports (with fallback if not available)
try:
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.preprocessing import LabelEncoder
    ML_AVAILABLE = True
except ImportError:
    ML_AVAILABLE = False
    print("Warning: scikit-learn not available. Using keyword-only classification.")

from .models import NewsItem, ClassifiedEvent, EventType
from .config import EVENT_TYPES


# Crime Keywords: Maps to severity scores and confidence values
# Format: keyword -> (severity, confidence_boost)
# Severity Guide:
#   -3: Murder, terrorism, kidnapping
#   -2: Robbery, assault, gang violence
#   -1: Theft, fraud, minor crimes

CRIME_KEYWORDS = {
    # Severe crimes (severity -3) - truly exceptional violent events
    "mass shooting": (-3, 0.95),
    "terrorist attack": (-3, 0.95),
    "bomb blast": (-3, 0.95),
    "suicide bombing": (-3, 0.95),
    "massacre": (-3, 0.95),
    "serial killer": (-3, 0.95),
    
    # Significant crimes (severity -2) - serious incidents
    "murder": (-2, 0.85),
    "homicide": (-2, 0.85),
    "killing": (-2, 0.82),
    "armed robbery": (-2, 0.88),
    "robbery": (-2, 0.80),  # Standalone robbery keyword
    "gang violence": (-2, 0.88),
    "kidnapping": (-2, 0.90),
    "kidnap": (-2, 0.88),
    "abduction": (-2, 0.88),
    "serious assault": (-2, 0.85),
    "assault": (-2, 0.78),  # Standalone assault keyword
    "shootout": (-2, 0.88),
    "shooting": (-2, 0.85),  # Standalone shooting keyword
    "stabbing": (-2, 0.85),
    "dacoity": (-2, 0.88),
    "mugging": (-2, 0.80),
    
    # Minor crimes (severity -1 to -2) - common incidents affecting traveler safety
    "theft reported": (-2, 0.78),  # Upgraded: theft is serious for travelers
    "robbery attempt": (-2, 0.82),  # Upgraded: attempted robbery still traumatic
    "pickpocket": (-2, 0.80),  # Upgraded: common tourist targeting crime
    "snatching": (-2, 0.82),  # Upgraded: chain/bag snatching is violent
    "chain snatching": (-2, 0.85),  # Upgraded: often involves injury
    "bag snatching": (-2, 0.82),  # Upgraded: traumatic for victims
    "burglary": (-2, 0.80),  # Upgraded: property invasion is serious
    "scam reported": (-1, 0.72),  # Minor: financial loss, no physical harm
    "scam": (-1, 0.68),  # Minor: financial crime
    "fraud case": (-1, 0.72),  # Minor: financial crime
    "fraud": (-1, 0.70),  # Minor: financial crime
    "minor assault": (-2, 0.78),  # Upgraded: any assault is serious
    "theft": (-2, 0.78),  # Upgraded: theft impacts traveler security
    "drug": (-1, 0.72),  # Minor: drug-related crimes
    "narcotics": (-2, 0.78),  # Upgraded: indicates dangerous activity
    "smuggling": (-2, 0.78),  # Upgraded: indicates criminal networks
    "vandalism": (-1, 0.70),  # Minor: property damage
    "trespassing": (-1, 0.65),  # Minor: usually non-violent
    
    # Crime-related law enforcement (severity -1 to -2) - indicates crime occurred even if resolved
    "arrested": (-1, 0.75),  # Crime occurred but resolved
    "suspect arrested": (-1, 0.72),  # Crime occurred but resolved
    "gang busted": (-2, 0.80),  # Upgraded: gang presence indicates danger
    "racket busted": (-2, 0.80),  # Upgraded: criminal networks indicate danger
    
    # Positive crime context (severity +1 to +2) - genuine safety improvements
    "criminal caught": (1, 0.70),  # Clearly positive outcome
    "police crackdown": (1, 0.68),  # Proactive policing
    "crime rate drops": (2, 0.85),  # Very positive - actual reduction in crime
    "crime free": (2, 0.88),  # Area declared crime-free
    "safety measures": (1, 0.70),
    "increased patrolling": (1, 0.65),
    "security enhanced": (1, 0.68),
}

# Protest Keywords
# -2: Violent protests, riots, curfew
# -1: Peaceful protests, strikes, bandh

PROTEST_KEYWORDS = {
    # Severe protests (severity -2) - truly violent
    "violent riot": (-2, 0.92),
    "mob violence": (-2, 0.90),
    "major clashes": (-2, 0.88),
    "curfew imposed": (-2, 0.88),
    "section 144": (-2, 0.85),
    "arson during protest": (-2, 0.88),
    "violent unrest": (-2, 0.90),
    
    # Moderate protests (severity -1) - disruptive but peaceful
    "strike": (-1, 0.75),
    "bandh": (-1, 0.78),
    "road blockade": (-1, 0.75),
    "agitation": (-1, 0.72),
    "shutdown": (-1, 0.75),
    "chakka jam": (-1, 0.75),
    
    # Minor protests (severity 0) - democratic expression
    "peaceful protest": (0, 0.60),
    "peaceful demonstration": (0, 0.60),
    "awareness rally": (0, 0.55),
    "sit-in": (0, 0.58),
    "dharna": (0, 0.58),
    "march": (0, 0.55),
    
    # Positive context
    "protest ends peacefully": (1, 0.70),
    "demands accepted": (1, 0.72),
    "peaceful resolution": (1, 0.75),
}

# Accident Keywords
# -3: Fatal accidents, major disasters
# -2: Serious accidents with injuries
# -1: Minor accidents, near-misses

ACCIDENT_KEYWORDS = {
    # Fatal/Major accidents (severity -3) - truly catastrophic
    "fatal multi-vehicle crash": (-3, 0.95),
    "multiple fatalities": (-3, 0.95),
    "train derailment": (-3, 0.92),
    "plane crash": (-3, 0.95),
    "building collapse": (-3, 0.92),
    "bridge collapse": (-3, 0.92),
    
    # Serious accidents (severity -2)
    "serious accident": (-2, 0.85),
    "major crash": (-2, 0.85),
    "bus accident": (-2, 0.82),
    "pile-up": (-2, 0.85),
    "major fire": (-2, 0.85),
    "explosion": (-2, 0.88),
    
    # Minor accidents (severity -1 to -2) - common incidents
    "minor accident": (-1, 0.75),
    "fender bender": (-1, 0.68),
    "traffic accident": (-2, 0.78),  # Upgraded: road safety concern
    "vehicle collision": (-2, 0.80),  # Upgraded: indicates dangerous roads
    "minor fire": (-1, 0.72),
    "mishap": (-1, 0.70),
    "traffic disruption": (-1, 0.68),
    "road closure": (-1, 0.72),
    
    # Positive context (safety improvements)
    "accident prevented": (1, 0.75),
    "safety audit": (1, 0.68),
    "road safety drive": (1, 0.72),
    "traffic safety measures": (1, 0.70),
}

# Disaster Keywords
# -3: Major natural disasters
# -2: Significant disasters
# -1: Minor events

DISASTER_KEYWORDS = {
    # Major disasters (severity -3)
    "earthquake": (-3, 0.95),
    "tsunami": (-3, 0.98),
    "cyclone": (-3, 0.92),
    "hurricane": (-3, 0.92),
    "tornado": (-3, 0.92),
    "major flood": (-3, 0.90),
    "landslide": (-3, 0.90),
    "avalanche": (-3, 0.92),
    "volcanic": (-3, 0.95),
    "catastrophe": (-3, 0.88),
    "devastation": (-3, 0.85),
    "emergency declared": (-3, 0.90),
    "disaster relief": (-2, 0.75),
    
    # Significant disasters (severity -2)
    "flood": (-2, 0.85),
    "flooding": (-2, 0.85),
    "flash flood": (-2, 0.88),
    "drought": (-2, 0.82),
    "famine": (-2, 0.88),
    "epidemic": (-2, 0.88),
    "outbreak": (-2, 0.78),
    "wildfire": (-2, 0.88),
    "forest fire": (-2, 0.85),
    "water crisis": (-2, 0.80),
    
    # Minor events (severity -1)
    "tremor": (-1, 0.78),
    "aftershock": (-1, 0.80),
    "water shortage": (-1, 0.72),
    "power outage": (-1, 0.65),
}

# Weather Keywords
# -2: Severe weather
# -1: Moderate weather disruption
# 0: General weather news

WEATHER_KEYWORDS = {
    # Severe weather (severity -2)
    "heavy rain": (-2, 0.85),
    "torrential": (-2, 0.88),
    "cloudburst": (-2, 0.90),
    "storm": (-2, 0.82),
    "thunderstorm": (-2, 0.82),
    "hailstorm": (-2, 0.88),
    "blizzard": (-2, 0.88),
    "heatwave": (-2, 0.85),
    "heat wave": (-2, 0.85),
    "extreme heat": (-2, 0.85),
    "cold wave": (-2, 0.85),
    "dense fog": (-2, 0.82),
    "zero visibility": (-2, 0.85),
    "red alert": (-2, 0.88),
    "orange alert": (-2, 0.82),
    
    # Moderate weather (severity -1)
    "rain": (-1, 0.60),
    "rainfall": (-1, 0.62),
    "showers": (-1, 0.58),
    "fog": (-1, 0.70),
    "smog": (-1, 0.75),
    "wind": (-1, 0.55),
    "gusty": (-1, 0.65),
    "weather warning": (-1, 0.80),
    "weather alert": (-1, 0.78),
    "yellow alert": (-1, 0.72),
    
    # Neutral weather (severity 0)
    "cloudy": (0, 0.50),
    "overcast": (0, 0.50),
    "temperature": (0, 0.45),
    "humidity": (0, 0.45),
    "forecast": (0, 0.40),
}

# POSITIVE Keywords (NEW - for tourism, festivals, achievements)
# +1: Minor positive
# +2: Moderately positive
# +3: Very positive

POSITIVE_KEYWORDS = {
    # Very positive (severity +3)
    "world record": (3, 0.90),
    "safest city award": (3, 0.92),
    "unesco heritage": (3, 0.88),
    "international acclaim": (3, 0.85),
    "major award": (3, 0.88),
    "tourism milestone": (3, 0.88),
    "zero crime": (3, 0.90),
    "city of the year": (3, 0.90),
    
    # Moderately positive (severity +2)
    "grand festival": (2, 0.85),
    "diwali celebration": (2, 0.85),
    "cultural festival": (2, 0.82),
    "carnival": (2, 0.82),
    "record tourists": (2, 0.85),
    "safe city ranking": (2, 0.88),
    "heritage restored": (2, 0.80),
    "infrastructure excellence": (2, 0.82),
    "peaceful": (2, 0.78),
    "crime free zone": (2, 0.85),
    "tourism boom": (2, 0.82),
    
    # Slightly positive (severity +1)
    "tourism": (1, 0.70),
    "safe travel": (1, 0.75),
    "tourist attraction": (1, 0.68),
    "heritage site": (1, 0.68),
    "new project": (1, 0.65),
    "development": (1, 0.62),
    "improvement": (1, 0.65),
    "infrastructure upgrade": (1, 0.68),
    "local hospitality": (1, 0.70),
    "cleanliness drive": (1, 0.68),
    "beautification": (1, 0.68),
    "safety measures": (1, 0.72),
    "secure": (1, 0.70),
    "well-managed": (1, 0.68),
}

# Neutral Keywords
NEUTRAL_KEYWORDS = {
    "meeting": (0, 0.50),
    "conference": (0, 0.50),
    "visit": (0, 0.48),
    "statement": (0, 0.45),
    "announced": (0, 0.50),
    "report": (0, 0.45),
    "survey": (0, 0.48),
    "study": (0, 0.45),
    "election": (0, 0.55),
    "voting": (0, 0.55),
}

# Combined keyword dictionaries
EVENT_KEYWORDS = {
    "crime": CRIME_KEYWORDS,
    "protest": PROTEST_KEYWORDS,
    "accident": ACCIDENT_KEYWORDS,
    "disaster": DISASTER_KEYWORDS,
    "weather": WEATHER_KEYWORDS,
    "positive": POSITIVE_KEYWORDS,
    "neutral": NEUTRAL_KEYWORDS,
}


class HybridClassifier:
    """
    Hybrid classifier combining keyword rules and ML model.
    
    The ML model is trained on the keyword patterns to improve
    generalization while maintaining interpretability.
    
    Uses singleton pattern to avoid repeated model training.
    """
    
    _instance = None
    _is_initialized = False
    
    def __new__(cls):
        """Ensure only one instance exists (singleton pattern)."""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        # Skip if already initialized (singleton)
        if HybridClassifier._is_initialized:
            return
            
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.classifier: Optional[LogisticRegression] = None
        self.label_encoder: Optional[LabelEncoder] = None
        self.is_trained = False
        
        if ML_AVAILABLE:
            self._train_model()
        
        HybridClassifier._is_initialized = True
    
    def _generate_training_data(self) -> Tuple[List[str], List[str], List[int]]:
        """
        Generate training data from keyword dictionaries.
        Creates synthetic examples for each event type.
        """
        texts = []
        labels = []
        severities = []
        
        # Template sentences for each event type
        templates = {
            "crime": [
                "{keyword} reported in city area",
                "Police investigate {keyword} case",
                "Victim of {keyword} files complaint",
                "{keyword} incident shocks residents",
            ],
            "protest": [
                "{keyword} disrupts traffic in city",
                "Citizens join {keyword} against new policy",
                "{keyword} organized by workers union",
                "Thousands participate in {keyword}",
            ],
            "accident": [
                "{keyword} on highway causes delays",
                "Multiple vehicles involved in {keyword}",
                "{keyword} leaves several injured",
                "Emergency services respond to {keyword}",
            ],
            "disaster": [
                "{keyword} affects thousands of residents",
                "Relief operations begin after {keyword}",
                "Government declares emergency after {keyword}",
                "{keyword} causes widespread damage",
            ],
            "weather": [
                "{keyword} expected in coming days",
                "Meteorological department warns of {keyword}",
                "{keyword} disrupts daily life",
                "Residents advised caution due to {keyword}",
            ],
            "positive": [
                "City celebrates {keyword} with enthusiasm",
                "{keyword} attracts visitors from across country",
                "Residents enjoy {keyword} festivities",
                "{keyword} brings joy to community",
            ],
            "neutral": [
                "Officials discuss {keyword} at meeting",
                "{keyword} scheduled for next week",
                "Committee reviews {keyword} proposal",
                "{keyword} highlights city development",
            ],
        }
        
        for event_type, keywords in EVENT_KEYWORDS.items():
            event_templates = templates.get(event_type, templates["neutral"])
            
            for keyword, (severity, _) in keywords.items():
                for template in event_templates:
                    text = template.format(keyword=keyword)
                    texts.append(text)
                    labels.append(event_type)
                    severities.append(severity)
        
        return texts, labels, severities
    
    def _train_model(self):
        """Train the ML model on generated data."""
        if not ML_AVAILABLE:
            return
        
        try:
            texts, labels, severities = self._generate_training_data()
            
            # Initialize components
            self.vectorizer = TfidfVectorizer(
                max_features=5000,
                ngram_range=(1, 2),
                stop_words='english',
                min_df=1
            )
            
            self.label_encoder = LabelEncoder()
            self.classifier = LogisticRegression(
                max_iter=1000,
                multi_class='multinomial',
                solver='lbfgs',
                C=1.0
            )
            
            # Transform and train
            X = self.vectorizer.fit_transform(texts)
            y = self.label_encoder.fit_transform(labels)
            
            self.classifier.fit(X, y)
            self.is_trained = True
            
        except Exception as e:
            print(f"Warning: ML model training failed: {e}")
            self.is_trained = False
    
    def predict(self, text: str) -> Tuple[str, float]:
        """
        Predict event type using ML model.
        
        Args:
            text: Text to classify
            
        Returns:
            Tuple of (predicted_label, confidence)
        """
        if not self.is_trained or not ML_AVAILABLE:
            return "neutral", 0.5
        
        try:
            X = self.vectorizer.transform([text])
            proba = self.classifier.predict_proba(X)[0]
            pred_idx = np.argmax(proba)
            confidence = proba[pred_idx]
            label = self.label_encoder.inverse_transform([pred_idx])[0]
            
            return label, float(confidence)
        except Exception as e:
            print(f"Warning: ML prediction failed: {e}")
            return "neutral", 0.5


# Global classifier instance (trained once on import)
_hybrid_classifier = HybridClassifier()


def _preprocess_text(text: str) -> str:
    """Preprocess text for classification."""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', ' ', text)
    text = ' '.join(text.split())
    return text


def _match_keywords(text: str, keywords: dict) -> Tuple[float, float, int]:
    """
    Match keywords and calculate scores.
    
    Returns:
        Tuple of (total_confidence, avg_severity, match_count)
    """
    total_confidence = 0.0
    total_severity = 0.0
    match_count = 0
    
    for keyword, (severity, confidence) in keywords.items():
        if keyword.lower() in text:
            total_confidence += confidence
            total_severity += severity
            match_count += 1
    
    avg_severity = total_severity / match_count if match_count > 0 else 0.0
    
    return total_confidence, avg_severity, match_count


def _classify_with_keywords(text: str) -> Tuple[str, int, float]:
    """
    Classify text using keyword matching.
    
    Returns:
        Tuple of (event_type, severity, confidence)
    """
    processed_text = _preprocess_text(text)
    
    best_event_type = "neutral"
    best_confidence = 0.0
    best_severity = 0
    
    for event_type, keywords in EVENT_KEYWORDS.items():
        total_conf, avg_sev, matches = _match_keywords(processed_text, keywords)
        
        # Weight by number of matches
        weighted_confidence = total_conf * (1 + 0.1 * matches)
        
        if weighted_confidence > best_confidence:
            best_confidence = weighted_confidence
            best_event_type = event_type
            best_severity = round(avg_sev)
    
    # Normalize confidence
    normalized_confidence = min(best_confidence / 3.0, 1.0)
    
    if normalized_confidence < 0.3:
        return "neutral", 0, 0.5
    
    # Clamp severity
    clamped_severity = max(-3, min(3, best_severity))
    
    return best_event_type, clamped_severity, round(normalized_confidence, 2)


def _classify_hybrid(text: str) -> Tuple[str, int, float]:
    """
    Hybrid classification combining keywords and ML.
    
    Strategy:
    1. Run keyword classification
    2. Run ML classification
    3. If both agree, boost confidence
    4. If disagree, use the one with higher confidence
    5. Calibrate final severity
    
    Returns:
        Tuple of (event_type, severity, confidence)
    """
    # Keyword-based classification
    kw_type, kw_severity, kw_conf = _classify_with_keywords(text)
    
    # ML-based classification
    ml_type, ml_conf = _hybrid_classifier.predict(_preprocess_text(text))
    
    # Combine predictions
    if kw_type == ml_type:
        # Agreement - boost confidence
        final_type = kw_type
        final_conf = min(1.0, (kw_conf + ml_conf) / 2 + 0.1)
        final_severity = kw_severity
    elif kw_conf >= ml_conf:
        # Keyword wins
        final_type = kw_type
        final_conf = kw_conf
        final_severity = kw_severity
    else:
        # ML wins - but use keyword severity if available
        final_type = ml_type
        final_conf = ml_conf
        # Estimate severity from type
        final_severity = _estimate_severity_for_type(ml_type, text)
    
    return final_type, final_severity, round(final_conf, 2)


def _estimate_severity_for_type(event_type: str, text: str) -> int:
    """
    Estimate severity when ML predicts but keywords don't match well.
    
    Uses a lookup of average severities per event type.
    """
    # Default severity by event type
    default_severities = {
        "crime": -2,
        "protest": -2,
        "accident": -1,
        "disaster": -2,
        "weather": -1,
        "positive": 2,
        "neutral": 1,
    }
    
    # Try to find any keyword match for better estimate
    if event_type in EVENT_KEYWORDS:
        processed = _preprocess_text(text)
        for keyword, (severity, _) in EVENT_KEYWORDS[event_type].items():
            if keyword in processed:
                return severity
    
    return default_severities.get(event_type, 0)


NEGATIVE_LEVEL_3_KWS = {
    "mass shooting": -3,
    "terrorist attack": -3,
    "bomb blast": -3,
    "suicide bombing": -3,
    "massacre": -3,
    "fatal accident": -3,
    "multiple deaths": -3,
    "major earthquake": -3,
    "severe cyclone": -3,
    "devastating flood": -3,
    "catastrophic disaster": -3,
    "emergency declared": -3,
}

NEGATIVE_LEVEL_2_KWS = {
    "armed robbery": -2,
    "serious assault": -2,
    "violent riot": -2,
    "major clashes": -2,
    "gang violence": -2,
    "multi-vehicle accident": -2,
    "red alert weather": -2,
    "severe landslide": -2,
    "major building fire": -2,
    "train derailment": -2,
    "bridge collapse": -2,
}

NEGATIVE_LEVEL_1_KWS = {
    "petty theft": -1,
    "pickpocket attempt": -1,
    "minor scam": -1,
    "traffic accident": -1,
    "fender bender": -1,
    "traffic jam": -1,
    "road closure": -1,
    "weather advisory": -1,
    "brief power outage": -1,
    "waterlogging": -1,
    "peaceful strike": -1,
    "demonstration": -1,
    "arrest made": -1,
}

POSITIVE_LEVEL_1_KWS = {
    "tourism boost": 1,
    "safe travel": 1,
    "improvement": 1,
    "development": 1,
    "safety measures": 1,
    "security enhanced": 1,
    "infrastructure upgrade": 1,
    "new attraction": 1,
    "local hospitality": 1,
    "crime rate drops": 1,
    "peaceful conditions": 1,
    "cleanliness drive": 1,
}

POSITIVE_LEVEL_2_KWS = {
    "grand festival": 2,
    "cultural celebration": 2,
    "major concert": 2,
    "tourists flock": 2,
    "record tourist arrivals": 2,
    "major infrastructure": 2,
    "city beautification": 2,
    "heritage site restored": 2,
    "safe city ranking": 2,
    "crime free zone": 2,
    "successful event": 2,
    "international recognition": 2,
}

POSITIVE_LEVEL_3_KWS = {
    "major award": 3,
    "world record": 3,
    "record visitors": 3,
    "safest city award": 3,
    "unesco heritage": 3,
    "city of the year": 3,
    "zero crime month": 3,
    "tourism milestone": 3,
    "infrastructure excellence": 3,
    "international acclaim": 3,
}

_BASE_SEVERITY_BY_TYPE = {
    "disaster": -2,
    "crime": -1,
    "accident": -1,
    "protest": -1,
    "weather": -1,
    "positive": 1,
    "neutral": 0,
}


def compute_event_severity(text: str, event_type: str) -> int:
    """Assign a keyword-based severity score in [-3, 3] for a news item."""
    processed = _preprocess_text(text)

    severity = _BASE_SEVERITY_BY_TYPE.get(event_type, 0)

    neg_candidates = []
    for kw, sev in NEGATIVE_LEVEL_3_KWS.items():
        if kw in processed:
            neg_candidates.append(sev)
    for kw, sev in NEGATIVE_LEVEL_2_KWS.items():
        if kw in processed:
            neg_candidates.append(sev)
    for kw, sev in NEGATIVE_LEVEL_1_KWS.items():
        if kw in processed:
            neg_candidates.append(sev)

    pos_candidates = []
    for kw, sev in POSITIVE_LEVEL_3_KWS.items():
        if kw in processed:
            pos_candidates.append(sev)
    for kw, sev in POSITIVE_LEVEL_2_KWS.items():
        if kw in processed:
            pos_candidates.append(sev)
    for kw, sev in POSITIVE_LEVEL_1_KWS.items():
        if kw in processed:
            pos_candidates.append(sev)

    strongest_neg = min(neg_candidates) if neg_candidates else None
    strongest_pos = max(pos_candidates) if pos_candidates else None

    if strongest_neg is not None and strongest_pos is not None:
        candidate = strongest_neg if abs(strongest_neg) >= abs(strongest_pos) else strongest_pos
        if abs(candidate) > abs(severity):
            severity = candidate
    elif strongest_neg is not None:
        if abs(strongest_neg) > abs(severity):
            severity = strongest_neg
    elif strongest_pos is not None:
        if abs(strongest_pos) > abs(severity):
            severity = strongest_pos

    severity = max(-3, min(3, int(round(severity))))
    return severity


def classify_news_item(news_item: NewsItem) -> ClassifiedEvent:
    """
    Classify a single news item using hybrid approach.
    
    Uses both keyword matching and ML model for robust classification.
    
    Args:
        news_item: NewsItem object to classify
        
    Returns:
        ClassifiedEvent with classification results
    """
    full_text = news_item.get_full_text()
    
    # Use hybrid classification
    event_type, _, confidence = _classify_hybrid(full_text)

    # Override severity using keyword-based scoring per article
    severity = compute_event_severity(full_text, event_type)
    
    return ClassifiedEvent(
        news_item=news_item,
        event_type=event_type,
        severity=severity,
        confidence=confidence
    )


def classify_news_list(news_items: List[NewsItem]) -> List[ClassifiedEvent]:
    """Classify a list of news items."""
    return [classify_news_item(item) for item in news_items]


def get_classification_explanation(event: ClassifiedEvent) -> str:
    """Generate explanation of classification."""
    text = event.news_item.get_full_text()
    processed = _preprocess_text(text)
    
    keywords = EVENT_KEYWORDS.get(event.event_type, {})
    matched = [kw for kw in keywords if kw.lower() in processed]
    
    lines = [
        f"**Event Type:** {event.event_type.capitalize()}",
        f"**Severity:** {event.severity} (-5 to +5 scale)",
        f"**Confidence:** {event.confidence:.0%}",
        "",
        "**Matched Keywords:**",
    ]
    
    if matched:
        for kw in matched[:5]:
            lines.append(f"  - {kw}")
    else:
        lines.append("  (ML classification - no specific keywords)")
    
    return "\n".join(lines)


def get_event_type_distribution(events: List[ClassifiedEvent]) -> dict:
    """Count events by type."""
    counts = {event_type: 0 for event_type in EVENT_TYPES}
    for event in events:
        if event.event_type in counts:
            counts[event.event_type] += 1
    return counts


def get_severity_statistics(events: List[ClassifiedEvent]) -> dict:
    """Calculate severity statistics."""
    if not events:
        return {"min": 0, "max": 0, "mean": 0, "by_type": {}}
    
    severities = [e.severity for e in events]
    
    by_type = {}
    for event_type in EVENT_TYPES:
        type_events = [e for e in events if e.event_type == event_type]
        if type_events:
            avg = sum(e.severity for e in type_events) / len(type_events)
            by_type[event_type] = round(avg, 2)
        else:
            by_type[event_type] = 0.0
    
    return {
        "min": min(severities),
        "max": max(severities),
        "mean": round(sum(severities) / len(severities), 2),
        "by_type": by_type
    }
