"""
Instagram Daily Movie Post Bot
Automatically generates and publishes engaging movie posts to Instagram daily via GitHub Actions.
Targets Indian audience (18–35, bilingual Hindi/English). Discovers diverse films across eras.
"""

import os
import json
import time
import base64
import random
import requests
from datetime import datetime
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
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"
GITHUB_API_BASE_URL = "https://api.github.com"

# Image card settings
PAGE_HANDLE = "@cinedrop"
CARD_WIDTH = 1080
CARD_HEIGHT = 1350

# CHANGE 2: Genre rotation by day of week (0=Monday, 6=Sunday)
GENRE_BY_DAY = {
    0: {"name": "Thriller", "id": 53},
    1: {"name": "Family", "id": 10751},
    2: {"name": "Action", "id": 28},
    3: {"name": "Drama", "id": 18},
    4: {"name": "Comedy", "id": 35},
    5: {"name": "Romance", "id": 10749},
    6: {"name": "Science Fiction", "id": 878},
}

# CHANGE 3: Streaming provider IDs (corrected)
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

# Path to history file
POSTED_MOVIES_FILE = Path("posted_movies.json")

# Temporary directory for images
TEMP_DIR = Path("/tmp" if os.name != "nt" else os.getenv("TEMP", "./temp"))

# Directory for generated cards
CARDS_DIR = Path("cards")

# Cache the SHA of the history file
_HISTORY_FILE_SHA = None


# ============================================================================
# UTILITY FUNCTIONS
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


def log_message(message, level="INFO"):
    """Print timestamped log messages."""
    timestamp = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"[{timestamp}] [{level}] {message}")


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
# STEP 3: GENERATE CAPTION USING GROQ
# ============================================================================

def write_caption(movie, streaming_platforms):
    """
    CHANGE 5 & 6: Use language/era detection and strict short-form structure.
    CHANGE 4: India-first streaming display with flags.
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment variables")

    try:
        log_message("Generating caption with Groq API...")

        client = Groq(api_key=GROQ_API_KEY)

        # CHANGE 5: Language and era detection
        original_language = movie.get("original_language", "en")
        LANGUAGE_LABEL_MAP = {
            "hi": "Bollywood",
            "ta": "Tamil",
            "te": "Telugu",
            "ml": "Malayalam",
            "kn": "Kannada",
        }
        language_label = LANGUAGE_LABEL_MAP.get(original_language, "Hollywood")

        release_date = movie.get("release_date", "")
        year_int = int(release_date[:4]) if release_date else 0

        if year_int > 0 and year_int < 1995:
            era = "classic"
        elif year_int >= 1995 and year_int < 2016:
            era = "modern"
        else:
            era = "recent"

        # CHANGE 4: India-first streaming display, two-liner format
        india_platforms = streaming_platforms.get("IN", [])
        us_only = [p for p in streaming_platforms.get("US", []) if p not in india_platforms]

        if india_platforms:
            platforms_text = f"🇮🇳 {' · '.join(india_platforms)}"
            if us_only:
                platforms_text += f"\n🇺🇸 {' · '.join(us_only)}"
        else:
            platforms_text = "Not streaming — rental/purchase only 🎬"

        movie_title = movie.get("title", "Unknown")
        year = release_date[:4] if release_date else "N/A"
        rating = round(movie.get("vote_average", 0), 1)
        overview = movie.get("overview", "")
        genres = movie.get("genres", [])
        genre_str = ", ".join([g["name"] for g in genres]) if genres else "Drama"

        log_message(f"Detected: {language_label} | Era: {era}")

        # CHANGE 6: Strict short-form caption prompt
        prompt = f"""You are a witty Indian movie curator for @cinedrop on Instagram.
Audience: Indians aged 18-35, love Bollywood and Hollywood, discover films on Instagram.

Movie details:
Title: {movie_title}
Year: {year}
Era: {era}
Cinema: {language_label}
Rating: {rating}/10
Genre: {genre_str}
Overview: {overview}

Streaming:
{platforms_text}

OUTPUT THIS EXACT FORMAT — nothing more, nothing less:

[Hook line — MAX 10 WORDS]

🎬 {movie_title} ({year}) · ⭐{rating}/10 · {language_label}

[ONE sentence. The single most compelling reason to watch. No spoilers. Max 20 words.]

📺 {platforms_text}

[One question to drive comments — max 10 words] 👇

[8 to 10 hashtags on ONE single line separated by spaces]

HOOK RULES BY ERA:
- classic (pre-1995): discovery energy — "Yeh toh legend hai yaar" / "Before OTT, before multiplexes..."
- modern (1995-2015): hidden gem energy — "Log bhool gaye isko" / "The one everyone slept on"
- recent (2016+): pure FOMO — "Abhi dekh. Seriously."

