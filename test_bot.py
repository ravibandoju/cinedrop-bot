"""
Test script for Instagram Movie Bot
Run this to test individual functions without publishing to Instagram
"""

import os
import sys
from dotenv import load_dotenv
from datetime import datetime

# Load environment variables
load_dotenv()

# Check if API keys are configured
required_keys = ["TMDB_API_KEY", "GROQ_API_KEY"]
missing_keys = [key for key in required_keys if not os.getenv(key)]

if missing_keys:
    print("❌ Missing API Keys:")
    for key in missing_keys:
        print(f"   - {key}")
    print("\n📝 Setup instructions:")
    print("   1. Copy .env.example to .env")
    print("   2. Fill in your API keys in .env")
    print("   3. Run this script again")
    sys.exit(1)

print("✅ API Keys loaded successfully!\n")

# Import main functions
from main import (
    get_movie,
    get_streaming_platforms,
    write_caption,
    create_card,
    log_message,
    get_today_genre,
)

def test_flow():
    """Test the complete bot flow"""
    
    print("=" * 80)
    print("TESTING INSTAGRAM MOVIE BOT")
    print("=" * 80)
    
    # Step 1: Get movie
    print("\n📽️  STEP 1: Fetching movie...")
    try:
        movie = get_movie()
        if not movie:
            print("❌ No movie found")
            return
        
        movie_title = movie.get("title", "Unknown")
        movie_id = movie.get("id")
        rating = movie.get("vote_average", 0)
        print(f"✅ Found: {movie_title} (ID: {movie_id}, Rating: {rating}/10)")
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Step 2: Get streaming platforms
    print("\n🎬 STEP 2: Checking streaming availability...")
    try:
        platforms = get_streaming_platforms(movie_id)
        india_platforms = platforms.get("IN", [])
        us_platforms = platforms.get("US", [])
        
        print(f"✅ India: {', '.join(india_platforms) if india_platforms else 'Not available'}")
        print(f"✅ US: {', '.join(us_platforms) if us_platforms else 'Not available'}")
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Step 3: Generate caption
    print("\n✍️  STEP 3: Generating caption with Groq AI...")
    try:
        caption = write_caption(movie, platforms)
        caption_length = len(caption)
        print(f"✅ Caption generated ({caption_length} characters)")
        print("\n--- CAPTION PREVIEW ---")
        print(caption[:500] + "...\n" if len(caption) > 500 else caption)
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Step 4: Create visual card
    print("🎨 STEP 4: Creating visual card with Pillow...")
    try:
        image_path = create_card(movie, platforms)
        if image_path:
            print(f"✅ Image created: {image_path}")
            print("\n📸 CARD DETAILS:")
            print("   - Poster background: Downloaded from TMDb")
            print("   - Title overlay: Large white bold text at bottom")
            print("   - Rating: Gold text with star emoji")
            print("   - Genre badge: Crimson background, top-left corner")
            print("   - Page handle: '@cinedrop' at bottom-right")
            print("   - Gradient overlay: Dark semi-transparent at bottom (text readability)")
            print("   - Size: 1080x1350px (Instagram feed size)")
        else:
            print("❌ Failed to create image")
            return
    except Exception as e:
        print(f"❌ Error: {e}")
        return
    
    # Summary
    print("\n" + "=" * 80)
    print("✅ TEST COMPLETED SUCCESSFULLY!")
    print("=" * 80)
    print(f"\n📊 Summary:")
    print(f"   Movie: {movie_title}")
    print(f"   Genre (today): {get_today_genre()['name']}")
    print(f"   Rating: {rating}/10")
    print(f"   India Streaming: {', '.join(india_platforms) if india_platforms else 'N/A'}")
    print(f"   US Streaming: {', '.join(us_platforms) if us_platforms else 'N/A'}")
    print(f"   Caption: {caption_length} characters")
    print(f"   Image: {image_path}")
    
    print("\n🚀 Next steps:")
    print("   1. Review the generated image and caption")
    print("   2. Push to GitHub: git push origin main")
    print("   3. Go to Actions tab and run workflow manually (or wait for 9 AM UTC)")
    print("   4. Check Instagram for the posted image!")
    print("\n" + "=" * 80)


if __name__ == "__main__":
    test_flow()
