import os
import re
import json
import requests
from datetime import datetime
from flask import jsonify, request, session
from flask_login import current_user
from app.db import get_db

try:
    from groq import Groq
    GROQ_AVAILABLE = True
except ImportError:
    GROQ_AVAILABLE = False

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
    1:"january",2:"february",3:"march",4:"april",5:"may",6:"june",
    7:"july",8:"august",9:"september",10:"october",11:"november",12:"december"
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

# ─── Entry Point ──────────────────────────────────────────────────────────────
def handle_chatbot_request():
    try:
        data    = request.get_json(silent=True) or {}
        message = (data.get("message") or "").strip()
        action  = (data.get("action") or "").strip()
        history = data.get("history", [])

        if action:
            result = handle_chatbot_action(action)
            _save_history_entry("action:"+action, result.get("reply",""), result.get("type",""))
            return jsonify(result), 200

        if message:
            result = handle_chatbot_message(message, history)
            _save_history_entry(message, result.get("reply",""), result.get("type",""))
            return jsonify(result), 200

        return jsonify({"status":"error","reply":"Please enter a message or select an option."}), 400

    except Exception as e:
        return jsonify({"status":"error","reply":f"Something went wrong: {str(e)}"}), 500


def handle_chatbot_get_history():
    """GET /api/chatbot/history — returns saved history for this user."""
    try:
        rows = _load_history()
        return jsonify({"status":"success","history":rows}), 200
    except Exception as e:
        return jsonify({"status":"error","history":[]}), 200


# ─── Action Handler ───────────────────────────────────────────────────────────
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
    return {"status":"error","reply":"Unknown action.","type":"error","items":[]}


# ─── Message Handler ──────────────────────────────────────────────────────────
def handle_chatbot_message(message: str, history: list):
    intent = detect_intent(message)
    if intent == "top_news":         return get_top_news_response()
    if intent == "weather":
        city = extract_city_name(message)
        return get_weather_response(city) if city else get_weather_prompt_response()
    if intent == "commodity_specific":
        return get_commodity_price_response(extract_commodity_name(message))
    if intent == "commodities":      return get_commodities_overview_response()
    if intent == "help":             return get_help_response()
    if intent == "raise_concern":    return get_concern_prompt_response()
    if intent == "save_concern":     return save_concern_response(message)
    return get_groq_response(message, history)


# ─── Intent ───────────────────────────────────────────────────────────────────
def detect_intent(message: str) -> str:
    msg = message.lower().strip()
    if any(msg.startswith(p) for p in ["my concern is","concern:","i want to report"]):
        return "save_concern"
    if any(k in msg for k in ["price of","cost of","rate of","mandi price","mandi rate",
                                "how much is","current price","today price","market rate"]):
        return "commodity_specific"
    crops = ["potato","onion","wheat","rice","maize","tomato","soyabean","cotton","groundnut",
             "sugarcane","barley","mustard","jowar","bajra","turmeric","chilli","ginger","garlic",
             "moong","urad","arhar","tur","corn","soya","dal"]
    if any(k in msg for k in crops):
        return "commodity_specific"
    if any(k in msg for k in ["weather","temperature","humid","forecast","rain","sunny",
                                "cloudy","wind speed","how hot","how cold","temp in","weather in"]):
        return "weather"
    if any(k in msg for k in ["top news","today's news","today news","headlines",
                                "latest news","news today","news","published news","unpublished"]):
        return "top_news"
    if any(k in msg for k in ["commodity","commodities","agmarknet","mandi"]):
        return "commodities"
    if any(k in msg for k in ["help","instruction","how to use","guide","what can you do"]):
        return "help"
    if any(k in msg for k in ["raise concern","complaint","issue","problem","concern","report"]):
        return "raise_concern"
    return "general"