TONE RULES:
- Use Hinglish naturally: yaar, bhai, ekdum solid, bilkul, trust me on this
- Indian film: celebrate with desi pride. Hollywood: frame it for Indian sensibility
- Match genre energy: thriller=tense, comedy=funny, drama=emotional, action=hype, romance=feel
- Sound like a real person, not a bot
- NO filler: no "This film", "Don't miss", "Make sure to watch", "In conclusion"
- Total caption MUST be under 300 characters before hashtags

GOOD EXAMPLE:
Dil ne kaha dekh. Dimaag ne kaha sone ja. Dil jeet gaya.

🎬 Dil Chahta Hai (2001) · ⭐8.1/10 · Bollywood

Three best friends. One decade. Everything changes.

📺 🇮🇳 Netflix · Prime Video

Which friendship era are you in right now? 👇

#bollywood #dilchahtahai #classicbollywood #mustwatch #filmrecommendations #movienight #cinedrop #watchthis #hindifilm #ottnow

BAD EXAMPLE (never do this):
Hey movie lovers! Are you searching for something incredible to watch tonight? This amazing film will absolutely blow your mind with its incredible storyline and amazing performances that will keep you glued...

Only output the caption. No explanations. No notes. No markdown."""

        message = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}]
        )

        caption = message.choices[0].message.content.strip()
        log_message(f"Caption generated successfully ({len(caption)} characters)")
        return caption

    except Exception as e:
        log_message(f"Groq API error: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 4: CREATE VISUAL CARD WITH PILLOW
# ============================================================================

def create_card(movie, streaming_platforms):
    """
    CHANGE 7: Adds language-based coloring and era stamp to visual card.
    """
    try:
        log_message("Creating visual card with Pillow...")

        poster_path = movie.get("poster_path")
        if not poster_path:
            log_message("No poster path available", level="WARNING")
            return None

        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        log_message(f"Downloading poster from {poster_url}")
        
        response = requests.get(poster_url, timeout=10)
        response.raise_for_status()
        poster_image = Image.open(BytesIO(response.content))

        poster_image.thumbnail((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(20, 20, 20))
        
        offset = ((CARD_WIDTH - poster_image.width) // 2, (CARD_HEIGHT - poster_image.height) // 2)
        card.paste(poster_image, offset)

        gradient = Image.new("RGBA", (CARD_WIDTH, 450), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        
        for y in range(450):
            alpha = int((y / 450) * 180)
            gradient_draw.rectangle([(0, y), (CARD_WIDTH, y + 1)], fill=(0, 0, 0, alpha))
        
        gradient = gradient.filter(ImageFilter.GaussianBlur(radius=5))
        card.paste(gradient, (0, CARD_HEIGHT - 450), gradient)

        draw = ImageDraw.Draw(card)

        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
            handle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except OSError:
            try:
                title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 48) if os.name == "nt" else ImageFont.load_default()
                subtitle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 32) if os.name == "nt" else ImageFont.load_default()
                handle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 24) if os.name == "nt" else ImageFont.load_default()
            except:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
                handle_font = ImageFont.load_default()

        # CHANGE 7: Detect language and era for badges
        original_language = movie.get("original_language", "en")
        release_date = movie.get("release_date", "")
        year_int = int(release_date[:4]) if release_date else 0

        if original_language in ["hi", "ta", "te", "ml", "kn"]:
            badge_color = (255, 103, 0)  # Saffron
            cinema_label = {
                "hi": "🇮🇳 Bollywood",
                "ta": "🇮🇳 Tamil",
                "te": "🇮🇳 Telugu",
                "ml": "🇮🇳 Malayalam",
                "kn": "🇮🇳 Kannada"
            }.get(original_language, "🇮🇳 Indian")
        else:
            badge_color = (186, 85, 211)  # Purple
            cinema_label = "🎬 Hollywood"

        if year_int < 1995:
            era_color = (255, 215, 0)  # Gold
            era_text = "🎞️ CLASSIC"
        elif year_int < 2016:
            era_color = (100, 200, 255)  # Light blue
            era_text = "💎 GEM"
        else:
            era_color = (100, 255, 100)  # Light green
            era_text = "⚡ NEW"

        log_message(f"Badge: {cinema_label} | Era: {era_text}")

        genres = movie.get("genres", [])
        genre_text = genres[0]["name"] if genres else "Drama"
        
        badge_padding = 10
        badge_bbox = draw.textbbox((20, 20), genre_text, font=subtitle_font)
        badge_width = badge_bbox[2] - badge_bbox[0] + 2 * badge_padding
        badge_height = badge_bbox[3] - badge_bbox[1] + 2 * badge_padding
        
        draw.rectangle([(15, 15), (15 + badge_width, 15 + badge_height)], fill=badge_color)
        draw.text((15 + badge_padding, 20), genre_text, fill=(255, 255, 255), font=subtitle_font)

        draw.text((15 + badge_padding, 20 + badge_height + 5), cinema_label, fill=(255, 255, 255), font=handle_font)

        era_bbox = draw.textbbox((0, 0), era_text, font=handle_font)
        era_width = era_bbox[2] - era_bbox[0] + 2 * badge_padding
        era_height = era_bbox[3] - era_bbox[1] + 2 * badge_padding
        
        draw.rectangle([(CARD_WIDTH - era_width - 15, 15), (CARD_WIDTH - 15, 15 + era_height)], fill=era_color)
        draw.text((CARD_WIDTH - era_width - 15 + badge_padding, 20), era_text, fill=(0, 0, 0), font=handle_font)

        movie_title = movie.get("title", "Unknown")
        title_bbox = draw.textbbox((0, 0), movie_title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (CARD_WIDTH - title_width) // 2
        title_y = CARD_HEIGHT - 320
        
        draw.text((title_x + 3, title_y + 3), movie_title, fill=(0, 0, 0, 200), font=title_font)
        draw.text((title_x + 1, title_y + 1), movie_title, fill=(50, 50, 50, 150), font=title_font)
        draw.text((title_x, title_y), movie_title, fill=(255, 255, 255), font=title_font)

        rating = round(movie.get("vote_average", 0), 1)
        rating_text = f"⭐ {rating}/10"
        rating_bbox = draw.textbbox((0, 0), rating_text, font=subtitle_font)
        rating_width = rating_bbox[2] - rating_bbox[0]
        rating_x = (CARD_WIDTH - rating_width) // 2
        rating_y = title_y + 60
        
        draw.text((rating_x + 2, rating_y + 2), rating_text, fill=(0, 0, 0, 150), font=subtitle_font)
        draw.text((rating_x, rating_y), rating_text, fill=(255, 223, 0), font=subtitle_font)

        handle_bbox = draw.textbbox((0, 0), PAGE_HANDLE, font=handle_font)
        handle_width = handle_bbox[2] - handle_bbox[0]
        handle_x = CARD_WIDTH - handle_width - 20
        handle_y = CARD_HEIGHT - 40
        
        draw.text((handle_x + 1, handle_y + 1), PAGE_HANDLE, fill=(0, 0, 0, 100), font=handle_font)
        draw.text((handle_x, handle_y), PAGE_HANDLE, fill=(200, 200, 200), font=handle_font)

        CARDS_DIR.mkdir(exist_ok=True)
        card_filename = CARDS_DIR / f"card_{movie['id']}.jpg"
        card.save(card_filename, "JPEG", quality=95)
        
        log_message(f"Visual card created and saved: {card_filename}")
        return str(card_filename)

    except requests.RequestException as e:
        log_message(f"Error downloading poster: {str(e)}", level="ERROR")
        return None
    except Exception as e:
        log_message(f"Error creating card: {str(e)}", level="ERROR")
        return None


# ============================================================================
# STEP 5: PUBLISH TO INSTAGRAM
# ============================================================================

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


# ============================================================================
# STEP 6: SAVE HISTORY
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
    """Main execution flow: fetch movie → get streaming → caption → card → publish → save."""
    try:
        log_message("=" * 80)
        log_message("STARTING DAILY INSTAGRAM MOVIE POST BOT")
        log_message("=" * 80)

        movie = get_movie()
        if not movie:
            log_message("Could not find a suitable movie to post. Exiting.", level="WARNING")
            return

        movie_id = movie["id"]
        movie_title = movie.get("title", "Unknown")

        streaming_platforms = get_streaming_platforms(movie_id)

        caption = write_caption(movie, streaming_platforms)

        image_url = create_card(movie, streaming_platforms)
        if not image_url:
            log_message("Could not generate image. Exiting.", level="ERROR")
            return

        public_image_url = upload_card_to_github(image_url)
        if not public_image_url:
            log_message("Could not host image publicly. Exiting.", level="ERROR")
            return

        log_message("Waiting for image to propagate on GitHub CDN...")
        time.sleep(10)

        post_id = publish_to_instagram(public_image_url, caption)

        save_history(movie, card_path=image_url)

        # CHANGE 11: Enhanced success log
        log_message("=" * 80)
        log_message("SUCCESS SUMMARY")
        log_message("=" * 80)
        log_message(f"Movie       : {movie_title} ({movie.get('release_date', '')[:4]})")
        log_message(f"Cinema      : {movie.get('original_language', 'en').upper()}")
        log_message(f"Rating      : {movie.get('vote_average', 0)}/10")
        log_message(f"🇮🇳 India    : {', '.join(streaming_platforms['IN']) or 'Not streaming'}")
        log_message(f"🇺🇸 US       : {', '.join(streaming_platforms['US']) or 'Not streaming'}")
        log_message(f"Post ID     : {post_id}")
        log_message(f"Card        : {public_image_url}")
        log_message("=" * 80)

    except Exception as e:
        log_message("=" * 80, level="ERROR")
        log_message(f"FATAL ERROR: {str(e)}", level="ERROR")
        log_message("=" * 80, level="ERROR")
        raise


if __name__ == "__main__":
    main()
