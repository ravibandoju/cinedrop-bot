"""
Instagram Daily Movie Post Bot - Multi-Format Edition
Automatically generates and publishes diverse movie posts to Instagram daily.
Supports 7 different card types (one per day of week) using Groq + Pillow.
Targets Indian audience (18–35, bilingual Hindi/English).
"""

import os
import json
import time
import base64
import random
import re
import requests
import textwrap
from datetime import datetime, timezone, timedelta
from pathlib import Path
from dotenv import load_dotenv
from groq import Groq
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from io import BytesIO

# Load environment variables from .env file
load_dotenv()

# ============================================================================
# CONFIGURATION & CONSTANTS
# ============================================================================

# API Keys from environment variables
TMDB_API_KEY = os.getenv("TMDB_API_KEY")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
INSTAGRAM_ACCESS_TOKEN = os.getenv("INSTAGRAM_ACCESS_TOKEN")
INSTAGRAM_ACCOUNT_ID = os.getenv("INSTAGRAM_ACCOUNT_ID")
GH_TOKEN = os.getenv("GH_TOKEN")

# Separate "state" repository that stores the posted-movies history.
HISTORY_REPO = os.getenv("HISTORY_REPO", "ravibandoju/cinedrop_state")
HISTORY_REPO_TOKEN = os.getenv("HISTORY_REPO_TOKEN") or GH_TOKEN
HISTORY_FILE_PATH = "posted_movies.json"
HISTORY_REPO_BRANCH = os.getenv("HISTORY_REPO_BRANCH", "main")

# API Base URLs
TMDB_BASE_URL = "https://api.themoviedb.org/3"
INSTAGRAM_GRAPH_BASE_URL = "https://graph.facebook.com/v18.0"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p"
GITHUB_API_BASE_URL = "https://api.github.com"

# Image card settings
PAGE_HANDLE = "@cinedrop"
CARD_WIDTH = 1080
CARD_HEIGHT = 1350
CARD_QUALITY = 95

# Paths
FONT_DIR = Path("fonts")
BEBAS = str(FONT_DIR / "BebasNeue-Regular.ttf")
OPENSANS = str(FONT_DIR / "OpenSans-Regular.ttf")
OPENSANS_BOLD = str(FONT_DIR / "OpenSans-Bold.ttf")

POSTED_MOVIES_FILE = Path("posted_movies.json")
TEMP_DIR = Path("/tmp" if os.name != "nt" else os.getenv("TEMP", "./temp"))
CARDS_DIR = Path("cards")

# Cache the SHA of the history file
_HISTORY_FILE_SHA = None

# ============================================================================
# BRAND COLORS
# ============================================================================

COLOR_BG_DARK = (8, 8, 12)
COLOR_BG_CARD = (13, 13, 20)
COLOR_SAFFRON = (255, 103, 0)          # Indian films
COLOR_PURPLE = (108, 63, 194)          # Hollywood
COLOR_GOLD = (212, 175, 55)            # Classic era
COLOR_GREEN = (29, 158, 117)           # Recent / mood
COLOR_RED = (229, 9, 20)               # Hot take / Netflix
COLOR_BLUE = (0, 168, 224)             # Prime Video
COLOR_PINK = (212, 80, 126)            # Romance mood
COLOR_WHITE = (255, 255, 255)
COLOR_GRAY = (136, 136, 136)
COLOR_DARK_GRAY = (34, 34, 34)
COLOR_GOLD_TEXT = (255, 215, 0)        # Ratings

# ============================================================================
# ERA & CINEMA CONFIGURATIONS
# ============================================================================

# Era configurations for diversified movie pool
ERA_CONFIGS = [
    {
        "primary_release_date.gte": "1950-01-01",
        "primary_release_date.lte": "1994-12-31",
        "vote_count.gte": 500,
        "sort_by": "vote_average.desc",
        "label": "classic"
    },
    {
        "primary_release_date.gte": "1995-01-01",
        "primary_release_date.lte": "2015-12-31",
        "vote_count.gte": 300,
        "sort_by": "vote_average.desc",
        "label": "modern"
    },
    {
        "primary_release_date.gte": "2016-01-01",
        "vote_count.gte": 100,
        "sort_by": "popularity.desc",
        "label": "recent"
    },
]

# Language groups
LANGUAGE_GROUPS = [
    {"langs": "en", "type": "Hollywood"},
    {"langs": "hi|ta|te|ml|kn", "type": "Indian"},
]

# Genre rotation by day of week (0=Monday, 6=Sunday)
GENRE_BY_DAY = {
    0: {"name": "Thriller", "id": 53},
    1: {"name": "Action", "id": 28},
    2: {"name": "Drama", "id": 18},
    3: {"name": "Family", "id": 10751},
    4: {"name": "Comedy", "id": 35},
    5: {"name": "Romance", "id": 10749},
    6: {"name": "Science Fiction", "id": 878},
}

# Post type by day of week (0=Monday, 6=Sunday)
POST_TYPE_BY_DAY = {
    0: "recommendation",   # Monday
    1: "hot_take",         # Tuesday
    2: "dialogue",         # Wednesday
    3: "mood_pick",        # Thursday
    4: "trivia",           # Friday
    5: "list",             # Saturday
    6: "rating",           # Sunday
}

# Streaming provider IDs (corrected mapping)
PROVIDER_MAPPING = {
    8: "Netflix",
    119: "Amazon Prime Video",
    35: "Apple TV+",
    122: "Disney+ Hotstar",
    232: "Zee5",
    237: "SonyLIV",
    892: "JioCinema",
    190: "Mubi",
    15: "Hulu",
    384: "Max",
    387: "Peacock",
    531: "Paramount+",
    337: "Disney+",
}

# Streaming provider colors
PROVIDER_COLORS = {
    "Netflix": (229, 9, 20),
    "Prime Video": COLOR_BLUE,
    "Disney+ Hotstar": COLOR_PURPLE,
    "Zee5": (230, 65, 115),
}

# ============================================================================
# HASHTAG POOLS - DYNAMIC & LAYERED STRATEGY
# ============================================================================

# Rotate daily so Instagram doesn't flag repetition
GLOBAL_TAG_POOLS = [
    ["#worldcinema","#cinephile","#filmrecommendation","#cinedrop","#watchlist"],
    ["#cinemalovers","#filmcommunity","#moviestowatch","#cinedrop","#filmobsessed"],
    ["#filmgeek","#cinemasociety","#moviebuff","#cinedrop","#filmfanatic"],
    ["#screened","#letterboxd","#filmtwitter","#cinedrop","#watchthis"],
    ["#indiefilm","#arthouse","#filmculture","#cinedrop","#cinematography"],
    ["#ottwatch","#streamingwatch","#weekendwatch","#cinedrop","#bingethis"],
    ["#movienerd","#filmnerds","#cinemaniac","#cinedrop","#dailyfilm"],
]

CINEMA_TAGS = {
    "hi": ["#bollywoodcinema","#hindifilm","#desicinema","#bollywoodlovers"],
    "ta": ["#tamilcinema","#kollywood","#tamilfilm","#southindiancinema"],
    "te": ["#telugucinema","#tollywood","#telugufilm","#southindiancinema"],
    "ml": ["#malayalamcinema","#mollywood","#malayalamfilm","#keralacinema"],
    "kn": ["#kannadacinema","#sandalwood","#kannadafilm","#southindiancinema"],
    "en": ["#hollywoodfilm","#englishmovie","#hollywoodcinema","#westerncinema"],
}

ERA_TAGS = {
    "classic": ["#classiccinema","#vintagemovies","#goldenageofcinema","#timelessfilm","#mustseeclassic"],
    "modern": ["#hiddengem","#underratedfilm","#sleptonsfilm","#modernclassic","#forgottencinema"],
    "recent": ["#newrelease","#ottrelease","#streamingpick","#freshdrop","#watchnow"],
}

GENRE_TAGS = {
    "Thriller": ["#thrillermovies","#mindbendingthriller","#suspensefilm","#plottwist","#edgeofyourseat"],
    "Drama": ["#emotionalfilm","#cinemathatfeels","#heartbreakingcinema","#powerfuldrama","#filmsthatmakeyoucry"],
    "Action": ["#actioncinema","#massfilm","#actionfilm","#blockbustercinema","#actionpacked"],
    "Comedy": ["#comedyfilm","#laughoutloud","#feelgoodmovie","#funnyfilm","#comedicgold"],
    "Romance": ["#romanticfilm","#lovestory","#romancecinema","#heartwarming","#couplesmovie"],
    "Horror": ["#horrorfilm","#scarymovie","#horrorcommunity","#horrorlovers","#dontwatchalone"],
    "Science Fiction": ["#scififilm","#sciencefiction","#scificinema","#mindblown","#futuristicfilm"],
    "Family": ["#familymovie","#watchwiththefamily","#allagesfilm","#familyfilm","#feelgoodcinema"],
}