# ─── Extractors ───────────────────────────────────────────────────────────────
def extract_city_name(message: str) -> str:
    msg = message.strip()
    patterns = [
        r"weather (?:in|of|at|for)\s+([A-Za-z ]+?)(?:\s+today|\s+now|[?!.,]|$)",
        r"(?:temperature|temp|forecast) (?:in|of|at|for)\s+([A-Za-z ]+?)(?:[?!.,]|$)",
        r"how(?:'s| is) (?:the )?weather (?:in|at|of)\s+([A-Za-z ]+?)(?:[?!.,]|$)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m:
            city = m.group(1).strip()
            if len(city) > 1: return city
    cleaned = re.sub(r'\b(weather|temperature|forecast|today|now|what|is|the|in|of|at|for|how|check|show|tell|me|get|city)\b',
                     '', msg, flags=re.IGNORECASE)
    city = cleaned.strip(" ?!.,")
    return city if len(city) > 2 else ""


def extract_commodity_name(message: str) -> str:
    msg = message.strip()
    patterns = [
        r"price of\s+([A-Za-z ]+?)(?:\s+today|\s+price|[?!.,]|$)",
        r"(?:rate|cost|mandi (?:price|rate)) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
        r"current (?:price|rate) of\s+([A-Za-z ]+?)(?:[?!.,]|$)",
        r"([A-Za-z]+) (?:price|rate|cost|mandi)",
    ]
    for pat in patterns:
        m = re.search(pat, msg, re.IGNORECASE)
        if m: return m.group(1).strip()
    known = ["potato","onion","wheat","rice","maize","tomato","soyabean","cotton","groundnut",
             "sugarcane","barley","mustard","jowar","bajra","turmeric","chilli","ginger","garlic",
             "moong","urad","arhar","tur","corn"]
    for k in known:
        if k in msg.lower(): return k.title()
    return ""


# ─── TOP NEWS — Published + Non-Published with category sections ──────────────
def get_top_news_response():
    """
    Returns ALL news grouped by:
      - Today's Published (with subcategories)
      - Non-Published / Pending (with subcategories)
    Each article gets a 3-4 line Groq summary.
    """
    published     = _fetch_all_published_news()
    non_published = _fetch_recent_non_published_news(limit=30)

    if not published and not non_published:
        return {
            "status":"success","type":"top_news",
            "reply":"📰 No news available right now. Check back later!",
            "items":[], "sections":[]
        }

    # Categorise published news
    pub_sections  = _categorise_news(published)
    npub_sections = _categorise_news(non_published)

    # Enrich each article with summary
    all_articles = published + non_published
    for art in all_articles:
        art["summary"] = _summarize_article(art)

    # Re-apply summaries by id
    art_map = {str(a["id"]): a for a in all_articles}
    for sec in pub_sections + npub_sections:
        for art in sec["articles"]:
            enriched = art_map.get(str(art["id"]), art)
            art["summary"] = enriched.get("summary","")

    # Top-level digest via Groq
    all_headlines = [a["headline"] for a in all_articles[:12]]
    if groq_client and all_headlines:
        try:
            ai = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role":"system","content":"You are a news editor. 2 sentences max."},
                    {"role":"user","content":"Brief overview of today's news:\n" + "\n".join(f"{i+1}. {h}" for i,h in enumerate(all_headlines))}
                ],
                max_tokens=100, temperature=0.4
            )
            digest = ai.choices[0].message.content.strip()
        except Exception:
            digest = f"{len(all_articles)} total articles today."
    else:
        digest = f"{len(all_articles)} total articles today."

    pub_count  = len(published)
    npub_count = len(non_published)
    reply = (
        f"📰 **Today's News Overview**\n\n{digest}\n\n"
        f"✅ **Published:** {pub_count} articles · "
        f"⏳ **Pending:** {npub_count} articles"
    )

    return {
        "status": "success",
        "type":   "top_news",
        "reply":  reply,
        "items":  [],
        "sections": {
            "published":     pub_sections,
            "non_published": npub_sections,
        }
    }


NEWS_CATEGORIES = {
    "agriculture": ["agriculture","farm","crop","kisan","mandi","soil","harvest","agri","wheat","rice","maize","onion","potato","vegetable","fruit","livestock","dairy","fishery","horticulture"],
    "finance":     ["finance","financial","market","economy","stock","sensex","nifty","budget","gdp","inflation","rbi","bank","rupee","forex","investment","trade","export","import","fiscal"],
    "energy":      ["energy","oil","fuel","petrol","diesel","gas","coal","solar","wind","power","electricity","nuclear","renewable","crude","brent"],
    "weather":     ["weather","rain","flood","drought","cyclone","monsoon","temperature","climate","storm","heatwave","cold","fog","frost","humidity"],
    "general":     [],  # catch-all
}

