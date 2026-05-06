# """
# chatbot.py  –  Seamless Assistant backend
# ==========================================
# Improvements over previous version
# ------------------------------------
# 1.  Fuzzy / typo tolerance via difflib (no extra pip install)
#     - City names: "mumbay" → Mumbai, "chandiwali" → Chandivali, etc.
#     - Commodity names: "pyaaz" → onion, "tomatoe" → tomato, etc.
#     - Weather keywords: "temprature" → temperature, "wheather" → weather, etc.
# 2.  Extended synonym lists (70+ commodities, 50+ weather terms)
# 3.  Session management: session_id on every message; new_session; list sessions
# 4.  Chat history auto-loads in frontend (session-aware DB schema)
# 5.  All existing features preserved: Groq Q&A, Agmarknet prices,
#     OpenWeather, news (published + non-published), concerns
# """

# from __future__ import annotations

# import difflib
# import os
# import re
# import uuid
# from datetime import datetime
# from flask import jsonify, request, session
# from flask_login import current_user
# from app.db import get_db

# try:
#     from groq import Groq
#     GROQ_AVAILABLE = True
# except ImportError:
#     GROQ_AVAILABLE = False

# import requests

# # ─── Config ───────────────────────────────────────────────────────────────────
# GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "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")
# OPENWEATHER_KEY = "2baab2dc7ad18ffef8b81c014e893e1c"
# AGMARK_BASE     = "https://api.agmarknet.gov.in/v1"
# GROQ_MODEL      = "llama-3.3-70b-versatile"

# groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_AVAILABLE and GROQ_API_KEY) else None

# AGMARK_HEADERS = {
#     "accept": "application/json, text/plain, */*",
#     "accept-language": "en-US,en;q=0.8",
#     "origin": "https://www.agmarknet.gov.in",
#     "referer": "https://www.agmarknet.gov.in/",
#     "user-agent": (
#         "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
#         "AppleWebKit/537.36 (KHTML, like Gecko) "
#         "Chrome/146.0.0.0 Safari/537.36"
#     ),
# }

# MONTH_NAMES = {
#     1:"january", 2:"february", 3:"march",    4:"april",
#     5:"may",     6:"june",     7:"july",     8:"august",
#     9:"september",10:"october",11:"november",12:"december"
# }
# MONTH_SHORT = {
#     "1":"Jan","2":"Feb","3":"Mar","4":"Apr","5":"May","6":"Jun",
#     "7":"Jul","8":"Aug","9":"Sep","10":"Oct","11":"Nov","12":"Dec"
# }

# SYSTEM_PROMPT = """You are Seamless Assistant, a helpful AI chatbot for the Seamless project management platform.
# You help with news summaries, live commodity prices, real-time weather, and general Q&A.
# Keep responses concise, friendly, and professional. Use **bold** for key terms.
# For general knowledge questions (farming, economy, weather concepts, agriculture), answer from your training knowledge.
# Never fabricate live data (prices, weather) — only reference data explicitly provided to you.
# """

# # ══════════════════════════════════════════════════════════════════════════════
# #  WEATHER  –  keywords, city aliases, patterns
# # ══════════════════════════════════════════════════════════════════════════════

# WEATHER_TERMS: set[str] = {
#     # Core
#     "weather", "forecast", "conditions", "climate",
#     # Temperature
#     "temperature", "temp", "hot", "cold", "heat", "warmth", "cool", "chilly",
#     "freezing", "degree", "degrees", "celsius", "fahrenheit", "kelvin",
#     "how hot", "how cold", "how warm",
#     # Precipitation
#     "rain", "rainfall", "raining", "rainy", "drizzle", "shower", "precipitation",
#     "snow", "snowfall", "hail", "sleet", "baarish", "barish", "paus",
#     # Wind / atmosphere
#     "wind", "wind speed", "windy", "gust", "storm", "thunder", "lightning",
#     "humid", "humidity", "fog", "foggy", "mist", "misty", "hawa",
#     # Sky
#     "sunny", "sunshine", "cloudy", "overcast", "clear sky", "partly cloudy",
#     # Hindi / Marathi
#     "mausam", "garmi", "sardi", "thand", "tapman", "dhuke",
#     # Conversational
#     "umbrella", "carry umbrella", "bring umbrella", "need umbrella",
#     "wear jacket", "dress warmly", "what to wear",
#     "is it raining", "will it rain", "going to rain", "chance of rain",
#     "is it hot", "is it cold", "is it sunny", "feels like",
#     "uv index", "air quality", "visibility", "pressure",
# }

# # All weather synonym words as a flat list for fuzzy matching
# _WEATHER_TERM_LIST: list[str] = sorted(WEATHER_TERMS)

# # Canonical city names for fuzzy matching
# KNOWN_CITIES: list[str] = [
#     "Mumbai", "Delhi", "New Delhi", "Bangalore", "Bengaluru", "Hyderabad",
#     "Ahmedabad", "Chennai", "Kolkata", "Pune", "Nagpur", "Surat", "Jaipur",
#     "Lucknow", "Kanpur", "Indore", "Thane", "Bhopal", "Visakhapatnam",
#     "Patna", "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik",
#     "Aurangabad", "Solapur", "Amravati", "Kolhapur", "Akola", "Latur",
#     "Dhule", "Nanded", "Chandivali", "Kalyan", "Navi Mumbai", "Pimpri",
#     "Coimbatore", "Kochi", "Thiruvananthapuram", "Madurai", "Mangaluru",
#     "Bhubaneswar", "Guwahati", "Ranchi", "Raipur", "Chandigarh",
#     "Dehradun", "Shimla", "Jammu", "Srinagar", "Varanasi", "Allahabad",
#     "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner",
# ]

# # Hard-coded alias corrections (always beats fuzzy)
# CITY_ALIASES: dict[str, str] = {
#     "mumbay":       "Mumbai",
#     "bombay":       "Mumbai",
#     "bomaby":       "Mumbai",
#     "dilli":        "Delhi",
#     "dilhi":        "Delhi",
#     "new delh":     "New Delhi",
#     "banglore":     "Bangalore",
#     "bangalor":     "Bangalore",
#     "bengaluru":    "Bengaluru",
#     "pune city":    "Pune",
#     "nagpure":      "Nagpur",
#     "hydrabad":     "Hyderabad",
#     "ahemdabad":    "Ahmedabad",
#     "ahemadabad":   "Ahmedabad",
#     "kolkatta":     "Kolkata",
#     "calcutta":     "Kolkata",
#     "chenai":       "Chennai",
#     "madras":       "Chennai",
#     "chandiwali":   "Chandivali",
#     "chandivalli":  "Chandivali",
#     "navi mubai":   "Navi Mumbai",
#     "vishakhapatnam": "Visakhapatnam",
# }

# WEATHER_CITY_PATTERNS: list[str] = [
#     r"(?:weather|forecast|conditions?|temperature|temp|rainfall|rain|humidity|wind|fog|mausam|barish|tapman)"
#     r"\s+(?:in|of|at|for|near)\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:\s+(?:today|now|currently|right now)|[?!.,]|$)",

#     r"(?:how(?:'s| is)(?: the)?|what(?:'s| is)(?: the)?)\s+"
#     r"(?:weather|temperature|temp|forecast|rain|humidity)\s+(?:in|at|of)\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

#     r"([A-Za-z][A-Za-z\s\-]{1,20}?)(?:'s|'s)\s+"
#     r"(?:weather|temperature|temp|rainfall|humidity|forecast|climate|mausam|tapman)",

#     r"([A-Za-z][A-Za-z\s\-]{1,20}?)\s+(?:weather|temperature|temp|rainfall|rain|humidity|forecast|mausam)",

#     r"(?:temperature|temp|rainfall|rain|weather|climate|humidity|forecast)\s+(?:of|in|at)?\s+"
#     r"([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

#     r"(?:will it rain|is it raining|going to rain)\s+in\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

#     r"how\s+(?:hot|cold|humid|warm|cool)\s+is\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",
# ]

# _WEATHER_NOISE = re.compile(
#     r"\b(weather|temperature|temp|forecast|rainfall|rain|humidity|wind|fog|"
#     r"today|now|currently|what|is|the|in|of|at|for|how|check|show|tell|me|"
#     r"get|city|degree|degrees|celsius|fahrenheit|conditions|climate|mausam|"
#     r"barish|tapman|sunny|cloudy|hot|cold|warm|windy|please|a|an|hawa)\b",
#     re.I,
# )

# # ══════════════════════════════════════════════════════════════════════════════
# #  COMMODITIES  –  synonyms, price triggers
# # ══════════════════════════════════════════════════════════════════════════════

# COMMODITY_SYNONYMS: dict[str, str] = {
#     # Grains
#     "wheat":        "wheat",  "gehun":      "wheat",  "gehu":       "wheat",  "gahu":     "wheat",
#     "rice":         "rice",   "paddy":      "rice",   "chawal":     "rice",   "dhan":     "rice",
#     "chaawal":      "rice",   "bhat":       "rice",
#     "maize":        "maize",  "corn":       "maize",  "makka":      "maize",  "bhutta":   "maize",
#     "makkai":       "maize",
#     "barley":       "barley", "jau":        "barley",
#     "jowar":        "jowar",  "sorghum":    "jowar",  "jwar":       "jowar",
#     "bajra":        "bajra",  "pearl millet":"bajra", "millet":     "bajra",  "bajri":    "bajra",
#     # Pulses
#     "moong":        "moong",  "green gram": "moong",  "mung":       "moong",
#     "urad":         "urad",   "black gram": "urad",   "urad dal":   "urad",   "urd":      "urad",
#     "arhar":        "arhar",  "tur":        "arhar",  "toor":       "arhar",  "pigeon pea":"arhar",
#     "tur dal":      "arhar",  "tuvar":      "arhar",  "arhar dal":  "arhar",
#     "chana":        "gram",   "gram":       "gram",   "chickpea":   "gram",   "Bengal gram":"gram",
#     "chanay":       "gram",   "chole":      "gram",   "kabuli chana":"gram",
#     "lentil":       "lentil", "masoor":     "lentil", "red lentil": "lentil", "masur":    "lentil",
#     # Vegetables
#     "potato":       "potato", "aloo":       "potato", "aaloo":      "potato", "alu":      "potato",
#     "aalu":         "potato", "batata":     "potato",
#     "onion":        "onion",  "pyaz":       "onion",  "pyaaz":      "onion",  "pyaj":     "onion",
#     "kanda":        "onion",  "piaz":       "onion",  "dungri":     "onion",
#     "tomato":       "tomato", "tamatar":    "tomato", "tamater":    "tomato", "tamaatar": "tomato",
#     "tomatoe":      "tomato",
#     "ginger":       "ginger", "adrak":      "ginger", "adrakh":     "ginger",
#     "garlic":       "garlic", "lahsun":     "garlic", "lasun":      "garlic", "lehsun":   "garlic",
#     "chilli":       "chilli", "mirchi":     "chilli", "chili":      "chilli",
#     "red chilli":   "chilli", "green chilli":"chilli","mirch":      "chilli",
#     "turmeric":     "turmeric","haldi":     "turmeric",
#     "brinjal":      "brinjal","baingan":    "brinjal","baigan":     "brinjal","vangi":    "brinjal",
#     "eggplant":     "brinjal","aubergine":  "brinjal",
#     "cabbage":      "cabbage","patta gobhi":"cabbage","bandh gobhi":"cabbage",
#     "cauliflower":  "cauliflower","phool gobhi":"cauliflower",
#     "bitter gourd": "bitter gourd","karela": "bitter gourd",
#     "bottle gourd": "bottle gourd","lauki":  "bottle gourd","dudhi":  "bottle gourd",
#     "ladyfinger":   "ladyfinger","bhindi":  "ladyfinger","okra":    "ladyfinger",
#     "pea":          "pea",    "matar":      "pea",    "mattar":     "pea",
#     "banana":       "banana", "kela":       "banana", "kele":       "banana",
#     # Oilseeds
#     "soyabean":     "soyabean","soybean":   "soyabean","soya":      "soyabean",
#     "groundnut":    "groundnut","peanut":   "groundnut","moongfali": "groundnut",
#     "mungfali":     "groundnut","shengdana":"groundnut",
#     "mustard":      "mustard","sarson":     "mustard","sarso":      "mustard",
#     "rapeseed":     "mustard","rai":        "mustard",
#     "sunflower":    "sunflower",
#     "sesame":       "sesame", "til":        "sesame",
#     "linseed":      "linseed","alsi":       "linseed",
#     # Cash crops
#     "cotton":       "cotton", "kapas":      "cotton", "kapaas":    "cotton",
#     "sugarcane":    "sugarcane","ganna":    "sugarcane","gana":     "sugarcane",
#     "jute":         "jute",
#     # Spices
#     "coriander":    "coriander","dhania":   "coriander","dhaniya":  "coriander",
#     "cumin":        "cumin",  "jeera":      "cumin",   "jira":      "cumin",
# }

# COMMODITY_PRICE_TRIGGERS: list[str] = [
#     "price of", "cost of", "rate of", "mandi price", "mandi rate",
#     "how much is", "current price", "today price", "market rate",
#     "price today", "today's price", "what is the price", "what's the price",
#     "bhav", "daam", "kya bhav", "kitna bhav", "market price",
#     "ka bhav", "ka daam", "ka rate", "ka price",
# ]

# # ══════════════════════════════════════════════════════════════════════════════
# #  FUZZY MATCHING HELPERS
# # ══════════════════════════════════════════════════════════════════════════════

# def _fuzzy_match_city(raw: str) -> str:
#     """
#     Return best-matching canonical city name.
#     Priority: alias map → exact → difflib.
#     Returns empty string if no good match (cutoff 0.72).
#     """
#     raw_lower = raw.strip().lower()
#     if not raw_lower or len(raw_lower) < 2:
#         return ""
#     # 1. Hard alias
#     if raw_lower in CITY_ALIASES:
#         return CITY_ALIASES[raw_lower]
#     # 2. Exact case-insensitive
#     for city in KNOWN_CITIES:
#         if city.lower() == raw_lower:
#             return city
#     # 3. Starts-with check (handles "nagpur city" → "Nagpur")
#     for city in KNOWN_CITIES:
#         if raw_lower.startswith(city.lower()) or city.lower().startswith(raw_lower):
#             if abs(len(raw_lower) - len(city.lower())) <= 4:
#                 return city
#     # 4. difflib fuzzy
#     lower_cities = [c.lower() for c in KNOWN_CITIES]
#     matches = difflib.get_close_matches(raw_lower, lower_cities, n=1, cutoff=0.72)
#     if matches:
#         for city in KNOWN_CITIES:
#             if city.lower() == matches[0]:
#                 return city
#     return ""


