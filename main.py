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
import shutil
import subprocess
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
ASSETS_DIR = Path("assets")   # optional bundled reel audio lives here

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
    8:   "Netflix",
    119: "Prime Video",
    9:   "Prime Video",   # legacy Amazon ID
    2100: "Prime Video",  # Prime Video with Ads
    35:  "Apple TV+",
    122: "JioHotstar",
    232: "Zee5",
    237: "SonyLIV",
    892: "JioCinema",
    190: "Mubi",
    532: "Aha",
    561: "Lionsgate Play",
    15:  "Hulu",
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
        # Instagram 2025+ deprioritises hashtag-stuffed posts. A tight, highly
        # relevant set of ~8 outperforms a 28-tag dump for reach and looks less spammy.
        all_tags = (
            trending[:2] +
            film_tags[:1] +
            cinema[:2] +
            genre_list[:2] +
            mood_list[:1] +
            type_list[:1]
        )

        # --- Deduplicate preserving priority order ---
        seen = set()
        final_tags = []
        for tag in all_tags:
            tag = tag.strip()
            if tag and tag not in seen:
                seen.add(tag)
                final_tags.append(tag)

        # Cap at 8 — focused and relevant beats broad and spammy
        final_tags = final_tags[:8]

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
            {"langs": "hi", "type": "Bollywood"},
            {"langs": "te", "type": "Tollywood"},
            {"langs": "ta", "type": "Kollywood"},
            {"langs": "ml", "type": "Mollywood"},
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
                        movie["_language"] = lang_group["langs"]
                    
                    all_movies.extend(movies)
                    log_message(f"  {era_label.capitalize()} {cinema_type}: Found {len(movies)} films")
                except Exception as e:
                    log_message(f"  {era_label.capitalize()} {cinema_type}: {str(e)}", level="WARNING")

        # Dedicated trending calls — heavier boost for Tollywood and Bollywood
        REGIONAL_LANGS = [("te","Tollywood",20),("hi","Bollywood",20),("ta","Kollywood",15),("ml","Mollywood",10)]
        for lang, cinema, limit in REGIONAL_LANGS:
            try:
                r = requests.get(
                    f"{TMDB_BASE_URL}/discover/movie",
                    params={
                        "api_key": TMDB_API_KEY, "with_original_language": lang,
                        "vote_average.gte": 7.0, "vote_count.gte": 50,
                        "sort_by": "popularity.desc", "language": "en-US",
                        "primary_release_date.gte": "2010-01-01", "page": 1,
                    },
                    timeout=10,
                )
                if r.status_code == 200:
                    for m in r.json().get("results", [])[:limit]:
                        m["_era"] = "recent"
                        m["_cinema_type"] = cinema
                        m["_language"] = lang
                        all_movies.append(m)
                    log_message(f"  {cinema} boost: +{len(r.json().get('results',[])[:limit])} films")
            except Exception as e:
                log_message(f"{cinema} boost failed: {e}", level="WARNING")

        # Add India daily trending movies to boost relevance
        try:
            trend_url = f"{TMDB_BASE_URL}/trending/movie/day"
            trend_resp = requests.get(
                trend_url,
                params={"api_key": TMDB_API_KEY, "region": "IN"},
                timeout=10,
            )
            if trend_resp.status_code == 200:
                trending_movies = trend_resp.json().get("results", [])[:12]
                for m in trending_movies:
                    lang = m.get("original_language", "en")
                    cinema_map = {"hi":"Bollywood","ta":"Kollywood","te":"Tollywood","ml":"Mollywood"}
                    m["_era"] = "recent"
                    m["_cinema_type"] = cinema_map.get(lang, "Hollywood")
                    m["_language"] = lang
                all_movies.extend(trending_movies)
                log_message(f"  India trending: added {len(trending_movies)} movies to pool")
        except Exception as e:
            log_message(f"India trending fetch failed: {e}", level="WARNING")

        # Source: TMDB /movie/popular — current crowd favourites per language
        for lang, cinema in [("te","Tollywood"),("hi","Bollywood"),("ta","Kollywood"),("ml","Mollywood"),("en","Hollywood")]:
            try:
                r = requests.get(
                    f"{TMDB_BASE_URL}/movie/popular",
                    params={"api_key": TMDB_API_KEY, "language": "en-US",
                            "region": "IN" if lang != "en" else "US", "page": 1},
                    timeout=10,
                )
                if r.status_code == 200:
                    added = 0
                    for m in r.json().get("results", []):
                        if m.get("original_language") == lang:
                            m["_era"] = "recent"
                            m["_cinema_type"] = cinema
                            m["_language"] = lang
                            all_movies.append(m)
                            added += 1
                    log_message(f"  Popular ({cinema}): +{added}")
            except Exception as e:
                log_message(f"Popular ({cinema}) failed: {e}", level="WARNING")

        # Source: TMDB /movie/top_rated — all-time greats (feeds the classic 30%)
        for lang, cinema in [("te","Tollywood"),("hi","Bollywood"),("ta","Kollywood"),("ml","Mollywood"),("en","Hollywood")]:
            try:
                r = requests.get(
                    f"{TMDB_BASE_URL}/movie/top_rated",
                    params={"api_key": TMDB_API_KEY, "language": "en-US",
                            "region": "IN" if lang != "en" else "US", "page": 1},
                    timeout=10,
                )
                if r.status_code == 200:
                    added = 0
                    for m in r.json().get("results", []):
                        if m.get("original_language") == lang:
                            yr = int(m.get("release_date", "0")[:4] or 0)
                            m["_era"] = "classic" if yr < 1995 else ("modern" if yr < 2016 else "recent")
                            m["_cinema_type"] = cinema
                            m["_language"] = lang
                            all_movies.append(m)
                            added += 1
                    log_message(f"  Top-rated ({cinema}): +{added}")
            except Exception as e:
                log_message(f"Top-rated ({cinema}) failed: {e}", level="WARNING")

        # Source: Groq LLM → TMDB search (AI-curated suggestions by genre + era)
        if GROQ_API_KEY:
            try:
                genre_name = today_genre["name"]
                current_year = datetime.now().year
                groq_prompt = (
                    f"List 10 highly acclaimed {genre_name} films from Indian cinema "
                    f"(Telugu, Hindi, Tamil, Malayalam, Kannada) released between "
                    f"{current_year - 3} and {current_year}. "
                    f"Also add 3 all-time Indian classics in this genre (pre-2000). "
                    f"Return ONLY a JSON array of English movie titles, nothing else. "
                    f'Example: ["Movie One","Movie Two"]'
                )
                groq_resp = requests.post(
                    "https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
                    json={
                        "model": "llama-3.3-70b-versatile",
                        "messages": [{"role": "user", "content": groq_prompt}],
                        "temperature": 0.7,
                        "max_tokens": 300,
                    },
                    timeout=15,
                )
                if groq_resp.status_code == 200:
                    raw = groq_resp.json()["choices"][0]["message"]["content"].strip()
                    json_match = re.search(r'\[.*?\]', raw, re.DOTALL)
                    if json_match:
                        suggested_titles = json.loads(json_match.group())
                        log_message(f"  Groq suggested {len(suggested_titles)} {genre_name} titles")
                        _cmap = {"hi":"Bollywood","ta":"Kollywood","te":"Tollywood","ml":"Mollywood","kn":"Tollywood"}
                        for title in suggested_titles[:13]:
                            try:
                                sr = requests.get(
                                    f"{TMDB_BASE_URL}/search/movie",
                                    params={"api_key": TMDB_API_KEY, "query": title,
                                            "language": "en-US", "page": 1},
                                    timeout=8,
                                )
                                if sr.status_code == 200:
                                    hits = sr.json().get("results", [])
                                    if hits:
                                        m = hits[0]
                                        lang = m.get("original_language", "en")
                                        yr = int(m.get("release_date", "0")[:4] or 0)
                                        m["_era"] = "classic" if yr < 1995 else ("modern" if yr < 2016 else "recent")
                                        m["_cinema_type"] = _cmap.get(lang, "Hollywood")
                                        m["_language"] = lang
                                        all_movies.append(m)
                            except Exception:
                                pass
            except Exception as e:
                log_message(f"Groq movie suggestions failed: {e}", level="WARNING")

        # Deduplicate by movie ID
        seen_ids = set()
        unique_movies = []
        for m in all_movies:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                unique_movies.append(m)

        indian_count = sum(1 for m in unique_movies if m.get("_cinema_type") not in ("Hollywood", None))
        hollywood_count = sum(1 for m in unique_movies if m.get("_cinema_type") == "Hollywood")
        log_message(f"Merged pool: {len(unique_movies)} unique films ({indian_count} Indian, {hollywood_count} Hollywood)")
        for cinema in ["Tollywood","Bollywood","Kollywood","Mollywood"]:
            n = sum(1 for m in unique_movies if m.get("_cinema_type") == cinema)
            if n: log_message(f"  {cinema}: {n}")

        if not unique_movies:
            log_message(f"No movies found for {today_genre['name']}", level="WARNING")
            return None

        # Shuffle for variety
        random.shuffle(unique_movies)

        # Era-biased weighted picker: ~70% recent (last 3 years), ~30% older/classic
        recent_cutoff = datetime.now().year - 3
        def _pick_era_biased(pool):
            if not pool:
                return None
            weights = []
            for m in pool:
                try:
                    yr = int(m.get("release_date", "0")[:4])
                except (ValueError, TypeError):
                    yr = 0
                weights.append(7 if yr >= recent_cutoff else 3)
            return random.choices(pool, weights=weights, k=1)[0]

        # Split pools — Tollywood+Bollywood are priority, other South secondary
        PRIORITY_TYPES = {"Tollywood", "Bollywood"}
        OTHER_SOUTH = {"Kollywood", "Mollywood"}
        unposted_priority = [m for m in unique_movies if m["id"] not in posted_ids and m.get("_cinema_type") in PRIORITY_TYPES]
        unposted_other_south = [m for m in unique_movies if m["id"] not in posted_ids and m.get("_cinema_type") in OTHER_SOUTH]
        unposted_hollywood = [m for m in unique_movies if m["id"] not in posted_ids and m.get("_cinema_type") == "Hollywood"]

        log_message(f"Unposted pool: {len(unposted_priority)} Tollywood+Bollywood, {len(unposted_other_south)} other South, {len(unposted_hollywood)} Hollywood")

        # 70% Tollywood/Bollywood, 15% other South, 15% Hollywood (era bias applied within each pool)
        roll = random.random()
        if unposted_priority and roll < 0.70:
            movie = _pick_era_biased(unposted_priority)
        elif unposted_other_south and roll < 0.85:
            movie = _pick_era_biased(unposted_other_south)
        elif unposted_hollywood:
            movie = _pick_era_biased(unposted_hollywood)
        elif unposted_priority:
            movie = _pick_era_biased(unposted_priority)
        elif unposted_other_south:
            movie = _pick_era_biased(unposted_other_south)
        else:
            movie = None

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
        
        # Fetch full movie details to get backdrop_path
        try:
            detail_url = f"{TMDB_BASE_URL}/movie/{movie['id']}"
            detail_resp = requests.get(detail_url, params={"api_key": TMDB_API_KEY}, timeout=10)
            if detail_resp.status_code == 200:
                detail = detail_resp.json()
                movie["backdrop_path"] = detail.get("backdrop_path")
                movie["genres"] = detail.get("genres", movie.get("genres", []))
                log_message(f"Backdrop available: {bool(movie.get('backdrop_path'))}")
        except Exception as e:
            log_message(f"Could not fetch movie details: {e}", level="WARNING")
            movie["backdrop_path"] = None

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
                
                seen = set()
                for provider in providers:
                    name = PROVIDER_MAPPING.get(provider["provider_id"], "")
                    # skip unknown IDs whose raw name contains "ads" or is empty
                    if not name:
                        raw = provider.get("provider_name", "")
                        if "with Ads" in raw or "Ads" in raw:
                            name = raw.split(" with ")[0].strip()
                        else:
                            name = raw.strip()
                    if name and name not in seen:
                        seen.add(name)
                        streaming_platforms[region_code].append(name)

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
No hashtags. No emojis overload.