def _categorise_news(articles: list) -> list:
    """Group articles into category sections."""
    buckets = {cat: [] for cat in NEWS_CATEGORIES}
    for art in articles:
        assigned = False
        text = (art.get("headline","") + " " + art.get("keywords","") + " " + (art.get("type",""))).lower()
        for cat, keywords in NEWS_CATEGORIES.items():
            if cat == "general":
                continue
            if any(kw in text for kw in keywords):
                buckets[cat].append(art)
                assigned = True
                break
        if not assigned:
            buckets["general"].append(art)

    sections = []
    labels = {
        "agriculture": ("🌾", "Agriculture"),
        "finance":     ("💹", "Finance"),
        "energy":      ("⚡", "Energy"),
        "weather":     ("🌦", "Weather"),
        "general":     ("📋", "General"),
    }
    for cat, arts in buckets.items():
        if arts:
            emoji, label = labels[cat]
            sections.append({"category": cat, "emoji": emoji, "label": label, "articles": arts})
    return sections


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
            "id":       str(row.get("id","")),
            "date":     d.strftime("%d-%m-%Y") if d and hasattr(d,"strftime") else str(d or ""),
            "type":     row.get("news_type") or "General",
            "headline": row.get("news_headline") or "No headline",
            "content":  (row.get("news_text") or "")[:800],
            "url":      row.get("news_url") or "",
            "keywords": row.get("keywords") or "",
        })
    return out


def _summarize_article(article: dict) -> str:
    content  = (article.get("content") or "").strip()
    headline = article.get("headline","")
    if not content or len(content) < 60:
        return content[:300] if content else ""
    if groq_client:
        try:
            ai = groq_client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role":"system","content":"Summarize in exactly 3-4 concise lines. Be factual and neutral."},
                    {"role":"user","content":f"Headline: {headline}\n\nContent: {content[:700]}\n\nSummarize in 3-4 lines:"}
                ],
                max_tokens=110, temperature=0.3
            )
            return ai.choices[0].message.content.strip()
        except Exception:
            pass
    # Sentence-based fallback
    sentences = re.split(r'(?<=[.!?])\s+', content.strip())
    result = []; chars = 0
    for s in sentences[:5]:
        if chars + len(s) > 350: break
        result.append(s); chars += len(s)
    return " ".join(result) if result else content[:280]


# ─── COMMODITIES — Fixed ──────────────────────────────────────────────────────
def get_commodities_overview_response():
    """
    Fetches live commodity prices from Agmarknet.
    Returns type='commodities_overview' with items as list of dicts:
      {name, avg_price, change, state_count, commodity_id}
    The frontend matches on type === 'commodities_overview' to render tiles.
    """
    now   = datetime.now()
    year  = str(now.year)
    month = str(now.month)

    all_options = _fetch_commodity_list()
    if not all_options:
        return {
            "status":"success", "type":"commodities_overview",
            "reply":"⚠️ Agmarknet commodity data is temporarily unavailable. Please try again later.",
            "items":[]
        }

    featured_names = [
        "Rice","Wheat","Maize","Onion","Potato","Soyabean",
        "Cotton","Groundnut","Mustard","Tomato","Arhar","Bajra",
    ]

    lookup = {}
    for c in all_options:
        lookup[c["cmdt_name"].strip().lower()] = c

    overview_items = []

    for name in featured_names:
        # Exact match first
        match = lookup.get(name.lower())
        # Partial match fallback
        if not match:
            match = next((c for c in all_options if name.lower() in c["cmdt_name"].lower()), None)
        if not match:
            continue

        # Try current month, fallback to previous
        prices = _fetch_price_for_commodity(match["id"], year, month)
        if not prices:
            pm = now.month - 1 or 12
            py = year if now.month > 1 else str(now.year - 1)
            prices = _fetch_price_for_commodity(match["id"], py, str(pm))

        if not prices:
            continue

        avg_p  = sum(r["current_price"] for r in prices) / len(prices)
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
            "status":"success", "type":"commodities_overview",
            "reply":(
                f"🌾 **Commodity Prices**\n\n"
                f"Agmarknet hasn't published data for {MONTH_SHORT[month]} {year} yet.\n"
                f"Prices appear in the first week of each month.\n\n"
                f"**{len(all_options)}** commodities tracked. Ask: _\"price of wheat\"_"
            ),
            "items":[]
        }

    # Build reply text
    lines = [f"📊 **Live Commodity Prices** ({MONTH_SHORT[month]} {year})\n"]
    for item in overview_items:
        arrow = "▲" if item["change"] > 0 else ("▼" if item["change"] < 0 else "—")
        lines.append(f"• **{item['name']}**: ₹{item['avg_price']:,.2f}/qtl {arrow}")
    lines.append("\n_Click any tile or ask: \"Price of Onion\" for state-wise details_")

    return {
        "status": "success",
        "type":   "commodities_overview",          # ← MUST match JS check
        "reply":  "\n".join(lines),
        "items":  overview_items,                  # ← list of commodity dicts
    }


