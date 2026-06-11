# Card Template Layout

## Visual Structure (1080 × 1350 px)

```
┌─────────────────────────────────────────┐
│                                         │
│   ┌──────┐                             │
│   │Genre │   [Movie Poster Background] │
│   │Badge │                             │
│   └──────┘                             │
│                                         │
│   [Full-size TMDb poster image]        │
│   [Dark poster colors]                  │
│                                         │
│   ┌─────────────────────────────────┐  │
│   │                                 │  │
│   │  [Dark Gradient Overlay]        │  │
│   │  (Semi-transparent fade)        │  │
│   │                                 │  │
│   │     Movie Title                 │  │
│   │     ⭐ X.X/10                    │  │
│   │                                 │  │
│   │                    @cinedrop    │  │
│   └─────────────────────────────────┘  │
│                                         │
└─────────────────────────────────────────┘
```

## Card Elements (Details)

### 1. **Genre Badge** (Top-Left Corner)
- Background: Crimson red (`#DC143C`)
- Text: White, bold, medium font
- Example: "Thriller", "Comedy", "Horror"
- Position: 15px from left, 15px from top
- Padding: 10px

### 2. **Movie Poster** (Background)
- Source: Downloaded from TMDb API
- Size: Fitted to card (1080×1350px)
- Aspect ratio: Preserved, centered if needed
- Dark background behind if poster doesn't fill entire card

### 3. **Dark Gradient Overlay** (Bottom 450px)
- Semi-transparent dark gradient (0 to 180 alpha)
- Blurred with Gaussian blur (radius 5px)
- Purpose: Make white text readable over poster
- Smooth fade from transparent to dark

### 4. **Streaming Platforms** (Generic)
- Combines available platforms from both India & US regions
- **No country flags or labels in caption**
- Backend still queries both regions for comprehensive data
- Deduplicates platforms (Netflix shown once even if available in both regions)
- Sorted alphabetically for consistency
- Format: `Amazon Prime Video, HBO Max, Netflix`

### 5. **Movie Title** (Center-Bottom)
- Font: Bold sans-serif, 48px
- Color: White with shadow effect
- Alignment: Centered horizontally
- Position: 320px from bottom
- Shadow: Black 2px offset for depth

### 6. **Rating Display** (Below Title)
- Format: `⭐ X.X/10`
- Font: Sans-serif, 32px
- Color: Gold (`#FFD700`)
- Alignment: Centered
- Position: 60px below title

### 7. **Page Handle** (Bottom-Right Corner)
- Text: `@cinedrop`
- Font: Sans-serif, 24px
- Color: Light gray (`#C8C8C8`)
- Position: 20px from right, 40px from bottom
- Shadow: Black 1px offset for visibility

---

## Color Scheme

| Element | Color | RGB |
|---------|-------|-----|
| Genre Badge | Crimson | `#DC143C` |
| Title Text | White | `#FFFFFF` |
| Rating | Gold | `#FFD700` |
| Handle | Light Gray | `#C8C8C8` |
| Overlay | Black (transparent) | `#000000` (α=180) |
| Background | Dark Gray | `#141414` |

---

## Example Outputs

### Example 1: Thriller Movie
```
┌──────────────────────────┐
│ ┌─────────┐              │
│ │Thriller │              │
│ └─────────┘              │
│                          │
│  [Dark action movie      │
│   poster background]     │
│                          │
│      The Silence         │
│      ⭐ 8.2/10           │
│                @cinedrop │
└──────────────────────────┘
```

### Example 2: Comedy Movie
```
┌──────────────────────────┐
│ ┌─────────┐              │
│ │ Comedy  │              │
│ └─────────┘              │
│                          │
│  [Colorful comedy poster │
│   with bright colors]    │
│                          │
│   Rush Hour              │
│   ⭐ 7.4/10              │
│               @cinedrop  │
└──────────────────────────┘
```

---

## Technical Details

- **Library:** Pillow (Python Imaging Library)
- **Format:** JPEG, 95% quality
- **Aspect Ratio:** 4:5 (standard Instagram feed)
- **Processing:** Local (no external APIs)
- **Font Fallback:** System fonts or default

---

## Font Handling

The bot tries fonts in this order (for cross-platform compatibility):

1. **Linux:** `/usr/share/fonts/truetype/dejavu/DejaVuSans-*.ttf`
2. **Windows:** `C:\Windows\Fonts\arial*.ttf`
3. **Fallback:** Default Pillow font (if no system fonts available)

This ensures the card looks consistent whether running on GitHub Actions (Ubuntu) or locally.