POST_TYPE_TAGS = {
    "recommendation": ["#movierecommendation","#filmsuggestion","#whattowatch"],
    "hot_take": ["#unpopularopinion","#filmopinion","#cinematake"],
    "dialogue": ["#moviequote","#filmquote","#iconiclines"],
    "mood_pick": ["#moodfilm","#watchthisif","#relatablefilm"],
    "trivia": ["#filmtrivia","#didyouknow","#filmfacts"],
    "list": ["#filmstowatch","#movielist","#watchlist"],
    "rating": ["#filmrating","#cinedroprates","#filmcritic"],
}

MOOD_TAGS = {
    "Thriller": ["#cantsleepfilm","#mindblownending","#onemoreminute"],
    "Drama": ["#cryingoverfilm","#filmsthathugyou","#emotionaldamage"],
    "Action": ["#pumpedupfilm","#adrenalinerush","#massmoment"],
    "Comedy": ["#laughtertherapy","#feelgoodfilm","#happywatch"],
    "Romance": ["#lovesickfilm","#romanticmood","#filmromance"],
    "Horror": ["#scaredbutcantlook","#horrornight","#jumpscarefilm"],
    "Science Fiction": ["#brainfood","#existentialfilm","#thinkingfilm"],
    "Family": ["#sundayfilm","#familytime","#hometheatre"],
}

# India Standard Time (UTC+5:30)
IST = timezone(timedelta(hours=5, minutes=30))


# ============================================================================
# POSTING TIME VALIDATION
# ============================================================================

def log_ist_time():
    """Log current IST time so Actions logs are readable for Indian users."""
    ist_now = datetime.now(IST)
    day_name = ist_now.strftime("%A")
    ist_str = ist_now.strftime("%I:%M %p IST")
    log_message(f"Posting time: {day_name} {ist_str}")
    log_message(f"Post type for today: {get_post_type()}")


def check_token_age():
    """
    Warn in logs if Instagram token might be expiring soon.
    Instagram long-lived tokens last 60 days.
    This checks the token against the graph API debug endpoint.
    """
    try:
        url = "https://graph.facebook.com/debug_token"
        params = {
            "input_token": INSTAGRAM_ACCESS_TOKEN,
            "access_token": INSTAGRAM_ACCESS_TOKEN
        }
        resp = requests.get(url, params=params, timeout=10)
        data = resp.json().get("data", {})
        expires_at = data.get("expires_at", 0)
        if expires_at:
            expiry_date = datetime.fromtimestamp(expires_at, tz=timezone.utc)
            days_left = (expiry_date - datetime.now(timezone.utc)).days
            if days_left < 3:
                log_message(f"🚨 Instagram token expires in {days_left} days — REFRESH NOW!", level="ERROR")
            elif days_left < 7:
                log_message(f"⚠️ Instagram token expires in {days_left} days — refresh soon!", level="WARNING")
    except Exception as e:
        log_message(f"Could not check token age: {str(e)}", level="WARNING")


# ============================================================================
# UTILITY FUNCTIONS - FONTS & COLORS
# ============================================================================

def load_font(path, size):
    """Load font, with fallback to default if file not found."""
    try:
        return ImageFont.truetype(path, size)
    except (OSError, IOError):
        return ImageFont.load_default()


def get_cinema_color(original_language):
    """Get color badge for cinema type."""
    return COLOR_SAFFRON if original_language in ["hi", "ta", "te", "ml", "kn"] else COLOR_PURPLE


def get_era_text(year):
    """Get era label and associated color."""
    if year < 1995:
        return "classic", COLOR_GOLD
    elif year < 2016:
        return "modern", COLOR_BLUE
    else:
        return "recent", COLOR_GREEN


def get_language_label(language_code):
    """Get human-readable language label."""
    labels = {
        "hi": "Bollywood",
        "ta": "Tamil",
        "te": "Telugu",
        "ml": "Malayalam",
        "kn": "Kannada",
    }
    return labels.get(language_code, "Hollywood")


def get_mood_color(genre_name):
    """Get color for mood-based posts."""
    mood_map = {
        "Romance": COLOR_PINK,
        "Comedy": COLOR_GOLD,
        "Drama": COLOR_BLUE,
        "Action": COLOR_RED,
        "Thriller": COLOR_PURPLE,
        "Science Fiction": COLOR_GREEN,
    }
    return mood_map.get(genre_name, COLOR_SAFFRON)


def wrap_text(draw, text, font, max_width):
    """Wrap text to fit within max_width."""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = " ".join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(" ".join(current_line))
    
    return lines


def draw_wrapped_text(draw, text, pos, font, fill, max_width, line_spacing=10):
    """Draw wrapped text and return the height used."""
    lines = wrap_text(draw, text, font, max_width)
    x, y = pos
    total_height = 0
    
    for line in lines:
        draw.text((x, y), line, font=font, fill=fill)
        bbox = draw.textbbox((x, y), line, font=font)
        line_height = bbox[3] - bbox[1]
        y += line_height + line_spacing
        total_height += line_height + line_spacing
    
    return total_height


def draw_centered_text(draw, text, y, font, fill, max_width=900):
    """Draw text centered horizontally at given y position."""
    lines = wrap_text(draw, text, font, max_width)
    total_height = 0
    
    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        line_width = bbox[2] - bbox[0]
        x = (CARD_WIDTH - line_width) // 2
        draw.text((x, y), line, font=font, fill=fill)
        line_height = bbox[3] - bbox[1]
        y += line_height + 8
        total_height += line_height + 8
    
    return total_height


# ============================================================================
# UTILITY FUNCTIONS - HISTORY & LOGGING
# ============================================================================