def get_commodity_price_response(commodity_name: str = ""):
    if not commodity_name:
        return get_commodities_overview_response()

    now   = datetime.now()
    year  = str(now.year)
    month = str(now.month)

    all_options = _fetch_commodity_list()
    if not all_options:
        return {"status":"success","type":"commodity_price",
                "reply":"⚠️ Commodity data unavailable right now.","items":[]}

    query   = commodity_name.lower().strip()
    matched = next((c for c in all_options if c["cmdt_name"].lower() == query), None)
    if not matched:
        matched = next((c for c in all_options if query in c["cmdt_name"].lower()), None)
    if not matched:
        words = [w for w in query.split() if len(w) > 2]
        matched = next((c for c in all_options
                        if any(w in c["cmdt_name"].lower() for w in words)), None)

    if not matched:
        preview = ", ".join(c["cmdt_name"] for c in all_options[:15])
        return {"status":"success","type":"commodity_price",
                "reply":(f"❓ **{commodity_name}** not found.\n\nAvailable: {preview}…\n\n"
                         "Try: _\"price of wheat\"_"),"items":[]}

    prices = _fetch_price_for_commodity(matched["id"], year, month)
    mlabel = f"{MONTH_SHORT[month]} {year}"
    if not prices:
        pm = now.month - 1 or 12
        py = year if now.month > 1 else str(now.year - 1)
        prices = _fetch_price_for_commodity(matched["id"], py, str(pm))
        mlabel = f"{MONTH_SHORT[str(pm)]} {py}"

    if not prices:
        return {"status":"success","type":"commodity_price",
                "reply":f"🌾 **{matched['cmdt_name']}** — no price data for recent months.","items":[]}

    avg_p  = sum(r["current_price"] for r in prices) / len(prices)
    high_r = max(prices, key=lambda r: r["current_price"])
    low_r  = min(prices, key=lambda r: r["current_price"])

    return {
        "status":"success","type":"commodity_price",
        "reply":(
            f"🌾 **{matched['cmdt_name']}** — Wholesale Prices ({mlabel})\n\n"
            f"📊 Avg: **₹{avg_p:,.2f}/qtl** across {len(prices)} states\n"
            f"📈 Highest: ₹{high_r['current_price']:,.2f} ({high_r.get('state','-')})\n"
            f"📉 Lowest: ₹{low_r['current_price']:,.2f} ({low_r.get('state','-')})\n\n"
            "_Source: Agmarknet_"
        ),
        "items": prices[:12]
    }


def _fetch_commodity_list():
    try:
        resp = requests.get(f"{AGMARK_BASE}/dashboard-commodities-filter",
                            headers=AGMARK_HEADERS, timeout=15)
        resp.raise_for_status()
        payload = resp.json()
        raw = (payload if isinstance(payload, list)
               else payload.get("data") or payload.get("rows") or
               payload.get("result") or payload.get("commodities") or [])
        if raw:
            print(f"[DEBUG commodity sample]: {raw[0]}")
        seen, out = set(), []
        for item in raw:
            if not isinstance(item, dict): continue
            cid  = str(item.get("id") or item.get("commodity_id") or
                       item.get("cmdt_id") or item.get("value") or "").strip()
            name = str(item.get("cmdt_name") or item.get("commodity_name") or
                       item.get("name") or item.get("label") or "").strip()
            if cid and name and cid not in seen:
                seen.add(cid)
                out.append({"id":cid,"cmdt_name":name})
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
            params={"report_mode":"Statewise","commodity":commodity_id,
                    "year":year,"month":month,"state":"0","district":"0","export":"false"},
            headers=AGMARK_HEADERS, timeout=20
        )
        resp.raise_for_status()
        data = resp.json()
        rows = data.get("rows",[]) if isinstance(data, dict) else []
        if rows:
            print(f"[DEBUG price keys id={commodity_id}]: {list(rows[0].keys())}")

        out = []
        for row in rows:
            if not isinstance(row, dict): continue
            curr = (row.get(ckey) or row.get("modal_price") or
                    row.get("avg_price") or row.get("price") or row.get("current_price"))
            prev = (row.get(pkey) or row.get("prev_modal_price") or row.get("previous_price"))
            try:
                curr = float(curr) if curr not in (None,"","N/A","0",0) else None
                prev = float(prev) if prev not in (None,"","N/A","0",0) else None
            except (ValueError, TypeError):
                curr = prev = None
            try: change = float(row.get("change_over_previous_month") or 0)
            except: change = 0.0
            state = row.get("state") or row.get("state_name") or row.get("statename") or "-"
            if curr is not None:
                out.append({"state":state,"current_price":curr,
                            "previous_price":prev,"change":change})
        return out
    except Exception as e:
        print(f"[Price Error id={commodity_id}] {e}"); return []


