"""
Demo/Sample Test for Instagram Movie Bot
Generate a sample card without needing API keys
"""

import os
import json
import requests
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from io import BytesIO

# ============================================================================
# SAMPLE MOVIE DATA (No API calls needed)
# ============================================================================

sample_movie = {
    "id": 550,
    "title": "Fight Club",
    "overview": "A ticking-time-bomb incarcerator and a demystifying unveiler of essential philosophical concepts walks into a gym and sneaks candy into a night of fleece.",
    "poster_path": "/pB8BM7pdSp6B6Io7b1DwaO1l8fr.jpg",
    "vote_average": 8.8,
    "release_date": "1999-10-15",
    "genres": [{"id": 18, "name": "Drama"}],
}

sample_streaming = {
    "IN": ["Netflix", "Amazon Prime Video"],
    "US": ["Netflix", "Amazon Prime Video", "HBO Max"]
}

sample_caption = """Tired of your boring routine? This psychological thriller will shake your entire perspective.

🎬 Fight Club (1999)
⭐ 8.8/10 · Drama

A masterpiece about identity, consumerism, and rebellion. Directed by David Fincher with an iconic twist ending that changes everything. No spoilers, but you'll rewatch it.

📺 Where to watch:
Amazon Prime Video, HBO Max, Netflix

Would you take the red pill? What's the one movie that completely changed how you see the world?

#FightClub #DavidFincher #PsychologicalThriller #CinematicMasterpiece #MovieNightMustWatch #FilmGeek #IndieFlicks #HiddenGems #MovieRecommendation #ClassicFilm #ThrillerCinema #FilmTwitter #ScreenGems #CinephileLife"""

# ============================================================================
# CREATE SAMPLE CARD (Uses Pillow locally)
# ============================================================================