CAPTION FORMAT — aim for 100-200 words:
- Hook: 5-8 words that stop the scroll (no period, just a line break)
- Body: 3-5 punchy sentences. Real talk. No fluff. No explaining.
- Streaming: mention where to watch in India naturally in the body
- Close: ONE specific question that starts a fight or hits deep
"""
            max_tokens = 600

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

CAPTION FORMAT — aim for 100-200 words:
- Hook: 5-8 words that stop the scroll (no period, just a line break)
- Body: 3-5 punchy sentences. Aggressive. Pick a hard side.
- Close: ONE line that will trigger replies — either agreement or anger
"""
            max_tokens = 600

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

CAPTION FORMAT — aim for 80-150 words:
- Lead with the quote (in original language/script)
- 2-3 sentences reacting to it like a human, not a critic
- Close: ONE question like "who else remembers this scene?"
"""
            max_tokens = 600

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

CAPTION FORMAT — aim for 100-200 words:
- Hook: the specific mood/moment this film is for (5-8 words)
- Body: 3-5 sentences — describe the exact vibe and who needs it
- Streaming: mention where to find it in India
- Close: ONE question — "what mood are you in right now?"
"""
            max_tokens = 600

        elif post_type == "trivia":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Story: {overview}

Give me one genuine, verifiable fact about this film.
Something that makes people go "wait what".
Include a number — days, crores, years, something concrete.
Only share facts you are confident are real. If unsure, share a genuine insight about its cultural impact, production story, or box office instead — no fabrication.
One sentence follow up reacting to it like a human would.
Sound like you just found this out and had to tell someone.

CAPTION FORMAT — aim for 80-150 words:
- Hook: the wild fact itself as the first line
- Body: 2-3 sentences reacting to it, adding context
- Close: ONE question like "did you know this?" or "what other facts am I missing?"
"""
            max_tokens = 600

        elif post_type == "list":
            prompt = f"""
{title} ({year}) · {language_label} · {rating}/10
Genre: {genre_name}

Give me 5 films to watch if someone loved this one.
Mix Indian and Hollywood. Mix languages. Real films only.
For each film: title, year, and a 2-3 word reason that actually means something.
Then one punchy line at the top introducing the list — sound like you made this at 2am because someone asked.