# ─── WEATHER ──────────────────────────────────────────────────────────────────
def get_weather_prompt_response():
    return {
        "status":"success","type":"weather_prompt",
        "reply":(
            "🌤 **Weather Lookup**\n\n"
            "Type any city name:\n"
            "• _Weather in Mumbai_\n"
            "• _Temperature in Delhi_\n"
            "• _How is the weather in Pune?_"
        ),
        "items":[]
    }


def get_weather_response(city: str):
    try:
        geo = requests.get(
            f"https://api.openweathermap.org/geo/1.0/direct?q={city}&limit=1&appid={OPENWEATHER_KEY}",
            timeout=6).json()
        if not geo:
            return {"status":"success","type":"weather",
                    "reply":f"❌ City **{city}** not found. Check spelling and try again.","items":[]}
        lat, lon = geo[0]["lat"], geo[0]["lon"]
        resolved = geo[0].get("name", city)
        country  = geo[0].get("country","")
        wr = requests.get(
            f"https://api.openweathermap.org/data/2.5/weather?lat={lat}&lon={lon}&units=metric&appid={OPENWEATHER_KEY}",
            timeout=6).json()
        if not wr.get("main"):
            return {"status":"success","type":"weather",
                    "reply":f"⚠️ Weather unavailable for **{city}**.","items":[]}
        temp     = round(wr["main"]["temp"])
        feels    = round(wr["main"]["feels_like"])
        humidity = wr["main"]["humidity"]
        wind     = round(wr["wind"]["speed"], 1)
        desc     = wr["weather"][0]["description"].title()
        icon     = wr["weather"][0]["icon"]
        advisory = _weather_advisory(temp, humidity, wind, desc)
        return {
            "status":"success","type":"weather",
            "reply":(f"🌤 **{resolved}, {country}** — {temp}°C ({desc})\n"
                     f"💧 Humidity: {humidity}% · 💨 Wind: {wind} m/s · Feels: {feels}°C\n\n"
                     f"📋 {advisory}"),
            "items":[{"location":f"{resolved}, {country}","temp":temp,"feels_like":feels,
                      "desc":desc,"icon":icon,"humidity":humidity,"wind":wind,"overview":advisory}]
        }
    except Exception as e:
        print(f"[Weather Error] {e}")
        return {"status":"error","type":"weather","reply":"⚠️ Could not fetch weather. Try again.","items":[]}


def _weather_advisory(temp, humidity, wind, desc):
    dl = desc.lower(); parts = []
    if temp >= 38:   parts.append("🔥 Extreme heat — stay hydrated.")
    elif temp >= 32: parts.append("☀️ Hot — carry water outdoors.")
    elif temp <= 5:  parts.append("🥶 Very cold — dress warmly.")
    elif temp <= 15: parts.append("🧥 Cool — jacket recommended.")
    else:            parts.append("😊 Comfortable temperatures.")
    if "rain" in dl or "drizzle" in dl:    parts.append("☔ Carry an umbrella.")
    elif "storm" in dl or "thunder" in dl: parts.append("⛈️ Thunderstorm — stay indoors.")
    elif "snow" in dl:                     parts.append("❄️ Snow expected.")
    elif "fog" in dl or "mist" in dl:     parts.append("🌫️ Low visibility.")
    if humidity > 80: parts.append("💦 High humidity.")
    if wind > 10:     parts.append(f"💨 Strong winds ({wind} m/s).")
    return " ".join(parts)


# ─── GROQ Q&A ─────────────────────────────────────────────────────────────────
def get_groq_response(user_message: str, history: list):
    if not groq_client:
        return _fallback_response()
    try:
        msgs = [{"role":"system","content":SYSTEM_PROMPT}]
        for t in history[-10:]:
            r, c = t.get("role","user"), t.get("content","")
            if r in ("user","assistant") and c:
                msgs.append({"role":r,"content":c})
        msgs.append({"role":"user","content":user_message})
        resp = groq_client.chat.completions.create(
            model=GROQ_MODEL, messages=msgs, max_tokens=600, temperature=0.7)
        return {"status":"success","type":"general",
                "reply":resp.choices[0].message.content.strip(),"items":[]}
    except Exception as e:
        print(f"[Groq Error] {e}"); return _fallback_response()


