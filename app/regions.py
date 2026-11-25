"""India's 28 states and 8 union territories (human-facing labels)."""
STATES = [
    "Andhra Pradesh", "Arunachal Pradesh", "Assam", "Bihar", "Chhattisgarh",
    "Goa", "Gujarat", "Haryana", "Himachal Pradesh", "Jharkhand", "Karnataka",
    "Kerala", "Madhya Pradesh", "Maharashtra", "Manipur", "Meghalaya",
    "Mizoram", "Nagaland", "Odisha", "Punjab", "Rajasthan", "Sikkim",
    "Tamil Nadu", "Telangana", "Tripura", "Uttar Pradesh", "Uttarakhand",
    "West Bengal",
]
UNION_TERRITORIES = [
    "Andaman and Nicobar Islands", "Chandigarh",
    "Dadra and Nagar Haveli and Daman and Diu", "Delhi", "Jammu and Kashmir",
    "Ladakh", "Lakshadweep", "Puducherry",
]
REGIONS = ["All India", *STATES, *UNION_TERRITORIES]
TOPICS = ["All topics", "Policy", "Business", "Technology", "Environment", "Transport", "Health", "General"]
TOPIC_TERMS = {
    "Policy": ["government", "minister", "assembly", "election", "policy", "cabinet", "parliament", "bill", "court", "legislation", "scheme"],
    "Business": ["market", "business", "economy", "startup", "investment", "jobs", "bank", "trade", "industry", "stock"],
    "Technology": ["technology", "artificial intelligence", "ai ", "digital", "software", "cyber", "internet", "semiconductor", "tech"],
    "Environment": ["climate", "rain", "flood", "pollution", "forest", "wildlife", "heatwave", "weather", "water"],
    "Transport": ["rail", "metro", "airport", "highway", "traffic", "transport", "road", "flight", "bus", "train"],
    "Health": ["hospital", "health", "medical", "disease", "doctor", "vaccine", "healthcare"],
}

def classify_topic(text: str) -> str:
    low = f" {text.lower()} "
    return next((topic for topic, words in TOPIC_TERMS.items() if any(w in low for w in words)), "General")


def infer_region(text: str, requested: str = "All India") -> tuple[str, str]:
    """Only assign a region when the article text explicitly mentions it.

    Otherwise use All India; no inferred region from the feed search alone.
    """
    low = f" {text.lower()} "
    # Unicode-aware explicit mention checking: English names and selected
    # endonyms. Names in headlines do not establish story location otherwise.
    import re
    matches = []
    for region in REGIONS[1:]:
        phrases = [region, *REGION_LOCAL_ALIASES.get(region, [])]
        if any(
            re.search(r"(?<!\w)" + re.escape(name.lower()) +
                      (r"(?!\w)" if name.isascii() else ""), low)
            for name in phrases
        ):
            matches.append(region)
    if requested in matches:
        return requested, "explicit"
    if len(matches) == 1:
        return matches[0], "explicit"
    return "All India", "not_verified"


# Language labels for response localisation. Unsupported automatic translations
# are never silently passed off as English summaries.
LANGUAGES = {
    "English": "en", "Hindi": "hi", "Bengali": "bn", "Tamil": "ta",
    "Telugu": "te", "Kannada": "kn", "Malayalam": "ml", "Marathi": "mr",
    "Gujarati": "gu", "Punjabi": "pa", "Odia": "or", "Assamese": "as",
    "Urdu": "ur",
}

# Prefer one local-language RSS search per selected region, where available.
# Google News is an aggregator: locale preferences do not guarantee results.
REGION_RSS_LANG = {
    "Andhra Pradesh": "te", "Assam": "as", "Bihar": "hi", "Chhattisgarh": "hi",
    "Delhi": "hi", "Goa": "mr", "Gujarat": "gu", "Haryana": "hi",
    "Himachal Pradesh": "hi", "Jharkhand": "hi", "Karnataka": "kn",
    "Kerala": "ml", "Madhya Pradesh": "hi", "Maharashtra": "mr",
    "Odisha": "or", "Punjab": "pa", "Rajasthan": "hi", "Tamil Nadu": "ta",
    "Telangana": "te", "Uttar Pradesh": "hi", "Uttarakhand": "hi",
    "West Bengal": "bn", "Jammu and Kashmir": "ur", "Puducherry": "ta",
}

REGION_LOCAL_ALIASES = {
    "Andhra Pradesh": ["ఆంధ్రప్రదేశ్"], "Assam": ["অসম", "অসমৰ"],
    "Bihar": ["बिहार"], "Chhattisgarh": ["छत्तीसगढ़"],
    "Delhi": ["दिल्ली", "नई दिल्ली"], "Goa": ["गोवा"],
    "Gujarat": ["ગુજરાત"], "Haryana": ["हरियाणा"],
    "Himachal Pradesh": ["हिमाचल प्रदेश"], "Jharkhand": ["झारखंड"],
    "Karnataka": ["ಕರ್ನಾಟಕ", "ಕರ್ನಾಟಕದ"], "Kerala": ["കേരളം", "കേരളത്തിലെ"],
    "Madhya Pradesh": ["मध्य प्रदेश"], "Maharashtra": ["महाराष्ट्र", "महाराष्ट्रात"],
    "Odisha": ["ଓଡ଼ିଶା", "ଓଡିଶା"], "Punjab": ["ਪੰਜਾਬ"],
    "Rajasthan": ["राजस्थान"], "Tamil Nadu": ["தமிழ்நாடு", "தமிழக"],
    "Telangana": ["తెలంగాణ"], "Uttar Pradesh": ["उत्तर प्रदेश"],
    "Uttarakhand": ["उत्तराखंड"], "West Bengal": ["পশ্চিমবঙ্গ"],
    "Jammu and Kashmir": ["जम्मू कश्मीर", "جموں و کشمیر"],
}

SCRIPT_LANGUAGES = (
    ("\u0b80", "\u0bff", "Tamil"),
    ("\u0c00", "\u0c7f", "Telugu"),
    ("\u0c80", "\u0cff", "Kannada"),
    ("\u0d00", "\u0d7f", "Malayalam"),
    ("\u0980", "\u09ff", "Bengali"),
    ("\u0a00", "\u0a7f", "Punjabi"),
    ("\u0a80", "\u0aff", "Gujarati"),
    ("\u0b00", "\u0b7f", "Odia"),
    ("\u0600", "\u06ff", "Urdu"),
)


def detect_language(text: str, region: str = "All India") -> str:
    """Heuristic script identification, *not* high-confidence language ID."""
    for start, end, name in SCRIPT_LANGUAGES:
        if any(start <= char <= end for char in text):
            if name == "Bengali" and region == "Assam":
                return "Assamese"  # shared script; a regional hint, not proof
            return name
    if any("\u0900" <= char <= "\u097f" for char in text):
        return "Marathi" if region in {"Maharashtra", "Goa"} else "Hindi"
    letters = [c for c in text if c.isalpha()]
    latin = sum("A" <= c <= "Z" or "a" <= c <= "z" for c in letters)
    return "English" if letters and latin / len(letters) >= .8 else "Unknown"