# def _fuzzy_match_commodity(raw: str) -> str:
#     """
#     Return canonical commodity name using synonym dict + difflib fallback.
#     Returns empty string if nothing found.
#     """
#     raw_lower = raw.strip().lower()
#     if not raw_lower:
#         return ""
#     # 1. Longest-match word-boundary in synonym dict
#     for key in sorted(COMMODITY_SYNONYMS, key=len, reverse=True):
#         if re.search(r"\b" + re.escape(key) + r"\b", raw_lower):
#             return COMMODITY_SYNONYMS[key]
#     # 2. difflib against synonym keys
#     syn_keys = list(COMMODITY_SYNONYMS.keys())
#     matches = difflib.get_close_matches(raw_lower, syn_keys, n=1, cutoff=0.78)
#     if matches:
#         return COMMODITY_SYNONYMS[matches[0]]
#     # 3. difflib against canonical values
#     canonical = list(set(COMMODITY_SYNONYMS.values()))
#     matches2 = difflib.get_close_matches(raw_lower, canonical, n=1, cutoff=0.78)
#     if matches2:
#         return matches2[0]
#     return ""


# def _fuzzy_is_weather_term(word: str) -> bool:
#     """Return True if word fuzzy-matches a weather keyword (cutoff 0.82)."""
#     return bool(difflib.get_close_matches(word.lower(), _WEATHER_TERM_LIST, n=1, cutoff=0.82))


# # ══════════════════════════════════════════════════════════════════════════════
# #  INTENT DETECTION
# # ══════════════════════════════════════════════════════════════════════════════

# def _is_weather_query(msg: str) -> bool:
#     """Check whether the message is about weather using synonyms + fuzzy."""
#     low = msg.lower()
#     # 1. Direct keyword match
#     for term in WEATHER_TERMS:
#         if term in low:
#             return True
#     # 2. Possessive pattern ("Chandivali's temperature")
#     if re.search(
#         r"[A-Za-z]+'s?\s+(?:temperature|temp|weather|forecast|rainfall|humidity|climate|mausam|tapman)",
#         msg, re.IGNORECASE
#     ):
#         return True
#     # 3. Fuzzy per-word
#     for word in re.sub(r"[^\w\s]", " ", low).split():
#         if len(word) > 3 and _fuzzy_is_weather_term(word):
#             return True
#     return False


# def _resolve_commodity_synonym(msg: str) -> str:
#     """
#     Return canonical commodity name if any synonym is found in the message.
#     First tries word-boundary exact match (longest first),
#     then falls back to difflib on individual tokens.
#     Returns empty string if nothing found.
#     """
#     low = msg.lower()
#     # 1. Longest word-boundary exact match
#     for syn in sorted(COMMODITY_SYNONYMS, key=len, reverse=True):
#         if re.search(r"\b" + re.escape(syn) + r"\b", low):
#             return COMMODITY_SYNONYMS[syn]
#     # 2. Fuzzy token matching
#     tokens = re.sub(r"[^\w\s]", " ", low).split()
#     for token in tokens:
#         if len(token) < 3:
#             continue
#         result = _fuzzy_match_commodity(token)
#         if result:
#             return result
#     return ""


# def detect_intent(message: str) -> str:
#     msg = message.lower().strip()

#     # Concern submission
#     if any(msg.startswith(p) for p in ["my concern is", "concern:", "i want to report"]):
#         return "save_concern"

#     # Weather
#     if _is_weather_query(msg):
#         return "weather"

#     # Commodity with explicit price trigger
#     if any(k in msg for k in COMMODITY_PRICE_TRIGGERS):
#         return "commodity_specific"

#     # Commodity by synonym
#     if _resolve_commodity_synonym(msg):
#         return "commodity_specific"

#     # News
#     if any(k in msg for k in [
#         "top news", "today's news", "today news", "headlines",
#         "latest news", "news today", "news", "published news", "unpublished"
#     ]):
#         return "top_news"

#     # Commodities overview
#     if any(k in msg for k in [
#         "commodity", "commodities", "agmarknet", "mandi", "market prices", "all prices"
#     ]):
#         return "commodities"

#     # Greeting — broad list of informal & formal greetings in English/Hindi
#     _GREETINGS = {
#         "hi", "hii", "hiii", "hiiii", "hey", "hello", "helo", "helo",
#         "namaste", "namaskar", "namasthe", "sat sri akal",
#         "good morning", "good afternoon", "good evening", "good night",
#         "sup", "wassup", "whats up", "what's up", "yo",
#         "kaise ho", "kaise hain", "kaisa hai", "kya haal", "kya hal",
#         "kya chal raha hai", "kya haal chaal", "theek ho",
#         "how are you", "how r u", "how ru", "how are u",
#         "how are you doing", "hows it going", "how's it going",
#         "how do you do", "greetings", "salaam", "salam",
#     }
#     # Check exact match OR if entire stripped message is a greeting phrase
#     if msg in _GREETINGS:
#         return "greeting"
#     # Check if message starts with a greeting word (e.g. "hii there")
#     first_word = msg.split()[0] if msg.split() else ""
#     if first_word in {"hi", "hii", "hiii", "hey", "hello", "namaste", "yo", "sup"}:
#         return "greeting"

#     # Help
#     if any(k in msg for k in ["help", "instruction", "how to use", "guide", "what can you do"]):
#         return "help"

#     # Raise concern
#     if any(k in msg for k in ["raise concern", "complaint", "issue", "problem", "concern", "report"]):
#         return "raise_concern"

#     return "general"


# # ══════════════════════════════════════════════════════════════════════════════
# #  ENTITY EXTRACTION
# # ══════════════════════════════════════════════════════════════════════════════

# def extract_city_name(message: str) -> str:
#     msg = message.strip()

#     # 1. Try structured regex patterns
#     for pat in WEATHER_CITY_PATTERNS:
#         m = re.search(pat, msg, re.IGNORECASE)
#         if m:
#             raw = m.group(1).strip()
#             if len(raw) > 1:
#                 # Try fuzzy canonicalisation
#                 canonical = _fuzzy_match_city(raw)
#                 return canonical if canonical else raw.title()

#     # 2. Noise-strip fallback
#     cleaned = _WEATHER_NOISE.sub("", msg)
#     cleaned = re.sub(r"'s?\b", "", cleaned)              # remove possessives
#     cleaned = re.sub(r"[^\w\s]", " ", cleaned)
#     cleaned = re.sub(r"\s+", " ", cleaned).strip()

#     if len(cleaned) > 2:
#         canonical = _fuzzy_match_city(cleaned)
#         return canonical if canonical else cleaned.title()

#     return ""


# def extract_commodity_name(message: str) -> str:
#     msg = message.strip()

#     # 1. Synonym + fuzzy resolution (returns canonical)
#     resolved = _resolve_commodity_synonym(msg.lower())
#     if resolved:
#         return resolved.title()

#     # 2. Explicit price pattern extraction → then resolve
#     patterns = [
#         r"price of\s+([A-Za-z ]+?)(?:\s+today|\s+price|[?!.,]|$)",
#         r"(?:rate|cost|mandi (?:price|rate)) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
#         r"current (?:price|rate) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
#         r"([A-Za-z]+) (?:price|rate|cost|mandi|bhav|daam)",
#         r"(?:bhav|daam) (?:of|for)?\s*([A-Za-z ]+?)(?:[?!.,]|$)",
#         r"(?:ka|ki|ke)\s+(?:bhav|daam|rate|price)\s+(?:of|for)?\s*([A-Za-z ]+?)(?:[?!.,]|$)",
#         r"([A-Za-z ]+?)\s+(?:ka|ki|ke)\s+(?:bhav|daam|rate|price)",
#     ]
#     for pat in patterns:
#         m = re.search(pat, msg, re.IGNORECASE)
#         if m:
#             raw = m.group(1).strip()
#             canonical = _fuzzy_match_commodity(raw)
#             return canonical.title() if canonical else raw.title()

#     return ""


# # ══════════════════════════════════════════════════════════════════════════════
# #  SESSION MANAGEMENT
# # ══════════════════════════════════════════════════════════════════════════════

# def _get_or_create_session_id() -> str:
#     """Use Flask server-side session to track the active chat session."""
#     if "chatbot_session_id" not in session:
#         session["chatbot_session_id"] = str(uuid.uuid4())
#     return session["chatbot_session_id"]


# def _current_user_id():
#     """Return the logged-in user's id, or None if not authenticated."""
#     try:
#         from flask_login import current_user as cu
#         if cu and cu.is_authenticated:
#             return int(cu.id)
#     except Exception:
#         pass
#     return None


# # ══════════════════════════════════════════════════════════════════════════════
# #  ENTRY POINTS  (called from routes.py)
# # ══════════════════════════════════════════════════════════════════════════════

# def handle_chatbot_request():
#     """POST /api/chatbot"""
#     try:
#         data       = request.get_json(silent=True) or {}
#         message    = (data.get("message") or "").strip()
#         action     = (data.get("action") or "").strip()
#         history    = data.get("history", [])
#         session_id = data.get("session_id") or _get_or_create_session_id()

#         if action:
#             result = handle_chatbot_action(action)
#             _save_history_entry("action:" + action, result.get("reply", ""), result.get("type", ""), session_id)
#             result["session_id"] = session_id
#             return jsonify(result), 200

#         if message:
#             result = handle_chatbot_message(message, history)
#             _save_history_entry(message, result.get("reply", ""), result.get("type", ""), session_id)
#             result["session_id"] = session_id
#             return jsonify(result), 200

#         return jsonify({"status": "error", "reply": "Please enter a message or select an option."}), 400

#     except Exception as e:
#         return jsonify({"status": "error", "reply": f"Something went wrong: {str(e)}"}), 500


# def handle_chatbot_get_history():
#     """GET /api/chatbot/history?session_id=<id>"""
#     try:
#         sid  = request.args.get("session_id")
#         rows = _load_history(session_id=sid)
#         return jsonify({"status": "success", "history": rows, "session_id": sid}), 200
#     except Exception as e:
#         print(f"[History Load Error] {e}")
#         return jsonify({"status": "error", "history": []}), 200


# def handle_chatbot_get_sessions():
#     """GET /api/chatbot/sessions  – list all sessions for this user."""
#     _ensure_session_column()
#     uid = _current_user_id()
#     if uid is None:
#         return jsonify({"status": "error", "sessions": [], "error": "Not authenticated"}), 200
#     if not _SESSION_COL_EXISTS:
#         return jsonify({"status": "success", "sessions": []}), 200
#     try:
#         db  = get_db()
#         cur = db.cursor(dictionary=True)
#         cur.execute("""
#             SELECT
#                 session_id,
#                 MIN(user_message)      AS first_msg,
#                 COUNT(*)               AS msg_count,
#                 MAX(created_at)        AS last_at
#             FROM chatbot_history
#             WHERE user_id = %s AND session_id IS NOT NULL
#             GROUP BY session_id
#             ORDER BY MAX(created_at) DESC
#             LIMIT 50
#         """, (uid,))
#         rows = cur.fetchall()
#         cur.close()
#         sessions = []
#         for row in rows:
#             ts = row["last_at"]
#             sessions.append({
#                 "session_id":    row["session_id"],
#                 "title":         _session_title(row["first_msg"]),
#                 "message_count": row["msg_count"],
#                 "last_at":       ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts or ""),
#             })
#         return jsonify({"status": "success", "sessions": sessions}), 200
#     except Exception as e:
#         print(f"[Sessions Error] {e}")
#         return jsonify({"status": "error", "sessions": []}), 200


# def handle_chatbot_new_session():
#     """POST /api/chatbot/new_session  – start a fresh chat session."""
#     new_sid = str(uuid.uuid4())
#     session["chatbot_session_id"] = new_sid
#     return jsonify({"status": "success", "session_id": new_sid}), 200


# def _session_title(first_msg) -> str:
#     if not first_msg:
#         return "Chat"
#     s = str(first_msg)
#     return s[:50] + ("…" if len(s) > 50 else "")


# # ══════════════════════════════════════════════════════════════════════════════
# #  ACTION HANDLER
# # ══════════════════════════════════════════════════════════════════════════════

# def handle_chatbot_action(action: str):
#     a = action.lower().strip()
#     dispatch = {
#         "top_news":      get_top_news_response,
#         "commodities":   get_commodities_overview_response,
#         "weather":       get_weather_prompt_response,
#         "help":          get_help_response,
#         "raise_concern": get_concern_prompt_response,
#     }
#     handler = dispatch.get(a)
#     if handler:
#         return handler()
#     return {"status": "error", "reply": "Unknown action.", "type": "error", "items": []}


# # ══════════════════════════════════════════════════════════════════════════════
# #  MESSAGE HANDLER
# # ══════════════════════════════════════════════════════════════════════════════

# def handle_chatbot_message(message: str, history: list):
#     intent = detect_intent(message)

#     if intent == "greeting":
#         return get_greeting_response()

#     if intent == "top_news":
#         return get_top_news_response()

#     if intent == "weather":
#         city = extract_city_name(message)
#         if city:
#             return get_weather_response(city)
#         # City not found — ask user
#         return get_weather_prompt_response()

#     if intent == "commodity_specific":
#         commodity = extract_commodity_name(message)
#         return get_commodity_price_response(commodity)

#     if intent == "commodities":
#         return get_commodities_overview_response()

#     if intent == "help":
#         return get_help_response()

#     if intent == "raise_concern":
#         return get_concern_prompt_response()

#     if intent == "save_concern":
#         return save_concern_response(message)

#     return get_groq_response(message, history)


# # ══════════════════════════════════════════════════════════════════════════════
# #  NEWS
# # ══════════════════════════════════════════════════════════════════════════════