def _history_api_headers():
    """Build auth headers for the GitHub Contents API."""
    return {
        "Authorization": f"Bearer {HISTORY_REPO_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_posted_movies():
    """Load the posted-movies history from the separate state repo via GitHub Contents API."""
    global _HISTORY_FILE_SHA

    if HISTORY_REPO_TOKEN:
        try:
            url = f"{GITHUB_API_BASE_URL}/repos/{HISTORY_REPO}/contents/{HISTORY_FILE_PATH}"
            resp = requests.get(
                url,
                headers=_history_api_headers(),
                params={"ref": HISTORY_REPO_BRANCH},
                timeout=15,
            )
            if resp.status_code == 200:
                payload = resp.json()
                _HISTORY_FILE_SHA = payload.get("sha")
                content = base64.b64decode(payload["content"]).decode("utf-8")
                data = json.loads(content) if content.strip() else []
                if data and isinstance(data[0], int):
                    return [{"id": mid, "title": "", "rating": None, "language": "en", "year": "N/A", "date": ""} for mid in data]
                return data
            elif resp.status_code == 404:
                log_message(f"No history file found in {HISTORY_REPO}; starting fresh.", level="WARNING")
                _HISTORY_FILE_SHA = None
                return []
            else:
                log_message(
                    f"Could not read history from {HISTORY_REPO}: {resp.status_code} {resp.text}",
                    level="WARNING",
                )
        except Exception as e:
            log_message(f"Error loading history from state repo: {str(e)}", level="WARNING")

    # Fallback: local file
    if POSTED_MOVIES_FILE.exists():
        with open(POSTED_MOVIES_FILE, "r") as f:
            try:
                data = json.load(f)
            except json.JSONDecodeError:
                return []
        if data and isinstance(data[0], int):
            return [{"id": mid, "title": "", "rating": None, "language": "en", "year": "N/A", "date": ""} for mid in data]
        return data
    return []


def get_posted_ids(history=None):
    """Return a set of movie IDs that have already been posted."""
    if history is None:
        history = load_posted_movies()
    return {entry["id"] for entry in history}


def get_today_genre():
    """Get the genre for today based on day of week."""
    today = datetime.utcnow().weekday()
    return GENRE_BY_DAY[today]


def get_post_type():
    """Get the post type for today based on day of week."""
    today = datetime.utcnow().weekday()
    return POST_TYPE_BY_DAY[today]


def log_message(message, level="INFO"):
    """Print timestamped log messages."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] [{level}] {message}")


# ============================================================================
# HASHTAG GENERATION - TRENDING + STATIC LAYERS
# ============================================================================

def get_trending_hashtags(movie_title, genre_name, original_language):
    """
    Fetch real-world trending search queries from Google Trends India.
    Returns up to 3 relevant trending hashtags.
    Fails silently — never breaks the post if Trends is down.
    """
    try:
        from pytrends.request import TrendReq
        import pandas as pd

        pytrends = TrendReq(hl='en-IN', tz=330, timeout=(10, 25), retries=1)

        # Build search terms relevant to this film's context
        search_terms = [genre_name, "movies"]
        if original_language in ["hi", "ta", "te", "ml", "kn"]:
            search_terms.append("indian cinema")
        else:
            search_terms.append("hollywood")

        search_terms = list(dict.fromkeys(search_terms))[:5]

        pytrends.build_payload(
            kw_list=search_terms,
            geo='IN',
            timeframe='now 1-d'
        )

        related = pytrends.related_queries()
        trending_tags = []

        for term in search_terms:
            if term not in related:
                continue
            rising = related[term].get("rising")
            if rising is None or rising.empty:
                continue
            for query in rising["query"].head(2).tolist():
                # Clean to hashtag format
                cleaned = query.strip().lower()
                cleaned = ''.join(c for c in cleaned if c.isalnum() or c == ' ')
                tag = "#" + cleaned.replace(" ", "")
                # Quality checks
                if len(tag) < 3 or len(tag) > 28:
                    continue
                if tag in trending_tags:
                    continue
                trending_tags.append(tag)
                if len(trending_tags) >= 4:
                    break
            if len(trending_tags) >= 4:
                break

        # Separately check if the movie title itself has search interest in India
        try:
            pytrends.build_payload(
                kw_list=[movie_title],
                geo='IN',
                timeframe='now 7-d'
            )
            interest = pytrends.interest_over_time()
            if not interest.empty and movie_title in interest.columns:
                avg = interest[movie_title].mean()
                if avg > 15:
                    title_tag = "#" + movie_title.lower().replace(" ","").replace("-","").replace(":","")
                    if len(title_tag) < 28 and title_tag not in trending_tags:
                        trending_tags.insert(0, title_tag)
        except Exception:
            pass

        log_message(f"Trending hashtags fetched: {len(trending_tags)} tags")
        return trending_tags[:3]

    except ImportError:
        log_message("pytrends not installed — skipping trending hashtags", level="WARNING")
        return []
    except Exception as e:
        log_message(f"Trending hashtag fetch failed: {str(e)} — continuing with static tags", level="WARNING")
        return []


def generate_hashtags(movie, post_type):
    """
    Build a dynamic, layered hashtag set for maximum global discovery.
    Combines real-world trending signals with niche static layers.
    Never repeats the same combination two days in a row.
    Returns a single string of space-separated hashtags.
    """
    try:
        original_language = movie.get("original_language", "en")
        title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "2000-01-01")
        year = int(release_date[:4]) if release_date else 2000
        rating = round(movie.get("vote_average", 0), 1)
        genre_name = movie.get("_genre_name", "Drama")

        # Compute era
        if year < 1995:
            era = "classic"
        elif year < 2016:
            era = "modern"
        else:
            era = "recent"

        # --- Layer 1: Real-world trending ---
        trending = get_trending_hashtags(title, genre_name, original_language)

        # --- Layer 2: Film-specific (title) ---
        film_tags = []
        try:
            title_tag = "#" + title.lower().replace(" ","").replace("-","").replace(":","")
            if 3 < len(title_tag) < 28:
                film_tags = [title_tag]
        except Exception:
            pass

        # --- Layer 3: Cinema/language community ---
        cinema = CINEMA_TAGS.get(original_language, CINEMA_TAGS.get("en", []))

        # --- Layer 4: Era ---
        era_list = ERA_TAGS.get(era, [])

        # --- Layer 5: Genre ---
        genre_list = GENRE_TAGS.get(genre_name, GENRE_TAGS.get("Drama", []))

        # --- Layer 6: Mood/emotional tags ---
        mood_list = MOOD_TAGS.get(genre_name, MOOD_TAGS.get("Drama", []))

        # --- Layer 7: Quality signal ---
        quality_tags = []
        if rating >= 9.0:
            quality_tags = ["#top250film","#imdb250","#greatestfilmsever"]
        elif rating >= 8.5:
            quality_tags = ["#highlyrated","#criticschoice","#filmlovers"]
        elif rating >= 8.0:
            quality_tags = ["#solidfilm","#recommendedfilm"]

        # --- Layer 8: Rotating global pool ---
        today = datetime.utcnow().weekday()
        global_list = GLOBAL_TAG_POOLS[today % len(GLOBAL_TAG_POOLS)]

        # --- Layer 9: Post type ---
        type_list = POST_TYPE_TAGS.get(post_type, POST_TYPE_TAGS.get("recommendation", []))

        # --- Combine all layers with priority ordering ---
        all_tags = (
            trending[:3] +
            film_tags[:2] +
            cinema[:3] +
            era_list[:2] +
            genre_list[:3] +
            mood_list[:2] +
            quality_tags[:2] +
            global_list[:3] +
            type_list[:2]
        )

        # --- Deduplicate preserving priority order ---
        seen = set()
        final_tags = []
        for tag in all_tags:
            tag = tag.strip()
            if tag and tag not in seen:
                seen.add(tag)
                final_tags.append(tag)

        # Cap at 28 — feels human, avoids spam flag
        final_tags = final_tags[:28]

        log_message(f"Hashtags built: {len(final_tags)} tags · trending={len(trending)} · era={era} · genre={genre_name}")
        return " ".join(final_tags)

    except Exception as e:
        log_message(f"Hashtag generation failed: {str(e)} — using fallback", level="WARNING")
        # Fallback: just use cinema + genre + post type
        try:
            original_language = movie.get("original_language", "en")
            genre_name = movie.get("_genre_name", "Drama")
            cinema = CINEMA_TAGS.get(original_language, [])
            genre_list = GENRE_TAGS.get(genre_name, [])
            type_list = POST_TYPE_TAGS.get(post_type, [])
            fallback = (cinema[:3] + genre_list[:3] + type_list[:2])
            seen = set()
            final = []
            for tag in fallback:
                if tag not in seen:
                    seen.add(tag)
                    final.append(tag)
            return " ".join(final[:15])
        except Exception:
            return "#cinedrop #filmlovers #moviestowatch"


# ============================================================================
# STEP 1: FETCH MOVIE FROM TMDB
# ============================================================================

def get_movie():
    """
    CHANGE 1: Fetch high-quality movies across 3 eras × 2 language groups (6 total API calls).
    Eras: Golden (1950–1994), Modern (1995–2015), Recent (2016–present).
    Languages: Hollywood (en) and Indian (hi|ta|te|ml|kn).
    
    Returns: dict with movie data
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not found in environment variables")

    try:
        log_message("Fetching movies from TMDb API across eras and language groups...")

        posted_ids = get_posted_ids()
        today_genre = get_today_genre()
        
        # CHANGE 1: Era configurations
        ERA_CONFIGS = [
            {
                "primary_release_date.gte": "1950-01-01",
                "primary_release_date.lte": "1994-12-31",
                "vote_count.gte": 500,
                "sort_by": "vote_average.desc",
                "label": "classic"
            },
            {
                "primary_release_date.gte": "1995-01-01",
                "primary_release_date.lte": "2015-12-31",
                "vote_count.gte": 300,
                "sort_by": "vote_average.desc",
                "label": "modern"
            },
            {
                "primary_release_date.gte": "2016-01-01",
                "vote_count.gte": 100,
                "sort_by": "popularity.desc",
                "label": "recent"
            },
        ]

        LANGUAGE_GROUPS = [
            {"langs": "en", "type": "Hollywood"},
            {"langs": "hi|ta|te|ml|kn", "type": "Indian"},
        ]

        all_movies = []
        url = f"{TMDB_BASE_URL}/discover/movie"
        
        # Make 6 API calls: 3 eras × 2 language groups
        for era_config in ERA_CONFIGS:
            for lang_group in LANGUAGE_GROUPS:
                era_label = era_config["label"]
                cinema_type = lang_group["type"]
                
                params = {
                    "api_key": TMDB_API_KEY,
                    "with_genres": today_genre["id"],
                    "vote_average.gte": 7.0,
                    "include_adult": False,
                    "language": "en-US",
                    "with_original_language": lang_group["langs"],
                    "primary_release_date.gte": era_config["primary_release_date.gte"],
                    "vote_count.gte": era_config["vote_count.gte"],
                    "sort_by": era_config["sort_by"],
                    "page": 1,
                }
                
                if "primary_release_date.lte" in era_config:
                    params["primary_release_date.lte"] = era_config["primary_release_date.lte"]

                try:
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    movies = response.json().get("results", [])
                    
                    # Tag each movie
                    for movie in movies:
                        movie["_era"] = era_label
                        movie["_cinema_type"] = cinema_type
                    
                    all_movies.extend(movies)
                    log_message(f"  {era_label.capitalize()} {cinema_type}: Found {len(movies)} films")
                except Exception as e:
                    log_message(f"  {era_label.capitalize()} {cinema_type}: {str(e)}", level="WARNING")

        # Deduplicate by movie ID
        seen_ids = set()
        unique_movies = []
        for m in all_movies:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                unique_movies.append(m)

        # Count by type
        indian_count = sum(1 for m in unique_movies if m.get("_cinema_type") == "Indian")
        hollywood_count = sum(1 for m in unique_movies if m.get("_cinema_type") == "Hollywood")
        log_message(f"Merged pool: {len(unique_movies)} unique films ({indian_count} Indian, {hollywood_count} Hollywood)")

        if not unique_movies:
            log_message(f"No movies found for {today_genre['name']}", level="WARNING")
            return None

        # Shuffle for variety
        random.shuffle(unique_movies)

        # Filter out posted movies
        movie = None
        for m in unique_movies:
            if m["id"] not in posted_ids:
                movie = m
                break

        if not movie:
            log_message(f"All {today_genre['name']} movies already posted", level="WARNING")
            return None

        lang = movie.get("original_language", "en")
        lang_label = {
            "hi": "Bollywood",
            "ta": "Tamil",
            "te": "Telugu",
            "ml": "Malayalam",
            "kn": "Kannada",
        }.get(lang, "Hollywood")

        # Attach genre name for downstream hashtag generation
        movie["_genre_name"] = today_genre["name"]

        log_message(f"Selected: '{movie['title']}' ({movie.get('release_date', '')[:4]}) - {lang_label} ({movie.get('_cinema_type')}) - Rating: {movie.get('vote_average')}/10")
        return movie

    except requests.RequestException as e:
        log_message(f"TMDb API error: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 2: GET STREAMING PLATFORMS
# ============================================================================

def get_streaming_platforms(movie_id):
    """Fetch streaming availability for India (IN) and US from TMDb API."""
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not found in environment variables")

    try:
        log_message(f"Fetching streaming platforms for movie ID {movie_id}...")

        url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
        params = {"api_key": TMDB_API_KEY}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        streaming_platforms = {"IN": [], "US": []}
        results = data.get("results", {})

        for region, region_code in [("India", "IN"), ("United States", "US")]:
            if region_code in results:
                provider_data = results[region_code]
                providers = provider_data.get("flatrate", [])
                
                for provider in providers:
                    provider_name = PROVIDER_MAPPING.get(provider["provider_id"], provider.get("provider_name", "Unknown"))
                    streaming_platforms[region_code].append(provider_name)
                
                log_message(f"{region} ({region_code}): {', '.join(streaming_platforms[region_code]) or 'No streaming data'}")

        return streaming_platforms

    except requests.RequestException as e:
        log_message(f"TMDb Watch Providers API error: {str(e)}", level="ERROR")
        return {"IN": [], "US": []}


# ============================================================================
# STEP 3: GENERATE CONTENT WITH GROQ
# ============================================================================

def generate_post_content(movie, streaming_platforms, post_type):
    """
    Generate post content for a specific post type using Groq.
    Uses a system message to establish tone, then raw conversational prompts.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment variables")

    try:
        log_message(f"Generating content for post type '{post_type}' with Groq...")

        client = Groq(api_key=GROQ_API_KEY)

        # System message — defines the personality
        system_message = """You are the person behind @cinedrop on Instagram.
You are a 24 year old Indian film obsessive who has seen everything.
You are opinionated, funny, sometimes aggressive, always real.
You text like a friend not a reviewer.
You randomly mix Telugu, Hindi, English — whatever feels right for that film.
You never explain yourself. You never say "I recommend". You never say "this film is".
You just talk. Like you just watched it and grabbed your phone immediately.
You are not professional. You are not a critic. You are not a bot.
If a film is bad you say it. If it's a masterpiece you lose your mind over it.
Your followers trust you because you sound exactly like them."""

        # Extract movie metadata
        original_language = movie.get("original_language", "en")
        language_label = get_language_label(original_language)
        release_date = movie.get("release_date", "")
        year = int(release_date[:4]) if release_date else 0
        rating = round(movie.get("vote_average", 0), 1)
        title = movie.get("title", "Unknown")
        overview = movie.get("overview", "")
        genres = movie.get("genres", [])
        genre_name = genres[0]["name"] if genres else "Drama"

        # Build streaming platforms string
        india_platforms = streaming_platforms.get("IN", [])
        us_only = [p for p in streaming_platforms.get("US", []) if p not in india_platforms]
        if india_platforms:
            platforms_text = f"📺 🇮🇳 {' · '.join(india_platforms)}"
            if us_only:
                platforms_text += f"\n🇺🇸 {' · '.join(us_only)}"
        else:
            platforms_text = "Not streaming — rental/purchase only"

        # Build prompt based on post type
        if post_type == "recommendation":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}
Story: {overview}
Streaming: {platforms_text}

Write an Instagram caption for this.
Be yourself. Talk like you just watched it.
Tell people who should watch it — not generically, based on the actual story.
Tell them when and how — be specific.
One question at the end to start a fight in the comments.
Mix Telugu/Hindi/English randomly — whatever feels right for this film.
No hashtags. No emojis overload. Max 220 characters before the streaming line.
Don't structure it. Don't format it. Just talk.
"""
            max_tokens = 400

        elif post_type == "hot_take":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}
Story: {overview}

Drop a hot take about this film.
Could be unpopular opinion, could be something everyone thinks but nobody says.
Could be comparing it to another film aggressively.
Could be defending it or destroying it.
Be aggressive. Be funny. Pick a side hard.
Mix Telugu/Hindi/English. Sound like you're arguing with someone right now.
End with something that will make people reply angrily or excitedly.
Max 180 characters. No formatting. No hashtags.
"""
            max_tokens = 400

        elif post_type == "dialogue":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Story: {overview}

Give me one iconic line from this film.
If it's a Telugu film give the line in Telugu script.
If it's Hindi give in Hindi.
If English give in English.
Then one line — just one — saying why that line hits.
Sound like you're sending this to a friend at 1am.
No hashtags. No formatting. Don't explain the film.
"""
            max_tokens = 400

        elif post_type == "mood_pick":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}
