"""
Instagram Daily Movie Post Bot
Automatically generates and publishes engaging movie posts to Instagram daily via GitHub Actions.
"""

import os
import json
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

# API Base URLs
TMDB_BASE_URL = "https://api.themoviedb.org/3"
INSTAGRAM_GRAPH_BASE_URL = "https://graph.instagram.com/v18.0"
TMDB_IMAGE_BASE_URL = "https://image.tmdb.org/t/p/w500"

# Image card settings
PAGE_HANDLE = "@cinedrop"
CARD_WIDTH = 1080
CARD_HEIGHT = 1350

# Genre mapping by day of week (0=Monday, 6=Sunday)
GENRE_BY_DAY = {
    0: {"name": "Thriller", "id": 53},
    1: {"name": "Comedy", "id": 35},
    2: {"name": "Horror", "id": 27},
    3: {"name": "Drama", "id": 18},
    4: {"name": "Action", "id": 28},
    5: {"name": "Science Fiction", "id": 878},
    6: {"name": "Romance", "id": 10749},
}

# Streaming platform mappings
# TMDb uses provider IDs, we map them to readable names
PROVIDER_MAPPING = {
    # Common providers across both regions
    8: "Netflix",
    119: "Amazon Prime Video",
    35: "Apple TV+",
    # India-specific
    1685: "Disney+ Hotstar",
    386: "Zee5",
    1476: "SonyLIV",
    1820: "JioCinema",
    190: "Mubi",
    # US-specific
    15: "Hulu",
    384: "HBO Max",
    386: "Peacock",
    38: "Paramount+",
    7: "Disney+",
    1852: "Mubi",
}

# Path to history file
POSTED_MOVIES_FILE = Path("posted_movies.json")

# Temporary directory for images
TEMP_DIR = Path("/tmp" if os.name != "nt" else os.getenv("TEMP", "./temp"))


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def load_posted_movies():
    """Load the list of previously posted movie IDs from history file."""
    if POSTED_MOVIES_FILE.exists():
        with open(POSTED_MOVIES_FILE, "r") as f:
            return json.load(f)
    return []


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
    Fetch a random high-quality movie from TMDb API.
    Filters by minimum rating 7.0+, excludes already-posted movies, uses today's genre.
    Returns: dict with movie data (id, title, overview, poster_path, vote_average, release_date, genres)
    """
    if not TMDB_API_KEY:
        raise ValueError("TMDB_API_KEY not found in environment variables")

    try:
        log_message("Fetching movie from TMDb API...")

        posted_movies = load_posted_movies()
        today_genre = get_today_genre()
        
        # Discover endpoint: get popular, high-rated movies of today's genre
        url = f"{TMDB_BASE_URL}/discover/movie"
        params = {
            "api_key": TMDB_API_KEY,
            "with_genres": today_genre["id"],
            "vote_average.gte": 7.0,
            "sort_by": "popularity.desc",
            "include_adult": False,
            "language": "en-US",
            "page": 1,
        }

        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data.get("results"):
            log_message(f"No movies found for {today_genre['name']}", level="WARNING")
            return None

        # Filter out already-posted movies and pick the first available
        movies = data["results"]
        movie = None
        for m in movies:
            if m["id"] not in posted_movies:
                movie = m
                break

        if not movie:
            log_message(f"All {today_genre['name']} movies already posted", level="WARNING")
            return None

        log_message(f"Selected movie: '{movie['title']}' (ID: {movie['id']}) - Rating: {movie['vote_average']}/10")
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
    Use Groq API (free tier, llama3-8b-8192 model) to generate an engaging Instagram caption.
    Caption includes: hook line, movie info, why to watch, streaming availability, engagement question, hashtags.
    Returns: str with the complete caption
    """
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not found in environment variables")

    try:
        log_message("Generating caption with Groq API...")

        client = Groq(api_key=GROQ_API_KEY)

        # Format streaming info for the prompt (generic, no country labels)
        # Combine platforms from both regions and deduplicate
        all_platforms = sorted(list(set(streaming_platforms["IN"] + streaming_platforms["US"])))
        platforms_text = ", ".join(all_platforms) if all_platforms else "Not streaming — rental/purchase only 🎬"

        movie_title = movie.get("title", "Unknown")
        release_date = movie.get("release_date", "")
        year = release_date[:4] if release_date else "N/A"
        rating = round(movie.get("vote_average", 0), 1)
        overview = movie.get("overview", "")
        genres = movie.get("genres", [])
        genre_str = ", ".join([g["name"] for g in genres]) if genres else "Drama"

        prompt = f"""Write the FUNNIEST, most engaging Instagram caption for this movie that'll make people stop scrolling and actually WANT to watch it.

Movie Details:
- Title: {movie_title}
- Year: {year}
- Rating: {rating}/10
- Genres: {genre_str}
- Overview: {overview}

Streaming Availability:
- Platforms: {platforms_text}

🎯 TONE & VIBES (CRITICAL):
- Write like you're texting a close friend who has impeccable taste in movies
- Be FUNNY, witty, use humor/sarcasm naturally (don't be cringey)
- Sound REAL, not like a bot - use relatable language
- Create FOMO - make them feel like they're seriously missing out
- Use casual phrases: "if you love...", "trust me on this...", "this one HIT different"
- Be confident in recommending it, like you just watched it and had to tell someone
- Conversational AF - like a genuine recommendation from a friend

📋 STRUCTURE:
1. HOOK: Super witty, funny, or curiosity-driven opening line (make it memorable!)
2. WHY WATCH: 2-3 casual sentences explaining why this film slaps (NO spoilers ever)
3. MOVIE INFO: Title, year, rating, genre (with emojis for flavor)
4. PLATFORMS: List where to watch (clean and simple, no flags)
5. ENGAGEMENT: Funny/spicy question, debate, or challenge to get comments
6. HASHTAGS: 10-15 relevant tags (avoid 1M+ post tags)
7. OVERALL: Under 2200 characters, punchy, readable, shareable

✨ BONUS TOUCHES:
- Use relevant emojis naturally (not overdone)
- If it's a comedy - be FUNNY
- If it's a thriller - build suspense/mystery
- If it's drama - be emotionally compelling
- Mix in pop culture references if they fit
- Make the engagement question fun, not forced

Format your response EXACTLY like this:
[Super witty/funny hook line]

🎬 [Movie Title] ([Year])
⭐ [Rating]/10 · [Genre]

[2-3 casual, conversational sentences - why this film is incredible]

📺 Where to watch:
{platforms_text}

[Funny/spicy/engaging question to drive comments]

[Hashtags]

IMPORTANT: Only output the caption, nothing else. No explanations, no notes."""

        message = client.messages.create(
            model="llama3-8b-8192",
            max_tokens=2000,
            messages=[
                {"role": "user", "content": prompt}
            ]
        )

        caption = message.content[0].text.strip()
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

        # Add genre badge in top-left corner (vibrant purple/magenta)
        genres = movie.get("genres", [])
        genre_text = genres[0]["name"] if genres else "Drama"
        
        # Create badge background with vibrant color
        badge_padding = 10
        badge_bbox = draw.textbbox((20, 20), genre_text, font=subtitle_font)
        badge_width = badge_bbox[2] - badge_bbox[0] + 2 * badge_padding
        badge_height = badge_bbox[3] - badge_bbox[1] + 2 * badge_padding
        
        draw.rectangle(
            [(15, 15), (15 + badge_width, 15 + badge_height)],
            fill=(186, 85, 211),  # Medium orchid - vibrant purple
        )
        draw.text((15 + badge_padding, 20), genre_text, fill=(255, 255, 255), font=subtitle_font)

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

        # Save the card locally
        TEMP_DIR.mkdir(exist_ok=True)
        card_filename = TEMP_DIR / f"card_{movie['id']}.jpg"
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
        raise
    except Exception as e:
        log_message(f"Unexpected error publishing to Instagram: {str(e)}", level="ERROR")
        raise