# NEWS_CATEGORIES = {
#     "agriculture": [
#         "agriculture", "farm", "crop", "kisan", "mandi", "soil", "harvest", "agri",
#         "wheat", "rice", "maize", "onion", "potato", "vegetable", "fruit",
#         "livestock", "dairy", "fishery", "horticulture",
#     ],
#     "finance": [
#         "finance", "financial", "market", "economy", "stock", "sensex", "nifty",
#         "budget", "gdp", "inflation", "rbi", "bank", "rupee", "forex",
#         "investment", "trade", "export", "import", "fiscal",
#     ],
#     "energy": [
#         "energy", "oil", "fuel", "petrol", "diesel", "gas", "coal", "solar",
#         "wind", "power", "electricity", "nuclear", "renewable", "crude", "brent",
#     ],
#     "weather": [
#         "weather", "rain", "flood", "drought", "cyclone", "monsoon",
#         "temperature", "climate", "storm", "heatwave", "cold", "fog", "frost", "humidity",
#     ],
#     "general": [],
# }


# def get_top_news_response():
#     published     = _fetch_all_published_news()
#     non_published = _fetch_recent_non_published_news(limit=30)

#     if not published and not non_published:
#         return {
#             "status": "success", "type": "top_news",
#             "reply": "📰 No news available right now. Check back later!",
#             "items": [], "sections": [],
#         }

#     pub_sections  = _categorise_news(published)
#     npub_sections = _categorise_news(non_published)

#     all_articles = published + non_published
#     for art in all_articles:
#         art["summary"] = _summarize_article(art)

#     art_map = {str(a["id"]): a for a in all_articles}
#     for sec in pub_sections + npub_sections:
#         for art in sec["articles"]:
#             enriched = art_map.get(str(art["id"]), art)
#             art["summary"] = enriched.get("summary", "")

#     all_headlines = [a["headline"] for a in all_articles[:12]]
#     if groq_client and all_headlines:
#         try:
#             ai = groq_client.chat.completions.create(
#                 model=GROQ_MODEL,
#                 messages=[
#                     {"role": "system", "content": "You are a news editor. 2 sentences max."},
#                     {"role": "user", "content": "Brief overview of today's news:\n" +
#                      "\n".join(f"{i+1}. {h}" for i, h in enumerate(all_headlines))},
#                 ],
#                 max_tokens=100, temperature=0.4,
#             )
#             digest = ai.choices[0].message.content.strip()
#         except Exception:
#             digest = f"{len(all_articles)} total articles today."
#     else:
#         digest = f"{len(all_articles)} total articles today."

#     reply = (
#         f"📰 **Today's News Overview**\n\n{digest}\n\n"
#         f"✅ **Published:** {len(published)} articles · "
#         f"⏳ **Pending:** {len(non_published)} articles"
#     )
#     return {
#         "status": "success", "type": "top_news",
#         "reply": reply, "items": [],
#         "sections": {
#             "published":     pub_sections,
#             "non_published": npub_sections,
#         },
#     }


# def _categorise_news(articles: list) -> list:
#     buckets = {cat: [] for cat in NEWS_CATEGORIES}
#     for art in articles:
#         assigned = False
#         text = (art.get("headline", "") + " " + art.get("keywords", "") + " " + art.get("type", "")).lower()
#         for cat, keywords in NEWS_CATEGORIES.items():
#             if cat == "general":
#                 continue
#             if any(kw in text for kw in keywords):
#                 buckets[cat].append(art)
#                 assigned = True
#                 break
#         if not assigned:
#             buckets["general"].append(art)

#     labels = {
#         "agriculture": ("🌾", "Agriculture"),
#         "finance":     ("💹", "Finance"),
#         "energy":      ("⚡", "Energy"),
#         "weather":     ("🌦", "Weather"),
#         "general":     ("📋", "General"),
#     }
#     return [
#         {"category": cat, "emoji": em, "label": lb, "articles": arts}
#         for cat, (em, lb) in labels.items()
#         if (arts := buckets[cat])
#     ]


# def _fetch_all_published_news():
#     try:
#         db = get_db(); cursor = db.cursor(dictionary=True)
#         cursor.execute("""
#             SELECT id, news_date, news_type, news_headline, news_text, news_url, keywords
#             FROM published_news
#             WHERE news_date = CURDATE()
#             ORDER BY published_at DESC, id DESC
#         """)
#         rows = cursor.fetchall(); cursor.close()
#         return _fmt_rows(rows)
#     except Exception as e:
#         print(f"[Published News Error] {e}"); return []


# def _fetch_recent_non_published_news(limit=30):
#     try:
#         db = get_db(); cursor = db.cursor(dictionary=True)
#         cursor.execute("""
#             SELECT id, news_date, news_type, news_headline, news_text, news_url, keywords,
#                    date_of_insert
#             FROM non_published_news
#             ORDER BY date_of_insert DESC, id DESC
#             LIMIT %s
#         """, (limit,))
#         rows = cursor.fetchall(); cursor.close()
#         return _fmt_rows(rows)
#     except Exception as e:
#         print(f"[Non-Pub News Error] {e}"); return []


# def _fmt_rows(rows):
#     out = []
#     for row in rows:
#         d = row.get("news_date") or row.get("date_of_insert")
#         out.append({
#             "id":       str(row.get("id", "")),
#             "date":     d.strftime("%d-%m-%Y") if d and hasattr(d, "strftime") else str(d or ""),
#             "type":     row.get("news_type") or "General",
#             "headline": row.get("news_headline") or "No headline",
#             "content":  (row.get("news_text") or "")[:800],
#             "url":      row.get("news_url") or "",
#             "keywords": row.get("keywords") or "",
#         })
#     return out


# def _summarize_article(article: dict) -> str:
#     content  = (article.get("content") or "").strip()
#     headline = article.get("headline", "")
#     if not content or len(content) < 60:
#         return content[:300] if content else ""
#     if groq_client:
#         try:
#             ai = groq_client.chat.completions.create(
#                 model=GROQ_MODEL,
#                 messages=[
#                     {"role": "system", "content": "Summarize in exactly 3-4 concise lines. Be factual and neutral."},
#                     {"role": "user", "content": f"Headline: {headline}\n\nContent: {content[:700]}\n\nSummarize in 3-4 lines:"},
#                 ],
#                 max_tokens=110, temperature=0.3,
#             )
#             return ai.choices[0].message.content.strip()
#         except Exception:
#             pass
#     # Sentence fallback
#     sentences = re.split(r"(?<=[.!?])\s+", content.strip())
#     result, chars = [], 0
#     for s in sentences[:5]:
#         if chars + len(s) > 350:
#             break
#         result.append(s); chars += len(s)
#     return " ".join(result) if result else content[:280]


# # ══════════════════════════════════════════════════════════════════════════════
# #  COMMODITIES
# # ══════════════════════════════════════════════════════════════════════════════

# def get_commodities_overview_response():
#     now   = datetime.now()
#     year  = str(now.year)
#     month = str(now.month)

#     all_options = _fetch_commodity_list()
#     if not all_options:
#         return {
#             "status": "success", "type": "commodities_overview",
#             "reply": "⚠️ Commodity data unavailable right now. Try again later.",
#             "items": [],
#         }

#     TARGET_CROPS = [
#         "Wheat", "Rice", "Onion", "Potato", "Tomato", "Maize", "Soyabean",
#         "Cotton", "Groundnut", "Mustard", "Barley", "Turmeric", "Chilli", "Ginger", "Garlic",
#     ]
#     overview_items = []
#     for name in TARGET_CROPS:
#         match = next((c for c in all_options if c["cmdt_name"].lower() == name.lower()), None)
#         if not match:
#             match = next((c for c in all_options if name.lower() in c["cmdt_name"].lower()), None)
#         if not match:
#             continue
#         prices = _fetch_price_for_commodity(match["id"], year, month)
#         if not prices:
#             pm = now.month - 1 or 12
#             py = year if now.month > 1 else str(now.year - 1)
#             prices = _fetch_price_for_commodity(match["id"], py, str(pm))
#         if not prices:
#             continue
#         avg_p = sum(r["current_price"] for r in prices) / len(prices)
#         changes = [r["change"] for r in prices if r.get("change") is not None]
#         avg_chg = sum(changes) / len(changes) if changes else 0.0
#         overview_items.append({
#             "name":         match["cmdt_name"],
#             "avg_price":    round(avg_p, 2),
#             "change":       round(avg_chg, 2),
#             "state_count":  len(prices),
#             "commodity_id": match["id"],
#         })

#     if not overview_items:
#         return {
#             "status": "success", "type": "commodities_overview",
#             "reply": (
#                 f"🌾 **Commodity Prices**\n\n"
#                 f"Agmarknet hasn't published data for {MONTH_SHORT[month]} {year} yet.\n"
#                 f"Prices appear in the first week of each month.\n\n"
#                 f"**{len(all_options)}** commodities tracked. Ask: _\"price of wheat\"_"
#             ),
#             "items": [],
#         }

#     lines = [f"📊 **Live Commodity Prices** ({MONTH_SHORT[month]} {year})\n"]
#     for item in overview_items:
#         arrow = "▲" if item["change"] > 0 else ("▼" if item["change"] < 0 else "—")
#         lines.append(f"• **{item['name']}**: ₹{item['avg_price']:,.2f}/qtl {arrow}")
#     lines.append("\n_Click any tile or ask: \"Price of Onion\" for state-wise details_")

#     return {
#         "status": "success", "type": "commodities_overview",
#         "reply": "\n".join(lines), "items": overview_items,
#     }


# def get_commodity_price_response(commodity_name: str = ""):
#     if not commodity_name:
#         return get_commodities_overview_response()

#     # Always resolve through synonym + fuzzy
#     resolved = _resolve_commodity_synonym(commodity_name.lower())
#     if resolved:
#         commodity_name = resolved

#     now   = datetime.now()
#     year  = str(now.year)
#     month = str(now.month)

#     all_options = _fetch_commodity_list()
#     if not all_options:
#         return {
#             "status": "success", "type": "commodity_price",
#             "reply": "⚠️ Commodity data unavailable right now.", "items": [],
#         }

#     query   = commodity_name.lower().strip()
#     matched = next((c for c in all_options if c["cmdt_name"].lower() == query), None)
#     if not matched:
#         matched = next((c for c in all_options if query in c["cmdt_name"].lower()), None)
#     if not matched:
#         # fuzzy against Agmarknet commodity names
#         names_lower = [c["cmdt_name"].lower() for c in all_options]
#         fm = difflib.get_close_matches(query, names_lower, n=1, cutoff=0.65)
#         if fm:
#             matched = next((c for c in all_options if c["cmdt_name"].lower() == fm[0]), None)
#     if not matched:
#         words = [w for w in query.split() if len(w) > 2]
#         matched = next(
#             (c for c in all_options if any(w in c["cmdt_name"].lower() for w in words)), None
#         )

#     if not matched:
#         preview = ", ".join(c["cmdt_name"] for c in all_options[:15])
#         return {
#             "status": "success", "type": "commodity_price",
#             "reply": (
#                 f"❓ **{commodity_name}** not found in Agmarknet data.\n\n"
#                 f"Available: {preview}…\n\nTry: _\"price of wheat\"_"
#             ),
#             "items": [],
#         }

#     prices = _fetch_price_for_commodity(matched["id"], year, month)
#     mlabel = f"{MONTH_SHORT[month]} {year}"
#     if not prices:
#         pm = now.month - 1 or 12
#         py = year if now.month > 1 else str(now.year - 1)
#         prices = _fetch_price_for_commodity(matched["id"], py, str(pm))
#         mlabel = f"{MONTH_SHORT[str(pm)]} {py}"

#     if not prices:
#         return {
#             "status": "success", "type": "commodity_price",
#             "reply": f"🌾 **{matched['cmdt_name']}** — no price data for recent months.",
#             "items": [],
#         }

#     avg_p  = sum(r["current_price"] for r in prices) / len(prices)
#     high_r = max(prices, key=lambda r: r["current_price"])
#     low_r  = min(prices, key=lambda r: r["current_price"])

#     return {
#         "status": "success", "type": "commodity_price",
#         "reply": (
#             f"🌾 **{matched['cmdt_name']}** — Wholesale Prices ({mlabel})\n\n"
#             f"📊 Avg: **₹{avg_p:,.2f}/qtl** across {len(prices)} states\n"
#             f"📈 Highest: ₹{high_r['current_price']:,.2f} ({high_r.get('state', '-')})\n"
#             f"📉 Lowest:  ₹{low_r['current_price']:,.2f} ({low_r.get('state', '-')})\n\n"
#             "_Source: Agmarknet_"
#         ),
#         "items": prices[:12],
#     }


# def _fetch_commodity_list():
#     try:
#         resp = requests.get(
#             f"{AGMARK_BASE}/dashboard-commodities-filter",
#             headers=AGMARK_HEADERS, timeout=15,
#         )
#         resp.raise_for_status()
#         payload = resp.json()
#         raw = (
#             payload if isinstance(payload, list) else
#             payload.get("data") or payload.get("rows") or
#             payload.get("result") or payload.get("commodities") or []
#         )
#         if raw:
#             print(f"[DEBUG commodity sample]: {raw[0]}")
#         seen, out = set(), []
#         for item in raw:
#             if not isinstance(item, dict):
#                 continue
#             cid  = str(item.get("id") or item.get("commodity_id") or
#                        item.get("cmdt_id") or item.get("value") or "").strip()
#             name = str(item.get("cmdt_name") or item.get("commodity_name") or
#                        item.get("name") or item.get("label") or "").strip()
#             if cid and name and cid not in seen:
#                 seen.add(cid)
#                 out.append({"id": cid, "cmdt_name": name})
#         return sorted(out, key=lambda x: x["cmdt_name"].lower())
#     except Exception as e:
#         print(f"[Commodity List Error] {e}"); return []


# def _fetch_price_for_commodity(commodity_id: str, year: str, month: str):
#     try:
#         mi   = int(month)
#         pm   = mi - 1 or 12
#         py   = year if mi > 1 else str(int(year) - 1)
#         ckey = f"prices_{MONTH_NAMES[mi]}_{year}"
#         pkey = f"prices_{MONTH_NAMES[pm]}_{py}"

#         resp = requests.get(
#             f"{AGMARK_BASE}/price-trend/wholesale-prices-monthly",
#             params={
#                 "report_mode": "Statewise", "commodity": commodity_id,
#                 "year": year, "month": month,
#                 "state": "0", "district": "0", "export": "false",
#             },
#             headers=AGMARK_HEADERS, timeout=20,
#         )
#         resp.raise_for_status()
#         data = resp.json()
#         rows = data.get("rows", []) if isinstance(data, dict) else []
#         if rows:
#             print(f"[DEBUG price keys id={commodity_id}]: {list(rows[0].keys())}")