Story: {overview}
Streaming: {platforms_text}

Tell people when exactly to watch this.
Not generic. Read the story. What kind of mood is this for?
Be hyper specific — "watch this when your situationship just went quiet"
or "Sunday morning chai before everyone wakes up"
or "when you need to cry but don't know why"
or "boys trip, after dinner, non negotiable"
Mix Telugu/Hindi/English freely.
One question at the end. Max 200 characters. No formatting. No hashtags.
"""
            max_tokens = 400

        elif post_type == "trivia":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Story: {overview}

Give me one wild fact about this film.
Something that makes people go "wait what".
Include a number — days, crores, years, something concrete.
If you don't know a real fact make it feel real and specific.
One sentence follow up reacting to the fact like a human would.
Sound like you just found this out and had to tell someone.
Mix Telugu/Hindi/English. Max 200 characters. No hashtags. No formatting.
"""
            max_tokens = 400

        elif post_type == "list":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}

Give me 5 films to watch if someone loved this one.
Mix Indian and Hollywood. Mix languages. Real films only.
For each film: title, year, one word why.
Then one aggressive line at the top introducing the list.
Sound like you made this list at 2am because someone asked you.
Return as JSON only:
{{
  "intro": "one aggressive intro line",
  "films": [
    {{"title": "...", "year": 0000, "reason": "one word"}},
    {{"title": "...", "year": 0000, "reason": "one word"}},
    {{"title": "...", "year": 0000, "reason": "one word"}},
    {{"title": "...", "year": 0000, "reason": "one word"}},
    {{"title": "...", "year": 0000, "reason": "one word"}}
  ]
}}
JSON only. No markdown. No explanation.
"""
            max_tokens = 300

        elif post_type == "rating":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}
Story: {overview}

Rate this film honestly on these 4 things — score out of 10:
Story, Performances, Rewatch value, Emotional hit
Give a one word verdict: MASTERPIECE / SOLID / DECENT / SKIP
Then one line verdict in Hinglish or Telugu — aggressive and honest.
Return as JSON only:
{{
  "story": 0.0,
  "performances": 0.0,
  "rewatch": 0.0,
  "emotional_hit": 0.0,
  "verdict": "WORD",
  "verdict_line": "one aggressive honest line"
}}
JSON only. No markdown. No explanation.
"""
            max_tokens = 300

        else:
            raise ValueError(f"Unknown post type: {post_type}")

        # Call Groq with system message
        message = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=max_tokens,
            messages=[
                {"role": "system", "content": system_message},
                {"role": "user", "content": prompt}
            ]
        )

        response_text = message.choices[0].message.content.strip()

        # Handle JSON types (list, rating) with fallback
        if post_type in ["list", "rating"]:
            # Strip markdown fences if present
            if response_text.startswith("```"):
                response_text = re.sub(r"```json\n?", "", response_text)
                response_text = re.sub(r"```\n?", "", response_text)

            try:
                content = json.loads(response_text)
            except json.JSONDecodeError as e:
                log_message(f"JSON parse failed for {post_type}, using fallback: {str(e)}", level="WARNING")
                if post_type == "list":
                    content = {
                        "intro": "films to watch next",
                        "films": [
                            {"title": "Unknown", "year": 2024, "reason": ""},
                        ]
                    }
                else:  # rating
                    content = {
                        "story": 7.0,
                        "performances": 7.0,
                        "rewatch": 6.5,
                        "emotional_hit": 7.0,
                        "verdict": "SOLID",
                        "verdict_line": "worth a watch"
                    }
        else:
            # For non-JSON types, use raw text as caption
            content = {"caption": response_text}

        log_message(f"Content generated for {post_type}")
        return content

    except Exception as e:
        log_message(f"Groq API error: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 4: PILLOW CARD RENDERING FUNCTIONS
# ============================================================================

def render_recommendation(movie, content, streaming_platforms):
    """Render recommendation card: poster + metadata + streaming on right panel."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Download poster
        poster_path = movie.get("poster_path")
        if poster_path:
            poster_url = f"{TMDB_IMAGE_BASE_URL}/w342{poster_path}"
            try:
                resp = requests.get(poster_url, timeout=10)
                resp.raise_for_status()
                poster = Image.open(BytesIO(resp.content)).convert("RGB")
                poster.thumbnail((440, 900), Image.Resampling.LANCZOS)
                
                # Round corners via mask
                mask = Image.new("L", poster.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle((0, 0, poster.size[0], poster.size[1]), radius=20, fill=255)
                poster.putalpha(mask)
                
                card.paste(poster, (40, 225), poster)
            except Exception as e:
                log_message(f"Could not download poster: {str(e)}", level="WARNING")
        
        # Right panel (x=520 to x=1040)
        draw.rectangle([(520, 50), (1040, 1300)], fill=COLOR_BG_CARD)
        
        # Cinema & era badges at top
        original_language = movie.get("original_language", "en")
        cinema_color = get_cinema_color(original_language)
        cinema_label = "🇮🇳 Indian" if original_language in ["hi", "ta", "te", "ml", "kn"] else "🎬 Hollywood"
        
        release_date = movie.get("release_date", "")
        year = int(release_date[:4]) if release_date else 0
        era_label, era_color = get_era_text(year)
        
        # Cinema badge
        cinema_font = load_font(OPENSANS_BOLD, 20)
        draw.rectangle([(540, 70), (620, 105)], fill=cinema_color)
        draw.text((545, 75), cinema_label, font=cinema_font, fill=COLOR_WHITE)
        
        # Era badge
        era_text = f"⭐ {era_label.upper()}"
        draw.rectangle([(630, 70), (750, 105)], fill=era_color)
        draw.text((635, 75), era_text, font=cinema_font, fill=COLOR_WHITE)
        
        # Movie title
        title_font = load_font(BEBAS, 72)
        title = movie.get("title", "Unknown")
        lines = wrap_text(draw, title, title_font, 480)
        y = 120
        for line in lines:
            draw.text((540, y), line, font=title_font, fill=COLOR_WHITE)
            bbox = draw.textbbox((540, y), line, font=title_font)
            y += bbox[3] - bbox[1] + 5
        
        # Year + director
        subtitle_font = load_font(OPENSANS, 28)
        year_text = f"{year} • Director TBD"
        draw.text((540, y), year_text, font=subtitle_font, fill=COLOR_GRAY)
        
        # Rating
        rating_font = load_font(BEBAS, 96)
        rating_small_font = load_font(OPENSANS, 28)
        rating = round(movie.get("vote_average", 0), 1)
        draw.text((540, y + 80), str(rating), font=rating_font, fill=COLOR_GOLD_TEXT)
        draw.text((720, y + 100), "/10", font=rating_small_font, fill=COLOR_GRAY)
        
        # Divider
        draw.line([(540, y + 180), (1000, y + 180)], fill=COLOR_DARK_GRAY, width=1)
        
        # Streaming label
        streaming_label_font = load_font(OPENSANS, 20)
        draw.text((540, y + 200), "STREAMING ON", font=streaming_label_font, fill=COLOR_GRAY)
        
        # Platform pills
        india_platforms = streaming_platforms.get("IN", [])
        platform_font = load_font(OPENSANS_BOLD, 18)
        px = 540
        py = y + 240
        for platform in india_platforms[:3]:
            color = PROVIDER_COLORS.get(platform, COLOR_DARK_GRAY)
            bbox = draw.textbbox((0, 0), platform, font=platform_font)
            w = bbox[2] - bbox[0] + 20
            h = bbox[3] - bbox[1] + 10
            draw.rounded_rectangle([(px, py), (px + w, py + h)], radius=8, fill=color)
            draw.text((px + 10, py + 5), platform, font=platform_font, fill=COLOR_WHITE)
            px += w + 10
        
        # Bottom bar
        draw.rectangle([(0, 1290), (CARD_WIDTH, 1350)], fill=COLOR_BG_DARK)
        handle_font = load_font(OPENSANS, 24)
        draw.text((40, 1305), PAGE_HANDLE, font=handle_font, fill=COLOR_GRAY)
        draw.text((CARD_WIDTH - 280, 1305), "save this 🔖", font=handle_font, fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_recommendation.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Recommendation card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering recommendation card: {str(e)}", level="ERROR")
        raise


def render_dialogue(movie, content):
    """Render dialogue card: centered iconic line."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Accent bar at top
        original_language = movie.get("original_language", "en")
        accent_color = get_cinema_color(original_language)
        draw.rectangle([(0, 0), (CARD_WIDTH, 8)], fill=accent_color)
        
        # Large quote mark
        quote_font = load_font(BEBAS, 200)
        draw.text((100, 200), '"', font=quote_font, fill=accent_color)
        
        # Dialogue text
        dialogue_font = load_font(OPENSANS_BOLD, 52)
        dialogue = content.get("dialogue", "No dialogue")
        draw.text((100, 500), dialogue, font=dialogue_font, fill=COLOR_WHITE)
        
        # Film attribution
        title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        attribution_font = load_font(OPENSANS, 28)
        attribution = f"— {title} · {year}"
        bbox = draw.textbbox((0, 0), attribution, font=attribution_font)
        x = (CARD_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, 1100), attribution, font=attribution_font, fill=accent_color)
        
        # Bottom bar
        draw.rectangle([(0, 1280), (CARD_WIDTH, 1350)], fill=accent_color)
        label_font = load_font(BEBAS, 36)
        draw.text((40, 1295), "ICONIC DIALOGUE", font=label_font, fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 280, 1303), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_dialogue.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Dialogue card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering dialogue card: {str(e)}", level="ERROR")
        raise


