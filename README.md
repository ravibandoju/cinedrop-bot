# 🎬 CineDrop - Daily Instagram Movie Post Bot

Automatically generates and publishes engaging movie posts to Instagram daily via GitHub Actions. Zero manual input required!

## What It Does

Every day at **9:00 AM UTC**, the bot:

1. ✅ Fetches a random high-quality movie (7.0+ rating) from TMDb, rotating genres by day of week
2. ✅ Finds where it's streaming in **India** and the **US**
3. ✅ Generates an engaging, human-written Instagram caption using AI (Groq)
4. ✅ Creates a branded visual card with the movie poster
5. ✅ Publishes everything to Instagram automatically
6. ✅ Saves the movie ID to history so it never posts the same film twice

**Genre Rotation by Day:**
- Monday: Thriller
- Tuesday: Comedy
- Wednesday: Horror
- Thursday: Drama
- Friday: Action
- Saturday: Sci-Fi
- Sunday: Romance

---

## Tech Stack

- **Language:** Python 3.11
- **Scheduler:** GitHub Actions (cron: `0 9 * * *`)
- **Movie Data:** TMDb API (free tier)
- **Caption Generation:** Groq API - `llama3-8b-8192` (free, no credit card)
- **Image Design:** Canva API (free tier)
- **Publishing:** Instagram Graph API
- **History:** `posted_movies.json` (prevents duplicates)

**Everything is FREE and open-source. No paid services.**

---

## Setup Instructions

### 1️⃣ Clone & Install

```bash
git clone https://github.com/YOUR_USERNAME/cinedrop.git
cd cinedrop
pip install -r requirements.txt
```

### 2️⃣ Get API Keys

#### TMDb API
1. Go to https://www.themoviedb.org/settings/api
2. Create a free account
3. Copy your **API Key** (v3 auth)

#### Groq API (Free Tier)
1. Visit https://console.groq.com/
2. Sign up (free, no credit card needed)
3. Create an API key
4. Copy your **API Key**

#### Canva API
1. Go to https://www.canva.com/developers/
2. Create a developer account
3. Create an app and get your **API Key**
4. **Important:** Create a design template on Canva and note its **Template ID**

#### Instagram Graph API
1. Go to https://developers.facebook.com/
2. Create an app (type: Business)
3. Add Instagram product to your app
4. Connect your Instagram Business Account
5. Get your **Instagram Access Token** and **Business Account ID**
6. Store your access token in a secure location

#### GitHub Token (for auto-commits)
1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Select scope: `repo` (full control of private repositories)
4. Copy your **Personal Access Token**

### 3️⃣ Configure Environment

Copy the template to `.env` and fill in your keys:

```bash
cp .env.example .env
```

Edit `.env` with your API keys:

```env
TMDB_API_KEY=your_key_here
GROQ_API_KEY=your_key_here
INSTAGRAM_ACCESS_TOKEN=your_token_here
INSTAGRAM_ACCOUNT_ID=your_account_id_here
GH_TOKEN=your_github_token_here
```

**⚠️ Important:** Add `.env` to `.gitignore` to never commit secrets!

```bash
echo ".env" >> .gitignore
```

### 4️⃣ Set Up GitHub Secrets

1. Go to your repo → **Settings** → **Secrets and variables** → **Actions**
2. Click **New repository secret** and add each key:
   - `TMDB_API_KEY`
   - `GROQ_API_KEY`
   - `INSTAGRAM_ACCESS_TOKEN`
   - `INSTAGRAM_ACCOUNT_ID`
   - `GH_TOKEN`

### 5️⃣ Test Locally (Before GitHub)

Before pushing to GitHub, test the bot locally to catch any issues:

```bash
# Copy environment template
cp .env.example .env

# Edit .env and add your real API keys
nano .env  # or use your editor

# Install dependencies
pip install -r requirements.txt

# Run the test script
python test_bot.py
```

**What the test script does:**
- ✅ Loads your API keys
- ✅ Fetches a random movie matching today's genre
- ✅ Checks streaming availability in India & US
- ✅ Generates an AI caption with Groq
- ✅ Creates the visual card (Pillow)
- ✅ Shows preview of everything

If all steps pass, you're ready for GitHub Actions!

### 6️⃣ Push to GitHub & Trigger Workflow

Push your code to GitHub:

```bash
git add .
git commit -m "Initial commit: CineDrop bot setup"
git push origin main
```

The workflow will:
- Run automatically every day at 9:00 AM UTC (via cron schedule)
- Or you can manually trigger it from **Actions** tab → **Daily Instagram Movie Post** → **Run workflow**

---

## Visual Card Template

The bot creates a branded Instagram card (1080×1350px) for each movie with:
- **Movie poster** as background (downloaded from TMDb)
- **Genre badge** in top-left (colored tag)
- **Movie title** in large white text (bottom center)
- **Rating** in gold (⭐ X.X/10)
- **Your handle** (@cinedrop) in bottom-right
- **Dark gradient overlay** for text readability