#         out = []
#         for row in rows:
#             if not isinstance(row, dict):
#                 continue
#             curr = (row.get(ckey) or row.get("modal_price") or
#                     row.get("avg_price") or row.get("price") or row.get("current_price"))
#             prev = (row.get(pkey) or row.get("prev_modal_price") or row.get("previous_price"))
#             try:
#                 curr = float(curr) if curr not in (None, "", "N/A", "0", 0) else None
#                 prev = float(prev) if prev not in (None, "", "N/A", "0", 0) else None
#             except (ValueError, TypeError):
#                 curr = prev = None
#             try:
#                 change = float(row.get("change_over_previous_month") or 0)
#             except Exception:
#                 change = 0.0
#             state = (row.get("state") or row.get("state_name") or row.get("statename") or "-")
#             if curr is not None:
#                 out.append({"state": state, "current_price": curr,
#                             "previous_price": prev, "change": change})
#         return out
#     except Exception as e:
#         print(f"[Price Error id={commodity_id}] {e}"); return []


# # ══════════════════════════════════════════════════════════════════════════════
# #  WEATHER
# # ══════════════════════════════════════════════════════════════════════════════

# def get_weather_prompt_response():
#     return {
#         "status": "success", "type": "weather_prompt",
#         "reply": (
#             "🌤 **Weather Lookup**\n\n"
#             "Type any city name using any phrasing:\n"
#             "• _Weather in Mumbai_\n"
#             "• _Temperature in Delhi_\n"
#             "• _Chandivali's temperature_\n"
#             "• _Rainfall in Nagpur_\n"
#             "• _How humid is Pune?_\n"
#             "• _Mausam in Aurangabad_"
#         ),
#         "items": [],
#     }


# def get_weather_response(city: str):
#     try:
#         geo = requests.get(
#             f"https://api.openweathermap.org/geo/1.0/direct"
#             f"?q={city}&limit=1&appid={OPENWEATHER_KEY}",
#             timeout=6,
#         ).json()

#         if not geo:
#             # Try fuzzy correction before giving up
#             corrected = _fuzzy_match_city(city)
#             if corrected and corrected.lower() != city.lower():
#                 return get_weather_response(corrected)
#             return {
#                 "status": "success", "type": "weather",
#                 "reply": f"❌ City **{city}** not found. Check spelling and try again.",
#                 "items": [],
#             }

#         lat, lon   = geo[0]["lat"], geo[0]["lon"]
#         resolved   = geo[0].get("name", city)
#         country    = geo[0].get("country", "")

#         wr = requests.get(
#             f"https://api.openweathermap.org/data/2.5/weather"
#             f"?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}",
#             timeout=6,
#         ).json()

#         if not wr.get("main"):
#             return {
#                 "status": "success", "type": "weather",
#                 "reply": f"⚠️ Weather unavailable for **{city}**.", "items": [],
#             }

#         temp     = round(wr["main"]["temp"])
#         feels    = round(wr["main"]["feels_like"])
#         humidity = wr["main"]["humidity"]
#         wind     = round(wr["wind"]["speed"], 1)
#         desc     = wr["weather"][0]["description"].title()
#         icon     = wr["weather"][0]["icon"]
#         advisory = _weather_advisory(temp, humidity, wind, desc)

#         return {
#             "status": "success", "type": "weather",
#             "reply": (
#                 f"🌤 **{resolved}, {country}** — {temp}°C ({desc})\n"
#                 f"💧 Humidity: {humidity}% · 💨 Wind: {wind} m/s · Feels: {feels}°C\n\n"
#                 f"📋 {advisory}"
#             ),
#             "items": [{
#                 "location":  f"{resolved}, {country}",
#                 "temp":      temp,
#                 "feels_like": feels,
#                 "desc":      desc,
#                 "icon":      icon,
#                 "humidity":  humidity,
#                 "wind":      wind,
#                 "overview":  advisory,
#             }],
#         }
#     except Exception as e:
#         print(f"[Weather Error] {e}")
#         return {"status": "error", "type": "weather",
#                 "reply": "⚠️ Could not fetch weather. Try again.", "items": []}


# def _weather_advisory(temp, humidity, wind, desc):
#     dl = desc.lower(); parts = []
#     if   temp >= 38: parts.append("🔥 Extreme heat — stay hydrated.")
#     elif temp >= 32: parts.append("☀️ Hot — carry water outdoors.")
#     elif temp <=  5: parts.append("🥶 Very cold — dress warmly.")
#     elif temp <= 15: parts.append("🧥 Cool — jacket recommended.")
#     else:            parts.append("😊 Comfortable temperatures.")
#     if   "rain"    in dl or "drizzle" in dl: parts.append("☔ Carry an umbrella.")
#     elif "storm"   in dl or "thunder" in dl: parts.append("⛈️ Thunderstorm — stay indoors.")
#     elif "snow"    in dl:                    parts.append("❄️ Snow expected.")
#     elif "fog"     in dl or "mist" in dl:    parts.append("🌫️ Low visibility — drive carefully.")
#     if humidity > 80: parts.append("💦 High humidity — feels muggy.")
#     if wind > 10:     parts.append(f"💨 Strong winds ({wind} m/s).")
#     return " ".join(parts)


# # ══════════════════════════════════════════════════════════════════════════════
# #  GROQ Q&A
# # ══════════════════════════════════════════════════════════════════════════════

# def get_groq_response(user_message: str, history: list):
#     if not groq_client:
#         return _fallback_response()
#     try:
#         msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
#         for t in history[-10:]:
#             r, c = t.get("role", "user"), t.get("content", "")
#             if r in ("user", "assistant") and c:
#                 msgs.append({"role": r, "content": c})
#         msgs.append({"role": "user", "content": user_message})
#         resp = groq_client.chat.completions.create(
#             model=GROQ_MODEL, messages=msgs, max_tokens=600, temperature=0.7,
#         )
#         return {
#             "status": "success", "type": "general",
#             "reply": resp.choices[0].message.content.strip(), "items": [],
#         }
#     except Exception as e:
#         print(f"[Groq Error] {e}"); return _fallback_response()


# # ══════════════════════════════════════════════════════════════════════════════
# #  HELP / CONCERN / FALLBACK
# # ══════════════════════════════════════════════════════════════════════════════

# def get_greeting_response():
#     from datetime import datetime as _dt
#     hour = _dt.now().hour
#     if hour < 12:
#         tod = "Good morning"
#     elif hour < 17:
#         tod = "Good afternoon"
#     else:
#         tod = "Good evening"
#     return {
#         "status": "success", "type": "greeting",
#         "reply": (
#             f"👋 {tod}! I'm your **Seamless Assistant**.\n\n"
#             "I can help you with:\n"
#             "• 📰 **Top News** — published & pending headlines\n"
#             "• 🌾 **Commodity Prices** — live Agmarknet data\n"
#             "• 🌤 **Weather** — real-time for any city\n"
#             "• 💬 **General Q&A** — ask me anything\n\n"
#             "Try: _\"Chandivali's temperature\"_, _\"Aloo ka bhav\"_, or _\"Top news\"_"
#         ),
#         "items": [],
#     }


# def get_help_response():
#     return {
#         "status": "success", "type": "help",
#         "reply": (
#             "👋 **Seamless Assistant — Help**\n\n"
#             "**What I can do:**\n"
#             "• **Top News** — All today's headlines (Published + Pending) with category sections\n"
#             "• **Commodities** — Live Agmarknet wholesale prices\n"
#             "• **Weather** — Real-time weather for any city\n"
#             "• **General Q&A** — Ask me anything\n"
#             "• **Raise Concern** — Submit a platform issue\n\n"
#             "**Natural Language Examples:**\n"
#             "- _\"Chandivali's temperature\"_ → weather lookup\n"
#             "- _\"Rainfall in Nagpur\"_ → weather lookup\n"
#             "- _\"Mausam in Pune\"_ → weather lookup\n"
#             "- _\"Aloo ka bhav\"_ → potato price\n"
#             "- _\"Gehu price today\"_ → wheat price\n"
#             "- _\"Pyaz rate\"_ → onion price\n"
#             "- _\"Tamatar ka daam\"_ → tomato price\n"
#             "- _\"Price of Wheat today\"_\n"
#             "- _\"Weather in Nagpur\"_\n"
#             "- _\"What is MSP?\"_\n"
#             "- _Concern: Dashboard is slow_\n\n"
#             "💡 **Tip:** I understand spelling mistakes too — "
#             "_\"mumbay\"_, _\"tomatoe\"_, _\"pyaaz\"_ all work fine!"
#         ),
#         "items": [],
#     }


# def get_concern_prompt_response():
#     return {
#         "status": "success", "type": "concern_prompt",
#         "reply": (
#             "⚠️ **Raise a Concern**\n\n"
#             "Start your message with: `Concern: [your issue]`\n\n"
#             "_Example:_ Concern: News feed is not loading on mobile."
#         ),
#         "items": [],
#     }


# def save_concern_response(message: str):
#     text = _extract_concern_text(message)
#     if _save_concern(text):
#         return {
#             "status": "success", "type": "concern_saved",
#             "reply": "✅ **Concern Recorded** — Saved and will be reviewed. Thank you!",
#             "items": [],
#         }
#     return {
#         "status": "error", "type": "concern_error",
#         "reply": "❌ Could not save concern. Please try again.", "items": [],
#     }


# def _extract_concern_text(msg: str) -> str:
#     msg = msg.strip()
#     for p in ["my concern is", "concern:", "i want to report", "i want to raise a concern about"]:
#         if msg.lower().startswith(p):
#             return msg[len(p):].strip(" :.-")
#     return msg


# def _save_concern(text: str) -> bool:
#     try:
#         db  = get_db(); cur = db.cursor()
#         uid = _current_user_id()
#         cur.execute(
#             "INSERT INTO chatbot_concerns (user_id, concern_text, created_at, status) "
#             "VALUES (%s, %s, NOW(), %s)",
#             (uid, text, "open"),
#         )
#         db.commit(); cur.close(); return True
#     except Exception as e:
#         print(f"[Concern Error] {e}"); return False


# def _fallback_response():
#     return {
#         "status": "success", "type": "fallback",
#         "reply": (
#             "I'm not sure I understood that. I can help with:\n\n"
#             "• **Top News** — all headlines with summaries\n"
#             "• **Commodity prices** — e.g. _\"price of wheat\"_ or _\"aloo ka bhav\"_\n"
#             "• **Weather** — e.g. _\"weather in Mumbai\"_ or _\"Chandivali's temperature\"_\n"
#             "• **General questions** — ask me anything\n\n"
#             "💡 I understand Hindi/Marathi names and spelling mistakes too!"
#         ),
#         "items": [],
#     }


# # ══════════════════════════════════════════════════════════════════════════════
# #  CHAT HISTORY  (DB-backed, session-aware)
# # ══════════════════════════════════════════════════════════════════════════════

# # Track whether we've already run the migration this process lifetime
# _SESSION_COL_EXISTS: bool = False


# def _ensure_session_column():
#     """
#     Add session_id column to chatbot_history if it doesn't exist yet.
#     Called lazily on first save — safe to call multiple times (idempotent).
#     """
#     global _SESSION_COL_EXISTS
#     if _SESSION_COL_EXISTS:
#         return
#     try:
#         db  = get_db()
#         cur = db.cursor()
#         # Check if column exists
#         cur.execute("""
#             SELECT COUNT(*) FROM information_schema.COLUMNS
#             WHERE TABLE_SCHEMA = DATABASE()
#               AND TABLE_NAME   = 'chatbot_history'
#               AND COLUMN_NAME  = 'session_id'
#         """)
#         (count,) = cur.fetchone()
#         if count == 0:
#             cur.execute(
#                 "ALTER TABLE chatbot_history ADD COLUMN session_id VARCHAR(64) NULL"
#             )
#             db.commit()
#             print("[chatbot] ✅ Added session_id column to chatbot_history")
#         cur.close()
#         _SESSION_COL_EXISTS = True
#     except Exception as e:
#         print(f"[chatbot] ⚠️  Could not add session_id column: {e}")
#         # Still mark as done so we don't retry every request
#         _SESSION_COL_EXISTS = True


# def _save_history_entry(user_msg: str, bot_reply: str, msg_type: str, session_id: str = None):
#     """
#     Save one conversation turn.
#     Works even if session_id column doesn't exist yet (falls back gracefully).
#     """
#     _ensure_session_column()
#     uid = _current_user_id()
#     sid = session_id or _get_or_create_session_id()
#     try:
#         db  = get_db()
#         cur = db.cursor()
#         if _SESSION_COL_EXISTS:
#             cur.execute(
#                 """INSERT INTO chatbot_history
#                    (user_id, session_id, user_message, bot_reply, msg_type, created_at)
#                    VALUES (%s, %s, %s, %s, %s, NOW())""",
#                 (uid, sid, user_msg[:500], bot_reply[:2000], msg_type),
#             )
#         else:
#             cur.execute(
#                 """INSERT INTO chatbot_history
#                    (user_id, user_message, bot_reply, msg_type, created_at)
#                    VALUES (%s, %s, %s, %s, NOW())""",
#                 (uid, user_msg[:500], bot_reply[:2000], msg_type),
#             )
#         db.commit()
#         cur.close()
#         print(f"[chatbot] 💾 Saved history — user_id={uid} session={sid} type={msg_type}")
#     except Exception as e:
#         print(f"[History Save Error] {e}")


# def _load_history(limit: int = 100, session_id: str = None) -> list:
#     """
#     Load chat history for the current user.
#     If session_id given → load that session (ASC order = oldest first).
#     Otherwise → load most recent `limit` messages across all sessions.
#     """
#     uid = _current_user_id()
#     if uid is None:
#         print("[History Load] user_id is None — user not authenticated?")
#         return []
#     try:
#         db  = get_db()
#         cur = db.cursor(dictionary=True)

#         if _SESSION_COL_EXISTS and session_id:
#             cur.execute(
#                 """SELECT user_message, bot_reply, msg_type, session_id, created_at
#                    FROM chatbot_history
#                    WHERE user_id = %s AND session_id = %s
#                    ORDER BY created_at ASC
#                    LIMIT %s""",
#                 (uid, session_id, limit),
#             )
#         else:
#             cur.execute(
#                 """SELECT user_message, bot_reply, msg_type, created_at
#                    FROM chatbot_history
#                    WHERE user_id = %s
#                    ORDER BY created_at DESC
#                    LIMIT %s""",
#                 (uid, limit),
#             )
#         rows = cur.fetchall()
#         cur.close()