Return as JSON only:
{{
  "intro": "one punchy intro line",
  "films": [
    {{"title": "...", "year": 0000, "reason": "2-3 words"}},
    {{"title": "...", "year": 0000, "reason": "2-3 words"}},
    {{"title": "...", "year": 0000, "reason": "2-3 words"}},
    {{"title": "...", "year": 0000, "reason": "2-3 words"}},
    {{"title": "...", "year": 0000, "reason": "2-3 words"}}
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
Verdict must be exactly one of: MUST WATCH / SOLID PICK / DECENT / SKIP
Then 1-2 sentences in Hinglish or Telugu — aggressive and honest. Make it sting.

Return as JSON only:
{{
  "story": 0.0,
  "performances": 0.0,
  "rewatch": 0.0,
  "emotional_hit": 0.0,
  "verdict": "MUST WATCH or SOLID PICK or DECENT or SKIP",
  "verdict_line": "1-2 aggressive honest sentences"
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

# Day-of-week card style dispatcher
CARD_STYLE_BY_DAY = {
    0: "b2",   # Monday    — dialogue poster
    1: "b3",   # Tuesday   — cinedrop score
    2: "d1",   # Wednesday — mood line
    3: "d2",   # Thursday  — quote + bar
    4: "b3",   # Friday    — cinedrop score
    5: "b2",   # Saturday  — dialogue poster
    6: "d1",   # Sunday    — mood line
}

def _load_fonts():
    """Load fonts with fallback to default."""
    paths = {
        "bold":    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "regular": "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    }
    try:
        return {
            "title":   ImageFont.truetype(paths["bold"],    110),  # was 72 — much bigger
            "large":   ImageFont.truetype(paths["bold"],     72),  # was 52
            "medium":  ImageFont.truetype(paths["bold"],     48),  # was 38
            "body":    ImageFont.truetype(paths["regular"],  34),  # was 30
            "small":   ImageFont.truetype(paths["regular"],  26),  # was 24
            "tiny":    ImageFont.truetype(paths["regular"],  22),  # unchanged
        }
    except:
        d = ImageFont.load_default()
        return {k: d for k in ["title","large","medium","body","small","tiny"]}

def _cover_resize(img, w, h):
    """Scale img to cover w×h preserving aspect ratio, then center-crop."""
    iw, ih = img.size
    scale = max(w / iw, h / ih)
    nw, nh = int(iw * scale), int(ih * scale)
    img = img.resize((nw, nh), Image.Resampling.LANCZOS)
    left = (nw - w) // 2
    top  = (nh - h) // 2
    return img.crop((left, top, left + w, top + h))

def _download_poster(poster_path, size="w780"):
    """Download poster image from TMDb."""
    url = f"https://image.tmdb.org/t/p/{size}{poster_path}"
    resp = requests.get(url, timeout=10)
    resp.raise_for_status()
    return Image.open(BytesIO(resp.content)).convert("RGB")

def _get_card_background(movie):
    """
    Randomly picks a background image source for the card.
    Weights: 50% poster, 30% TMDb backdrop, 20% solid mood color.
    Returns a PIL Image (RGB).
    """
    poster_path = movie.get("poster_path")
    backdrop_path = movie.get("backdrop_path")
    
    # Weighted choice
    choice = random.choices(
        ["poster", "backdrop", "mood_color"],
        weights=[50, 30, 20]
    )[0]
    
    # Fallback if source unavailable
    if choice == "backdrop" and not backdrop_path:
        choice = "poster"
    if choice == "poster" and not poster_path:
        choice = "mood_color"
    
    log_message(f"Card background source: {choice}")
    
    # SOURCE 1 — Standard poster (w780)
    if choice == "poster" and poster_path:
        try:
            url = f"https://image.tmdb.org/t/p/w780{poster_path}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            movie["_bg_source"] = "poster"
            return img
        except Exception as e:
            log_message(f"Poster fetch failed: {e} — falling back", level="WARNING")
    
    # SOURCE 2 — TMDb backdrop (cinematic wide still)
    if choice == "backdrop" and backdrop_path:
        try:
            url = f"https://image.tmdb.org/t/p/w1280{backdrop_path}"
            resp = requests.get(url, timeout=10)
            resp.raise_for_status()
            img = Image.open(BytesIO(resp.content)).convert("RGB")
            movie["_bg_source"] = "backdrop"
            return img
        except Exception as e:
            log_message(f"Backdrop fetch failed: {e} — falling back", level="WARNING")
    
    # SOURCE 3 — Mood color canvas (solid color gradient)
    genre_name = movie.get("_genre_name", "Drama")
    MOOD_COLORS = {
        "Thriller":        [(10,5,20),   (30,10,50)],
        "Horror":          [(5,5,5),     (20,5,5)],
        "Drama":           [(8,12,20),   (15,25,40)],
        "Romance":         [(20,5,15),   (40,10,30)],
        "Comedy":          [(15,12,5),   (30,25,10)],
        "Action":          [(15,5,5),    (35,10,5)],
        "Science Fiction": [(5,10,20),   (10,20,45)],
        "Family":          [(8,15,8),    (15,30,15)],
    }
    colors = MOOD_COLORS.get(genre_name, [(8,8,12), (15,15,25)])
    c1, c2 = colors[0], colors[1]
    
    # Create gradient canvas
    canvas = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), c1)
    for y in range(CARD_HEIGHT):
        factor = y / CARD_HEIGHT
        r = int(c1[0] + (c2[0]-c1[0]) * factor)
        g = int(c1[1] + (c2[1]-c1[1]) * factor)
        b = int(c1[2] + (c2[2]-c1[2]) * factor)
        ImageDraw.Draw(canvas).rectangle([(0,y),(CARD_WIDTH,y+1)], fill=(r,g,b))
    
    # Add subtle noise texture
    noise_draw = ImageDraw.Draw(canvas)
    for _ in range(800):
        nx = random.randint(0, CARD_WIDTH)
        ny = random.randint(0, CARD_HEIGHT)
        brightness = random.randint(15, 35)
        noise_draw.point((nx,ny), fill=(brightness,brightness,brightness))
    
    movie["_bg_source"] = "mood_color"
    log_message(f"Mood color canvas generated for genre: {genre_name}")
    return canvas

def _get_cinema_info(movie):
    """Get cinema label and color based on language."""
    lang = movie.get("original_language", "en")
    is_indian = lang in ["hi","ta","te","ml","kn"]
    label = {"hi":"Bollywood","ta":"Tamil","te":"Telugu","ml":"Malayalam","kn":"Kannada"}.get(lang, "Hollywood")
    color = (255,103,0) if is_indian else (108,63,194)
    return label, color, is_indian

def _get_era(movie):
    """Get era label, color, and year."""
    year = int(movie.get("release_date","2000")[:4] or 2000)
    if year < 1995: return "CLASSIC", (212,175,55), year
    if year < 2016: return "MODERN", (100,149,237), year
    return "NEW", (50,205,50), year

def _draw_pill(draw, x, y, text, font, bg_color, text_color=(255,255,255), padding=18):
    """Draw rounded pill with text."""
    bbox = draw.textbbox((0,0), text, font=font)
    w = bbox[2] - bbox[0] + padding * 2
    h = bbox[3] - bbox[1] + 14
    draw.rounded_rectangle([(x, y), (x+w, y+h)], radius=h//2, fill=bg_color)
    draw.text((x+padding, y+7), text, font=font, fill=text_color)
    return w, h

def _wrap_text(draw, text, font, max_width):
    """Wrap text to fit within max_width."""
    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        if draw.textbbox((0,0), test, font=font)[2] <= max_width:
            line = test
        else:
            if line: lines.append(line)
            line = word
    if line: lines.append(line)
    return lines

def _save_card(card, movie_id):
    """Save card to disk."""
    CARDS_DIR.mkdir(exist_ok=True)
    path = CARDS_DIR / f"card_{movie_id}.jpg"
    card.convert("RGB").save(str(path), "JPEG", quality=92)
    log_message(f"Card saved: {path}")
    return str(path)

def render_b2(movie, streaming_platforms):
    """Dialogue poster — full poster background with iconic dialogue overlay."""
    fonts = _load_fonts()
    poster_img = _get_card_background(movie)
    cinema_label, cinema_color, is_indian = _get_cinema_info(movie)
    era_text, era_color, year = _get_era(movie)
    rating = round(movie.get("vote_average", 0), 1)
    title  = movie.get("title", "Unknown")

    # Background — cover-fit so aspect ratio is preserved, then darkened
    bg = _cover_resize(poster_img.copy(), CARD_WIDTH, CARD_HEIGHT)
    dark = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (0,0,0))
    card = Image.blend(bg, dark, alpha=0.45)
    
    # Log background source
    bg_source = movie.get("_bg_source", "poster")
    log_message(f"Background used in render_b2: {bg_source}")
    
    # Decorative element if mood color canvas
    if movie.get("_bg_source") == "mood_color":
        try:
            emoji_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 380) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()
            card_temp = card.convert("RGBA")
            draw_temp = ImageDraw.Draw(card_temp)
            draw_temp.text((CARD_WIDTH//2 - 200, CARD_HEIGHT//2 - 250), "🎬", font=emoji_font, fill=(20,20,30,150))
            card = card_temp.convert("RGB")
        except:
            pass

    # Strong dark gradient bottom half for readability — 500px minimum
    grad = Image.new("RGBA", (CARD_WIDTH, 500), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(500):
        alpha = int((i / 500) * 245)
        gd.rectangle([(0, i), (CARD_WIDTH, i+1)], fill=(0, 0, 0, alpha))
    card_rgba = card.convert("RGBA")
    card_rgba.paste(grad, (0, CARD_HEIGHT - 500), grad)
    card = card_rgba.convert("RGB")

    draw = ImageDraw.Draw(card)

    # Top badges — era only
    _draw_pill(draw, 40, 50, era_text, fonts["tiny"],
               era_color, (0,0,0) if era_color == (212,175,55) else (255,255,255))

    # Dialogue quote — center of card
    dialogue = movie.get("_dialogue", "Ek baar jo tune commitment kar di... phir toh khud ki bhi nahi sunta.")
    quote_y = 480
    # Left accent bar
    draw.rectangle([(50, quote_y), (56, quote_y+180)], fill=cinema_color)
    # Large open quote
    draw.text((70, quote_y-20), "\u201c", font=fonts["title"], fill=(*cinema_color, 180))
    # Wrap and draw dialogue
    q_lines = _wrap_text(draw, dialogue, fonts["body"], 900)
    for i, line in enumerate(q_lines[:4]):
        draw.text((72, quote_y + 50 + i*44), line, font=fonts["body"],
                  fill=(220,220,220))

    # Movie info bottom — massive centered title and rating
    title_upper = title.upper()
    title_lines = _wrap_text(draw, title_upper, fonts["title"], CARD_WIDTH - 80)
    title_start_y = CARD_HEIGHT - 420
    
    for i, line in enumerate(title_lines[:2]):
        t_bbox = draw.textbbox((0, 0), line, font=fonts["title"])
        t_w = t_bbox[2] - t_bbox[0]
        t_x = (CARD_WIDTH - t_w) // 2  # centered
        # Shadow for readability
        draw.text((t_x + 3, title_start_y + i*90 + 3), line,
                  font=fonts["title"], fill=(0, 0, 0))
        # Main text
        draw.text((t_x, title_start_y + i*90), line,
                  font=fonts["title"], fill=(255, 255, 255))
    
    # Rating — very large, centered, gold
    rating_str = f"⭐ {rating} / 10"
    rating_y = title_start_y + len(title_lines[:2]) * 90 + 20
    
    r_bbox = draw.textbbox((0, 0), rating_str, font=fonts["large"])
    r_w = r_bbox[2] - r_bbox[0]
    r_x = (CARD_WIDTH - r_w) // 2  # centered
    
    # Shadow
    draw.text((r_x + 2, rating_y + 2), rating_str,
              font=fonts["large"], fill=(0, 0, 0))
    # Main
    draw.text((r_x, rating_y), rating_str,
              font=fonts["large"], fill=(255, 215, 0))

    # Streaming
    india_p = streaming_platforms.get("IN", [])[:2]
    stream_text = "  \u00b7  ".join(india_p) if india_p else "Rental only"
    draw.text((50, rating_y+80), f"Watch on: {stream_text}", font=fonts["tiny"], fill=(160,160,160))

    # Bottom bar
    bar_y = CARD_HEIGHT - 70
    draw.rectangle([(0, bar_y),(CARD_WIDTH, CARD_HEIGHT)], fill=cinema_color)
    draw.text((40, bar_y+18), "@cinedrop", font=fonts["small"], fill=(255,255,255,140))
    save_text = "save this"
    s_w = draw.textbbox((0,0), save_text, font=fonts["small"])[2]
    draw.text((CARD_WIDTH-s_w-40, bar_y+18), save_text, font=fonts["small"], fill=(255,255,255))

    return _save_card(card, movie["id"])

def render_b3(movie, streaming_platforms):
    """Cinedrop score — full poster background darkened. Cinedrop custom score pill top right."""
    fonts = _load_fonts()
    poster_img = _get_card_background(movie)
    cinema_label, cinema_color, is_indian = _get_cinema_info(movie)
    era_text, era_color, year = _get_era(movie)
    rating  = round(movie.get("vote_average", 0), 1)
    title   = movie.get("title", "Unknown")

    bg = _cover_resize(poster_img.copy(), CARD_WIDTH, CARD_HEIGHT)
    dark = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (0,0,0))
    card = Image.blend(bg, dark, alpha=0.4)
    
    # Log background source
    bg_source = movie.get("_bg_source", "poster")
    log_message(f"Background used in render_b3: {bg_source}")
    
    # Decorative element if mood color canvas
    if movie.get("_bg_source") == "mood_color":
        try:
            emoji_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 380) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()
            card_temp = card.convert("RGBA")
            draw_temp = ImageDraw.Draw(card_temp)
            draw_temp.text((CARD_WIDTH//2 - 200, CARD_HEIGHT//2 - 250), "🎬", font=emoji_font, fill=(20,20,30,150))
            card = card_temp.convert("RGB")
        except:
            pass

    # Bottom gradient — 500px minimum
    grad = Image.new("RGBA", (CARD_WIDTH, 500), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(500):
        alpha = int((i / 500) * 245)
        gd.rectangle([(0, i), (CARD_WIDTH, i+1)], fill=(0, 0, 0, alpha))
    card_rgba = card.convert("RGBA")
    card_rgba.paste(grad, (0, CARD_HEIGHT - 500), grad)
    card = card_rgba.convert("RGB")

    draw = ImageDraw.Draw(card)

    # Top left — era badge only
    _draw_pill(draw, 40, 50, era_text, fonts["tiny"],
               era_color, (0,0,0) if era_color==(212,175,55) else (255,255,255))

    # Top right — Cinedrop score box
    cd_score = min(10.0, round(rating * 1.05, 1))  # slightly adjusted score
    score_text = str(cd_score)
    box_x, box_y = CARD_WIDTH-160, 40
    draw.rounded_rectangle([(box_x, box_y),(box_x+120, box_y+110)],
                           radius=12, fill=(0,0,0,180))
    draw.rounded_rectangle([(box_x, box_y),(box_x+120, box_y+110)],
                           radius=12, outline=(255,215,0), width=2)
    # Score number
    s_bbox = draw.textbbox((0,0), score_text, font=fonts["title"])
    s_w = s_bbox[2]-s_bbox[0]
    draw.text((box_x+(120-s_w)//2, box_y+10), score_text,
              font=fonts["title"], fill=(255,215,0))
    # Label
    label = "CINEDROP"
    l_bbox = draw.textbbox((0,0), label, font=fonts["tiny"])
    l_w = l_bbox[2]-l_bbox[0]
    draw.text((box_x+(120-l_w)//2, box_y+78), label,
              font=fonts["tiny"], fill=(136,136,136))

    # Bottom content — massive centered title and rating
    title_upper = title.upper()
    title_lines = _wrap_text(draw, title_upper, fonts["title"], CARD_WIDTH - 80)
    title_start_y = CARD_HEIGHT - 420
    
    for i, line in enumerate(title_lines[:2]):
        t_bbox = draw.textbbox((0, 0), line, font=fonts["title"])
        t_w = t_bbox[2] - t_bbox[0]
        t_x = (CARD_WIDTH - t_w) // 2  # centered
        # Shadow for readability
        draw.text((t_x + 3, title_start_y + i*90 + 3), line,
                  font=fonts["title"], fill=(0, 0, 0))
        # Main text
        draw.text((t_x, title_start_y + i*90), line,
                  font=fonts["title"], fill=(255, 255, 255))
    
    # Rating — very large, centered, gold
    rating_str = f"⭐ {rating} / 10"
    rating_y = title_start_y + len(title_lines[:2]) * 90 + 20
    
    r_bbox = draw.textbbox((0, 0), rating_str, font=fonts["large"])
    r_w = r_bbox[2] - r_bbox[0]
    r_x = (CARD_WIDTH - r_w) // 2  # centered
    
    # Shadow
    draw.text((r_x + 2, rating_y + 2), rating_str,
              font=fonts["large"], fill=(0, 0, 0))
    # Main
    draw.text((r_x, rating_y), rating_str,
              font=fonts["large"], fill=(255, 215, 0))

    # Verdict pill
    verdict = movie.get("_verdict", "MUST WATCH")
    vdict_colors = {
        "MUST WATCH": (229,9,20),
        "SOLID PICK": (50,205,50),
        "DECENT":     (255,103,0),
        "SKIP":       (100,100,100),
    }
    v_color = vdict_colors.get(verdict, (229,9,20))
    _draw_pill(draw, 50, rating_y+80, verdict, fonts["small"], v_color)

    # Streaming
    india_p = streaming_platforms.get("IN", [])[:2]
    stream_text = "  \u00b7  ".join(india_p) if india_p else "Rental only"
    draw.text((50, rating_y+140), stream_text, font=fonts["tiny"], fill=(120,120,120))

    # Bottom bar
    bar_y = CARD_HEIGHT - 70
    draw.rectangle([(0,bar_y),(CARD_WIDTH,CARD_HEIGHT)], fill=(8,8,12))
    draw.text((40, bar_y+18), "@cinedrop", font=fonts["small"], fill=(60,60,60))
    save_text = "save this"
    s_w = draw.textbbox((0,0), save_text, font=fonts["small"])[2]
    draw.text((CARD_WIDTH-s_w-40, bar_y+18), save_text, font=fonts["small"], fill=(140,140,140))

    return _save_card(card, movie["id"])

def render_d1(movie, streaming_platforms):
    """Minimal mood line — full poster background, centered title, big rating, mood line."""
    fonts = _load_fonts()
    poster_img = _get_card_background(movie)
    cinema_label, cinema_color, is_indian = _get_cinema_info(movie)
    era_text, era_color, year = _get_era(movie)
    rating = round(movie.get("vote_average", 0), 1)
    title  = movie.get("title", "Unknown")
    mood   = movie.get("_mood", "watch alone, lights off")

    bg = _cover_resize(poster_img.copy(), CARD_WIDTH, CARD_HEIGHT)
    dark = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0))
    card = Image.blend(bg, dark, alpha=0.40)

    if movie.get("_bg_source") == "mood_color":
        try:
            emoji_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 380) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()
            card_temp = card.convert("RGBA")
            draw_temp = ImageDraw.Draw(card_temp)
            draw_temp.text((CARD_WIDTH//2 - 200, CARD_HEIGHT//2 - 250), "🎬", font=emoji_font, fill=(20,20,30,150))
            card = card_temp.convert("RGB")
        except:
            pass

    # Strong bottom gradient (600px) for text readability
    grad = Image.new("RGBA", (CARD_WIDTH, 600), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for i in range(600):
        alpha = int((i / 600) * 250)
        gd.rectangle([(0, i), (CARD_WIDTH, i+1)], fill=(0, 0, 0, alpha))
    card_rgba = card.convert("RGBA")
    card_rgba.paste(grad, (0, CARD_HEIGHT - 600), grad)
    card = card_rgba.convert("RGB")

    draw = ImageDraw.Draw(card)
    log_message(f"Background used in render_d1: {movie.get('_bg_source', 'poster')}")

    # Top badges — era only
    _draw_pill(draw, 40, 50, era_text, fonts["tiny"],
               era_color, (0,0,0) if era_color==(212,175,55) else (255,255,255))

    # Bottom zone — massive centered title
    title_upper = title.upper()
    title_lines = _wrap_text(draw, title_upper, fonts["title"], CARD_WIDTH - 80)
    title_start_y = CARD_HEIGHT - 520

    for i, line in enumerate(title_lines[:2]):
        t_bbox = draw.textbbox((0, 0), line, font=fonts["title"])
        t_w = t_bbox[2] - t_bbox[0]
        t_x = (CARD_WIDTH - t_w) // 2
        draw.text((t_x + 3, title_start_y + i*90 + 3), line, font=fonts["title"], fill=(0, 0, 0))
        draw.text((t_x, title_start_y + i*90), line, font=fonts["title"], fill=(255, 255, 255))

    # Rating — large, centered, gold
    rating_str = f"\u2b50 {rating} / 10"
    rating_y = title_start_y + len(title_lines[:2]) * 90 + 40
    r_bbox = draw.textbbox((0, 0), rating_str, font=fonts["large"])
    r_w = r_bbox[2] - r_bbox[0]
    r_x = (CARD_WIDTH - r_w) // 2
    draw.text((r_x + 2, rating_y + 2), rating_str, font=fonts["large"], fill=(0, 0, 0))
    draw.text((r_x, rating_y), rating_str, font=fonts["large"], fill=(255, 215, 0))

    # Mood line
    mood_y = rating_y + 90
    draw.text((54, mood_y), f"\u2022 {mood}", font=fonts["body"], fill=cinema_color)

    # Streaming
    india_p = streaming_platforms.get("IN", [])[:2]
    stream_text = "  \u00b7  ".join(india_p) if india_p else "Rental only"
    draw.text((54, mood_y + 50), stream_text, font=fonts["small"], fill=(160, 160, 160))

    # Bottom bar
    bar_y = CARD_HEIGHT - 70
    draw.rectangle([(0, bar_y), (CARD_WIDTH, CARD_HEIGHT)], fill=cinema_color)
    draw.text((40, bar_y + 18), "@cinedrop", font=fonts["small"], fill=(255, 255, 255, 140))
    save_text = "save this"
    s_w = draw.textbbox((0, 0), save_text, font=fonts["small"])[2]
    draw.text((CARD_WIDTH - s_w - 40, bar_y + 18), save_text, font=fonts["small"], fill=(255, 255, 255))

    return _save_card(card, movie["id"])

def render_d2(movie, streaming_platforms):
    """Quote card — blurred full poster background, featured dialogue quote."""
    fonts = _load_fonts()
    poster_img = _get_card_background(movie)
    cinema_label, cinema_color, is_indian = _get_cinema_info(movie)
    era_text, era_color, year = _get_era(movie)
    rating   = round(movie.get("vote_average", 0), 1)
    title    = movie.get("title", "Unknown")
    dialogue = movie.get("_dialogue", "Some stories stay with you forever.")

    bg = _cover_resize(poster_img.copy(), CARD_WIDTH, CARD_HEIGHT)
    bg = bg.filter(ImageFilter.GaussianBlur(radius=12))
    dark = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), (0, 0, 0))
    card = Image.blend(bg, dark, alpha=0.62)

    if movie.get("_bg_source") == "mood_color":
        try:
            emoji_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 300) if os.path.exists("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf") else ImageFont.load_default()
            card_temp = card.convert("RGBA")
            draw_temp = ImageDraw.Draw(card_temp)
            draw_temp.text((CARD_WIDTH//2 - 160, CARD_HEIGHT//2 - 200), "\U0001f4ac", font=emoji_font, fill=(25,25,35,120))
            card = card_temp.convert("RGB")
        except:
            pass

    log_message(f"Background used in render_d2: {movie.get('_bg_source', 'poster')} (blurred)")
    draw = ImageDraw.Draw(card)

    # Top: era badge only
    _draw_pill(draw, 54, 54, era_text, fonts["tiny"],
               era_color, (0,0,0) if era_color==(212,175,55) else (255,255,255))

    # Title and year below badges
    title_lines = _wrap_text(draw, title, fonts["large"], CARD_WIDTH - 108)
    for i, line in enumerate(title_lines[:2]):
        draw.text((54, 120 + i * 80), line, font=fonts["large"], fill=(240, 240, 240))
    year_y = 120 + min(len(title_lines[:2]), 2) * 80 + 10
    draw.text((54, year_y), str(year), font=fonts["body"], fill=(80, 80, 80))

    # Thin divider
    div1_y = year_y + 50
    draw.rectangle([(54, div1_y), (CARD_WIDTH - 54, div1_y + 1)], fill=(30, 30, 30))

    # Quote hero section — centered in the remaining space
    quote_y = div1_y + 120
    draw.rectangle([(54, quote_y), (62, quote_y + 330)], fill=cinema_color)
    draw.text((76, quote_y - 30), "\u201c", font=fonts["title"], fill=cinema_color)
    q_lines = _wrap_text(draw, dialogue, fonts["medium"], CARD_WIDTH - 130)
    for i, line in enumerate(q_lines[:5]):
        draw.text((80, quote_y + 50 + i * 62), line, font=fonts["medium"], fill=(200, 200, 200))

    # Streaming
    india_p = streaming_platforms.get("IN", [])[:2]
    stream_text = "  \u00b7  ".join(india_p) if india_p else "Rental only"
    draw.text((54, CARD_HEIGHT - 155), stream_text, font=fonts["small"], fill=(100, 100, 100))

    # Colored bottom bar with centered rating
    draw.rectangle([(0, CARD_HEIGHT - 100), (CARD_WIDTH, CARD_HEIGHT)], fill=cinema_color)
    rating_str = f"\u2b50 {rating} / 10"
    r_bbox = draw.textbbox((0, 0), rating_str, font=fonts["large"])
    r_w = r_bbox[2] - r_bbox[0]
    r_x = (CARD_WIDTH - r_w) // 2
    draw.text((r_x, CARD_HEIGHT - 80), rating_str, font=fonts["large"], fill=(255, 255, 255))
    handle = "@cinedrop"
    h_w = draw.textbbox((0, 0), handle, font=fonts["small"])[2]
    draw.text((CARD_WIDTH - h_w - 54, CARD_HEIGHT - 38), handle, font=fonts["small"], fill=(255, 255, 255, 160))

    return _save_card(card, movie["id"])


def create_story_card(feed_card_path, movie, post_type, post_permalink=None,
                      cta_lines=None, filename_prefix="story"):
    """
    Create a Story/Reel-optimized version of the feed card.
    Output is 1080x1920px (9:16).
    Places the feed card centered on a blurred dark background.
    Adds a top label and bottom CTA (overridable via cta_lines).
    Returns path to the generated image.
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

        # CTA lines — default guides Story viewers to the feed post; reels override this
        if cta_lines is None:
            cta_lines = [
                "full post in our feed 👆",
                "@cinedrop.01"
            ]

        cta_y = STORY_HEIGHT - 220

        # Dark pill background
        draw.rounded_rectangle(
            [(60, cta_y - 20), (STORY_WIDTH - 60, STORY_HEIGHT - 60)],
            radius=30,
            fill=(0, 0, 0, 200)
        )

        for i, line in enumerate(cta_lines):
            font = font_medium if i == 0 else font_large
            color = (180, 180, 180) if i == 0 else COLOR_SAFFRON
            bbox = draw.textbbox((0, 0), line, font=font)
            line_w = bbox[2] - bbox[0]
            draw.text(
                ((STORY_WIDTH - line_w) // 2, cta_y + i * 60),
                line,
                font=font,
                fill=color
            )

        # Save story card
        CARDS_DIR.mkdir(exist_ok=True)
        story_path = CARDS_DIR / f"{filename_prefix}_{movie['id']}_{post_type}.jpg"
        story.save(str(story_path), "JPEG", quality=95)
        log_message(f"Story card saved: {story_path}")
        return str(story_path)

    except Exception as e:
        log_message(f"Story card creation failed: {str(e)}", level="WARNING")
        return None


# ============================================================================
# STEP 5: CARD DISPATCHER & CAPTION BUILDER
# ============================================================================

def create_card(movie, streaming_platforms):
    """
    Dispatch to one of four card styles based on day of week.
    B2 Mon/Sat — dialogue poster
    B3 Tue/Fri — cinedrop score
    D1 Wed/Sun — mood line minimal
    D2 Thu     — quote + colored bar
    """
    try:
        style = CARD_STYLE_BY_DAY.get(datetime.utcnow().weekday(), "b2")
        log_message(f"Card style: {style}")

        if not movie.get("poster_path"):
            log_message("No poster path — skipping card", level="WARNING")
            return None

        if style == "b2": return render_b2(movie, streaming_platforms)
        if style == "b3": return render_b3(movie, streaming_platforms)
        if style == "d1": return render_d1(movie, streaming_platforms)
        if style == "d2": return render_d2(movie, streaming_platforms)
        return render_b2(movie, streaming_platforms)  # fallback

    except Exception as e:
        log_message(f"Card creation failed: {str(e)}", level="ERROR")
        return None



def add_caption_spice(caption, movie, post_type):
    """
    One tiny Groq call that appends 1-3 spicy words to the caption.
    Never fails — returns original caption if anything goes wrong.
    """
    try:
        client = Groq(api_key=GROQ_API_KEY)
        
        title  = movie.get("title", "")
        lang   = movie.get("original_language", "en")
        genre  = movie.get("_genre_name", "Drama")
        rating = round(movie.get("vote_average", 0), 1)
        
        prompt = f"""You are a 24 year old Indian who runs @cinedrop on Instagram.
You just finished writing this caption and you cannot help yourself —
you HAVE to add one last thing. It is compulsive. It is who you are.

Caption you just wrote:
{caption}

Film: {title}
Genre: {genre}
Language: {lang}
Rating: {rating}/10
Post type: {post_type}

Add 1 to 3 words at the very end. That is it.

Be SPICY. Be unexpected. Make it sting a little.
Could be aggressive. Could be emotional. Could be a gut punch.
Could be Telugu, Hindi, or English — whatever hits hardest for this film.
One emoji maximum if it makes it land harder.

Do NOT be safe. Do NOT be generic. Do NOT explain yourself.
Just say the thing. The thing nobody else would say but everyone is thinking.

Output the words only. Nothing else.

HARD LIMIT: 3 words maximum. Not 4. Not a sentence. 3 words."""
        
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=8,
            messages=[{"role": "user", "content": prompt}]
        )
        
        suffix = resp.choices[0].message.content.strip()
        
        if not suffix or len(suffix) > 60:
            return caption
        if "\n" in suffix:
            suffix = suffix.split("\n")[0].strip()
        
        # Insert suffix before hashtags if they exist
        lines = caption.split("\n")
        hashtag_start = None
        for i, line in enumerate(lines):
            if line.strip().startswith("#"):
                hashtag_start = i
                break
        
        if hashtag_start is not None:
            lines.insert(hashtag_start, suffix)
            lines.insert(hashtag_start, "")
            result = "\n".join(lines)
        else:
            result = caption + "\n\n" + suffix
        
        log_message(f"Spice added: '{suffix}'")
        return result
    
    except Exception as e:
        log_message(f"Caption spice skipped: {str(e)}", level="WARNING")
        return caption

def build_caption(content, movie, post_type):
    """Returns (caption_body, hashtag_block) — hashtags posted separately as first comment."""
    # Build caption body depending on post type
    if post_type == "list" and "films" in content:
        intro = content.get("intro", "films to watch next")
        films = content.get("films", [])
        lines = [intro, ""]
        for idx, film in enumerate(films, 1):
            lines.append(f"{idx}. {film.get('title', '?')} ({film.get('year', '')}) \u2014 {film.get('reason', '')}")
        caption_text = "\n".join(lines)
    elif post_type == "rating" and "verdict" in content:
        caption_text = (
            f"{content.get('verdict_line', 'worth a watch')}\n\n"
            f"Story: {content.get('story', 7.0)}/10\n"
            f"Performances: {content.get('performances', 7.0)}/10\n"
            f"Rewatch: {content.get('rewatch', 6.5)}/10\n"
            f"Emotional Hit: {content.get('emotional_hit', 7.0)}/10\n\n"
            f"VERDICT: {content.get('verdict', 'SOLID')}"
        )
    else:
        caption_text = content.get("caption", "")

    hashtag_block = content.get("hashtags", "")
    caption_body = add_caption_spice(caption_text, movie, post_type)

    # Saves are weighted heavily by the algorithm — always nudge for one
    caption_body = caption_body + "\n\n📌 save this for later"

    # Embed a small, focused hashtag set in the caption (first comment repeats the hook)
    if hashtag_block:
        top_tags = " ".join(hashtag_block.split()[:8])
        caption_body = caption_body + "\n\n" + top_tags

    # Respect Instagram's 2200 char limit without aggressive truncation
    if len(caption_body) > 2200:
        caption_body = caption_body[:2200].rsplit("\n", 1)[0].strip()

    log_message(f"Caption: {len(caption_body)} chars | Hashtags: {len(hashtag_block.split())} tags")
    return caption_body, hashtag_block


def build_first_comment(movie, post_type, hashtag_block):
    """Movie-specific line from Groq + curated hashtags. Hinglish fallback if Groq fails."""
    title = movie.get("title", "")
    year  = int(movie.get("release_date", "2000")[:4] or 2000)
    lang  = movie.get("original_language", "en")

    hook = ""
    if GROQ_API_KEY:
        try:
            client = Groq(api_key=GROQ_API_KEY)
            prompt = f"""You run @cinedrop on Instagram. You just posted about {title} ({year}).
Write ONE punchy line to drop as a comment on your own post.
Rules:
- Don't start with "this film", "this movie", or "watch"
- Reference something specific about {title} — a feeling it gives, type of scene, culture, a character vibe
- Sound like a 24-year-old Indian film obsessive — real, not polished
- End with a question OR an action trigger (tag someone, drop an emoji, save this)
- Mix Hindi/Telugu/English if it hits harder for this particular film
- Max 15 words. Just the line. No hashtags."""
            resp = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                max_tokens=50,
                messages=[{"role": "user", "content": prompt}]
            )
            raw = resp.choices[0].message.content.strip().split("\n")[0].strip()
            if raw and len(raw) <= 120:
                hook = raw
        except Exception as e:
            log_message(f"First comment Groq call failed: {e}", level="WARNING")

    if not hook:
        fallbacks = {
            "recommendation": "agar ye miss kiya toh seriously kya dekha hai \ud83e\udd26",
            "hot_take":       "ek baar dekho phir bolna \u2014 aaj bhi stand by my take",
            "dialogue":       "kuch lines hoti hain jo literally aapke saath rehti hain",
            "mood_pick":      "sahi mood mein dekho ye \u2014 trust me on this",
            "trivia":         "ye fact mujhe bhi recently pata chala aur main shocked tha",
            "list":           "ye list maine 2 baje banaya tha \u2014 ab aapke kaam aayega",
            "rating":         "honest review mein darrta nahi \u2014 agree karo ya na karo",
        }
        hook = fallbacks.get(post_type, "tag karo kisi ko jo ye nahi dekha \ud83d\udc47")

    # First comment is just the hook — hashtags are already in the caption
    return hook.strip()


def upload_card_for_instagram(card_path):
    """
    Upload card image to GitHub via the Contents API.
    Uses the same GH_TOKEN already working for history.
    Returns a jsDelivr CDN URL — more reliable than raw.githubusercontent.com for Instagram.
    """
    try:
        repo   = HISTORY_REPO  # public state repo hosts cards so bot repo stays clean
        branch = "main"
        token  = os.getenv("HISTORY_REPO_TOKEN") or os.getenv("GH_TOKEN")

        if not token:
            log_message("GH_TOKEN not set — cannot upload card", level="ERROR")
            return None

        with open(card_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")

        file_path = str(card_path).replace("\\", "/")
        api_url   = f"https://api.github.com/repos/{repo}/contents/{file_path}"
        headers   = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        # Check if file already exists — need SHA to update existing file
        existing_sha = None
        check = requests.get(api_url, headers=headers, timeout=10)
        if check.status_code == 200:
            existing_sha = check.json().get("sha")

        body = {
            "message": f"Auto: card {datetime.utcnow().strftime('%Y-%m-%d')}",
            "content": image_b64,
            "branch":  branch,
        }
        if existing_sha:
            body["sha"] = existing_sha

        resp = requests.put(api_url, headers=headers, json=body, timeout=30)

        if resp.status_code in (200, 201):
            # jsDelivr serves GitHub content via a CDN that Instagram accepts
            commit_sha = resp.json().get("commit", {}).get("sha", branch)
            public_url = f"https://cdn.jsdelivr.net/gh/{repo}@{commit_sha}/{file_path}"
            log_message(f"Card uploaded successfully: {public_url}")
            return public_url
        else:
            log_message(f"GitHub Contents API failed: {resp.status_code} {resp.text}", level="ERROR")
            return None

    except Exception as e:
        log_message(f"Card upload error: {str(e)}", level="ERROR")
        return None


def publish_to_instagram(image_url, caption, alt_text=""):
    """Publish image and caption to Instagram using the Instagram Graph API."""
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not found in environment variables")

    try:
        log_message("Publishing to Instagram...")

        container_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
        
        container_payload = {
            "image_url": image_url,
            "caption": caption,
            "alt_text": alt_text or "",
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


def create_reel_video(image_path, duration=8):
    """
    Turn a still 1080x1920 frame into a Ken Burns (slow zoom) MP4 for Reels.
    Reels get far more reach than static images, so the daily post tries this first.
    Requires ffmpeg (preinstalled on GitHub Actions runners). If ffmpeg is missing
    or encoding fails, returns None so the caller falls back to a static image post.
    Audio: uses assets/reel_audio.mp3 if present, otherwise synthesizes a soft
    royalty-free ambient chord pad with ffmpeg (open source, no API, no copyright).
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        log_message("ffmpeg not found — skipping Reel, will post static image", level="WARNING")
        return None
    try:
        out_path = str(CARDS_DIR / "reel.mp4")
        fps = 30
        frames = duration * fps
        # Scale up first so zoompan motion stays smooth, then slow zoom-in to 1.15x
        vf = (
            f"scale=2160:3840,"
            f"zoompan=z='min(zoom+0.00035,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"s=1080x1920:fps={fps},format=yuv420p"
        )
        audio_path = ASSETS_DIR / "reel_audio.mp3"
        cmd = [ffmpeg, "-y", "-i", image_path]
        audio_filter = None

        if audio_path.exists():
            # Bundled track takes priority if the user ever adds one
            cmd += ["-i", str(audio_path)]
            audio_src = "file"
        else:
            # Synthesize a soft ambient chord pad — 100% ffmpeg, no API, no licensing.
            # Rotate the chord by weekday so daily Reels don't all sound identical.
            chords = [
                (130.81, 164.81, 196.00),  # C major
                (110.00, 130.81, 164.81),  # A minor
                (146.83, 185.00, 220.00),  # D major
                (98.00,  123.47, 146.83),  # G major
                (123.47, 155.56, 185.00),  # B minor colour
                (116.54, 146.83, 174.61),  # Bb major
                (164.81, 196.00, 246.94),  # E minor colour
            ]
            f1, f2, f3 = chords[datetime.utcnow().weekday() % len(chords)]
            expr = (f"0.13*sin(2*PI*{f1}*t)+0.12*sin(2*PI*{f2}*t)"
                    f"+0.10*sin(2*PI*{f3}*t)+0.05*sin(2*PI*{f1 * 2}*t)")
            cmd += ["-f", "lavfi", "-i", f"aevalsrc=exprs={expr}:d={duration}:s=44100"]
            audio_filter = (
                f"tremolo=f=0.2:d=0.5,lowpass=f=1500,aecho=0.8:0.88:70:0.25,"
                f"afade=t=in:st=0:d=1.5,afade=t=out:st={duration - 1.5}:d=1.5,volume=1.3"
            )
            audio_src = "synth"

        cmd += ["-vf", vf, "-t", str(duration), "-r", str(fps),
                "-c:v", "libx264", "-preset", "medium", "-pix_fmt", "yuv420p",
                "-movflags", "+faststart"]
        if audio_filter:
            cmd += ["-af", audio_filter]
        cmd += ["-c:a", "aac", "-b:a", "128k",
                "-map", "0:v", "-map", "1:a", "-shortest", out_path]

        subprocess.run(cmd, check=True, capture_output=True, timeout=180)
        log_message(f"Reel video created: {out_path} (audio={audio_src})")
        return out_path
    except subprocess.CalledProcessError as e:
        err = (e.stderr or b"").decode("utf-8", "ignore")[-500:]
        log_message(f"Reel encoding failed: {err} — falling back to image", level="WARNING")
        return None
    except Exception as e:
        log_message(f"Reel video creation failed: {e} — falling back to image", level="WARNING")
        return None


def publish_reel_to_instagram(video_url, caption):
    """
    Publish a Reel from a public video URL. Reels must finish server-side encoding
    before publishing, so this polls the container status until FINISHED.
    Returns the post ID, or None so the caller can fall back to a static image post.
    """
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        return None
    try:
        log_message("Publishing Reel to Instagram...")
        container_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media"
        payload = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "share_to_feed": "true",   # also show in the grid/feed, not just Reels tab
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }
        r = requests.post(container_url, data=payload, timeout=30)
        r.raise_for_status()
        cid = r.json().get("id")
        if not cid:
            log_message(f"Reel container creation failed: {r.json()}", level="ERROR")
            return None
        log_message(f"Reel container created: {cid} — waiting for encoding")

        # Poll until FINISHED (up to ~100s) — publishing early returns an error
        status_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{cid}"
        finished = False
        for attempt in range(20):
            time.sleep(5)
            s = requests.get(status_url, params={
                "fields": "status_code",
                "access_token": INSTAGRAM_ACCESS_TOKEN,
            }, timeout=15)
            code = s.json().get("status_code")
            log_message(f"Reel status [{attempt+1}/20]: {code}")
            if code == "FINISHED":
                finished = True
                break
            if code == "ERROR":
                log_message(f"Reel processing errored: {s.json()}", level="ERROR")
                return None
        if not finished:
            log_message("Reel not ready in time — falling back to image", level="WARNING")
            return None

        publish_url = f"{INSTAGRAM_GRAPH_BASE_URL}/{INSTAGRAM_ACCOUNT_ID}/media_publish"
        p = requests.post(publish_url, data={
            "creation_id": cid,
            "access_token": INSTAGRAM_ACCESS_TOKEN,
        }, timeout=30)
        p.raise_for_status()
        post_id = p.json().get("id")
        if post_id:
            log_message(f"Reel published! Post ID: {post_id}")
        return post_id
    except requests.RequestException as e:
        log_message(f"Reel publish error: {e}", level="ERROR")
        resp = getattr(e, "response", None)
        if resp is not None:
            log_message(f"Reel API response: {resp.text}", level="ERROR")
        return None


def post_first_comment(post_id, comment_text):
    """Post hashtags as the first comment to keep the caption clean."""
    if not INSTAGRAM_ACCESS_TOKEN or not post_id or not comment_text.strip():
        return None
    try:
        url = f"{INSTAGRAM_GRAPH_BASE_URL}/{post_id}/comments"
        resp = requests.post(
            url,
            data={"message": comment_text, "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=15,
        )
        resp.raise_for_status()
        comment_id = resp.json().get("id")
        if comment_id:
            log_message(f"Hashtag comment posted: {comment_id}")
        return comment_id
    except Exception as e:
        log_message(f"First comment failed (non-critical): {e}", level="WARNING")
        return None


def get_post_permalink(post_id):
    """Fetch the permanent URL of a published Instagram post."""
    try:
        url = f"{INSTAGRAM_GRAPH_BASE_URL}/{post_id}"
        resp = requests.get(
            url,
            params={"fields": "permalink", "access_token": INSTAGRAM_ACCESS_TOKEN},
            timeout=10
        )
        permalink = resp.json().get("permalink")
        if permalink:
            log_message(f"Post permalink: {permalink}")
        return permalink
    except Exception as e:
        log_message(f"Could not fetch post permalink: {e}", level="WARNING")
        return None


def publish_to_story(image_url, post_permalink=None):
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
        link_url = post_permalink or "https://www.instagram.com/cinedrop.01/"
        container_payload = {
            "image_url": image_url,
            "media_type": "STORIES",
            "access_token": INSTAGRAM_ACCESS_TOKEN,
            # Instagram Graph API: sticker_data with link_sticker.link for tappable URL
            "sticker_data": json.dumps({"link_sticker": {"link": link_url}}),
        }
        log_message(f"Story link sticker URL: {link_url}")

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
        
        # Attach card fields to movie dict for render functions to access
        movie["_dialogue"] = content.get("dialogue", "")
        movie["_mood"] = content.get("mood_line", "")
        movie["_verdict"] = content.get("verdict", "MUST WATCH")
        
        card_path = create_card(movie, streaming_platforms)
        if not card_path:
            log_message("Could not generate card. Exiting.", level="ERROR")
            return

        caption_body, hashtag_block = build_caption(content, movie, post_type)
        alt_text = (
            f"{movie_title} ({movie.get('release_date', '')[:4]}) "
            f"{movie.get('_genre_name', '')} — film card by @cinedrop"
        ).strip()

        # --- REEL-FIRST STRATEGY ---
        # Video Reels get dramatically more reach than static images on Instagram —
        # the single biggest lever for growing a small account. Build a 9:16 Ken Burns
        # video from the card and post it as a Reel (share_to_feed=true so it also lands
        # in the grid). If anything fails, fall back to a static single-image post.
        post_id = None
        posted_as_reel = False
        media_url = None
        try:
            reel_frame = create_story_card(
                card_path, movie, post_type,
                cta_lines=["follow for daily films 🎬", "@cinedrop.01"],
                filename_prefix="reel",
            )
            reel_video = create_reel_video(reel_frame) if reel_frame else None
            if reel_video:
                reel_url = upload_card_for_instagram(reel_video)
                if reel_url:
                    log_message("Waiting for GitHub CDN to serve the video...")
                    time.sleep(20)
                    post_id = publish_reel_to_instagram(reel_url, caption_body)
                    if post_id:
                        posted_as_reel = True
                        media_url = reel_url
        except Exception as e:
            log_message(f"Reel flow failed: {e} — falling back to static image", level="WARNING")

        # Fallback: static single-image post
        if not post_id:
            media_url = upload_card_for_instagram(card_path)
            if not media_url:
                log_message("Image upload failed. Exiting.", level="ERROR")
                return
            log_message("Waiting for GitHub CDN to serve the image...")
            time.sleep(20)
            log_message("Image ready for Instagram publishing")
            post_id = publish_to_instagram(media_url, caption_body, alt_text=alt_text)

        # Post first comment — engaging hook + curated hashtags (not a raw tag dump)
        first_comment = build_first_comment(movie, post_type, hashtag_block)
        post_first_comment(post_id, first_comment)

        # Fetch the post permalink so the story can link directly to it
        post_permalink = get_post_permalink(post_id)

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
            story_card_path = create_story_card(card_path, movie, post_type, post_permalink=post_permalink)

            if story_card_path:
                # Upload story card to GitHub via Contents API for public hosting
                story_public_url = upload_card_for_instagram(story_card_path)

                if story_public_url:
                    # Publish story immediately after feed post succeeds
                    story_id = publish_to_story(story_public_url, post_permalink=post_permalink)

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
        log_message(f"Format       : {'REEL (video)' if posted_as_reel else 'IMAGE (static)'}")
        log_message(f"Cinema       : {movie.get('original_language', 'en').upper()}")
        log_message(f"Rating       : {movie.get('vote_average', 0)}/10")
        log_message(f"🇮🇳 India     : {', '.join(streaming_platforms['IN']) or 'Not streaming'}")
        log_message(f"🇺🇸 US        : {', '.join(streaming_platforms['US']) or 'Not streaming'}")
        log_message(f"Post ID      : {post_id}")
        log_message(f"Story ID     : {story_id if story_id else 'failed'}")
        log_message(f"Media        : {media_url}")
        log_message("=" * 80)

    except Exception as e:
        log_message("=" * 80, level="ERROR")
        log_message(f"FATAL ERROR: {str(e)}", level="ERROR")
        log_message("=" * 80, level="ERROR")
        raise


# ============================================================================
# OTT WEEKLY LIST — separate flow, runs every Friday evening
# ============================================================================

def _search_ott_web() -> list[dict]:
    """
    Multi-source OTT discovery: DuckDuckGo news + free RSS feeds → Groq extraction.
    Only targets this week's Indian OTT film releases.
    Returns a list of {title, platform, lang} dicts.
    """
    import xml.etree.ElementTree as ET

    week_label = datetime.utcnow().strftime("%B %d %Y")
    snippets = []

    # Source A: DuckDuckGo news + web search — live results for this week
    try:
        from duckduckgo_search import DDGS
        queries = [
            f"new OTT movies India this week {week_label}",
            f"Netflix Prime Video Hotstar new movies India {week_label}",
            f"Telugu Hindi Tamil OTT streaming release this week",
            f"Aha Zee5 SonyLIV JioCinema new movie release {week_label}",
        ]
        with DDGS() as ddgs:
            for q in queries:
                try:
                    for r in ddgs.news(q, max_results=10, timelimit="w"):
                        body = (r.get("body") or r.get("title") or "")[:300]
                        if body:
                            snippets.append(body)
                except Exception:
                    pass
            # Web search gives broader coverage beyond news articles
            web_queries = [
                f"OTT releases this week India {week_label} site:ottplay.com OR site:bollywoodhungama.com OR site:pinkvilla.com",
                f"movies streaming now India {week_label} Netflix Hotstar Prime Zee5",
            ]
            for q in web_queries:
                try:
                    for r in ddgs.text(q, max_results=8, timelimit="w"):
                        body = (r.get("body") or r.get("title") or "")[:400]
                        if body:
                            snippets.append(body)
                except Exception:
                    pass
    except ImportError:
        log_message("duckduckgo-search not installed; skipping DDG search", level="WARNING")
    except Exception as e:
        log_message(f"DuckDuckGo search error: {e}", level="WARNING")

    # Source B: Free entertainment RSS feeds
    OTT_KW = {"ott", "netflix", "prime", "hotstar", "zee5", "sonyliv", "jiocinema",
              "aha", "lionsgate", "streaming", "digital release", "now streaming", "drops on"}
    RSS_FEEDS = [
        "https://www.bollywoodhungama.com/feed/",
        "https://timesofindia.indiatimes.com/rss/4719148.cms",
        "https://www.123telugu.com/feed",
        "https://www.pinkvilla.com/feed",
    ]
    for feed_url in RSS_FEEDS:
        try:
            resp = requests.get(feed_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
            if resp.status_code == 200:
                root = ET.fromstring(resp.content)
                for item in root.iter("item"):
                    title_el = item.find("title")
                    desc_el  = item.find("description")
                    text = ""
                    if title_el is not None and title_el.text:
                        text += title_el.text + ". "
                    if desc_el is not None and desc_el.text:
                        clean = re.sub(r"<[^>]+>", " ", desc_el.text)[:200]
                        text += clean
                    if any(k in text.lower() for k in OTT_KW):
                        snippets.append(text[:300])
        except Exception as e:
            log_message(f"RSS {feed_url} failed: {e}", level="WARNING")

    # Source C: Direct page scraping of OTT release listing pages
    RELEASE_PAGES = [
        "https://www.91mobiles.com/entertainment/ott-release-this-week",
        "https://www.ottplay.com/ott-releases-streaming-now-this-week-watch-online",
        "https://www.bollywoodhungama.com/latest-new-movies/",
        "https://www.123telugu.com/videos/ott",
        "https://trendraja.in/telugu-movie-ott-release-dates-2021/",
        "https://www.pinkvilla.com/entertainment/south/ott-releases-this-week",
    ]
    UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120 Safari/537.36"
    for page_url in RELEASE_PAGES:
        try:
            pr = requests.get(page_url, timeout=10, headers={"User-Agent": UA})
            if pr.status_code == 200:
                # Strip all HTML tags and collapse whitespace
                page_text = re.sub(r"<[^>]+>", " ", pr.text)
                page_text = re.sub(r"\s+", " ", page_text).strip()
                # Take up to 6000 chars to get past navigation into actual listings
                snippets.append(f"[PAGE: {page_url}]\n{page_text[:6000]}")
        except Exception as e:
            log_message(f"Page scrape {page_url} failed: {e}", level="WARNING")

    log_message(f"OTT web search: {len(snippets)} snippets from DDG news + RSS + page scrapes")

    if not snippets or not GROQ_API_KEY:
        return []

    context = "\n---\n".join(snippets[:40])
    try:
        client = Groq(api_key=GROQ_API_KEY)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=1000,
            messages=[{"role": "user", "content": f"""You are looking at content from Indian OTT release listing pages and news snippets for the week of {week_label}.

{context}

Extract movies AND web series that dropped on Indian OTT platforms THIS WEEK.
Return ONLY a valid JSON array, nothing else:
[{{"title": "Exact Title", "platform": "Netflix|Prime Video|JioHotstar|ZEE5|JioCinema|SonyLIV|Aha|Lionsgate Play|Apple TV+", "lang": "Hindi|Tamil|Telugu|Malayalam|Kannada|Korean|English", "type": "movie|series"}}]

Rules:
- Only include titles explicitly mentioned as releasing/streaming THIS WEEK
- Do NOT fabricate or guess titles not visible in the text above
- Include both films and web series/OTT originals
- Exclude documentaries and reality shows
- Prefer titles that appear in multiple sources
- Max 15 items"""}]
        )
        raw = resp.choices[0].message.content.strip()
        m = re.search(r'\[.*?\]', raw, re.DOTALL)
        if m:
            parsed = json.loads(m.group())
            log_message(f"Multi-source OTT search extracted {len(parsed)} candidates")
            return parsed if isinstance(parsed, list) else []
    except Exception as e:
        log_message(f"Groq OTT extraction failed: {e}", level="WARNING")

    return []


def _tmdb_validate_film(title: str) -> dict | None:
    """Search TMDB by title and return the best match, or None if not found."""
    try:
        r = requests.get(f"{TMDB_BASE_URL}/search/movie", params={
            "api_key": TMDB_API_KEY, "query": title, "language": "en-US", "page": 1,
        }, timeout=8)
        r.raise_for_status()
        results = r.json().get("results", [])
        return results[0] if results else None
    except Exception:
        return None


def get_new_ott_releases():
    """
    Fetch movies that hit Indian OTT platforms this week.

    Source priority:
      1. DuckDuckGo web search + Groq extraction (real-time, finds actual OTT drops)
      2. TMDB discover with digital release type (release_type=4|6, last 14 days)
      3. TMDB theatrical-date proxy fallback (smarter per-language windows)
    Every candidate is validated against TMDB for metadata + provider confirmation.
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not set")

    INDIA_PROVIDERS = "8|119|122|237|232|892|190|35|532|561"  # +AppleTV+, Aha, LionsgatePlay
    LANG_CODE = {"Hindi":"hi","Tamil":"ta","Telugu":"te","Malayalam":"ml","Kannada":"kn","English":"en","Korean":"ko"}

    films = []      # accumulates TMDB movie dicts
    seen  = set()   # dedup by tmdb id

    # ── Source 0: TMDB now_playing with region=IN ─────────────────────────────
    try:
        r = requests.get(f"{TMDB_BASE_URL}/movie/now_playing", params={
            "api_key": TMDB_API_KEY, "region": "IN", "language": "en-US", "page": 1,
        }, timeout=10)
        r.raise_for_status()
        np_added = 0
        for m in r.json().get("results", [])[:15]:
            if m["id"] not in seen:
                seen.add(m["id"])
                lang = m.get("original_language", "en")
                m["_cinema_type"] = "Indian" if lang in {"hi","ta","te","ml","kn"} else "Hollywood"
                m["_date_source"] = "now_playing"
                films.append(m)
                np_added += 1
        log_message(f"TMDB now_playing: +{np_added} films")
    except Exception as e:
        log_message(f"TMDB now_playing failed: {e}", level="WARNING")

    # ── Source 1: web search + Groq ──────────────────────────────────────────
    web_candidates = _search_ott_web()
    for item in web_candidates:
        title = item.get("title", "")
        if not title:
            continue
        movie = _tmdb_validate_film(title)
        if movie and movie["id"] not in seen:
            seen.add(movie["id"])
            movie["_cinema_type"]  = "Indian" if movie.get("original_language","en") != "en" else "Hollywood"
            movie["_date_source"]  = "web"
            lang_code = LANG_CODE.get(item.get("lang",""), movie.get("original_language","en"))
            movie["original_language"] = lang_code
            # only store Groq platform if it's a known name (Groq sometimes returns "Unknown")
            raw_plat = item.get("platform", "")
            if raw_plat and raw_plat in PROVIDER_MAPPING.values():
                movie["_groq_platform"] = raw_plat
            films.append(movie)
    log_message(f"Web source: {len(films)} validated films")

    # ── Source 2: TMDB digital release type (last 7 days) ────────────────────
    today    = datetime.utcnow().strftime("%Y-%m-%d")
    week_ago = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
    BASE     = {"api_key": TMDB_API_KEY, "watch_region": "IN",
                "with_watch_providers": INDIA_PROVIDERS, "language": "en-US",
                "vote_count.gte": 5, "sort_by": "primary_release_date.desc", "page": 1}

    # Indian + Korean lang groups; Hollywood/Korean get a min-rating filter
    for lang, label, min_votes in [
        ("hi|ta|te|ml|kn", "Indian",    5),
        ("en",             "Hollywood", 50),
        ("ko",             "Korean",    50),
    ]:
        try:
            r = requests.get(f"{TMDB_BASE_URL}/discover/movie", params={
                **BASE, "with_release_type": "4|6",
                "release_date.gte": week_ago, "release_date.lte": today,
                "with_original_language": lang, "region": "IN",
                "vote_count.gte": min_votes,
            }, timeout=10)
            r.raise_for_status()
            for m in r.json().get("results", [])[:5]:
                if m["id"] not in seen:
                    seen.add(m["id"])
                    m["_cinema_type"] = label
                    m["_date_source"] = "digital"
                    films.append(m)
        except Exception as e:
            log_message(f"TMDB digital pass failed ({label}): {e}", level="WARNING")

    # ── Source 3: theatrical-date proxy (fallback if list is thin) ───────────
    if len(films) < 5:
        # tighter windows — only films plausibly hitting OTT *this* week
        indian_gte = (datetime.utcnow() - timedelta(days=42)).strftime("%Y-%m-%d")
        indian_lte = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")
        hw_gte     = (datetime.utcnow() - timedelta(days=75)).strftime("%Y-%m-%d")
        hw_lte     = (datetime.utcnow() - timedelta(days=42)).strftime("%Y-%m-%d")
        for lang, label, gte, lte, min_v in [
            ("hi|ta|te|ml|kn", "Indian",    indian_gte, indian_lte, 5),
            ("en",             "Hollywood", hw_gte,     hw_lte,    50),
            ("ko",             "Korean",    hw_gte,     hw_lte,    50),
        ]:
            try:
                r = requests.get(f"{TMDB_BASE_URL}/discover/movie", params={
                    **BASE, "primary_release_date.gte": gte,
                    "primary_release_date.lte": lte, "with_original_language": lang,
                    "vote_count.gte": min_v,
                }, timeout=10)
                r.raise_for_status()
                for m in r.json().get("results", [])[:5]:
                    if m["id"] not in seen:
                        seen.add(m["id"])
                        m["_cinema_type"] = label
                        m["_date_source"] = "proxy"
                        films.append(m)
            except Exception as e:
                log_message(f"TMDB proxy pass failed ({label}): {e}", level="WARNING")

    # ── Confirm each film is actually streaming in India right now ────────────
    # Indian films first, then Hollywood, then verify provider
    films.sort(key=lambda x: (0 if x.get("_cinema_type") == "Indian" else 1,
                               0 if x.get("_date_source") == "web" else 1))

    confirmed = []
    for m in films:
        if len(confirmed) >= 8:
            break
        try:
            wp = requests.get(
                f"{TMDB_BASE_URL}/movie/{m['id']}/watch/providers",
                params={"api_key": TMDB_API_KEY}, timeout=8,
            ).json().get("results", {}).get("IN", {})
            providers = [
                PROVIDER_MAPPING.get(p["provider_id"], p.get("provider_name", ""))
                for p in wp.get("flatrate", [])
            ]
            seen_p = dict.fromkeys(p for p in providers if p)  # dedup, preserve order
            m["_platforms"] = list(seen_p)[:2]
            # TMDB provider data lags for new releases — fall back to Groq-extracted platform
            if not m["_platforms"] and m.get("_groq_platform"):
                m["_platforms"] = [m["_groq_platform"]]
            if m["_platforms"]:
                confirmed.append(m)
        except Exception:
            pass

    log_message(f"OTT final list: {len(confirmed)} confirmed (sources: "
                f"web={sum(1 for m in confirmed if m.get('_date_source')=='web')}, "
                f"digital={sum(1 for m in confirmed if m.get('_date_source')=='digital')}, "
                f"proxy={sum(1 for m in confirmed if m.get('_date_source')=='proxy')})")
    return confirmed


def render_ott_list_card(films):
    """
    Clean dark editorial card listing 5-8 new OTT releases.
    No movie posters — pure typography.
    """
    fonts = _load_fonts()

    PLATFORM_COLORS = {
        "Netflix":        (229,  9, 20),
        "Prime Video":    (  0,168,224),
        "JioHotstar":     (108, 63,194),
        "Zee5":           (230, 65,115),
        "JioCinema":      (255,103,  0),
        "SonyLIV":        (  0,120,215),
        "Apple TV+":      (240,240,240),
        "Aha":            ( 34,197, 94),
        "Lionsgate Play": (230, 50, 50),
        "Mubi":           (255,103,  0),
    }

    BG        = (28, 30, 42)   # dark navy instead of near-black
    ROW_ALT   = (34, 37, 52)   # alternating row — barely lighter
    DIVIDER   = (52, 55, 75)   # visible but soft
    IDX_COL   = (90, 95, 125)  # index numbers — readable, not washed-out
    TITLE_COL = (220, 222, 235)
    META_COL  = (120, 125, 155)

    card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), BG)
    draw = ImageDraw.Draw(card)

    # Subtle noise texture
    for _ in range(400):
        nx, ny = random.randint(0, CARD_WIDTH), random.randint(0, CARD_HEIGHT)
        v = random.randint(35, 50)
        draw.point((nx, ny), fill=(v, v, v + 8))

    # Header
    ORANGE = COLOR_SAFFRON
    draw.rectangle([(0, 0), (CARD_WIDTH, 8)], fill=ORANGE)

    header1 = "OTT RELEASES"
    h1_bbox = draw.textbbox((0, 0), header1, font=fonts["title"])
    h1_w = h1_bbox[2] - h1_bbox[0]
    draw.text(((CARD_WIDTH - h1_w) // 2, 40), header1, font=fonts["title"], fill=(245, 245, 250))

    header2 = "THIS WEEK"
    h2_bbox = draw.textbbox((0, 0), header2, font=fonts["medium"])
    h2_w = h2_bbox[2] - h2_bbox[0]
    draw.text(((CARD_WIDTH - h2_w) // 2, 160), header2, font=fonts["medium"], fill=ORANGE)

    # Divider
    draw.rectangle([(60, 230), (CARD_WIDTH - 60, 233)], fill=DIVIDER)

    # Film rows
    row_y = 258
    ROW_H = 126  # height per film row

    for i, film in enumerate(films[:8]):
        title   = film.get("title", "Unknown")
        year    = (film.get("release_date") or "")[:4]
        langs   = {"hi":"Bollywood","ta":"Tamil","te":"Telugu","ml":"Malayalam","kn":"Kannada"}
        lang    = film.get("original_language", "en")
        lang_label = langs.get(lang, "Korean" if lang == "ko" else "Hollywood")
        platforms  = film.get("_platforms", [])

        # Row background (alternating)
        if i % 2 == 0:
            draw.rectangle([(0, row_y), (CARD_WIDTH, row_y + ROW_H - 2)], fill=ROW_ALT)

        # Index number
        draw.text((54, row_y + 22), f"{i+1}.", font=fonts["medium"], fill=IDX_COL)

        # Title — downsize to body font if it wraps at medium size
        MAX_TITLE_W = CARD_WIDTH - 164
        title_upper = title.upper()
        t_lines = _wrap_text(draw, title_upper, fonts["medium"], MAX_TITLE_W)
        if len(t_lines) > 1:
            t_font = fonts["body"]
            t_lines = _wrap_text(draw, title_upper, t_font, MAX_TITLE_W)
            title_y = row_y + 22
        else:
            t_font = fonts["medium"]
            title_y = row_y + 18
        draw.text((110, title_y), t_lines[0], font=t_font, fill=TITLE_COL)
        if len(t_lines) > 1:
            draw.text((110, title_y + 38), t_lines[1], font=t_font, fill=TITLE_COL)

        # Meta line: always below title — pushed down enough to clear longest title
        meta_y = row_y + 86
        draw.text((110, meta_y), f"{year}  ·  {lang_label}", font=fonts["small"], fill=META_COL)

        # Platform pills right-aligned on meta baseline
        pill_x = CARD_WIDTH - 54
        for plat in reversed(platforms):
            pc = PLATFORM_COLORS.get(plat, (100, 100, 120))
            short = plat.replace("Lionsgate Play", "Lionsgate")
            pb = draw.textbbox((0, 0), short, font=fonts["tiny"])
            pw = pb[2] - pb[0] + 20
            ph = pb[3] - pb[1] + 10
            pill_x -= pw
            draw.rounded_rectangle([(pill_x, meta_y - 2), (pill_x + pw, meta_y + ph)],
                                    radius=10, fill=pc)
            draw.text((pill_x + 10, meta_y + 1), short, font=fonts["tiny"],
                      fill=(255, 255, 255) if plat != "Apple TV+" else (0, 0, 0))
            pill_x -= 10

        row_y += ROW_H
        # Row separator
        draw.rectangle([(54, row_y - 2), (CARD_WIDTH - 54, row_y - 1)], fill=DIVIDER)

    # Bottom bar
    bar_y = CARD_HEIGHT - 70
    draw.rectangle([(0, bar_y), (CARD_WIDTH, CARD_HEIGHT)], fill=ORANGE)
    draw.text((54, bar_y + 20), "@cinedrop", font=fonts["medium"], fill=(255, 255, 255))
    save_text = "save this"
    s_w = draw.textbbox((0, 0), save_text, font=fonts["small"])[2]
    draw.text((CARD_WIDTH - s_w - 54, bar_y + 26), save_text, font=fonts["small"], fill=(255, 255, 255))

    CARDS_DIR.mkdir(exist_ok=True)
    path = CARDS_DIR / "ott_weekly_list.jpg"
    card.convert("RGB").save(str(path), "JPEG", quality=93)
    log_message(f"OTT list card saved: {path}")
    return str(path)


def generate_ott_caption(films):
    """Description with movie names + hashtags for reach."""
    lines = ["🎬 OTT Releases This Week\n"]
    for f in films:
        title   = f.get("title", "")
        plats   = f.get("_platforms", [])
        plat_str = " · ".join(plats) if plats else ""
        lines.append(f"▸ {title}" + (f"  ({plat_str})" if plat_str else ""))
    lines.append("\nSave this & plan your weekend watch 🍿")

    # Dynamic tags based on actual langs / platforms in the list
    lang_tags = {
        "te": "#tollywood #telugumovies",
        "hi": "#bollywood #hindicinema",
        "ta": "#kollywood #tamilmovies",
        "ml": "#mollywood #malayalammovies",
        "en": "#hollywood #englishmovies",
        "ko": "#koreanmovies #kdrama",
    }
    plat_tags = {
        "Netflix":          "#netflixindia",
        "Amazon Prime Video": "#primevideoindia",
        "JioCinema":        "#jiocinemanow",
        "Disney+ Hotstar":  "#hotstar",
        "SonyLIV":          "#sonyliv",
        "ZEE5":             "#zee5",
        "Apple TV+":        "#appletv",
        "Mubi":             "#mubi",
    }

    seen_lang_tags, seen_plat_tags = set(), set()
    for f in films:
        tag = lang_tags.get(f.get("original_language", ""))
        if tag:
            seen_lang_tags.add(tag)
        for p in f.get("_platforms", []):
            pt = plat_tags.get(p)
            if pt:
                seen_plat_tags.add(pt)

    base_tags = (
        "#cinedrop #newonott #ottrelease #ottindia #weekendwatch "
        "#streamingwatch #ottwatch #weekendwatchlist #bingelist #cinephile "
        "#indiefilms #worldcinema #newmovies2025 #mustwatch #moviestowatch"
    )
    dynamic = " ".join(sorted(seen_lang_tags) + sorted(seen_plat_tags))
    tags = (base_tags + " " + dynamic).strip()

    return "\n".join(lines) + "\n\n" + tags


def main_ott_list():
    """Weekly OTT releases post — runs every Friday evening."""
    try:
        log_message("=" * 80)
        log_message("STARTING WEEKLY OTT LIST POST")
        log_message("=" * 80)
        log_ist_time()
        check_token_age()

        films = get_new_ott_releases()
        if not films:
            log_message("No new OTT releases found. Exiting.", level="WARNING")
            return

        log_message(f"Found {len(films)} new OTT releases for the list")

        card_path = render_ott_list_card(films)
        public_image_url = upload_card_for_instagram(card_path)
        if not public_image_url:
            log_message("Card upload failed. Exiting.", level="ERROR")
            return

        log_message("Waiting for GitHub CDN...")
        time.sleep(20)

        caption = generate_ott_caption(films)

        title_list = " · ".join(f.get("title", "") for f in films[:6])
        alt_text = f"OTT releases this week: {title_list} — by @cinedrop"
        post_id = publish_to_instagram(public_image_url, caption, alt_text=alt_text)

        # Short engagement hook as first comment (no hashtag repeat)
        post_first_comment(post_id, "save this — tag someone who needs a watch plan this weekend")

        # Story — link sticker points back to the feed post
        post_permalink = get_post_permalink(post_id)
        story_id = None
        try:
            story_card_path = create_story_card(card_path, {"id": "ott_list"}, "list", post_permalink=post_permalink)
            if story_card_path:
                story_public_url = upload_card_for_instagram(story_card_path)
                if story_public_url:
                    story_id = publish_to_story(story_public_url, post_permalink=post_permalink)
        except Exception as e:
            log_message(f"OTT list story failed: {str(e)} — main post unaffected", level="WARNING")

        log_message("=" * 80)
        log_message(f"OTT LIST POST SUCCESS — {len(films)} films | Post ID: {post_id} | Story: {story_id or 'failed'}")
        log_message("=" * 80)

    except Exception as e:
        log_message(f"OTT list post failed: {str(e)}", level="ERROR")
        raise


if __name__ == "__main__":
    import sys
    if "--ott-list" in sys.argv:
        main_ott_list()
    else:
        main()