def render_hot_take(movie, content):
    """Render hot take card: unpopular opinion prominently displayed."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Hot take badge
        badge_font = load_font(BEBAS, 32)
        badge_text = "UNPOPULAR OPINION"
        bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
        badge_w = bbox[2] - bbox[0] + 20
        draw.rectangle([(40, 60), (40 + badge_w, 100)], fill=COLOR_RED)
        draw.text((50, 65), badge_text, font=badge_font, fill=COLOR_WHITE)
        
        # Main take text
        take_font = load_font(BEBAS, 88)
        take = content.get("take", "No take")
        y = 160
        lines = wrap_text(draw, take, take_font, 1000)
        for line in lines:
            draw.text((40, y), line, font=take_font, fill=COLOR_WHITE)
            bbox = draw.textbbox((40, y), line, font=take_font)
            y += bbox[3] - bbox[1] + 10
        
        # Explanation text
        explanation_font = load_font(OPENSANS, 38)
        explanation = content.get("explanation", "")
        y += 30
        lines = wrap_text(draw, explanation, explanation_font, 960)
        for line in lines:
            draw.text((40, y), line, font=explanation_font, fill=COLOR_GRAY)
            bbox = draw.textbbox((40, y), line, font=explanation_font)
            y += bbox[3] - bbox[1] + 8
        
        # Film attribution
        title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        original_language = movie.get("original_language", "en")
        accent_color = get_cinema_color(original_language)
        
        attribution = f"— {title} · {year}"
        attribution_font = load_font(OPENSANS_BOLD, 30)
        bbox = draw.textbbox((0, 0), attribution, font=attribution_font)
        x = (CARD_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, 1080), attribution, font=attribution_font, fill=accent_color)
        
        # Bottom bar
        draw.rectangle([(0, 1280), (CARD_WIDTH, 1350)], fill=COLOR_RED)
        cta_font = load_font(BEBAS, 36)
        cta = content.get("cta", "What do you think?")
        draw.text((40, 1295), cta, font=cta_font, fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 280, 1303), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_hot_take.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Hot take card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering hot take card: {str(e)}", level="ERROR")
        raise


def render_mood_pick(movie, content, streaming_platforms):
    """Render mood pick card: mood-based recommendation with vibe."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Get mood color
        genres = movie.get("genres", [])
        genre_name = genres[0]["name"] if genres else "Drama"
        mood_color = get_mood_color(genre_name)
        
        # Tint background with mood color
        tint = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), mood_color)
        card = Image.blend(card, tint, 0.05)
        draw = ImageDraw.Draw(card)
        
        # Mood badge
        badge_font = load_font(BEBAS, 32)
        draw.rectangle([(40, 60), (280, 110)], fill=mood_color)
        draw.text((50, 68), "WATCH THIS IF...", font=badge_font, fill=COLOR_WHITE)
        
        # Mood line
        mood_font = load_font(BEBAS, 72)
        mood_line = content.get("mood_line", "You need something good")
        y = 140
        lines = wrap_text(draw, mood_line, mood_font, 900)
        for line in lines:
            draw.text((60, y), line, font=mood_font, fill=COLOR_WHITE)
            bbox = draw.textbbox((60, y), line, font=mood_font)
            y += bbox[3] - bbox[1] + 8
        
        # Vibe
        vibe_font = load_font(OPENSANS, 36)
        vibe = content.get("vibe", "")
        draw.text((60, y + 20), vibe, font=vibe_font, fill=COLOR_GRAY)
        
        # Divider
        draw.line([(60, 680), (1000, 680)], fill=mood_color, width=1)
        
        # Bottom section with poster & info
        poster_path = movie.get("poster_path")
        if poster_path:
            poster_url = f"{TMDB_IMAGE_BASE_URL}/w185{poster_path}"
            try:
                resp = requests.get(poster_url, timeout=10)
                resp.raise_for_status()
                poster = Image.open(BytesIO(resp.content)).convert("RGB")
                poster.thumbnail((200, 280), Image.Resampling.LANCZOS)
                
                # Round corners
                mask = Image.new("L", poster.size, 0)
                mask_draw = ImageDraw.Draw(mask)
                mask_draw.rounded_rectangle((0, 0, poster.size[0], poster.size[1]), radius=10, fill=255)
                poster.putalpha(mask)
                
                card.paste(poster, (60, 720), poster)
            except Exception as e:
                log_message(f"Could not download poster: {str(e)}", level="WARNING")
        
        # Movie info on right of poster
        title_font = load_font(BEBAS, 56)
        title = movie.get("title", "Unknown")
        draw.text((280, 720), title, font=title_font, fill=COLOR_WHITE)
        
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        lang = movie.get("original_language", "en")
        lang_label = get_language_label(lang)
        
        info_font = load_font(OPENSANS, 26)
        draw.text((280, 800), f"{year} • {lang_label}", font=info_font, fill=COLOR_GRAY)
        
        rating = round(movie.get("vote_average", 0), 1)
        rating_font = load_font(BEBAS, 64)
        draw.text((280, 850), f"⭐ {rating}", font=rating_font, fill=COLOR_GOLD_TEXT)
        
        # Streaming
        india_platforms = streaming_platforms.get("IN", [])
        platform_text = ", ".join(india_platforms[:2]) if india_platforms else "Not streaming"
        platform_font = load_font(OPENSANS, 22)
        draw.text((280, 940), platform_text, font=platform_font, fill=mood_color)
        
        # Bottom bar
        draw.rectangle([(0, 1280), (CARD_WIDTH, 1350)], fill=mood_color)
        draw.text((40, 1303), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        if india_platforms:
            draw.text((CARD_WIDTH - 400, 1303), f"🇮🇳 {india_platforms[0]}", font=load_font(OPENSANS, 22), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_mood_pick.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Mood pick card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering mood pick card: {str(e)}", level="ERROR")
        raise


def render_trivia(movie, content):
    """Render trivia card: fun behind-the-scenes fact."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Trivia badge
        badge_font = load_font(BEBAS, 30)
        draw.rectangle([(40, 60), (280, 105)], fill=COLOR_PURPLE)
        draw.text((50, 68), "DID YOU KNOW", font=badge_font, fill=COLOR_WHITE)
        
        # Large ? watermark
        watermark_font = load_font(BEBAS, 400)
        watermark_bbox = draw.textbbox((0, 0), "?", font=watermark_font)
        wx = (CARD_WIDTH - (watermark_bbox[2] - watermark_bbox[0])) // 2
        draw.text((wx, 300), "?", font=watermark_font, fill=COLOR_PURPLE, alpha=20)
        
        # Fact text
        fact_font = load_font(OPENSANS_BOLD, 44)
        fact = content.get("fact", "No fact")
        
        # Draw fact with numbers highlighted
        lines = wrap_text(draw, fact, fact_font, 900)
        y = 500
        for line in lines:
            # Check for numbers and highlight them
            words = line.split()
            x = 90
            for word in words:
                if re.search(r"\d", word):
                    draw.text((x, y), word, font=fact_font, fill=COLOR_PURPLE)
                else:
                    draw.text((x, y), word, font=fact_font, fill=COLOR_WHITE)
                
                bbox = draw.textbbox((x, y), word + " ", font=fact_font)
                x += bbox[2] - bbox[0]
            
            bbox = draw.textbbox((90, y), line, font=fact_font)
            y += bbox[3] - bbox[1] + 10
        
        # Film attribution
        title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        attribution = f"— {title} · {year}"
        attribution_font = load_font(OPENSANS, 28)
        bbox = draw.textbbox((0, 0), attribution, font=attribution_font)
        x = (CARD_WIDTH - (bbox[2] - bbox[0])) // 2
        draw.text((x, 1100), attribution, font=attribution_font, fill=COLOR_PURPLE)
        
        # Bottom bar
        draw.rectangle([(0, 1280), (CARD_WIDTH, 1350)], fill=COLOR_PURPLE)
        label_font = load_font(BEBAS, 34)
        draw.text((40, 1295), "FILM TRIVIA", font=label_font, fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 500, 1295), "share with a film buff 🎬", font=load_font(OPENSANS, 22), fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 200, 1303), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_trivia.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Trivia card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering trivia card: {str(e)}", level="ERROR")
        raise


def render_list(movie, content):
    """Render list card: 5 similar films."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Header
        draw.rectangle([(0, 0), (CARD_WIDTH, 280)], fill=COLOR_BG_CARD)
        
        header_label_font = load_font(OPENSANS, 24)
        draw.text((60, 60), "THIS WEEK ON CINEDROP", font=header_label_font, fill=COLOR_SAFFRON)
        
        title_font = load_font(BEBAS, 72)
        list_title = content.get("list_title", "5 Films Like This")
        y = 100
        lines = wrap_text(draw, list_title, title_font, 960)
        for line in lines:
            draw.text((60, y), line, font=title_font, fill=COLOR_WHITE)
            bbox = draw.textbbox((60, y), line, font=title_font)
            y += bbox[3] - bbox[1] + 5
        
        # List items
        films = content.get("films", [])
        item_height = 170
        y = 280
        
        for idx, film in enumerate(films[:5]):
            # Alternate background
            if idx % 2 == 0:
                draw.rectangle([(0, y), (CARD_WIDTH, y + item_height)], fill=COLOR_BG_DARK)
            else:
                draw.rectangle([(0, y), (CARD_WIDTH, y + item_height)], fill=COLOR_BG_CARD)
            
            # Number
            num_font = load_font(BEBAS, 56)
            draw.text((60, y + 30), str(idx + 1), font=num_font, fill=COLOR_SAFFRON)
            
            # Film title & language
            film_font = load_font(OPENSANS_BOLD, 36)
            draw.text((150, y + 30), film.get("title", "Unknown"), font=film_font, fill=COLOR_WHITE)
            
            info_font = load_font(OPENSANS, 24)
            lang = film.get("language", "en")
            year = film.get("year", "")
            draw.text((150, y + 75), f"{lang} · {year}", font=info_font, fill=COLOR_GRAY)
            
            # Rating
            rating_font = load_font(BEBAS, 40)
            rating = film.get("rating", 0)
            draw.text((CARD_WIDTH - 150, y + 40), f"{rating}", font=rating_font, fill=COLOR_GOLD_TEXT)
            
            # Divider
            if idx < 4:
                draw.line([(60, y + item_height - 1), (CARD_WIDTH - 60, y + item_height - 1)], fill=COLOR_DARK_GRAY, width=1)
            
            y += item_height
        
        # Bottom bar
        draw.rectangle([(0, 1280), (CARD_WIDTH, 1350)], fill=COLOR_SAFFRON)
        label_font = load_font(BEBAS, 34)
        draw.text((40, 1295), "SWIPE FOR MORE →", font=label_font, fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 280, 1303), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_list.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"List card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering list card: {str(e)}", level="ERROR")
        raise


def render_rating(movie, content):
    """Render rating card: 4 metric scores + verdict."""
    try:
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG_DARK)
        draw = ImageDraw.Draw(card)
        
        # Header
        header_font = load_font(OPENSANS, 28)
        draw.text((60, 60), "CINEDROP RATES", font=header_font, fill=COLOR_GRAY)
        
        title_font = load_font(BEBAS, 96)
        title = movie.get("title", "Unknown")
        draw.text((60, 100), title, font=title_font, fill=COLOR_WHITE)
        
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        lang = movie.get("original_language", "en")
        lang_label = get_language_label(lang)
        
        info_font = load_font(OPENSANS, 30)
        draw.text((60, 210), f"{year} • {lang_label}", font=info_font, fill=COLOR_GRAY)
        
        # Metrics
        metrics = [
            ("Story", content.get("story", 8.0)),
            ("Performances", content.get("performances", 8.5)),
            ("Rewatch value", content.get("rewatch", 8.0)),
            ("Emotional hit", content.get("emotional_hit", 8.5)),
        ]
        
        y = 280
        label_font = load_font(OPENSANS_BOLD, 32)
        score_font = load_font(BEBAS, 56)
        bar_height = 16
        
        for label, score in metrics:
            # Label
            draw.text((60, y + 40), label, font=label_font, fill=COLOR_GRAY)
            
            # Score
            draw.text((900, y + 40), str(score), font=score_font, fill=COLOR_SAFFRON)
            
            # Bar background
            bar_y = y + 90
            draw.rounded_rectangle([(60, bar_y), (850, bar_y + bar_height)], radius=8, fill=COLOR_DARK_GRAY)
            
            # Bar fill
            bar_width = int((score / 10.0) * 790)
            draw.rounded_rectangle([(60, bar_y), (60 + bar_width, bar_y + bar_height)], radius=8, fill=COLOR_SAFFRON)
            
            # Divider
            if metrics.index((label, score)) < len(metrics) - 1:
                draw.line([(60, y + 130), (900, y + 130)], fill=COLOR_DARK_GRAY, width=1)
            
            y += 160
        
        # Verdict bar
        verdict_y = 980
        draw.rectangle([(0, verdict_y), (CARD_WIDTH, verdict_y + 120)], fill=COLOR_SAFFRON)
        
        verdict_label_font = load_font(BEBAS, 36)
        verdict_font = load_font(BEBAS, 48)
        verdict_text = content.get("verdict", "MUST WATCH")
        verdict_line = content.get("verdict_line", "A solid pick")
        
        draw.text((60, verdict_y + 15), "VERDICT:", font=verdict_label_font, fill=COLOR_WHITE)
        draw.text((280, verdict_y + 15), verdict_text, font=verdict_font, fill=COLOR_WHITE)
        draw.text((CARD_WIDTH - 280, verdict_y + 35), PAGE_HANDLE, font=load_font(OPENSANS, 24), fill=COLOR_WHITE)
        
        # Save card
        CARDS_DIR.mkdir(exist_ok=True)
        card_path = CARDS_DIR / f"card_{movie['id']}_rating.jpg"
        card.save(str(card_path), "JPEG", quality=CARD_QUALITY)
        log_message(f"Rating card rendered: {card_path}")
        return str(card_path)
        
    except Exception as e:
        log_message(f"Error rendering rating card: {str(e)}", level="ERROR")
        raise