#         # DESC query → reverse for chronological display
#         if not (session_id and _SESSION_COL_EXISTS):
#             rows = list(reversed(rows))

#         result = []
#         for row in rows:
#             ts     = row.get("created_at")
#             ts_str = ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts or "")
#             result.append({
#                 "user_message": row["user_message"],
#                 "bot_reply":    row["bot_reply"],
#                 "msg_type":     row.get("msg_type", "general"),
#                 "session_id":   row.get("session_id", ""),
#                 "timestamp":    ts_str,
#             })
#         return result
#     except Exception as e:
#         print(f"[History Load Error] {e}")
#         return []


# # ══════════════════════════════════════════════════════════════════════════════
# #  ROUTES REFERENCE  (add to your routes.py / main blueprint)
# # ══════════════════════════════════════════════════════════════════════════════
# #
# #  from .chatbot import (
# #      handle_chatbot_request,
# #      handle_chatbot_get_history,
# #      handle_chatbot_get_sessions,
# #      handle_chatbot_new_session,
# #  )
# #
# #  @main_bp.route("/chatbot",                  methods=["GET"])
# #  @login_required
# #  def chatbot():
# #      return render_template("main/chatbot.html")
# #
# #  @main_bp.route("/api/chatbot",              methods=["POST"])
# #  @login_required
# #  def chatbot_api():
# #      return handle_chatbot_request()
# #
# #  @main_bp.route("/api/chatbot/history",      methods=["GET"])
# #  @login_required
# #  def chatbot_history_api():
# #      return handle_chatbot_get_history()
# #
# #  @main_bp.route("/api/chatbot/sessions",     methods=["GET"])
# #  @login_required
# #  def chatbot_sessions_api():
# #      return handle_chatbot_get_sessions()
# #
# #  @main_bp.route("/api/chatbot/new_session",  methods=["POST"])
# #  @login_required
# #  def chatbot_new_session_api():
# #      return handle_chatbot_new_session()


"""
chatbot.py  –  Seamless Assistant backend
==========================================
Improvements over previous version
------------------------------------
1.  Fuzzy / typo tolerance via difflib (no extra pip install)
    - City names: "mumbay" → Mumbai, "chandiwali" → Chandivali, etc.
    - Commodity names: "pyaaz" → onion, "tomatoe" → tomato, etc.
    - Weather keywords: "temprature" → temperature, "wheather" → weather, etc.
2.  Extended synonym lists (70+ commodities, 50+ weather terms)
3.  Session management: session_id on every message; new_session; list sessions
4.  Chat history auto-loads in frontend (session-aware DB schema)
5.  All existing features preserved: Groq Q&A, Agmarknet prices,
    OpenWeather, news (published + non-published), concerns
"""

from __future__ import annotations

import difflib
import os
import re
import uuid
from datetime import datetime
from flask import jsonify, request, session
from flask_login import current_user
from app.db import get_db

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

import requests

# ─── Config ───────────────────────────────────────────────────────────────────
GROQ_API_KEY    = os.environ.get("GROQ_API_KEY", "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")
OPENWEATHER_KEY = "2baab2dc7ad18ffef8b81c014e893e1c"
AGMARK_BASE     = "https://api.agmarknet.gov.in/v1"
GROQ_MODEL      = "llama-3.3-70b-versatile"

groq_client = Groq(api_key=GROQ_API_KEY) if (GROQ_AVAILABLE and GROQ_API_KEY) else None

AGMARK_HEADERS = {
    "accept": "application/json, text/plain, */*",
    "accept-language": "en-US,en;q=0.8",
    "origin": "https://www.agmarknet.gov.in",
    "referer": "https://www.agmarknet.gov.in/",
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/146.0.0.0 Safari/537.36"
    ),
}

MONTH_NAMES = {
    1:"january", 2:"february", 3:"march",    4:"april",
    5:"may",     6:"june",     7:"july",     8:"august",
    9:"september",10:"october",11:"november",12:"december"
}
MONTH_SHORT = {
    "1":"Jan","2":"Feb","3":"Mar","4":"Apr","5":"May","6":"Jun",
    "7":"Jul","8":"Aug","9":"Sep","10":"Oct","11":"Nov","12":"Dec"
}

SYSTEM_PROMPT = """You are Seamless Assistant, a helpful AI chatbot for the Seamless project management platform.
You help with news summaries, live commodity prices, real-time weather, and general Q&A.
Keep responses concise, friendly, and professional. Use **bold** for key terms.
For general knowledge questions (farming, economy, weather concepts, agriculture), answer from your training knowledge.
Never fabricate live data (prices, weather) — only reference data explicitly provided to you.
"""

# ══════════════════════════════════════════════════════════════════════════════
#  WEATHER  –  keywords, city aliases, patterns
# ══════════════════════════════════════════════════════════════════════════════

WEATHER_TERMS: set[str] = {
    # Core
    "weather", "forecast", "conditions", "climate",
    # Temperature
    "temperature", "temp", "hot", "cold", "heat", "warmth", "cool", "chilly",
    "freezing", "degree", "degrees", "celsius", "fahrenheit", "kelvin",
    "how hot", "how cold", "how warm",
    # Precipitation
    "rain", "rainfall", "raining", "rainy", "drizzle", "shower", "precipitation",
    "snow", "snowfall", "hail", "sleet", "baarish", "barish", "paus",
    # Wind / atmosphere
    "wind", "wind speed", "windy", "gust", "storm", "thunder", "lightning",
    "humid", "humidity", "fog", "foggy", "mist", "misty", "hawa",
    # Sky
    "sunny", "sunshine", "cloudy", "overcast", "clear sky", "partly cloudy",
    # Hindi / Marathi
    "mausam", "garmi", "sardi", "thand", "tapman", "dhuke",
    # Conversational
    "umbrella", "carry umbrella", "bring umbrella", "need umbrella",
    "wear jacket", "dress warmly", "what to wear",
    "is it raining", "will it rain", "going to rain", "chance of rain",
    "is it hot", "is it cold", "is it sunny", "feels like",
    "uv index", "air quality", "visibility", "pressure",
}

# All weather synonym words as a flat list for fuzzy matching
_WEATHER_TERM_LIST: list[str] = sorted(WEATHER_TERMS)

# Canonical city names for fuzzy matching
KNOWN_CITIES: list[str] = [
    "Mumbai", "Delhi", "New Delhi", "Bangalore", "Bengaluru", "Hyderabad",
    "Ahmedabad", "Chennai", "Kolkata", "Pune", "Nagpur", "Surat", "Jaipur",
    "Lucknow", "Kanpur", "Indore", "Thane", "Bhopal", "Visakhapatnam",
    "Patna", "Vadodara", "Ghaziabad", "Ludhiana", "Agra", "Nashik",
    "Aurangabad", "Solapur", "Amravati", "Kolhapur", "Akola", "Latur",
    "Dhule", "Nanded", "Chandivali", "Kalyan", "Navi Mumbai", "Pimpri",
    "Coimbatore", "Kochi", "Thiruvananthapuram", "Madurai", "Mangaluru",
    "Bhubaneswar", "Guwahati", "Ranchi", "Raipur", "Chandigarh",
    "Dehradun", "Shimla", "Jammu", "Srinagar", "Varanasi", "Allahabad",
    "Jodhpur", "Udaipur", "Kota", "Ajmer", "Bikaner",
]

# Hard-coded alias corrections (always beats fuzzy)
CITY_ALIASES: dict[str, str] = {
    "mumbay":       "Mumbai",
    "bombay":       "Mumbai",
    "bomaby":       "Mumbai",
    "dilli":        "Delhi",
    "dilhi":        "Delhi",
    "new delh":     "New Delhi",
    "banglore":     "Bangalore",
    "bangalor":     "Bangalore",
    "bengaluru":    "Bengaluru",
    "pune city":    "Pune",
    "nagpure":      "Nagpur",
    "hydrabad":     "Hyderabad",
    "ahemdabad":    "Ahmedabad",
    "ahemadabad":   "Ahmedabad",
    "kolkatta":     "Kolkata",
    "calcutta":     "Kolkata",
    "chenai":       "Chennai",
    "madras":       "Chennai",
    "chandiwali":   "Chandivali",
    "chandivalli":  "Chandivali",
    "navi mubai":   "Navi Mumbai",
    "vishakhapatnam": "Visakhapatnam",
}

WEATHER_CITY_PATTERNS: list[str] = [
    r"(?:weather|forecast|conditions?|temperature|temp|rainfall|rain|humidity|wind|fog|mausam|barish|tapman)"
    r"\s+(?:in|of|at|for|near)\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:\s+(?:today|now|currently|right now)|[?!.,]|$)",

    r"(?:how(?:'s| is)(?: the)?|what(?:'s| is)(?: the)?)\s+"
    r"(?:weather|temperature|temp|forecast|rain|humidity)\s+(?:in|at|of)\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

    r"([A-Za-z][A-Za-z\s\-]{1,20}?)(?:'s|'s)\s+"
    r"(?:weather|temperature|temp|rainfall|humidity|forecast|climate|mausam|tapman)",

    r"([A-Za-z][A-Za-z\s\-]{1,20}?)\s+(?:weather|temperature|temp|rainfall|rain|humidity|forecast|mausam)",

    r"(?:temperature|temp|rainfall|rain|weather|climate|humidity|forecast)\s+(?:of|in|at)?\s+"
    r"([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

    r"(?:will it rain|is it raining|going to rain)\s+in\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",

    r"how\s+(?:hot|cold|humid|warm|cool)\s+is\s+([A-Za-z][A-Za-z\s\-]{1,30}?)(?:[?!.,]|$)",
]

_WEATHER_NOISE = re.compile(
    r"\b(weather|temperature|temp|forecast|rainfall|rain|humidity|wind|fog|"
    r"today|now|currently|what|is|the|in|of|at|for|how|check|show|tell|me|"
    r"get|city|degree|degrees|celsius|fahrenheit|conditions|climate|mausam|"
    r"barish|tapman|sunny|cloudy|hot|cold|warm|windy|please|a|an|hawa)\b",
    re.I,
)

# ══════════════════════════════════════════════════════════════════════════════
#  COMMODITIES  –  synonyms, price triggers
# ══════════════════════════════════════════════════════════════════════════════

COMMODITY_SYNONYMS: dict[str, str] = {
    # Grains
    "wheat":        "wheat",  "gehun":      "wheat",  "gehu":       "wheat",  "gahu":     "wheat",
    "rice":         "rice",   "paddy":      "rice",   "chawal":     "rice",   "dhan":     "rice",
    "chaawal":      "rice",   "bhat":       "rice",
    "maize":        "maize",  "corn":       "maize",  "makka":      "maize",  "bhutta":   "maize",
    "makkai":       "maize",
    "barley":       "barley", "jau":        "barley",
    "jowar":        "jowar",  "sorghum":    "jowar",  "jwar":       "jowar",
    "bajra":        "bajra",  "pearl millet":"bajra", "millet":     "bajra",  "bajri":    "bajra",
    # Pulses
    "moong":        "moong",  "green gram": "moong",  "mung":       "moong",
    "urad":         "urad",   "black gram": "urad",   "urad dal":   "urad",   "urd":      "urad",
    "arhar":        "arhar",  "tur":        "arhar",  "toor":       "arhar",  "pigeon pea":"arhar",
    "tur dal":      "arhar",  "tuvar":      "arhar",  "arhar dal":  "arhar",
    "chana":        "gram",   "gram":       "gram",   "chickpea":   "gram",   "Bengal gram":"gram",
    "chanay":       "gram",   "chole":      "gram",   "kabuli chana":"gram",
    "lentil":       "lentil", "masoor":     "lentil", "red lentil": "lentil", "masur":    "lentil",
    # Vegetables
    "potato":       "potato", "aloo":       "potato", "aaloo":      "potato", "alu":      "potato",
    "aalu":         "potato", "batata":     "potato",
    "onion":        "onion",  "pyaz":       "onion",  "pyaaz":      "onion",  "pyaj":     "onion",
    "kanda":        "onion",  "piaz":       "onion",  "dungri":     "onion",
    "tomato":       "tomato", "tamatar":    "tomato", "tamater":    "tomato", "tamaatar": "tomato",
    "tomatoe":      "tomato",
    "ginger":       "ginger", "adrak":      "ginger", "adrakh":     "ginger",
    "garlic":       "garlic", "lahsun":     "garlic", "lasun":      "garlic", "lehsun":   "garlic",
    "chilli":       "chilli", "mirchi":     "chilli", "chili":      "chilli",
    "red chilli":   "chilli", "green chilli":"chilli","mirch":      "chilli",
    "turmeric":     "turmeric","haldi":     "turmeric",
    "brinjal":      "brinjal","baingan":    "brinjal","baigan":     "brinjal","vangi":    "brinjal",
    "eggplant":     "brinjal","aubergine":  "brinjal",
    "cabbage":      "cabbage","patta gobhi":"cabbage","bandh gobhi":"cabbage",
    "cauliflower":  "cauliflower","phool gobhi":"cauliflower",
    "bitter gourd": "bitter gourd","karela": "bitter gourd",
    "bottle gourd": "bottle gourd","lauki":  "bottle gourd","dudhi":  "bottle gourd",
    "ladyfinger":   "ladyfinger","bhindi":  "ladyfinger","okra":    "ladyfinger",
    "pea":          "pea",    "matar":      "pea",    "mattar":     "pea",
    "banana":       "banana", "kela":       "banana", "kele":       "banana",
    # Oilseeds
    "soyabean":     "soyabean","soybean":   "soyabean","soya":      "soyabean",
    "groundnut":    "groundnut","peanut":   "groundnut","moongfali": "groundnut",
    "mungfali":     "groundnut","shengdana":"groundnut",
    "mustard":      "mustard","sarson":     "mustard","sarso":      "mustard",
    "rapeseed":     "mustard","rai":        "mustard",
    "sunflower":    "sunflower",
    "sesame":       "sesame", "til":        "sesame",
    "linseed":      "linseed","alsi":       "linseed",
    # Cash crops
    "cotton":       "cotton", "kapas":      "cotton", "kapaas":    "cotton",
    "sugarcane":    "sugarcane","ganna":    "sugarcane","gana":     "sugarcane",
    "jute":         "jute",
    # Spices
    "coriander":    "coriander","dhania":   "coriander","dhaniya":  "coriander",
    "cumin":        "cumin",  "jeera":      "cumin",   "jira":      "cumin",
}

