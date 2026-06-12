"""
Instagram Daily Movie Post Bot
Automatically generates and publishes engaging movie posts to Instagram daily via GitHub Actions.
"""

import os
import json
import time
import base64
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
# Note: Canva API is not used. Image generation uses Pillow (local processing)

# Separate "state" repository that stores the posted-movies history.
# HISTORY_REPO_TOKEN must be a Personal Access Token with write (contents) access
# to HISTORY_REPO. Falls back to GH_TOKEN if not provided.
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

# Genre mapping by day of week (0=Monday, 6=Sunday) — India-friendly selection
GENRE_BY_DAY = {
    0: {"name": "Thriller", "id": 53},
    1: {"name": "Family", "id": 10751},
    2: {"name": "Action", "id": 28},
    3: {"name": "Drama", "id": 18},
    4: {"name": "Comedy", "id": 35},
    5: {"name": "Romance", "id": 10749},
    6: {"name": "Science Fiction", "id": 878},
}

# Streaming platform mappings (corrected TMDb provider IDs)
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

# Directory (inside the repo) where generated cards are stored so they can be
# served publicly via raw.githubusercontent.com for Instagram to fetch.
CARDS_DIR = Path("cards")


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

# Cache the SHA of the history file in the state repo so we can update it.
_HISTORY_FILE_SHA = None


