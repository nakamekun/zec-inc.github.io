# Kickoff Results Auto Update

The `zec-inc.github.io` repository owns both the automation and the public JSON files for Kickoff Bell 2026. GitHub Actions runs in this same repository and updates these published files directly:

- `https://zec-inc.jp/data/kickoff-2026/matchResults.json`
- `https://zec-inc.jp/data/kickoff-2026/groupStandings.json`

The iOS app is unchanged. It continues to read the two remote JSON files above.

## Layout

Automation lives in:

`tools/kickoff-2026/results/`

Important files:

- `scripts/results/auto_update_results.py`
- `scripts/results/generate_match_results.py`
- `scripts/results/generate_group_standings.py`
- `scripts/results/deploy_generated_results.py`
- `scripts/results/providers/fifa_match_centre_provider.py`
- `data/results/match-id-map.json`
- `data/results/manual-match-results.json`
- `data/results/auto-update-state.json`

Generated intermediate files stay under `tools/kickoff-2026/results/data/generated/`. The public files are always:

- `data/kickoff-2026/matchResults.json`
- `data/kickoff-2026/groupStandings.json`

## Schedule

Workflow:

`.github/workflows/kickoff-results-auto-update.yml`

It runs every 10 minutes and also supports manual `workflow_dispatch`. The GitHub Actions schedule is intentionally staggered to minutes `3,13,23,33,43,53` instead of minute `0`, because GitHub scheduled workflows can be delayed or dropped during high-load periods.

The updater checks matches from `match-id-map.json` and attempts result capture at:

- `kickoffUTC + 2h10m`: first check for normal full-time results
- `kickoffUTC + 3h`: final check for delays, stoppage time, extra time in unusual cases, or provider lag

GitHub Actions schedule is a best-effort trigger, not a guaranteed timer. It is currently the primary update path. The updater is idempotent and commits only when JSON changes.

Local Mac `crontab` dispatch was tested as a secondary trigger and then disabled because cron could not read the interactive `gh` keyring authentication state. Do not restore local cron by placing a GitHub token directly in a crontab entry or repository file.

If a second trigger is needed again, prefer a hosted scheduler such as Cloudflare Workers Cron that stores a fine-scoped GitHub token as a scheduler secret and calls GitHub's `workflow_dispatch` API for branch `main`. Do not put tokens in this repository.

Reference local cron command, only for environments where `gh auth status` succeeds from cron:

```cron
8,18,28,38,48,58 * * * * cd /Users/kt/zec-inc.github.io && /opt/homebrew/bin/gh workflow run kickoff-results-auto-update.yml --ref main >/tmp/kickoff-results-auto-update.log 2>&1
```

If `gh` is installed elsewhere, replace `/opt/homebrew/bin/gh` with the output of `which gh`. The GitHub account used by `gh` needs permission to run workflows in `nakamekun/zec-inc.github.io`.

### External Cron Auth Troubleshooting

If `/tmp/kickoff-results-auto-update.log` contains `HTTP 401: Requires authentication`, the local cron environment cannot read the interactive `gh` authentication state. Confirm the cron-like environment with:

```sh
env -i HOME=/Users/kt PATH=/opt/homebrew/bin:/usr/bin:/bin /opt/homebrew/bin/gh auth status
```

If it fails, either reconfigure `gh` so the user crontab can access its auth state, or move the second trigger to a hosted scheduler that stores its GitHub token as a scheduler secret. Never write a GitHub token into this repository or into the crontab command itself.

## Enable / Disable

Repository variable:

`KICKOFF_AUTO_UPDATE_ENABLED=true`

This workflow is intentionally gated. It runs only when the variable is exactly `true`. Set it to `false` to pause the automation. After the tournament, either set the variable to `false` or remove/comment out the `schedule` block in the workflow.

GitHub repository settings must allow Actions to write commits:

`Settings > Actions > General > Workflow permissions > Read and write permissions`

`ZEC_PAGES_DEPLOY_TOKEN` is not required for same-repository updates. The workflow uses `GITHUB_TOKEN`.

Keep `KICKOFF_AUTO_UPDATE_ENABLED=false` as the global kill switch. Scheduled and externally dispatched runs will exit without updating when that variable is not exactly `true`.

## Provider Safety

The FIFA Match Centre provider first reads the public FIFA calendar JSON endpoint used by the site, then falls back to page embedded JSON if that endpoint is unavailable. It updates only when confidence is at least `0.90` and all of these are true:

- home and away teams match the app schedule
- competition and season match the 2026 tournament
- kickoff date supports the identity
- match number is used only as a confidence signal, not as a required identity field
- both scores are present
- the source marks the match final
- winner can be derived from score or penalties
- the provider result does not conflict with an existing final result

If the provider returns `not_found`, `not_final_yet`, `provider_error`, `low_confidence`, or `conflict`, existing JSON is preserved and the next cron run retries.

## Local Commands

Run from the repository root:

```sh
cd /Users/kt/zec-inc.github.io
python3 tools/kickoff-2026/results/scripts/results/auto_update_results.py --dry-run
python3 tools/kickoff-2026/results/scripts/results/auto_update_results.py
python3 tools/kickoff-2026/results/scripts/results/generate_match_results.py
python3 tools/kickoff-2026/results/scripts/results/generate_group_standings.py
python3 tools/kickoff-2026/results/scripts/results/deploy_generated_results.py --no-push --no-curl
python3 -m unittest discover -s tools/kickoff-2026/results/tests -p 'test_*.py'
```

## Fallback

Manual input is an emergency override only. If the provider breaks because the source page structure changes, update `tools/kickoff-2026/results/data/results/manual-match-results.json`, regenerate both JSON files, run the deploy script, and commit the result. Store only factual values: match IDs, scores, penalty scores, winner team IDs, statuses, and timestamps. Do not store official copy, images, logos, or page text.