COMMODITY_PRICE_TRIGGERS: list[str] = [
    "price of", "cost of", "rate of", "mandi price", "mandi rate",
    "how much is", "current price", "today price", "market rate",
    "price today", "today's price", "what is the price", "what's the price",
    "bhav", "daam", "kya bhav", "kitna bhav", "market price",
    "ka bhav", "ka daam", "ka rate", "ka price",
]

# ══════════════════════════════════════════════════════════════════════════════
#  FUZZY MATCHING HELPERS
# ══════════════════════════════════════════════════════════════════════════════

def _fuzzy_match_city(raw: str) -> str:
    """
    Return best-matching canonical city name.
    Priority: alias map → exact → difflib.
    Returns empty string if no good match (cutoff 0.72).
    """
    raw_lower = raw.strip().lower()
    if not raw_lower or len(raw_lower) < 2:
        return ""
    # 1. Hard alias
    if raw_lower in CITY_ALIASES:
        return CITY_ALIASES[raw_lower]
    # 2. Exact case-insensitive
    for city in KNOWN_CITIES:
        if city.lower() == raw_lower:
            return city
    # 3. Starts-with check (handles "nagpur city" → "Nagpur")
    for city in KNOWN_CITIES:
        if raw_lower.startswith(city.lower()) or city.lower().startswith(raw_lower):
            if abs(len(raw_lower) - len(city.lower())) <= 4:
                return city
    # 4. difflib fuzzy
    lower_cities = [c.lower() for c in KNOWN_CITIES]
    matches = difflib.get_close_matches(raw_lower, lower_cities, n=1, cutoff=0.72)
    if matches:
        for city in KNOWN_CITIES:
            if city.lower() == matches[0]:
                return city
    return ""


def _fuzzy_match_commodity(raw: str) -> str:
    """
    Return canonical commodity name using synonym dict + difflib fallback.
    Returns empty string if nothing found.
    """
    raw_lower = raw.strip().lower()
    if not raw_lower:
        return ""
    # 1. Longest-match word-boundary in synonym dict
    for key in sorted(COMMODITY_SYNONYMS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(key) + r"\b", raw_lower):
            return COMMODITY_SYNONYMS[key]
    # 2. difflib against synonym keys
    syn_keys = list(COMMODITY_SYNONYMS.keys())
    matches = difflib.get_close_matches(raw_lower, syn_keys, n=1, cutoff=0.78)
    if matches:
        return COMMODITY_SYNONYMS[matches[0]]
    # 3. difflib against canonical values
    canonical = list(set(COMMODITY_SYNONYMS.values()))
    matches2 = difflib.get_close_matches(raw_lower, canonical, n=1, cutoff=0.78)
    if matches2:
        return matches2[0]
    return ""


def _fuzzy_is_weather_term(word: str) -> bool:
    """Return True if word fuzzy-matches a weather keyword (cutoff 0.82)."""
    return bool(difflib.get_close_matches(word.lower(), _WEATHER_TERM_LIST, n=1, cutoff=0.82))


# ══════════════════════════════════════════════════════════════════════════════
#  INTENT DETECTION
# ══════════════════════════════════════════════════════════════════════════════

def _is_weather_query(msg: str) -> bool:
    """Check whether the message is about weather using synonyms + fuzzy."""
    low = msg.lower()
    # 1. Direct keyword match
    for term in WEATHER_TERMS:
        if term in low:
            return True
    # 2. Possessive pattern ("Chandivali's temperature")
    if re.search(
        r"[A-Za-z]+'s?\s+(?:temperature|temp|weather|forecast|rainfall|humidity|climate|mausam|tapman)",
        msg, re.IGNORECASE
    ):
        return True
    # 3. Fuzzy per-word
    for word in re.sub(r"[^\w\s]", " ", low).split():
        if len(word) > 3 and _fuzzy_is_weather_term(word):
            return True
    return False


def _resolve_commodity_synonym(msg: str) -> str:
    """
    Return canonical commodity name if any synonym is found in the message.
    First tries word-boundary exact match (longest first),
    then falls back to difflib on individual tokens.
    Returns empty string if nothing found.
    """
    low = msg.lower()
    # 1. Longest word-boundary exact match
    for syn in sorted(COMMODITY_SYNONYMS, key=len, reverse=True):
        if re.search(r"\b" + re.escape(syn) + r"\b", low):
            return COMMODITY_SYNONYMS[syn]
    # 2. Fuzzy token matching
    tokens = re.sub(r"[^\w\s]", " ", low).split()
    for token in tokens:
        if len(token) < 3:
            continue
        result = _fuzzy_match_commodity(token)
        if result:
            return result
    return ""


def detect_intent(message: str) -> str:
    msg = message.lower().strip()

    # Concern submission
    if any(msg.startswith(p) for p in ["my concern is", "concern:", "i want to report"]):
        return "save_concern"

    # Weather
    if _is_weather_query(msg):
        return "weather"

    # Commodity with explicit price trigger
    if any(k in msg for k in COMMODITY_PRICE_TRIGGERS):
        return "commodity_specific"

    # Commodity by synonym
    if _resolve_commodity_synonym(msg):
        return "commodity_specific"

    # News
    if any(k in msg for k in [
        "top news", "today's news", "today news", "headlines",
        "latest news", "news today", "news", "published news", "unpublished"
    ]):
        return "top_news"

    # Commodities overview
    if any(k in msg for k in [
        "commodity", "commodities", "agmarknet", "mandi", "market prices", "all prices"
    ]):
        return "commodities"

    # Greeting — broad list of informal & formal greetings in English/Hindi
    _GREETINGS = {
        "hi", "hii", "hiii", "hiiii", "hey", "hello", "helo", "helo",
        "namaste", "namaskar", "namasthe", "sat sri akal",
        "good morning", "good afternoon", "good evening", "good night",
        "sup", "wassup", "whats up", "what's up", "yo",
        "kaise ho", "kaise hain", "kaisa hai", "kya haal", "kya hal",
        "kya chal raha hai", "kya haal chaal", "theek ho",
        "how are you", "how r u", "how ru", "how are u",
        "how are you doing", "hows it going", "how's it going",
        "how do you do", "greetings", "salaam", "salam",
    }
    # Check exact match OR if entire stripped message is a greeting phrase
    if msg in _GREETINGS:
        return "greeting"
    # Check if message starts with a greeting word (e.g. "hii there")
    first_word = msg.split()[0] if msg.split() else ""
    if first_word in {"hi", "hii", "hiii", "hey", "hello", "namaste", "yo", "sup"}:
        return "greeting"

    # Help
    if any(k in msg for k in ["help", "instruction", "how to use", "guide", "what can you do"]):
        return "help"

    # Raise concern
    if any(k in msg for k in ["raise concern", "complaint", "issue", "problem", "concern", "report"]):
        return "raise_concern"

    return "general"


# ══════════════════════════════════════════════════════════════════════════════
#  ENTITY EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def extract_city_name(message: str) -> str:
    msg = message.strip()

    # 1. Try structured regex patterns
    for pat in WEATHER_CITY_PATTERNS:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            if len(raw) > 1:
                # Try fuzzy canonicalisation
                canonical = _fuzzy_match_city(raw)
                return canonical if canonical else raw.title()

    # 2. Noise-strip fallback
    cleaned = _WEATHER_NOISE.sub("", msg)
    cleaned = re.sub(r"'s?\b", "", cleaned)              # remove possessives
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > 2:
        canonical = _fuzzy_match_city(cleaned)
        return canonical if canonical else cleaned.title()

    return ""


def extract_commodity_name(message: str) -> str:
    msg = message.strip()

    # 1. Synonym + fuzzy resolution (returns canonical)
    resolved = _resolve_commodity_synonym(msg.lower())
    if resolved:
        return resolved.title()

    # 2. Explicit price pattern extraction → then resolve
    patterns = [
        r"price of\s+([A-Za-z ]+?)(?:\s+today|\s+price|[?!.,]|$)",
        r"(?:rate|cost|mandi (?:price|rate)) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
        r"current (?:price|rate) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
        r"([A-Za-z]+) (?:price|rate|cost|mandi|bhav|daam)",
        r"(?:bhav|daam) (?:of|for)?\s*([A-Za-z ]+?)(?:[?!.,]|$)",
        r"(?:ka|ki|ke)\s+(?:bhav|daam|rate|price)\s+(?:of|for)?\s*([A-Za-z ]+?)(?:[?!.,]|$)",
        r"([A-Za-z ]+?)\s+(?:ka|ki|ke)\s+(?:bhav|daam|rate|price)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            raw = m.group(1).strip()
            canonical = _fuzzy_match_commodity(raw)
            return canonical.title() if canonical else raw.title()

    return ""


# ══════════════════════════════════════════════════════════════════════════════
#  SESSION MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════

def _get_or_create_session_id() -> str:
    """Use Flask server-side session to track the active chat session."""
    if "chatbot_session_id" not in session:
        session["chatbot_session_id"] = str(uuid.uuid4())
    return session["chatbot_session_id"]


def _current_user_id():
    """Return the logged-in user's id, or None if not authenticated."""
    try:
        from flask_login import current_user as cu
        if cu and cu.is_authenticated:
            return int(cu.id)
    except Exception:
        pass
    return None


# ══════════════════════════════════════════════════════════════════════════════
#  ENTRY POINTS  (called from routes.py)
# ══════════════════════════════════════════════════════════════════════════════

def handle_chatbot_request():
    """POST /api/chatbot"""
    try:
        data       = request.get_json(silent=True) or {}
        message    = (data.get("message") or "").strip()
        action     = (data.get("action") or "").strip()
        history    = data.get("history", [])
        session_id = data.get("session_id") or _get_or_create_session_id()

        if action:
            result = handle_chatbot_action(action)
            _save_history_entry("action:" + action, result.get("reply", ""), result.get("type", ""), session_id)
            result["session_id"] = session_id
            return jsonify(result), 200

        if message:
            result = handle_chatbot_message(message, history)
            _save_history_entry(message, result.get("reply", ""), result.get("type", ""), session_id)
            result["session_id"] = session_id
            return jsonify(result), 200

        return jsonify({"status": "error", "reply": "Please enter a message or select an option."}), 400

    except Exception as e:
        return jsonify({"status": "error", "reply": f"Something went wrong: {str(e)}"}), 500


def handle_chatbot_get_history():
    """GET /api/chatbot/history?session_id=<id>"""
    try:
        sid  = request.args.get("session_id") or _get_or_create_session_id()
        rows = _load_history(session_id=sid)
        return jsonify({"status": "success", "history": rows, "session_id": sid}), 200
    except Exception as e:
        print(f"[History Load Error] {e}")
        return jsonify({"status": "error", "history": []}), 200


def handle_chatbot_get_sessions():
    """GET /api/chatbot/sessions – list sessions for the logged-in user or guest user."""
    _ensure_session_column()
    uid = _current_user_id()

    if not _SESSION_COL_EXISTS:
        return jsonify({"status": "success", "sessions": []}), 200

    try:
        db = get_db()
        cur = db.cursor(dictionary=True)

        if uid is not None:
            cur.execute("""
                SELECT
                    session_id,
                    MIN(user_message) AS first_msg,
                    COUNT(*) AS msg_count,
                    MAX(created_at) AS last_at
                FROM chatbot_history
                WHERE user_id = %s AND session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY MAX(created_at) DESC
                LIMIT 50
            """, (uid,))
        else:
            # Your current table is saving user_id as NULL, so load those rows too.
            cur.execute("""
                SELECT
                    session_id,
                    MIN(user_message) AS first_msg,
                    COUNT(*) AS msg_count,
                    MAX(created_at) AS last_at
                FROM chatbot_history
                WHERE user_id IS NULL AND session_id IS NOT NULL
                GROUP BY session_id
                ORDER BY MAX(created_at) DESC
                LIMIT 50
            """)

        rows = cur.fetchall()
        cur.close()

        sessions = []
        for row in rows:
            ts = row.get("last_at")
            sessions.append({
                "session_id": row.get("session_id"),
                "title": _session_title(row.get("first_msg")),
                "message_count": row.get("msg_count", 0),
                "last_at": ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts or ""),
            })

        return jsonify({"status": "success", "sessions": sessions}), 200

    except Exception as e:
        print(f"[Sessions Error] {e}")
        return jsonify({"status": "error", "sessions": []}), 200


def handle_chatbot_new_session():
    """POST /api/chatbot/new_session  – start a fresh chat session."""
    new_sid = str(uuid.uuid4())
    session["chatbot_session_id"] = new_sid
    return jsonify({"status": "success", "session_id": new_sid}), 200


def _session_title(first_msg) -> str:
    if not first_msg:
        return "Chat"
    s = str(first_msg)
    return s[:50] + ("…" if len(s) > 50 else "")


# ══════════════════════════════════════════════════════════════════════════════
#  ACTION HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def handle_chatbot_action(action: str):
    a = action.lower().strip()
    dispatch = {
        "top_news":      get_top_news_response,
        "commodities":   get_commodities_overview_response,
        "weather":       get_weather_prompt_response,
        "help":          get_help_response,
        "raise_concern": get_concern_prompt_response,
    }
    handler = dispatch.get(a)
    if handler:
        return handler()
    return {"status": "error", "reply": "Unknown action.", "type": "error", "items": []}


# ══════════════════════════════════════════════════════════════════════════════
#  MESSAGE HANDLER
# ══════════════════════════════════════════════════════════════════════════════

def handle_chatbot_message(message: str, history: list):
    intent = detect_intent(message)

    if intent == "greeting":
        return get_greeting_response()

    if intent == "top_news":
        return get_top_news_response()

    if intent == "weather":
        city = extract_city_name(message)
        if city:
            return get_weather_response(city)
        # City not found — ask user
        return get_weather_prompt_response()

    if intent == "commodity_specific":
        commodity = extract_commodity_name(message)
        return get_commodity_price_response(commodity)

    if intent == "commodities":
        return get_commodities_overview_response()

    if intent == "help":
        return get_help_response()

    if intent == "raise_concern":
        return get_concern_prompt_response()

    if intent == "save_concern":
        return save_concern_response(message)

    return get_groq_response(message, history)


# ══════════════════════════════════════════════════════════════════════════════
#  NEWS
# ══════════════════════════════════════════════════════════════════════════════