**See [CARD_TEMPLATE.md](CARD_TEMPLATE.md) for detailed layout examples.**

---

## File Structure

```
cinedrop/
├── main.py                          # Main bot script
├── test_bot.py                      # Local testing script (run before GitHub)
├── requirements.txt                 # Python dependencies (includes Pillow)
├── posted_movies.json               # History of posted movies (auto-updated)
├── .env.example                     # Template for environment variables
├── .env                             # Your actual API keys (NEVER commit!)
├── README.md                        # This file
├── CARD_TEMPLATE.md                 # Visual card layout documentation
└── .github/
    └── workflows/
        └── daily_post.yml           # GitHub Actions workflow
```

---

## How It Works

### Caption Format

The bot generates captions following this structure:

```
[Hook line that stops the scroll]

🎬 Movie Title (Year)
⭐ Rating/10 · Genre

[2-3 sentences: why this film is worth your time, conversational tone, no spoilers]

📺 Where to watch:
[Streaming platforms - combined from all regions, deduplicated]

[Debate or question to drive comments]

[10-15 niche hashtags]
```

### Streaming Platforms Supported

The bot checks streaming availability across multiple regions:

**India:** Netflix, Amazon Prime Video, Disney+ Hotstar, Zee5, SonyLIV, Apple TV+, JioCinema, Mubi

**US:** Netflix, Amazon Prime Video, Hulu, Apple TV+, HBO Max, Peacock, Paramount+, Disney+, Mubi

**Caption Format:** Platforms from both regions are combined, deduplicated, and listed generically (no country flags or labels in the post).

If no streaming info available: "Not streaming — rental/purchase only 🎬"

### Duplicate Prevention

Movie IDs are stored in `posted_movies.json`. The bot always filters out already-posted movies, so you'll never see repeats (unless you manually delete the file).

---

## Customization

### Change Schedule

Edit `.github/workflows/daily_post.yml`:

```yaml
- cron: '0 9 * * *'  # Change this cron expression
```

Examples:
- `'0 9 * * *'` = Every day at 9 AM UTC
- `'0 */12 * * *'` = Every 12 hours
- `'0 9 * * 1'` = Every Monday at 9 AM UTC

### Change Genres

Edit `main.py` - `GENRE_BY_DAY` dictionary to swap genres or order.

### Add More Streaming Platforms

Update `PROVIDER_MAPPING` in `main.py` with new provider IDs from TMDb API.

---

## Troubleshooting

### ❌ "API Key not found"
- Check all secrets are set in GitHub Actions settings
- Ensure your `.env` file exists locally for testing
- Verify no typos in secret names

### ❌ "No streaming data found"
- Not all movies have watch provider data on TMDb
- The bot will use fallback message automatically
- This is normal behavior

### ❌ "Failed to publish to Instagram"
- Verify your Instagram account is a **Business Account**
- Check your access token is still valid (tokens can expire)
- Ensure your app has Instagram product enabled

### ❌ "Canva template not found"
- Verify your template ID is correct
- The bot will fall back to TMDb movie poster if template fails
- Check Canva API permissions

### 🔍 View Logs

1. Go to your repo → **Actions** tab
2. Click the latest workflow run
3. Expand **Run daily post bot** to see full logs
4. Check for error messages and API responses

---

## Features

✅ **Fully Automated** - No manual input after setup  
✅ **Duplicate Prevention** - Tracks posted movies  
✅ **Smart Genre Rotation** - Different genres each day  
✅ **Streaming Detection** - India & US covered  
✅ **AI-Generated Captions** - Natural, engaging text  
✅ **Branded Visuals** - Custom templates or TMDb posters  
✅ **Error Handling** - Graceful fallbacks for API failures  
✅ **Scheduled Publishing** - Runs daily at fixed time  
✅ **Zero Cost** - All free APIs & GitHub Actions  

---

## API Rate Limits

- **TMDb:** 40 requests / 10 seconds (free tier) ✅
- **Groq:** Free tier supports high throughput ✅
- **Instagram Graph API:** 200 requests / hour (Business account) ✅
- **GitHub Actions:** 2000 minutes/month free ✅

This bot uses ~5-6 requests per run, so you're well within limits.

---

## Future Enhancements

- [ ] Support more regions (UK, Canada, etc.)
- [ ] Multi-image carousel posts
- [ ] Reel generation instead of static images
- [ ] Hashtag trend analysis
- [ ] Analytics dashboard
- [ ] Discord/Slack notifications on post success

---

## License

MIT License - Feel free to fork and customize!

---

## Support

Got questions? 
- Check the troubleshooting section above
- Review GitHub Actions logs for specific errors
- Verify all API keys and permissions are correct

Happy posting! 🍿✨
