# Fonts for CineDrop Bot

This directory contains custom fonts used by the CineDrop Instagram bot for generating high-quality movie cards.

## Required Fonts

### 1. Bebas Neue (Display Font)
- **Purpose**: Large headings, titles, ratings, metadata
- **Download**: https://fonts.google.com/download?family=Bebas%20Neue
- **File**: `BebasNeue-Regular.ttf`
- **Size**: Place directly in this `fonts/` folder

### 2. Open Sans (Body Font)
- **Purpose**: Captions, descriptions, smaller text
- **Download**: https://fonts.google.com/download?family=Open%20Sans
- **Files**:
  - `OpenSans-Regular.ttf` (normal weight)
  - `OpenSans-Bold.ttf` (bold weight)
- **Installation**: Place both files directly in this `fonts/` folder

## Setup Instructions

### Local Development

1. Download Bebas Neue from Google Fonts:
   - Go to https://fonts.google.com/specimen/Bebas+Neue
   - Click "Download family"
   - Extract and copy `BebasNeue-Regular.ttf` to this folder

2. Download Open Sans from Google Fonts:
   - Go to https://fonts.google.com/specimen/Open+Sans
   - Click "Download family"
   - Extract and copy `OpenSans-Regular.ttf` and `OpenSans-Bold.ttf` to this folder

### GitHub Actions (Ubuntu Runner)

The `.github/workflows/daily_post.yml` includes a font installation step that:
- Installs `fonts-open-sans` package via apt
- Rebuilds the system font cache with `fc-cache -fv`
- Open Sans is available system-wide on Ubuntu

For Bebas Neue, the TTF file must be in this repo's `fonts/` folder and the Python code loads it directly.

## Folder Structure

```
cinedrop/
├── fonts/
│   ├── README.md                    ← this file
│   ├── BebasNeue-Regular.ttf        ← download from Google Fonts
│   ├── OpenSans-Regular.ttf         ← download from Google Fonts
│   └── OpenSans-Bold.ttf            ← download from Google Fonts
├── main.py
├── requirements.txt
└── ...
```

## Font Loading in Code

The `main.py` script loads fonts like this:

```python
FONT_DIR = Path("fonts")
BEBAS = str(FONT_DIR / "BebasNeue-Regular.ttf")
OPENSANS = str(FONT_DIR / "OpenSans-Regular.ttf")
OPENSANS_BOLD = str(FONT_DIR / "OpenSans-Bold.ttf")

def load_font(path, size, fallback_size=None):
    try:
        return ImageFont.truetype(path, size)
    except:
        return ImageFont.load_default()
```

If a font file is missing, the code falls back to default fonts gracefully.

## License

- **Bebas Neue**: Licensed under the SIL Open Font License (OFL)
- **Open Sans**: Licensed under the Apache License 2.0

Both fonts are free for personal and commercial use.