NEWS_CATEGORIES = {
    "agriculture": [
        "agriculture", "farm", "crop", "kisan", "mandi", "soil", "harvest", "agri",
        "wheat", "rice", "maize", "onion", "potato", "vegetable", "fruit",
        "livestock", "dairy", "fishery", "horticulture",
    ],
    "finance": [
        "finance", "financial", "market", "economy", "stock", "sensex", "nifty",
        "budget", "gdp", "inflation", "rbi", "bank", "rupee", "forex",
        "investment", "trade", "export", "import", "fiscal",
    ],
    "energy": [
        "energy", "oil", "fuel", "petrol", "diesel", "gas", "coal", "solar",
        "wind", "power", "electricity", "nuclear", "renewable", "crude", "brent",
    ],
    "weather": [
        "weather", "rain", "flood", "drought", "cyclone", "monsoon",
        "temperature", "climate", "storm", "heatwave", "cold", "fog", "frost", "humidity",
    ],
    "general": [],
}


def get_top_news_response():
    published     = _fetch_all_published_news()
    non_published = _fetch_recent_non_published_news(limit=30)

    if not published and not non_published:
        return {
            "status": "success", "type": "top_news",
            "reply": "📰 No news available right now. Check back later!",
            "items": [], "sections": [],
        }

    pub_sections  = _categorise_news(published)
    npub_sections = _categorise_news(non_published)

    all_articles = published + non_published
    for art in all_articles:
        art["summary"] = _summarize_article(art)

    art_map = {str(a["id"]): a for a in all_articles}
    for sec in pub_sections + npub_sections:
        for art in sec["articles"]:
            enriched = art_map.get(str(art["id"]), art)
            art["summary"] = enriched.get("summary", "")

    all_headlines = [a["headline"] for a in all_articles[:12]]
    if groq_client and all_headlines:
        try:
            ai = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "You are a news editor. 2 sentences max."},
                    {"role": "user", "content": "Brief overview of today's news:\n" +
                     "\n".join(f"{i+1}. {h}" for i, h in enumerate(all_headlines))},
                ],
                max_tokens=100, temperature=0.4,
            )
            digest = ai.choices[0].message.content.strip()
        except Exception:
            digest = f"{len(all_articles)} total articles today."
    else:
        digest = f"{len(all_articles)} total articles today."

    reply = (
        f"📰 **Today's News Overview**\n\n{digest}\n\n"
        f"✅ **Published:** {len(published)} articles · "
        f"⏳ **Pending:** {len(non_published)} articles"
    )
    return {
        "status": "success", "type": "top_news",
        "reply": reply, "items": [],
        "sections": {
            "published":     pub_sections,
            "non_published": npub_sections,
        },
    }


def _categorise_news(articles: list) -> list:
    buckets = {cat: [] for cat in NEWS_CATEGORIES}
    for art in articles:
        assigned = False
        text = (art.get("headline", "") + " " + art.get("keywords", "") + " " + art.get("type", "")).lower()
        for cat, keywords in NEWS_CATEGORIES.items():
            if cat == "general":
                continue
            if any(kw in text for kw in keywords):
                buckets[cat].append(art)
                assigned = True
                break
        if not assigned:
            buckets["general"].append(art)

    labels = {
        "agriculture": ("🌾", "Agriculture"),
        "finance":     ("💹", "Finance"),
        "energy":      ("⚡", "Energy"),
        "weather":     ("🌦", "Weather"),
        "general":     ("📋", "General"),
    }
    return [
        {"category": cat, "emoji": em, "label": lb, "articles": arts}
        for cat, (em, lb) in labels.items()
        if (arts := buckets[cat])
    ]


def _fetch_all_published_news():
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, news_date, news_type, news_headline, news_text, news_url, keywords
            FROM published_news
            WHERE news_date = CURDATE()
            ORDER BY published_at DESC, id DESC
        """)
        rows = cursor.fetchall(); cursor.close()
        return _fmt_rows(rows)
    except Exception as e:
        print(f"[Published News Error] {e}"); return []


def _fetch_recent_non_published_news(limit=30):
    try:
        db = get_db(); cursor = db.cursor(dictionary=True)
        cursor.execute("""
            SELECT id, news_date, news_type, news_headline, news_text, news_url, keywords,
                   date_of_insert
            FROM non_published_news
            ORDER BY date_of_insert DESC, id DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall(); cursor.close()
        return _fmt_rows(rows)
    except Exception as e:
        print(f"[Non-Pub News Error] {e}"); return []


def _fmt_rows(rows):
    out = []
    for row in rows:
        d = row.get("news_date") or row.get("date_of_insert")
        out.append({
            "id":       str(row.get("id", "")),
            "date":     d.strftime("%d-%m-%Y") if d and hasattr(d, "strftime") else str(d or ""),
            "type":     row.get("news_type") or "General",
            "headline": row.get("news_headline") or "No headline",
            "content":  (row.get("news_text") or "")[:800],
            "url":      row.get("news_url") or "",
            "keywords": row.get("keywords") or "",
        })
    return out


def _summarize_article(article: dict) -> str:
    content  = (article.get("content") or "").strip()
    headline = article.get("headline", "")
    if not content or len(content) < 60:
        return content[:300] if content else ""
    if groq_client:
        try:
            ai = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": "Summarize in exactly 3-4 concise lines. Be factual and neutral."},
                    {"role": "user", "content": f"Headline: {headline}\n\nContent: {content[:700]}\n\nSummarize in 3-4 lines:"},
                ],
                max_tokens=110, temperature=0.3,
            )
            return ai.choices[0].message.content.strip()
        except Exception:
            pass
    # Sentence fallback
    sentences = re.split(r"(?<=[.!?])\s+", content.strip())
    result, chars = [], 0
    for s in sentences[:5]:
        if chars + len(s) > 350:
            break
        result.append(s); chars += len(s)
    return " ".join(result) if result else content[:280]


# ══════════════════════════════════════════════════════════════════════════════
#  COMMODITIES
# ══════════════════════════════════════════════════════════════════════════════

def get_commodities_overview_response():
    now   = datetime.now()
    year  = str(now.year)
    month = str(now.month)

    all_options = _fetch_commodity_list()
    if not all_options:
        return {
            "status": "success", "type": "commodities_overview",
            "reply": "⚠️ Commodity data unavailable right now. Try again later.",
            "items": [],
        }

    TARGET_CROPS = [
        "Wheat", "Rice", "Onion", "Potato", "Tomato", "Maize", "Soyabean",
        "Cotton", "Groundnut", "Mustard", "Barley", "Turmeric", "Chilli", "Ginger", "Garlic",
    ]
    overview_items = []
    for name in TARGET_CROPS:
        match = next((c for c in all_options if c["cmdt_name"].lower() == name.lower()), None)
        if not match:
            match = next((c for c in all_options if name.lower() in c["cmdt_name"].lower()), None)
        if not match:
            continue
        prices = _fetch_price_for_commodity(match["id"], year, month)
        if not prices:
            pm = now.month - 1 or 12
            py = year if now.month > 1 else str(now.year - 1)
            prices = _fetch_price_for_commodity(match["id"], py, str(pm))
        if not prices:
            continue
        avg_p = sum(r["current_price"] for r in prices) / len(prices)
        changes = [r["change"] for r in prices if r.get("change") is not None]
        avg_chg = sum(changes) / len(changes) if changes else 0.0
        overview_items.append({
            "name":         match["cmdt_name"],
            "avg_price":    round(avg_p, 2),
            "change":       round(avg_chg, 2),
            "state_count":  len(prices),
            "commodity_id": match["id"],
        })

    if not overview_items:
        return {
            "status": "success", "type": "commodities_overview",
            "reply": (
                f"🌾 **Commodity Prices**\n\n"
                f"Agmarknet hasn't published data for {MONTH_SHORT[month]} {year} yet.\n"
                f"Prices appear in the first week of each month.\n\n"
                f"**{len(all_options)}** commodities tracked. Ask: _\"price of wheat\"_"
            ),
            "items": [],
        }

    lines = [f"📊 **Live Commodity Prices** ({MONTH_SHORT[month]} {year})\n"]
    for item in overview_items:
        arrow = "▲" if item["change"] > 0 else ("▼" if item["change"] < 0 else "—")
        lines.append(f"• **{item['name']}**: ₹{item['avg_price']:,.2f}/qtl {arrow}")
    lines.append("\n_Click any tile or ask: \"Price of Onion\" for state-wise details_")

    return {
        "status": "success", "type": "commodities_overview",
        "reply": "\n".join(lines), "items": overview_items,
    }


def get_commodity_price_response(commodity_name: str = ""):
    if not commodity_name:
        return get_commodities_overview_response()

    # Always resolve through synonym + fuzzy
    resolved = _resolve_commodity_synonym(commodity_name.lower())
    if resolved:
        commodity_name = resolved

    now   = datetime.now()
    year  = str(now.year)
    month = str(now.month)

    all_options = _fetch_commodity_list()
    if not all_options:
        return {
            "status": "success", "type": "commodity_price",
            "reply": "⚠️ Commodity data unavailable right now.", "items": [],
        }

    query   = commodity_name.lower().strip()
    matched = next((c for c in all_options if c["cmdt_name"].lower() == query), None)
    if not matched:
        matched = next((c for c in all_options if query in c["cmdt_name"].lower()), None)
    if not matched:
        # fuzzy against Agmarknet commodity names
        names_lower = [c["cmdt_name"].lower() for c in all_options]
        fm = difflib.get_close_matches(query, names_lower, n=1, cutoff=0.65)
        if fm:
            matched = next((c for c in all_options if c["cmdt_name"].lower() == fm[0]), None)
    if not matched:
        words = [w for w in query.split() if len(w) > 2]
        matched = next(
            (c for c in all_options if any(w in c["cmdt_name"].lower() for w in words)), None
        )

    if not matched:
        preview = ", ".join(c["cmdt_name"] for c in all_options[:15])
        return {
            "status": "success", "type": "commodity_price",
            "reply": (
                f"❓ **{commodity_name}** not found in Agmarknet data.\n\n"
                f"Available: {preview}…\n\nTry: _\"price of wheat\"_"
            ),
            "items": [],
        }

    prices = _fetch_price_for_commodity(matched["id"], year, month)
    mlabel = f"{MONTH_SHORT[month]} {year}"
    if not prices:
        pm = now.month - 1 or 12
        py = year if now.month > 1 else str(now.year - 1)
        prices = _fetch_price_for_commodity(matched["id"], py, str(pm))
        mlabel = f"{MONTH_SHORT[str(pm)]} {py}"

    if not prices:
        return {
            "status": "success", "type": "commodity_price",
            "reply": f"🌾 **{matched['cmdt_name']}** — no price data for recent months.",
            "items": [],
        }

    avg_p  = sum(r["current_price"] for r in prices) / len(prices)
    high_r = max(prices, key=lambda r: r["current_price"])
    low_r  = min(prices, key=lambda r: r["current_price"])

    return {
        "status": "success", "type": "commodity_price",
        "reply": (
            f"🌾 **{matched['cmdt_name']}** — Wholesale Prices ({mlabel})\n\n"
            f"📊 Avg: **₹{avg_p:,.2f}/qtl** across {len(prices)} states\n"
            f"📈 Highest: ₹{high_r['current_price']:,.2f} ({high_r.get('state', '-')})\n"
            f"📉 Lowest:  ₹{low_r['current_price']:,.2f} ({low_r.get('state', '-')})\n\n"
            "_Source: Agmarknet_"
        ),
        "items": prices[:12],
    }