# ─── Help / Concern / Fallback ────────────────────────────────────────────────
def get_help_response():
    return {"status":"success","type":"help","reply":(
        "👋 **Seamless Assistant — Help**\n\n"
        "**What I can do:**\n"
        "• **Top News** — All today's headlines (Published + Pending) with category sections\n"
        "• **Commodities** — Live Agmarknet wholesale prices\n"
        "• **Weather** — Real-time weather for any city\n"
        "• **General Q&A** — Ask me anything\n"
        "• **Raise Concern** — Submit a platform issue\n\n"
        "**Examples:**\n"
        "- _\"Price of Wheat today\"_\n"
        "- _\"Weather in Nagpur\"_\n"
        "- _\"What is MSP?\"_\n"
        "- _Concern: Dashboard is slow_"
    ),"items":[]}


def get_concern_prompt_response():
    return {"status":"success","type":"concern_prompt","reply":(
        "⚠️ **Raise a Concern**\n\n"
        "Start your message with: `Concern: [your issue]`\n\n"
        "_Example:_ Concern: News feed is not loading on mobile."
    ),"items":[]}


def save_concern_response(message: str):
    text = _extract_concern_text(message)
    if _save_concern(text):
        return {"status":"success","type":"concern_saved",
                "reply":"✅ **Concern Recorded** — Saved and will be reviewed. Thank you!","items":[]}
    return {"status":"error","type":"concern_error",
            "reply":"❌ Could not save concern. Please try again.","items":[]}


def _extract_concern_text(msg: str) -> str:
    msg = msg.strip()
    for p in ["my concern is","concern:","i want to report","i want to raise a concern about"]:
        if msg.lower().startswith(p):
            return msg[len(p):].strip(" :.-")
    return msg


def _save_concern(text: str) -> bool:
    try:
        db = get_db(); cur = db.cursor()
        uid = getattr(current_user, "id", None)
        cur.execute("INSERT INTO chatbot_concerns (user_id, concern_text, created_at, status) VALUES (%s,%s,NOW(),%s)",
                    (uid, text, "open"))
        db.commit(); cur.close(); return True
    except Exception as e:
        print(f"[Concern Error] {e}"); return False


def _fallback_response():
    return {"status":"success","type":"fallback","reply":(
        "I'm not sure I understood that. I can help with:\n\n"
        "• **Top News** — all headlines with summaries\n"
        "• **Commodity prices** — e.g. _\"price of wheat\"_\n"
        "• **Weather** — e.g. _\"weather in Mumbai\"_\n"
        "• **General questions** — ask me anything"
    ),"items":[]}


# ─── CHAT HISTORY (DB-backed) ─────────────────────────────────────────────────
def _save_history_entry(user_msg: str, bot_reply: str, msg_type: str):
    """Save a conversation turn to chatbot_history table."""
    try:
        db = get_db(); cur = db.cursor()
        uid = getattr(current_user, "id", None)
        cur.execute("""
            INSERT INTO chatbot_history (user_id, user_message, bot_reply, msg_type, created_at)
            VALUES (%s, %s, %s, %s, NOW())
        """, (uid, user_msg[:500], bot_reply[:2000], msg_type))
        db.commit(); cur.close()
    except Exception as e:
        # Silently fail — history is non-critical
        print(f"[History Save Error] {e}")


def _load_history(limit=50):
    """Load recent chat history for the current user."""
    try:
        db = get_db(); cur = db.cursor(dictionary=True)
        uid = getattr(current_user, "id", None)
        cur.execute("""
            SELECT user_message, bot_reply, msg_type, created_at
            FROM chatbot_history
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (uid, limit))
        rows = cur.fetchall(); cur.close()
        result = []
        for row in reversed(rows):
            ts = row["created_at"]
            ts_str = ts.strftime("%d %b %Y, %H:%M") if hasattr(ts,"strftime") else str(ts)
            result.append({
                "user_message": row["user_message"],
                "bot_reply":    row["bot_reply"],
                "msg_type":     row["msg_type"],
                "timestamp":    ts_str,
            })
        return result
    except Exception as e:
        print(f"[History Load Error] {e}"); return []