def create_sample_card():
    """Create a branded visual card using Pillow library."""
    
    print("🎨 Creating sample visual card...")
    
    try:
        # Download poster image from TMDb
        poster_url = f"https://image.tmdb.org/t/p/w500{sample_movie['poster_path']}"
        print(f"   Downloading poster: {poster_url}")
        
        response = requests.get(poster_url, timeout=10)
        response.raise_for_status()
        poster_image = Image.open(BytesIO(response.content))
        print("   ✅ Poster downloaded")
        
        # Create card (1080x1350px for Instagram)
        CARD_WIDTH, CARD_HEIGHT = 1080, 1350
        poster_image.thumbnail((CARD_WIDTH, CARD_HEIGHT), Image.Resampling.LANCZOS)
        card = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), color=(20, 20, 20))
        
        # Center poster
        offset = ((CARD_WIDTH - poster_image.width) // 2, (CARD_HEIGHT - poster_image.height) // 2)
        card.paste(poster_image, offset)
        
        # Dark gradient overlay at bottom
        gradient = Image.new("RGBA", (CARD_WIDTH, 450), (0, 0, 0, 0))
        gradient_draw = ImageDraw.Draw(gradient)
        
        for y in range(450):
            alpha = int((y / 450) * 180)
            gradient_draw.rectangle([(0, y), (CARD_WIDTH, y + 1)], fill=(0, 0, 0, alpha))
        
        gradient = gradient.filter(ImageFilter.GaussianBlur(radius=5))
        card.paste(gradient, (0, CARD_HEIGHT - 450), gradient)
        
        draw = ImageDraw.Draw(card)
        
        # Load fonts (with fallback)
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
        
        # Genre badge (top-left)
        genre_text = sample_movie["genres"][0]["name"]
        badge_padding = 10
        badge_bbox = draw.textbbox((20, 20), genre_text, font=subtitle_font)
        badge_width = badge_bbox[2] - badge_bbox[0] + 2 * badge_padding
        badge_height = badge_bbox[3] - badge_bbox[1] + 2 * badge_padding
        
        draw.rectangle(
            [(15, 15), (15 + badge_width, 15 + badge_height)],
            fill=(220, 20, 60)  # Crimson
        )
        draw.text((15 + badge_padding, 20), genre_text, fill=(255, 255, 255), font=subtitle_font)
        
        # Movie title (center-bottom)
        movie_title = sample_movie["title"]
        title_bbox = draw.textbbox((0, 0), movie_title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (CARD_WIDTH - title_width) // 2
        title_y = CARD_HEIGHT - 320
        
        draw.text((title_x + 2, title_y + 2), movie_title, fill=(0, 0, 0, 150), font=title_font)
        draw.text((title_x, title_y), movie_title, fill=(255, 255, 255), font=title_font)
        
        # Rating
        rating = sample_movie["vote_average"]
        rating_text = f"⭐ {rating}/10"
        rating_bbox = draw.textbbox((0, 0), rating_text, font=subtitle_font)
        rating_width = rating_bbox[2] - rating_bbox[0]
        rating_x = (CARD_WIDTH - rating_width) // 2
        rating_y = title_y + 60
        
        draw.text((rating_x + 1, rating_y + 1), rating_text, fill=(0, 0, 0, 100), font=subtitle_font)
        draw.text((rating_x, rating_y), rating_text, fill=(255, 215, 0), font=subtitle_font)
        
        # Page handle (bottom-right)
        PAGE_HANDLE = "@cinedrop"
        handle_bbox = draw.textbbox((0, 0), PAGE_HANDLE, font=handle_font)
        handle_width = handle_bbox[2] - handle_bbox[0]
        handle_x = CARD_WIDTH - handle_width - 20
        handle_y = CARD_HEIGHT - 40
        
        draw.text((handle_x + 1, handle_y + 1), PAGE_HANDLE, fill=(0, 0, 0, 100), font=handle_font)
        draw.text((handle_x, handle_y), PAGE_HANDLE, fill=(200, 200, 200), font=handle_font)
        
        # Save the card
        output_path = Path("sample_card.jpg")
        card.save(output_path, "JPEG", quality=95)
        
        print(f"   ✅ Card saved: {output_path}")
        return str(output_path)
        
    except Exception as e:
        print(f"   ❌ Error: {e}")
        return None

# ============================================================================
# DEMO/TEST
# ============================================================================

def demo():
    """Run demo without API keys"""
    
    print("=" * 80)
    print("INSTAGRAM MOVIE BOT - DEMO (No API Keys Required)")
    print("=" * 80)
    
    # Show sample movie
    print("\n📽️  SAMPLE MOVIE DATA")
    print(f"   Title: {sample_movie['title']}")
    print(f"   Year: {sample_movie['release_date'][:4]}")
    print(f"   Rating: {sample_movie['vote_average']}/10")
    print(f"   Genre: {sample_movie['genres'][0]['name']}")
    print(f"   IMDb ID: {sample_movie['id']}")
    
    # Show streaming availability
    print("\n🎬 STREAMING AVAILABILITY (Sample)")
    all_platforms = sorted(list(set(sample_streaming['IN'] + sample_streaming['US'])))
    print(f"   Available on: {', '.join(all_platforms)}")
    print(f"   (Checked across India & US regions)")
    
    # Show sample caption
    print("\n✍️  SAMPLE INSTAGRAM CAPTION")
    print("   " + "-" * 76)
    for line in sample_caption.split('\n'):
        print(f"   {line}")
    print("   " + "-" * 76)
    print(f"\n   📊 Caption Length: {len(sample_caption)} characters")
    
    # Create visual card
    print("\n🎨 GENERATING VISUAL CARD")
    card_path = create_sample_card()
    
    if card_path:
        print("\n" + "=" * 80)
        print("✅ DEMO COMPLETE!")
        print("=" * 80)
        print(f"\n📸 Sample card saved to: {card_path}")
        print("\n📋 What the bot will do:")
        print("   1. ✅ Fetch movie from TMDb (daily, rotating genres)")
        print("   2. ✅ Check streaming in India & US")
        print("   3. ✅ Generate AI caption (conversational, engaging)")
        print("   4. ✅ Create visual card (movie poster + overlays)")
        print("   5. ✅ Post to Instagram automatically")
        print("   6. ✅ Save to history (never post same movie twice)")
        print("\n🚀 Next Steps:")
        print("   1. Add your API keys to .env file")
        print("   2. Run: python test_bot.py")
        print("   3. Push to GitHub and enable GitHub Actions")
        print("\n" + "=" * 80)
    else:
        print("❌ Failed to create sample card")


if __name__ == "__main__":
    demo()