def _fetch_commodity_list():
    try:
        resp = requests.get(
            f"{AGMARK_BASE}/dashboard-commodities-filter",
            headers=AGMARK_HEADERS, timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        raw = (
            payload if isinstance(payload, list) else
            payload.get("data") or payload.get("rows") or
            payload.get("result") or payload.get("commodities") or []
        )
        if raw:
            print(f"[DEBUG commodity sample]: {raw[0]}")
        seen, out = set(), []
        for item in raw:
            if not isinstance(item, dict):
                continue
            cid  = str(item.get("id") or item.get("commodity_id") or
                       item.get("cmdt_id") or item.get("value") or "").strip()
            name = str(item.get("cmdt_name") or item.get("commodity_name") or
                       item.get("name") or item.get("label") or "").strip()
            if cid and name and cid not in seen:
                seen.add(cid)
                out.append({"id": cid, "cmdt_name": name})
        return sorted(out, key=lambda x: x["cmdt_name"].lower())
    except Exception as e:
        print(f"[Commodity List Error] {e}"); return []


def _fetch_price_for_commodity(commodity_id: str, year: str, month: str):
    try:
        mi   = int(month)
        pm   = mi - 1 or 12
        py   = year if mi > 1 else str(int(year) - 1)
        ckey = f"prices_{MONTH_NAMES[mi]}_{year}"
        pkey = f"prices_{MONTH_NAMES[pm]}_{py}"

        resp = requests.get(
            f"{AGMARK_BASE}/price-trend/wholesale-prices-monthly",
            params={
                "report_mode": "Statewise", "commodity": commodity_id,
                "year": year, "month": month,
                "state": "0", "district": "0", "export": "false",
            },
            headers=AGMARK_HEADERS, timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows", []) if isinstance(data, dict) else []
        if rows:
            print(f"[DEBUG price keys id={commodity_id}]: {list(rows[0].keys())}")

        out = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            curr = (row.get(ckey) or row.get("modal_price") or
                    row.get("avg_price") or row.get("price") or row.get("current_price"))
            prev = (row.get(pkey) or row.get("prev_modal_price") or row.get("previous_price"))
            try:
                curr = float(curr) if curr not in (None, "", "N/A", "0", 0) else None
                prev = float(prev) if prev not in (None, "", "N/A", "0", 0) else None
            except (ValueError, TypeError):
                curr = prev = None
            try:
                change = float(row.get("change_over_previous_month") or 0)
            except Exception:
                change = 0.0
            state = (row.get("state") or row.get("state_name") or row.get("statename") or "-")
            if curr is not None:
                out.append({"state": state, "current_price": curr,
                            "previous_price": prev, "change": change})
        return out
    except Exception as e:
        print(f"[Price Error id={commodity_id}] {e}"); return []


# ══════════════════════════════════════════════════════════════════════════════
#  WEATHER
# ══════════════════════════════════════════════════════════════════════════════

def get_weather_prompt_response():
    return {
        "status": "success", "type": "weather_prompt",
        "reply": (
            "🌤 **Weather Lookup**\n\n"
            "Type any city name using any phrasing:\n"
            "• _Weather in Mumbai_\n"
            "• _Temperature in Delhi_\n"
            "• _Chandivali's temperature_\n"
            "• _Rainfall in Nagpur_\n"
            "• _How humid is Pune?_\n"
            "• _Mausam in Aurangabad_"
        ),
        "items": [],
    }


def get_weather_response(city: str):
    try:
        geo = requests.get(
            f"https://api.openweathermap.org/geo/1.0/direct"
            f"?q={city}&limit=1&appid={OPENWEATHER_KEY}",
            timeout=6,
        ).json()

        if not geo:
            # Try fuzzy correction before giving up
            corrected = _fuzzy_match_city(city)
            if corrected and corrected.lower() != city.lower():
                return get_weather_response(corrected)
            return {
                "status": "success", "type": "weather",
                "reply": f"❌ City **{city}** not found. Check spelling and try again.",
                "items": [],
            }

        lat, lon   = geo[0]["lat"], geo[0]["lon"]
        resolved   = geo[0].get("name", city)
        country    = geo[0].get("country", "")

        wr = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather"
            f"?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}",
            timeout=6,
        ).json()

        if not wr.get("main"):
            return {
                "status": "success", "type": "weather",
                "reply": f"⚠️ Weather unavailable for **{city}**.", "items": [],
            }

        temp     = round(wr["main"]["temp"])
        feels    = round(wr["main"]["feels_like"])
        humidity = wr["main"]["humidity"]
        wind     = round(wr["wind"]["speed"], 1)
        desc     = wr["weather"][0]["description"].title()
        icon     = wr["weather"][0]["icon"]
        advisory = _weather_advisory(temp, humidity, wind, desc)

        return {
            "status": "success", "type": "weather",
            "reply": (
                f"🌤 **{resolved}, {country}** — {temp}°C ({desc})\n"
                f"💧 Humidity: {humidity}% · 💨 Wind: {wind} m/s · Feels: {feels}°C\n\n"
                f"📋 {advisory}"
            ),
            "items": [{
                "location":  f"{resolved}, {country}",
                "temp":      temp,
                "feels_like": feels,
                "desc":      desc,
                "icon":      icon,
                "humidity":  humidity,
                "wind":      wind,
                "overview":  advisory,
            }],
        }
    except Exception as e:
        print(f"[Weather Error] {e}")
        return {"status": "error", "type": "weather",
                "reply": "⚠️ Could not fetch weather. Try again.", "items": []}


def _weather_advisory(temp, humidity, wind, desc):
    dl = desc.lower(); parts = []
    if   temp >= 38: parts.append("🔥 Extreme heat — stay hydrated.")
    elif temp >= 32: parts.append("☀️ Hot — carry water outdoors.")
    elif temp <=  5: parts.append("🥶 Very cold — dress warmly.")
    elif temp <= 15: parts.append("🧥 Cool — jacket recommended.")
    else:            parts.append("😊 Comfortable temperatures.")
    if   "rain"    in dl or "drizzle" in dl: parts.append("☔ Carry an umbrella.")
    elif "storm"   in dl or "thunder" in dl: parts.append("⛈️ Thunderstorm — stay indoors.")
    elif "snow"    in dl:                    parts.append("❄️ Snow expected.")
    elif "fog"     in dl or "mist" in dl:    parts.append("🌫️ Low visibility — drive carefully.")
    if humidity > 80: parts.append("💦 High humidity — feels muggy.")
    if wind > 10:     parts.append(f"💨 Strong winds ({wind} m/s).")
    return " ".join(parts)


# ══════════════════════════════════════════════════════════════════════════════
#  GROQ Q&A
# ══════════════════════════════════════════════════════════════════════════════

def get_groq_response(user_message: str, history: list):
    if not groq_client:
        return _fallback_response()
    try:
        msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
        for t in history[-10:]:
            r, c = t.get("role", "user"), t.get("content", "")
            if r in ("user", "assistant") and c:
                msgs.append({"role": r, "content": c})
        msgs.append({"role": "user", "content": user_message})
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL, messages=msgs, max_tokens=600, temperature=0.7,
        )
        return {
            "status": "success", "type": "general",
            "reply": resp.choices[0].message.content.strip(), "items": [],
        }
    except Exception as e:
        print(f"[Groq Error] {e}"); return _fallback_response()


# ══════════════════════════════════════════════════════════════════════════════
#  HELP / CONCERN / FALLBACK
# ══════════════════════════════════════════════════════════════════════════════

def get_greeting_response():
    from datetime import datetime as _dt
    hour = _dt.now().hour
    if hour < 12:
        tod = "Good morning"
    elif hour < 17:
        tod = "Good afternoon"
    else:
        tod = "Good evening"
    return {
        "status": "success", "type": "greeting",
        "reply": (
            f"👋 {tod}! I'm your **Seamless Assistant**.\n\n"
            "I can help you with:\n"
            "• 📰 **Top News** — published & pending headlines\n"
            "• 🌾 **Commodity Prices** — live Agmarknet data\n"
            "• 🌤 **Weather** — real-time for any city\n"
            "• 💬 **General Q&A** — ask me anything\n\n"
            "Try: _\"Chandivali's temperature\"_, _\"Aloo ka bhav\"_, or _\"Top news\"_"
        ),
        "items": [],
    }


def get_help_response():
    return {
        "status": "success", "type": "help",
        "reply": (
            "👋 **Seamless Assistant — Help**\n\n"
            "**What I can do:**\n"
            "• **Top News** — All today's headlines (Published + Pending) with category sections\n"
            "• **Commodities** — Live Agmarknet wholesale prices\n"
            "• **Weather** — Real-time weather for any city\n"
            "• **General Q&A** — Ask me anything\n"
            "• **Raise Concern** — Submit a platform issue\n\n"
            "**Natural Language Examples:**\n"
            "- _\"Chandivali's temperature\"_ → weather lookup\n"
            "- _\"Rainfall in Nagpur\"_ → weather lookup\n"
            "- _\"Mausam in Pune\"_ → weather lookup\n"
            "- _\"Aloo ka bhav\"_ → potato price\n"
            "- _\"Gehu price today\"_ → wheat price\n"
            "- _\"Pyaz rate\"_ → onion price\n"
            "- _\"Tamatar ka daam\"_ → tomato price\n"
            "- _\"Price of Wheat today\"_\n"
            "- _\"Weather in Nagpur\"_\n"
            "- _\"What is MSP?\"_\n"
            "- _Concern: Dashboard is slow_\n\n"
            "💡 **Tip:** I understand spelling mistakes too — "
            "_\"mumbay\"_, _\"tomatoe\"_, _\"pyaaz\"_ all work fine!"
        ),
        "items": [],
    }


def get_concern_prompt_response():
    return {
        "status": "success", "type": "concern_prompt",
        "reply": (
            "⚠️ **Raise a Concern**\n\n"
            "Start your message with: `Concern: [your issue]`\n\n"
            "_Example:_ Concern: News feed is not loading on mobile."
        ),
        "items": [],
    }


def save_concern_response(message: str):
    text = _extract_concern_text(message)
    if _save_concern(text):
        return {
            "status": "success", "type": "concern_saved",
            "reply": "✅ **Concern Recorded** — Saved and will be reviewed. Thank you!",
            "items": [],
        }
    return {
        "status": "error", "type": "concern_error",
        "reply": "❌ Could not save concern. Please try again.", "items": [],
    }


def _extract_concern_text(msg: str) -> str:
    msg = msg.strip()
    for p in ["my concern is", "concern:", "i want to report", "i want to raise a concern about"]:
        if msg.lower().startswith(p):
            return msg[len(p):].strip(" :.-")
    return msg


def _save_concern(text: str) -> bool:
    try:
        db  = get_db(); cur = db.cursor()
        uid = _current_user_id()
        cur.execute(
            "INSERT INTO chatbot_concerns (user_id, concern_text, created_at, status) "
            "VALUES (%s, %s, NOW(), %s)",
            (uid, text, "open"),
        )
        db.commit(); cur.close(); return True
    except Exception as e:
        print(f"[Concern Error] {e}"); return False


def _fallback_response():
    return {
        "status": "success", "type": "fallback",
        "reply": (
            "I'm not sure I understood that. I can help with:\n\n"
            "• **Top News** — all headlines with summaries\n"
            "• **Commodity prices** — e.g. _\"price of wheat\"_ or _\"aloo ka bhav\"_\n"
            "• **Weather** — e.g. _\"weather in Mumbai\"_ or _\"Chandivali's temperature\"_\n"
            "• **General questions** — ask me anything\n\n"
            "💡 I understand Hindi/Marathi names and spelling mistakes too!"
        ),
        "items": [],
    }


# ══════════════════════════════════════════════════════════════════════════════
#  CHAT HISTORY  (DB-backed, session-aware)
# ══════════════════════════════════════════════════════════════════════════════

# Track whether we've already run the migration this process lifetime
_SESSION_COL_EXISTS: bool = False


def _ensure_session_column():
    """
    Add session_id column to chatbot_history if it doesn't exist yet.
    Called lazily on first save — safe to call multiple times (idempotent).
    """
    global _SESSION_COL_EXISTS
    if _SESSION_COL_EXISTS:
        return
    try:
        db  = get_db()
        cur = db.cursor()
        # Check if column exists
        cur.execute("""
            SELECT COUNT(*) FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME   = 'chatbot_history'
              AND COLUMN_NAME  = 'session_id'
        """)
        (count,) = cur.fetchone()
        if count == 0:
            cur.execute(
                "ALTER TABLE chatbot_history ADD COLUMN session_id VARCHAR(64) NULL"
            )
            db.commit()
            print("[chatbot] ✅ Added session_id column to chatbot_history")
        cur.close()
        _SESSION_COL_EXISTS = True
    except Exception as e:
        print(f"[chatbot] ⚠️  Could not add session_id column: {e}")
        # Still mark as done so we don't retry every request
        _SESSION_COL_EXISTS = True


def _save_history_entry(user_msg: str, bot_reply: str, msg_type: str, session_id: str = None):
    """
    Save one conversation turn.
    Works even if session_id column doesn't exist yet (falls back gracefully).
    """
    _ensure_session_column()
    uid = _current_user_id()
    sid = session_id or _get_or_create_session_id()
    try:
        db  = get_db()
        cur = db.cursor()
        if _SESSION_COL_EXISTS:
            cur.execute(
                """INSERT INTO chatbot_history
                   (user_id, session_id, user_message, bot_reply, msg_type, created_at)
                   VALUES (%s, %s, %s, %s, %s, NOW())""",
                (uid, sid, user_msg[:500], bot_reply[:2000], msg_type),
            )
        else:
            cur.execute(
                """INSERT INTO chatbot_history
                   (user_id, user_message, bot_reply, msg_type, created_at)
                   VALUES (%s, %s, %s, %s, NOW())""",
                (uid, user_msg[:500], bot_reply[:2000], msg_type),
            )
        db.commit()
        cur.close()
        print(f"[chatbot] 💾 Saved history — user_id={uid} session={sid} type={msg_type}")
    except Exception as e:
        print(f"[History Save Error] {e}")


def _load_history(limit: int = 100, session_id: str = None) -> list:
    """
    Load chat history for the current user.
    - If user is logged in, load rows by user_id.
    - If user_id is NULL, load guest rows by session_id/user_id IS NULL.
    """
    _ensure_session_column()
    uid = _current_user_id()

    try:
        db = get_db()
        cur = db.cursor(dictionary=True)

        if _SESSION_COL_EXISTS and session_id:
            if uid is not None:
                cur.execute(
                    """SELECT user_message, bot_reply, msg_type, session_id, created_at
                       FROM chatbot_history
                       WHERE user_id = %s AND session_id = %s
                       ORDER BY created_at ASC
                       LIMIT %s""",
                    (uid, session_id, limit),
                )
            else:
                cur.execute(
                    """SELECT user_message, bot_reply, msg_type, session_id, created_at
                       FROM chatbot_history
                       WHERE user_id IS NULL AND session_id = %s
                       ORDER BY created_at ASC
                       LIMIT %s""",
                    (session_id, limit),
                )
        else:
            if uid is not None:
                cur.execute(
                    """SELECT user_message, bot_reply, msg_type, session_id, created_at
                       FROM chatbot_history
                       WHERE user_id = %s
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (uid, limit),
                )
            else:
                cur.execute(
                    """SELECT user_message, bot_reply, msg_type, session_id, created_at
                       FROM chatbot_history
                       WHERE user_id IS NULL
                       ORDER BY created_at DESC
                       LIMIT %s""",
                    (limit,),
                )

        rows = cur.fetchall()
        cur.close()

        # DESC query → reverse for chronological display.
        if not (session_id and _SESSION_COL_EXISTS):
            rows = list(reversed(rows))

        result = []
        for row in rows:
            ts = row.get("created_at")
            ts_str = ts.strftime("%d %b %Y, %H:%M") if hasattr(ts, "strftime") else str(ts or "")
            result.append({
                "user_message": row.get("user_message") or "",
                "bot_reply": row.get("bot_reply") or "",
                "msg_type": row.get("msg_type", "general"),
                "session_id": row.get("session_id", ""),
                "timestamp": ts_str,
            })

        return result

    except Exception as e:
        print(f"[History Load Error] {e}")
        return []


# ══════════════════════════════════════════════════════════════════════════════
#  ROUTES REFERENCE  (add to your routes.py / main blueprint)
# ══════════════════════════════════════════════════════════════════════════════
#
#  from .chatbot import (
#      handle_chatbot_request,
#      handle_chatbot_get_history,
#      handle_chatbot_get_sessions,
#      handle_chatbot_new_session,
#  )
#
#  @main_bp.route("/chatbot",                  methods=["GET"])
#  @login_required
#  def chatbot():
#      return render_template("main/chatbot.html")
#
#  @main_bp.route("/api/chatbot",              methods=["POST"])
#  @login_required
#  def chatbot_api():
#      return handle_chatbot_request()
#
#  @main_bp.route("/api/chatbot/history",      methods=["GET"])
#  @login_required
#  def chatbot_history_api():
#      return handle_chatbot_get_history()
#
#  @main_bp.route("/api/chatbot/sessions",     methods=["GET"])
#  @login_required
#  def chatbot_sessions_api():
#      return handle_chatbot_get_sessions()
#
#  @main_bp.route("/api/chatbot/new_session",  methods=["POST"])
#  @login_required
#  def chatbot_new_session_api():
#      return handle_chatbot_new_session()