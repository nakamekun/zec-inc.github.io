# ZEC Inc. Website

This repository contains the source for the ZEC Inc. company website.
The site is published as a static site on GitHub Pages.

## Pages

- Home page: `index.html`
- Apps page: `/apps/`
- Apps page source: `apps/index.html`

## Apps Sync

- Sync script: `scripts/update_apps_page.py`
- Purpose:
  Fetch the public ZEC Inc. app list from the App Store and reflect it into `/apps/`.
- Data source:
  Apple Lookup API
- Developer ID:
  `1889726396`

The apps page is generated locally and committed as static HTML.
The live website does not call the App Store API at page-view time.

The weekly GitHub Actions workflow `.github/workflows/update-apps-page.yml`
runs the same generator, commits generated changes only when files changed, and
opens a single failure issue if the scheduled update fails.

### API endpoint

`https://itunes.apple.com/lookup?id=1889726396&entity=software&country=us&limit=200`

### How it works

- The script fetches App Store app data for ZEC Inc.
- Only `kind == software` entries are used.
- The script also checks `artistId == 1889726396`.
- `apps/index.html` contains these markers:
  - `<!-- APPS_LIST_START -->`
  - `<!-- APPS_LIST_END -->`
- Only the HTML inside that marker range is replaced.
- The page layout, header, lead text, and footer stay manual.

## Run

Windows:

```powershell
python scripts\update_apps_page.py
```

macOS / Linux:

```bash
python3 scripts/update_apps_page.py
```

## After Updating

1. Run `git diff`
2. Confirm each app link in `apps/index.html` points to an individual App Store `trackViewUrl`
3. Confirm `Coming soon` is not present
4. Open `apps/index.html` locally and verify the layout

## Commit / Push Flow

```powershell
python scripts\update_apps_page.py
git diff
git add apps/index.html scripts/update_apps_page.py README.md
git commit -m "Update apps page"
git push
```

## Notes

- Use the Apple Lookup API, not App Store HTML scraping.
- Do not add runtime API calls to the published page.
- Do not change content outside the marker range unless you are intentionally editing the page design.
- Keep design-only changes and app-list sync changes in separate commits when possible.
- Re-run the script after releasing a new app on the App Store.