def create_story_card(feed_card_path, movie, post_type):
    """
    Create a Story-optimized version of the feed card.
    Stories are 1080x1920px (9:16).
    Places the feed card centered on a blurred dark background.
    Adds a top label and bottom swipe-up prompt.
    Returns path to story card image.
    """
    try:
        log_message("Creating Story card...")

        STORY_WIDTH = 1080
        STORY_HEIGHT = 1920

        # Load the already-generated feed card
        feed_card = Image.open(feed_card_path).convert("RGBA")

        # Create story canvas — dark background
        story = Image.new("RGB", (STORY_WIDTH, STORY_HEIGHT), COLOR_BG_DARK)

        # Create blurred background by scaling feed card up and blurring heavily
        bg = feed_card.copy().convert("RGB")
        bg = bg.resize((STORY_WIDTH, STORY_HEIGHT), Image.Resampling.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=40))
        # Darken the blurred background
        darkener = Image.new("RGB", (STORY_WIDTH, STORY_HEIGHT), (0, 0, 0))
        bg = Image.blend(bg, darkener, alpha=0.6)
        story.paste(bg, (0, 0))

        # Place feed card centered vertically with padding
        feed_card_rgb = feed_card.convert("RGB")
        # Scale feed card to fit story width with side padding
        target_width = int(STORY_WIDTH * 0.88)
        scale_factor = target_width / feed_card_rgb.width
        target_height = int(feed_card_rgb.height * scale_factor)
        feed_resized = feed_card_rgb.resize(
            (target_width, target_height),
            Image.Resampling.LANCZOS
        )
        # Center horizontally, position in middle of story
        x_offset = (STORY_WIDTH - target_width) // 2
        y_offset = (STORY_HEIGHT - target_height) // 2
        story.paste(feed_resized, (x_offset, y_offset))

        draw = ImageDraw.Draw(story)

        # Load fonts
        font_large = load_font(BEBAS, 52)
        font_medium = load_font(OPENSANS_BOLD, 32)
        font_small = load_font(OPENSANS, 26)

        # Top label — post type context
        type_labels = {
            "recommendation": "TODAY'S PICK 🎬",
            "hot_take": "HOT TAKE 🔥",
            "dialogue": "ICONIC LINE 💬",
            "mood_pick": "WATCH THIS IF... 🌙",
            "trivia": "DID YOU KNOW 🎭",
            "list": "WATCH LIST 📋",
            "rating": "CINEDROP RATES ⭐",
        }
        top_label = type_labels.get(post_type, "TODAY'S PICK 🎬")

        # Top bar — dark pill behind text
        top_text_y = 80
        draw.rounded_rectangle(
            [(60, top_text_y - 10), (STORY_WIDTH - 60, top_text_y + 55)],
            radius=30,
            fill=(0, 0, 0, 160)
        )
        # Center top label text
        top_bbox = draw.textbbox((0, 0), top_label, font=font_large)
        top_w = top_bbox[2] - top_bbox[0]
        draw.text(
            ((STORY_WIDTH - top_w) // 2, top_text_y),
            top_label,
            font=font_large,
            fill=COLOR_SAFFRON
        )

        # Bottom swipe prompt area
        bottom_y = STORY_HEIGHT - 200

        # Dark pill background for bottom area
        draw.rounded_rectangle(
            [(60, bottom_y - 20), (STORY_WIDTH - 60, STORY_HEIGHT - 60)],
            radius=30,
            fill=(0, 0, 0, 180)
        )

        # Main CTA
        cta_texts = {
            "recommendation": "check the post for full details",
            "hot_take": "drop your take in the post 👊",
            "dialogue": "share this with someone 🤙",
            "mood_pick": "tag someone who needs this 🌙",
            "trivia": "bet you didn't know this 👀",
            "list": "save the post for later 🔖",
            "rating": "agree with our rating? 🎯",
        }
        cta = cta_texts.get(post_type, "check the post 👆")

        cta_bbox = draw.textbbox((0, 0), cta, font=font_medium)
        cta_w = cta_bbox[2] - cta_bbox[0]
        draw.text(
            ((STORY_WIDTH - cta_w) // 2, bottom_y),
            cta,
            font=font_medium,
            fill=COLOR_WHITE
        )

        # Handle
        handle_bbox = draw.textbbox((0, 0), "@cinedrop", font=font_small)
        handle_w = handle_bbox[2] - handle_bbox[0]
        draw.text(
            ((STORY_WIDTH - handle_w) // 2, bottom_y + 55),
            "@cinedrop",
            font=font_small,
            fill=COLOR_GRAY
        )

        # Save story card
        CARDS_DIR.mkdir(exist_ok=True)
        story_path = CARDS_DIR / f"story_{movie['id']}_{post_type}.jpg"
        story.save(str(story_path), "JPEG", quality=95)
        log_message(f"Story card saved: {story_path}")
        return str(story_path)

    except Exception as e:
        log_message(f"Story card creation failed: {str(e)}", level="WARNING")
        return None


# ============================================================================
# STEP 5: CARD DISPATCHER & CAPTION BUILDER
# ============================================================================

def create_card(movie, content, streaming_platforms, post_type):
    """Dispatch to the correct card rendering function based on post type."""
    dispatch = {
        "recommendation": lambda: render_recommendation(movie, content, streaming_platforms),
        "hot_take": lambda: render_hot_take(movie, content),
        "dialogue": lambda: render_dialogue(movie, content),
        "mood_pick": lambda: render_mood_pick(movie, content, streaming_platforms),
        "trivia": lambda: render_trivia(movie, content),
        "list": lambda: render_list(movie, content),
        "rating": lambda: render_rating(movie, content),
    }
    
    fn = dispatch.get(post_type, lambda: render_recommendation(movie, content, streaming_platforms))
    return fn()


def build_caption(content, post_type):
    """Build Instagram caption from content and post type."""
    caption = content.get("caption", "")
    hashtags = content.get("hashtags", "")
    return f"{caption}\n\n{hashtags}"

def upload_card_to_github(card_path):
    """Commit and push the card image to GitHub for public hosting."""
    try:
        repo = os.getenv("GITHUB_REPOSITORY")
        if not repo:
            try:
                import subprocess
                remote = subprocess.check_output(
                    ["git", "config", "--get", "remote.origin.url"],
                    text=True,
                ).strip()
                remote = remote.replace("git@github.com:", "").replace(
                    "https://github.com/", ""
                )
                repo = remote[:-4] if remote.endswith(".git") else remote
            except Exception:
                repo = None

        if not repo:
            log_message("Could not determine GitHub repository - cannot host image", level="ERROR")
            return None

        branch = os.getenv("GITHUB_REF_NAME", "main")

        log_message(f"Pushing card image to GitHub ({repo}@{branch}) for public hosting...")

        os.system(f'git add "{card_path}"')
        os.system('git commit -m "Auto: Add daily movie card image" || echo "nothing to commit"')
        push_result = os.system("git push")
        if push_result != 0:
            log_message("git push for card image returned non-zero status", level="WARNING")

        public_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{card_path}".replace("\\", "/")
        log_message(f"Card image hosted at: {public_url}")
        return public_url

    except Exception as e:
        log_message(f"Error hosting card image on GitHub: {str(e)}", level="ERROR")
        return None


def publish_to_instagram(image_url, caption):
    """Publish image and caption to Instagram using the Instagram Graph API."""
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not found in environment variables")

    try:
        log_message("Publishing to Instagram...")

        container_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
        
        container_payload = {
            "image_url": image_url,
            "caption": caption,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        container_response = requests.post(container_url, data=container_payload, timeout=15)
        container_response.raise_for_status()
        container_data = container_response.json()

        if not container_data.get("id"):
            raise ValueError(f"Failed to create media container: {container_data}")

        media_container_id = container_data["id"]
        log_message(f"Media container created: {media_container_id}")

        log_message("Waiting for media to be processed by Instagram...")
        time.sleep(5)

        publish_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        publish_payload = {
            "creation_id": media_container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        publish_response = requests.post(publish_url, data=publish_payload, timeout=15)
        publish_response.raise_for_status()
        publish_data = publish_response.json()

        post_id = publish_data.get("id")
        if not post_id:
            raise ValueError(f"Failed to publish media: {publish_data}")

        log_message(f"Post published successfully! Instagram Post ID: {post_id}")
        return post_id

    except requests.RequestException as e:
        log_message(f"Instagram Graph API error: {str(e)}", level="ERROR")
        resp = getattr(e, "response", None)
        if resp is not None:
            log_message(f"Instagram API response: {resp.text}", level="ERROR")
        raise


def publish_to_story(image_url):
    """
    Publish the same card image as an Instagram Story immediately after the feed post.
    Instagram Stories use a separate media container flow with media_type=STORIES.
    Returns story post ID or None if it fails — story failure never blocks the main post.
    """
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        log_message("Story skipped — missing credentials", level="WARNING")
        return None

    try:
        log_message("Publishing to Instagram Story...")

        # Step 1: Create story media container
        container_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
        container_payload = {
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        container_resp = requests.post(
            container_url,
            data=container_payload,
            timeout=15
        )
        container_resp.raise_for_status()
        container_data = container_resp.json()

        if not container_data.get("id"):
            log_message(f"Story container creation failed: {container_data}", level="WARNING")
            return None

        story_container_id = container_data["id"]
        log_message(f"Story container created: {story_container_id}")

        # Wait for Instagram to process
        time.sleep(5)

        # Step 2: Publish story container
        publish_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        publish_payload = {
            "creation_id": story_container_id,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }

        publish_resp = requests.post(
            publish_url,
            data=publish_payload,
            timeout=15
        )
        publish_resp.raise_for_status()
        publish_data = publish_resp.json()

        story_id = publish_data.get("id")
        if story_id:
            log_message(f"Story published successfully: {story_id}")
            return story_id
        else:
            log_message(f"Story publish returned no ID: {publish_data}", level="WARNING")
            return None

    except requests.RequestException as e:
        resp = getattr(e, "response", None)
        if resp is not None:
            log_message(f"Story API error: {resp.text}", level="WARNING")
        log_message(f"Story publishing failed: {str(e)} — main post unaffected", level="WARNING")
        return None

    except Exception as e:
        log_message(f"Unexpected story error: {str(e)} — main post unaffected", level="WARNING")
        return None


# ============================================================================
# STEP 7: SAVE HISTORY
# ============================================================================

def save_history(movie, card_path=None):
    """
    CHANGE 10: Append posted movie with era and language info to history.
    """
    global _HISTORY_FILE_SHA
    try:
        movie_id = movie["id"]
        movie_title = movie.get("title", "Unknown")
        log_message(f"Saving '{movie_title}' (ID: {movie_id}) to history...")

        history = load_posted_movies()
        if movie_id not in get_posted_ids(history):
            release_date = movie.get("release_date", "")
            year = release_date[:4] if release_date else "N/A"
            language = movie.get("original_language", "en")
            
            # CHANGE 10: Extended history entry
            history.append({
                "id": movie_id,
                "title": movie_title,
                "rating": round(movie.get("vote_average", 0), 1),
                "language": language,
                "year": year,
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
            })

        content_str = json.dumps(history, indent=2, ensure_ascii=False)

        if not HISTORY_REPO_TOKEN:
            log_message("HISTORY_REPO_TOKEN/GH_TOKEN not set - saving history locally only.", level="WARNING")
            with open(POSTED_MOVIES_FILE, "w") as f:
                f.write(content_str)
            return

        url = f"{GITHUB_API_BASE_URL}/repos/{HISTORY_REPO}/contents/{HISTORY_FILE_PATH}"
        body = {
            "message": f"Add '{movie_title}' to posted history",
            "content": base64.b64encode(content_str.encode("utf-8")).decode("utf-8"),
            "branch": HISTORY_REPO_BRANCH,
        }
        if _HISTORY_FILE_SHA:
            body["sha"] = _HISTORY_FILE_SHA

        resp = requests.put(url, headers=_history_api_headers(), json=body, timeout=15)
        if resp.status_code in (200, 201):
            _HISTORY_FILE_SHA = resp.json().get("content", {}).get("sha")
            log_message(f"History updated in {HISTORY_REPO}. Total movies posted: {len(history)}")
        else:
            log_message(
                f"Failed to update history in {HISTORY_REPO}: {resp.status_code} {resp.text}",
                level="ERROR",
            )

    except Exception as e:
        log_message(f"Error saving history: {str(e)}", level="ERROR")
        raise


# ============================================================================
# MAIN EXECUTION
# ============================================================================

def main():
    """Main execution flow: fetch movie → generate content → create card → publish → save."""
    try:
        log_message("=" * 80)
        log_message("STARTING DAILY INSTAGRAM MOVIE POST BOT - MULTI-FORMAT EDITION")
        log_message("=" * 80)

        # Log IST time and validate post type
        log_ist_time()

        # Check Instagram token expiry
        check_token_age()

        movie = get_movie()
        if not movie:
            log_message("Could not find a suitable movie to post. Exiting.", level="WARNING")
            return

        movie_id = movie["id"]
        movie_title = movie.get("title", "Unknown")
        
        post_type = get_post_type()
        log_message(f"Today's post type: {post_type}")

        streaming_platforms = get_streaming_platforms(movie_id)
        
        content = generate_post_content(movie, streaming_platforms, post_type)
        content["hashtags"] = generate_hashtags(movie, post_type)
        
        card_path = create_card(movie, content, streaming_platforms, post_type)
        if not card_path:
            log_message("Could not generate card. Exiting.", level="ERROR")
            return

        public_image_url = upload_card_to_github(card_path)
        if not public_image_url:
            log_message("Could not host image publicly. Exiting.", level="ERROR")
            return

        log_message("Waiting for image to propagate on GitHub CDN...")
        time.sleep(10)

        caption = build_caption(content, post_type)
        post_id = publish_to_instagram(public_image_url, caption)

        # Save history immediately after main post succeeds
        save_history(movie, card_path=card_path)

        # --- STORY STRATEGY ---
        # Posting a Story immediately after a feed post does two things:
        # 1. Existing followers see the Story first — they tap through to the feed post
        #    which generates early engagement (likes, comments, saves) in the first hour
        # 2. Early engagement signals to Instagram's algorithm that the post is worth
        #    showing to non-followers — this is what drives reach beyond your current audience
        # The Story itself uses the same card but formatted for 9:16 with a CTA
        # pointing back to the feed post. No extra content needed. Zero extra API calls.

        story_id = None
        try:
            log_message("Starting Story flow...")

            # Create story-optimized card (1080x1920)
            story_card_path = create_story_card(card_path, movie, post_type)

            if story_card_path:
                # Upload story card to GitHub for public hosting
                story_public_url = upload_card_to_github(story_card_path)

                if story_public_url:
                    # Wait for CDN propagation
                    log_message("Waiting for story image CDN propagation...")
                    time.sleep(12)

                    # Publish story
                    story_id = publish_to_story(story_public_url)

                    if story_id:
                        log_message(f"Story published: {story_id}")
                    else:
                        log_message("Story publish returned no ID", level="WARNING")
                else:
                    log_message("Story card upload failed", level="WARNING")
            else:
                log_message("Story card creation failed", level="WARNING")

        except Exception as e:
            log_message(f"Story flow failed: {str(e)} — main post unaffected", level="WARNING")

        # Success summary
        log_message("=" * 80)
        log_message("SUCCESS SUMMARY")
        log_message("=" * 80)
        log_message(f"Movie        : {movie_title} ({movie.get('release_date', '')[:4]})")
        log_message(f"Post Type    : {post_type.upper()}")
        log_message(f"Cinema       : {movie.get('original_language', 'en').upper()}")
        log_message(f"Rating       : {movie.get('vote_average', 0)}/10")
        log_message(f"🇮🇳 India     : {', '.join(streaming_platforms['IN']) or 'Not streaming'}")
        log_message(f"🇺🇸 US        : {', '.join(streaming_platforms['US']) or 'Not streaming'}")
        log_message(f"Post ID      : {post_id}")
        log_message(f"Story ID     : {story_id if story_id else 'failed'}")
        log_message(f"Card         : {public_image_url}")
        log_message("=" * 80)

    except Exception as e:
        log_message("=" * 80, level="ERROR")
        log_message(f"FATAL ERROR: {str(e)}", level="ERROR")
        log_message("=" * 80, level="ERROR")
        raise


if __name__ == "__main__":
    main()