# ============================================================================
# STEP 6: SAVE HISTORY
# ============================================================================

def save_history(movie_id):
    """
    Save the posted movie's TMDb ID to posted_movies.json so we don't repeat it.
    Also commits the file back to the GitHub repo.
    """
    try:
        log_message(f"Saving movie ID {movie_id} to history...")

        posted_movies = load_posted_movies()
        if movie_id not in posted_movies:
            posted_movies.append(movie_id)

        with open(POSTED_MOVIES_FILE, "w") as f:
            json.dump(posted_movies, f, indent=2)

        log_message(f"History updated. Total movies posted: {len(posted_movies)}")

        # Commit back to GitHub repo if GH_TOKEN is available
        if GH_TOKEN:
            try:
                log_message("Committing posted_movies.json back to repository...")
                # Note: This requires git to be configured in the GitHub Actions environment
                # The workflow file handles this with: git config --global user.name "GitHub Actions" etc.
                os.system(f'git add {POSTED_MOVIES_FILE}')
                os.system('git commit -m "Auto: Update posted movies history"')
                os.system('git push')
                log_message("Repository updated successfully")
            except Exception as e:
                log_message(f"Git commit/push error: {str(e)}", level="WARNING")
        else:
            log_message("GH_TOKEN not set - skipping git commit (file saved locally)", level="WARNING")

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

        # Step 5: Publish to Instagram
        post_id = publish_to_instagram(image_url, caption)

        # Step 6: Save to history
        save_history(movie_id)

        # Success summary
        log_message("=" * 80)
        log_message("SUCCESS SUMMARY")
        log_message("=" * 80)
        log_message(f"Movie Title: {movie_title}")
        log_message(f"Movie ID: {movie_id}")
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
