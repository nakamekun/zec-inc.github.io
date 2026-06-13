# ZEC Apps Content Operations

This document defines the hand-maintained content and screenshot rules for the generated ZEC Apps pages.

## Overrides Source

Production copy lives in `data/app-details-overrides.json`.

The App Store Lookup API remains the canonical app list and App Store URL source. Overrides should only add first-party explanatory copy, stable slugs, categories, screenshots, and locale-specific text.

Minimum override fields for priority apps:

```json
{
  "APP_STORE_TRACK_ID": {
    "slug": "app-slug",
    "short_description": "One sentence explaining who the app helps and what it makes easier.",
    "meta_description": "Search-friendly description under 155 characters.",
    "categories": ["productivity"],
    "overview": [
      "Explain the real use case and when someone would open the app.",
      "Clarify what the app is not, when that reduces confusion or risk."
    ],
    "target_users": [
      "Primary user group",
      "Secondary user group"
    ],
    "features": [
      "Main feature in user language",
      "Second feature in user language",
      "Privacy or simplicity feature where relevant"
    ],
    "how_to_use": [
      "Install the app from the App Store.",
      "Open the app and complete the main task.",
      "Return when the same situation comes up again."
    ],
    "pricing": "See the App Store for current pricing and regional availability.",
    "privacy": "Plain-language privacy note. Point to the App Store privacy label for current disclosure.",
    "faq": [
      {
        "question": "What is this app for?",
        "answer": "A direct answer in one or two sentences."
      }
    ]
  }
}
```

## Override Expansion Priority

The first seven apps already have production overrides:

- PhotoDay
- Packed
- Kickoff Bell 2026
- PillTap
- LaundryTap
- Big Text Note
- CleanURL Tap

Next priority apps:

- Study Buddy Timer: study sessions, stopwatch/timer use, focus record, widget context if shipped.
- WaterDone: hydration logging, quick daily taps, privacy and non-medical wellness wording.
- PoopTap: personal body rhythm logging, private daily record, avoid medical diagnosis claims.
- CaffeineTap: caffeine record, daily intake awareness, avoid health or safety guarantees.

For all remaining apps, add at least:

- `slug`
- `short_description`
- `meta_description`
- `categories`
- `overview`
- `target_users`
- `features`
- `how_to_use`
- `pricing`
- `privacy`
- `faq` with 5 to 8 entries

## Screenshot Placement

Preferred source:

```text
assets/apps/<slug>/screenshots/
```

Supported formats:

- `.png`
- `.jpg`
- `.jpeg`
- `.webp`

Recommended naming:

```text
01-overview.png
02-main-action.png
03-widget.png
04-history.png
05-settings.png
```

Rules:

- Use lowercase ASCII filenames.
- Prefix with two digits to control display order.
- Keep at most 5 screenshots per app page.
- Prefer App Store-ready screenshots from the released app, not mockups.
- Do not add placeholder or generated dummy images.
- If reusing App Store screenshots, place the exact exported files under the app slug directory and keep the App Store ordering.
- Avoid screenshots that expose personal data, medical details, precise location, or private family photos.

Alt text is generated as:

```text
<App Name> screenshot
```

If screenshot-specific alt text becomes necessary, extend `data/app-details-overrides.json` with structured screenshot objects in a future change. Keep the current array-of-strings format until there is a real need to migrate.

## Validation

Run before committing:

```sh
python3 scripts/update_apps_page.py --strict
python3 scripts/validate_apps_pages.py
python3 -m py_compile scripts/update_apps_page.py scripts/validate_apps_pages.py
git diff --exit-code
```

`git diff --exit-code` should be run after generation to confirm generated HTML, sitemap, robots, and `llms.txt` are committed with the source data that produced them.