def _history_api_headers():
    """Build auth headers for the GitHub Contents API."""
    return {
        "Authorization": f"Bearer {HISTORY_REPO_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def load_posted_movies():
    """Load the posted-movies history from the separate state repo via the GitHub
    Contents API. Each entry is a dict: {"id", "title", "rating", "date"}.
    Falls back to a local file (and legacy list-of-ints format) if the remote
    repo is unavailable. Caches the remote file SHA for the subsequent update.
    """
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
                    return [{"id": mid, "title": "", "rating": None, "date": ""} for mid in data]
                return data
            elif resp.status_code == 404:
                # File doesn't exist yet in the state repo — start fresh
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
            return [{"id": mid, "title": "", "rating": None, "date": ""} for mid in data]
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
    Fetch high-quality movies spanning multiple eras (classics to recent releases).
    Queries both Hollywood (English) and Indian language films across three time periods:
    - Golden classics (1950–1994): ranked by vote_average.desc
    - Modern classics (1995–2015): ranked by popularity.desc
    - Recent (2016–present): ranked by popularity.desc
    Merges all results, deduplicates by ID, excludes already-posted movies, uses today's genre.
    Returns: dict with movie data (id, title, overview, poster_path, vote_average, 
             release_date, genres, original_language)
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not found in environment variables")

    try:
        import random
        log_message("Fetching movies from TMDb API across eras (classics to recent)...")

        posted_ids = get_posted_ids()
        today_genre = get_today_genre()
        
        # Define era filters: date ranges and vote count thresholds
        ERA_FILTERS = [
            {
                "name": "Golden Classics (1950–1994)",
                "primary_release_date.gte": "1950-01-01",
                "primary_release_date.lte": "1994-12-31",
                "vote_count.gte": 500,
                "sort_by": "vote_average.desc",  # Rank classics by quality, not popularity
            },
            {
                "name": "Modern Classics (1995–2015)",
                "primary_release_date.gte": "1995-01-01",
                "primary_release_date.lte": "2015-12-31",
                "vote_count.gte": 300,
                "sort_by": "popularity.desc",
            },
            {
                "name": "Recent (2016–present)",
                "primary_release_date.gte": "2016-01-01",
                "vote_count.gte": 100,
                "sort_by": "popularity.desc",
            },
        ]

        all_movies = []
        url = f"{TMDB_BASE_URL}/discover/movie"

        # Make 6 API calls: 3 eras × 2 language groups (English + Indian)
        for era in ERA_FILTERS:
            era_name = era["name"]
            
            # Call 1: English films in this era
            params_english = {
                "api_key": TMDB_API_KEY,
                "with_genres": today_genre["id"],
                "vote_average.gte": 7.0,
                "include_adult": False,
                "language": "en-US",
                "with_original_language": "en",
                "primary_release_date.gte": era["primary_release_date.gte"],
                "vote_count.gte": era["vote_count.gte"],
                "sort_by": era["sort_by"],
                "page": 1,
            }
            if "primary_release_date.lte" in era:
                params_english["primary_release_date.lte"] = era["primary_release_date.lte"]

            try:
                response_english = requests.get(url, params=params_english, timeout=10)
                response_english.raise_for_status()
                english_movies = response_english.json().get("results", [])
                log_message(f"  {era_name}: Found {len(english_movies)} English films")
                all_movies.extend(english_movies)
            except Exception as e:
                log_message(f"  {era_name} (English): {str(e)}", level="WARNING")

            # Call 2: Indian language films in this era
            params_indian = {
                "api_key": TMDB_API_KEY,
                "with_genres": today_genre["id"],
                "vote_average.gte": 7.0,
                "include_adult": False,
                "language": "en-US",
                "with_original_language": "hi|ta|te|ml|kn",
                "region": "IN",
                "primary_release_date.gte": era["primary_release_date.gte"],
                "vote_count.gte": era["vote_count.gte"],
                "sort_by": era["sort_by"],
                "page": 1,
            }
            if "primary_release_date.lte" in era:
                params_indian["primary_release_date.lte"] = era["primary_release_date.lte"]

            try:
                response_indian = requests.get(url, params=params_indian, timeout=10)
                response_indian.raise_for_status()
                indian_movies = response_indian.json().get("results", [])
                log_message(f"  {era_name}: Found {len(indian_movies)} Indian language films")
                all_movies.extend(indian_movies)
            except Exception as e:
                log_message(f"  {era_name} (Indian): {str(e)}", level="WARNING")

        # Deduplicate by movie ID
        seen_ids = set()
        unique_movies = []
        for m in all_movies:
            if m["id"] not in seen_ids:
                seen_ids.add(m["id"])
                unique_movies.append(m)

        log_message(f"Total merged pool: {len(unique_movies)} unique films from all eras")

        if not unique_movies:
            log_message(f"No movies found for {today_genre['name']}", level="WARNING")
            return None

        # Shuffle to add variety across eras
        random.shuffle(unique_movies)

        # Filter out already-posted movies and pick the first available
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

        # Determine which era this film belongs to
        year = int(movie.get("release_date", "2020")[:4]) if movie.get("release_date") else 2020
        if year < 1995:
            era_label = "Golden Classic"
        elif year < 2016:
            era_label = "Modern Classic"
        else:
            era_label = "Recent"

        log_message(f"Selected movie: '{movie['title']}' ({year}) - {lang_label} {era_label} - Rating: {movie['vote_average']}/10")
        return movie

    except requests.RequestException as e:
        log_message(f"TMDb API error: {str(e)}", level="ERROR")
        raise
    except Exception as e:
        log_message(f"Unexpected error fetching movie: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 2: GET STREAMING PLATFORMS
# ============================================================================

def get_streaming_platforms(movie_id):
    """
    Fetch streaming availability for India (IN) and US from TMDb API.
    Returns: dict with keys 'IN' and 'US', each containing list of streaming platforms
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not found in environment variables")

    try:
        log_message(f"Fetching streaming platforms for movie ID {movie_id}...")

        url = f"{TMDB_BASE_URL}/movie/{movie_id}/watch/providers"
        params = {"api_key": TMDB_API_KEY}

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        streaming_platforms = {
            "IN": [],
            "US": [],
        }

        results = data.get("results", {})

        # Extract flatrate (subscription) providers for each region
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
        # Return empty availability but don't fail - we'll use fallback message
        return {"IN": [], "US": []}
    except Exception as e:
        log_message(f"Unexpected error fetching streaming platforms: {str(e)}", level="ERROR")
        return {"IN": [], "US": []}


# ============================================================================
# STEP 3: GENERATE CAPTION USING GROQ
# ============================================================================

def write_caption(movie, streaming_platforms):
    """
    Use Groq API (llama-3.3-70b-versatile model) to generate an India-focused Instagram caption.
    Detects film language (Bollywood/Regional/Hollywood) and tailors tone accordingly.
    Returns: str with the complete caption
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment variables")

    try:
        log_message("Generating caption with Groq API...")

        # Initialize Groq client
        client = Groq(api_key=GROQ_API_KEY)

        # Detect film language and create appropriate label
        original_language = movie.get("original_language", "en")
        language_label = {
            "hi": "Bollywood",
            "ta": "Tamil",
            "te": "Telugu",
            "ml": "Malayalam",
            "kn": "Kannada",
        }.get(original_language, "Hollywood")

        # Format streaming info: India-first display with flags
        india_platforms = streaming_platforms.get("IN", [])
        us_only_platforms = [p for p in streaming_platforms.get("US", []) if p not in india_platforms]

        if india_platforms:
            platforms_text = f"🇮🇳 {' · '.join(india_platforms)}"
            if us_only_platforms:
                platforms_text += f"\n🇺🇸 {' · '.join(us_only_platforms)}"
        else:
            platforms_text = "Not streaming — rental/purchase only 🎬"

        movie_title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        rating = round(movie.get("vote_average", 0), 1)
        overview = movie.get("overview", "")
        genres = movie.get("genres", [])
        genre_str = ", ".join([g["name"] for g in genres]) if genres else "Drama"

        # Determine film era for tone guidance
        try:
            year_int = int(year)
            if year_int < 1995:
                era_label = "Golden Classic"
                era_tone = """
- If the film is from before 1995, open with something like "Yeh toh classic hai yaar 🎞️" or "Before Netflix, before OTT — this one defined cinema"
- Make classics feel like a discovery, not old news
- Frame the timelessness: "Decades old par abhi bhi relevant" or "Yeh film aaj ke generation ko dekhna chahiye"
- NEVER make an old film sound dated or boring — sell the cinematic brilliance and legacy"""
            elif year_int < 2016:
                era_label = "Modern Classic"
                era_tone = """
- If the film is between 1995–2015, frame it as a hidden gem or underrated masterpiece people may have missed
- "Sab ko nahi pata par ye film masterpiece hai" — discovery angle
- Emphasize why it's been overlooked and why NOW is the time to watch
- Make it feel like you're introducing them to something special and timeless"""
            else:
                era_label = "Recent Release"
                era_tone = """
- If recent (2016–present), create urgency and FOMO
- "Fresh, relevant, and everyone's talking about it" — emphasize timeliness
- New films deserve hype and momentum"""
        except:
            era_label = "Film"
            era_tone = ""

        log_message(f"Detected film language: {language_label} | Era: {era_label}")

        prompt = f"""You are a witty, culturally-aware Indian movie curator writing for an Instagram page called @cinedrop.
Your audience is Indian (18-35), bilingual (Hindi/English), loves both Bollywood and Hollywood,
and discovers movies on Instagram reels and posts.

Movie Details:
- Title: {movie_title}
- Year: {year}
- Rating: {rating}/10
- Language: {language_label}
- Era: {era_label}
- Genres: {genre_str}
- Overview: {overview}

Streaming Availability:
{platforms_text}

🎯 TONE & STYLE (NON-NEGOTIABLE):
- Write like a cool Indian friend with great taste — not a bot
- If the film is Indian (Bollywood/Tamil/Telugu/Malayalam/Kannada), CELEBRATE it with desi pride
- If Hollywood, frame it specifically for what Indian audiences will love about it
- Use Hinglish naturally where it fits: "yaar", "bilkul solid", "ekdum", "bhai", "yaad rakh"
- Reference Indian culture naturally: chai-movie nights, weekend binge, family drama vibes, "log bolte hain..."
- Be FUNNY, real, and conversational — no cringe, no corporate tone
- Match the genre energy: thriller = suspense, comedy = funny, romance = emotional, action = hype
- NEVER make an old film sound dated or boring — sell the timelessness
{era_tone}

📋 CAPTION STRUCTURE (follow exactly):

[One killer hook line — funny, mysterious, or emotional depending on genre]

🎬 [Movie Title] ([Year])
⭐ [Rating]/10 · [Genre] · [Language: Bollywood / Tamil / Telugu / Hollywood etc.]

[2-3 casual sentences on why this film is incredible — no spoilers, desi lens]

📺 Kahan dekhein:
{platforms_text}

[Spicy question or debate to drive comments — make it fun and India-relevant]

[10-15 hashtags — mix of English and Hindi tags, avoid tags with 1M+ posts]

RULES:
- Total caption under 2200 characters
- Only output the caption, nothing else
- No explanations, no markdown, no extra notes
- Hashtags on the last line only
"""

        message = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
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
    Create a branded visual card using Pillow library.
    Downloads TMDb poster, adds title overlay, gradient, genre badge, and page handle.
    Returns: str with the path to the generated image file (local or uploaded URL)
    """
    try:
        log_message("Creating visual card with Pillow...")

        poster_path = movie.get("poster_path")
        if not poster_path:
            log_message("No poster path available", level="WARNING")
            return None

        # Download poster image from TMDb
        poster_url = f"{TMDB_IMAGE_BASE_URL}{poster_path}"
        log_message(f"Downloading poster from {poster_url}")
        
        response = requests.get(poster_url, timeout=10)
        response.raise_for_status()
        poster_image = Image.open(BytesIO(response.content))

        # Resize to standard Instagram card size (1080x1350)
        # Keep aspect ratio and pad if needed
        poster_image.thumbnail((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(20, 20, 20))
        
        # Center the poster on the card
        offset = ((CARD_WIDTH - poster_image.width) // 2, (CARD_HEIGHT - poster_image.height) // 2)
        card.paste(poster_image, offset)

        # Create a semi-transparent dark gradient overlay at the bottom (for text readability)
        gradient = Image.new("RGBA", (CARD_WIDTH, 450), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        
        # Draw semi-transparent gradient from transparent to dark
        for y in range(450):
            alpha = int((y / 450) * 180)  # Fade from 0 to 180 alpha
            gradient_draw.rectangle([(0, y), (CARD_WIDTH, y + 1)], fill=(0, 0, 0, alpha))
        
        # Apply gradient overlay
        gradient = gradient.filter(ImageFilter.GaussianBlur(radius=5))
        card.paste(gradient, (0, CARD_HEIGHT - 450), gradient)

        draw = ImageDraw.Draw(card)

        # Load fonts (use default if system fonts not available)
        try:
            title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            subtitle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 32)
            handle_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 24)
        except OSError:
            # Fallback to default font if truetype not available (Windows/Mac)
            try:
                title_font = ImageFont.truetype("C:\\Windows\\Fonts\\arialbd.ttf", 48) if os.name == "nt" else ImageFont.load_default()
                subtitle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 32) if os.name == "nt" else ImageFont.load_default()
                handle_font = ImageFont.truetype("C:\\Windows\\Fonts\\arial.ttf", 24) if os.name == "nt" else ImageFont.load_default()
            except:
                title_font = ImageFont.load_default()
                subtitle_font = ImageFont.load_default()
                handle_font = ImageFont.load_default()

        # Detect film language and set badge color accordingly
        original_language = movie.get("original_language", "en")
        if original_language in ["hi", "ta", "te", "ml", "kn"]:
            badge_color = (255, 103, 0)    # Saffron orange — Indian films
            is_indian_film = True
        else:
            badge_color = (186, 85, 211)   # Purple — Hollywood
            is_indian_film = False

        log_message(f"Badge color: {'Saffron (Indian film)' if is_indian_film else 'Purple (Hollywood)'}")

        # Add genre badge in top-left corner
        genres = movie.get("genres", [])
        genre_text = genres[0]["name"] if genres else "Drama"
        
        # Create badge background with appropriate color
        badge_padding = 10
        badge_bbox = draw.textbbox((20, 20), genre_text, font=subtitle_font)
        badge_width = badge_bbox[2] - badge_bbox[0] + 2 * badge_padding
        badge_height = badge_bbox[3] - badge_bbox[1] + 2 * badge_padding
        
        draw.rectangle(
            [(15, 15), (15 + badge_width, 15 + badge_height)],
            fill=badge_color,
        )
        draw.text((15 + badge_padding, 20), genre_text, fill=(255, 255, 255), font=subtitle_font)

        # Add language label below the genre badge
        language_label = {
            "hi": "🇮🇳 Bollywood",
            "ta": "🇮🇳 Tamil",
            "te": "🇮🇳 Telugu",
            "ml": "🇮🇳 Malayalam",
            "kn": "🇮🇳 Kannada",
        }.get(original_language, "🎬 Hollywood")

        draw.text((15 + badge_padding, 20 + badge_height + 5), language_label, fill=(255, 255, 255), font=handle_font)

        # Add movie title at the bottom with glow effect
        movie_title = movie.get("title", "Unknown")
        title_bbox = draw.textbbox((0, 0), movie_title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (CARD_WIDTH - title_width) // 2  # Center horizontally
        title_y = CARD_HEIGHT - 320
        
        # Add glow/shadow effect for better readability
        draw.text((title_x + 3, title_y + 3), movie_title, fill=(0, 0, 0, 200), font=title_font)
        draw.text((title_x + 1, title_y + 1), movie_title, fill=(50, 50, 50, 150), font=title_font)
        draw.text((title_x, title_y), movie_title, fill=(255, 255, 255), font=title_font)

        # Add rating below title with vibrant color
        rating = round(movie.get("vote_average", 0), 1)
        rating_text = f"⭐ {rating}/10"
        rating_bbox = draw.textbbox((0, 0), rating_text, font=subtitle_font)
        rating_width = rating_bbox[2] - rating_bbox[0]
        rating_x = (CARD_WIDTH - rating_width) // 2
        rating_y = title_y + 60
        
        # Add glow effect to rating
        draw.text((rating_x + 2, rating_y + 2), rating_text, fill=(0, 0, 0, 150), font=subtitle_font)
        draw.text((rating_x, rating_y), rating_text, fill=(255, 223, 0), font=subtitle_font)  # Brighter gold

        # Add page handle in bottom-right corner
        handle_bbox = draw.textbbox((0, 0), PAGE_HANDLE, font=handle_font)
        handle_width = handle_bbox[2] - handle_bbox[0]
        handle_x = CARD_WIDTH - handle_width - 20
        handle_y = CARD_HEIGHT - 40
        
        draw.text((handle_x + 1, handle_y + 1), PAGE_HANDLE, fill=(0, 0, 0, 100), font=handle_font)
        draw.text((handle_x, handle_y), PAGE_HANDLE, fill=(200, 200, 200), font=handle_font)

        # Save the card inside the repo's cards/ directory so it can be committed
        # and served publicly (Instagram needs a public HTTPS image URL).
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
    """
    Commit and push the generated card image to the GitHub repository so it can be
    served publicly via raw.githubusercontent.com. Instagram's Graph API requires a
    publicly accessible HTTPS image URL (it cannot read local files).
    Returns: str public raw URL to the image, or None if it cannot be hosted.
    """
    try:
        # Determine the repo "owner/name" (set automatically in GitHub Actions)
        repo = os.getenv("GITHUB_REPOSITORY")
        if not repo:
            # Fall back to parsing the git remote URL locally
            try:
                import subprocess
                remote = subprocess.check_output(
                    ["git", "config", "--get", "remote.origin.url"],
                    text=True,
                ).strip()
                # Normalize git@github.com:owner/repo.git or https://github.com/owner/repo.git
                remote = remote.replace("git@github.com:", "").replace(
                    "https://github.com/", ""
                )
                repo = remote[:-4] if remote.endswith(".git") else remote
            except Exception:
                repo = None

        if not repo:
            log_message("Could not determine GitHub repository - cannot host image", level="ERROR")
            return None

        # Determine current branch (default to main)
        branch = os.getenv("GITHUB_REF_NAME", "main")

        log_message(f"Pushing card image to GitHub ({repo}@{branch}) for public hosting...")

        os.system(f'git add "{card_path}"')
        os.system('git commit -m "Auto: Add daily movie card image" || echo "nothing to commit"')
        push_result = os.system("git push")
        if push_result != 0:
            log_message("git push for card image returned non-zero status", level="WARNING")

        # Build the public raw URL
        public_url = f"https://raw.githubusercontent.com/{repo}/{branch}/{card_path}".replace("\\", "/")
        log_message(f"Card image hosted at: {public_url}")
        return public_url

    except Exception as e:
        log_message(f"Error hosting card image on GitHub: {str(e)}", level="ERROR")
        return None


def publish_to_instagram(image_url, caption):
    """
    Publish image and caption to Instagram using the Instagram Graph API.
    Flow: Create image container -> Upload image -> Publish
    Returns: str with the Instagram post ID
    """
    if not INSTAGRAM_ACCESS_TOKEN or not INSTAGRAM_ACCOUNT_ID:
        raise ValueError("INSTAGRAM_ACCESS_TOKEN or INSTAGRAM_ACCOUNT_ID not found in environment variables")

    try:
        log_message("Publishing to Instagram...")

        # Step 1: Create a media container (image upload)
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

        # Give Instagram a moment to process the media before publishing
        log_message("Waiting for media to be processed by Instagram...")
        time.sleep(5)

        # Step 2: Publish the media
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
        # Surface the actual API response body to aid debugging
        resp = getattr(e, "response", None)
        if resp is not None:
            log_message(f"Instagram API response: {resp.text}", level="ERROR")
        raise
    except Exception as e:
        log_message(f"Unexpected error publishing to Instagram: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 6: SAVE HISTORY
# ============================================================================

def save_history(movie, card_path=None):
    """
    Append the posted movie (id + title + rating + date) to the history and write it
    back to the separate state repo (HISTORY_REPO) via the GitHub Contents API.
    The card image stays in the bot repo and is handled separately.
    """
    global _HISTORY_FILE_SHA
    try:
        movie_id = movie["id"]
        movie_title = movie.get("title", "Unknown")
        log_message(f"Saving '{movie_title}' (ID: {movie_id}) to history...")

        history = load_posted_movies()
        if movie_id not in get_posted_ids(history):
            history.append({
                "id": movie_id,
                "title": movie_title,
                "rating": round(movie.get("vote_average", 0), 1),
                "date": datetime.utcnow().strftime("%Y-%m-%d"),
            })

        content_str = json.dumps(history, indent=2, ensure_ascii=False)

        if not HISTORY_REPO_TOKEN:
            log_message("HISTORY_REPO_TOKEN/GH_TOKEN not set - saving history locally only.", level="WARNING")
            with open(POSTED_MOVIES_FILE, "w") as f:
                f.write(content_str)
            return

        # Write the updated history back to the state repo via the Contents API
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
    """Main execution flow: fetch movie → get streaming info → generate caption → create card → publish → save history."""
    try:
        log_message("=" * 80)
        log_message("STARTING DAILY INSTAGRAM MOVIE POST BOT")
        log_message("=" * 80)

        # Step 1: Get a movie
        movie = get_movie()
        if not movie:
            log_message("Could not find a suitable movie to post. Exiting.", level="WARNING")
            return

        movie_id = movie["id"]
        movie_title = movie.get("title", "Unknown")

        # Step 2: Get streaming platforms for India and US
        streaming_platforms = get_streaming_platforms(movie_id)

        # Step 3: Generate caption using Groq
        caption = write_caption(movie, streaming_platforms)

        # Step 4: Create visual card with Canva (or use TMDb poster as fallback)
        image_url = create_card(movie, streaming_platforms)
        if not image_url:
            log_message("Could not generate image. Exiting.", level="ERROR")
            return

        # Step 4b: Host the card publicly (Instagram requires a public HTTPS URL)
        public_image_url = upload_card_to_github(image_url)
        if not public_image_url:
            log_message("Could not host image publicly. Exiting.", level="ERROR")
            return

        # Give raw.githubusercontent.com a moment to serve the freshly pushed image
        log_message("Waiting for image to propagate on GitHub CDN...")
        time.sleep(10)

        # Step 5: Publish to Instagram
        post_id = publish_to_instagram(public_image_url, caption)

        # Step 6: Save to history (and clean up the card image)
        save_history(movie, card_path=image_url)

        # Determine film language/type for summary
        original_language = movie.get("original_language", "en")
        language_label = {
            "hi": "Bollywood",
            "ta": "Tamil",
            "te": "Telugu",
            "ml": "Malayalam",
            "kn": "Kannada",
        }.get(original_language, "Hollywood")

        # Determine film era
        release_date = movie.get("release_date", "")
        year = int(release_date[:4]) if release_date and release_date[:4].isdigit() else 2020
        if year < 1995:
            era_label = "Golden Classic"
        elif year < 2016:
            era_label = "Modern Classic"
        else:
            era_label = "Recent Release"

        # Success summary
        log_message("=" * 80)
        log_message("SUCCESS SUMMARY")
        log_message("=" * 80)
        log_message(f"Movie Title: {movie_title}")
        log_message(f"Movie ID: {movie_id}")
        log_message(f"Release Year: {year}")
        log_message(f"Film Type: {language_label} | Era: {era_label}")
        log_message(f"India Platforms: {', '.join(streaming_platforms['IN']) or 'Not streaming'}")
        log_message(f"US Platforms: {', '.join(streaming_platforms['US']) or 'Not streaming'}")
        log_message(f"Instagram Post ID: {post_id}")
        log_message("=" * 80)

    except Exception as e:
        log_message("=" * 80, level="ERROR")
        log_message(f"FATAL ERROR: {str(e)}", level="ERROR")
        log_message("=" * 80, level="ERROR")
        raise


if __name__ == "__main__":
    main()
