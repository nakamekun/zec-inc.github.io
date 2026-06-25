# Kickoff Results Auto Update

The `zec-inc.github.io` repository owns both the automation and the public JSON files for Kickoff Bell 2026. GitHub Actions runs in this same repository and updates these published files directly:

- `https://zec-inc.jp/data/kickoff-2026/matchResults.json`
- `https://zec-inc.jp/data/kickoff-2026/groupStandings.json`
- `https://zec-inc.jp/data/kickoff-2026/matchDisplayOverrides.json`

The iOS app reads the remote JSON files above. The base bundled schedule remains app-local; knockout matchup cards are reflected through `matchDisplayOverrides.json`.

## Layout

Automation lives in:

`tools/kickoff-2026/results/`

Important files:

- `scripts/results/auto_update_results.py`
- `scripts/results/generate_match_results.py`
- `scripts/results/generate_group_standings.py`
- `scripts/results/generate_match_display_overrides.py`
- `scripts/results/deploy_generated_results.py`
- `scripts/results/providers/fifa_match_centre_provider.py`
- `data/results/match-id-map.json`
- `data/results/manual-match-results.json`
- `data/results/manual-match-display-overrides.json`
- `data/results/auto-update-state.json`

Generated intermediate files stay under `tools/kickoff-2026/results/data/generated/`. The public files are always:

- `data/kickoff-2026/matchResults.json`
- `data/kickoff-2026/groupStandings.json`
- `data/kickoff-2026/matchDisplayOverrides.json`

## Schedule

Workflow:

`.github/workflows/kickoff-results-auto-update.yml`

It runs every 10 minutes and also supports manual or external `workflow_dispatch`. The GitHub Actions schedule is intentionally staggered to minutes `7,17,27,37,47,57` instead of minute `0`, because GitHub scheduled workflows can be delayed or dropped during high-load periods.

The updater checks matches from `match-id-map.json` and attempts result capture at:

- `kickoffUTC + 2h10m`: first check for normal full-time results
- `kickoffUTC + 3h`: final check for delays, stoppage time, extra time in unusual cases, or provider lag

GitHub Actions schedule is a best-effort trigger, not a guaranteed timer. It remains enabled, but it is not the only trigger. A second external cron path should dispatch the same workflow through GitHub's REST API. The updater is idempotent and commits only when JSON or state changes.

The workflow has a concurrency group (`kickoff-results-auto-update`) so scheduled and external dispatches can safely overlap. Already finished matches are skipped unless `force=true` is passed.

After results and standings generation, the workflow also regenerates `matchDisplayOverrides.json`. It first reads the FIFA calendar match API and matches knockout fixtures by match number and kickoff time, then maps FIFA Home/Away team names to the app team IDs. If a fixture is not present in the FIFA calendar response yet, it falls back to resolving simple placeholders such as `winner-group-a` and `runner-up-group-b` from the current group standings. Third-place matchup slots can still be added through `manual-match-display-overrides.json` if needed.

## External Cron

Use the REST dispatch script instead of `gh workflow run`. This avoids macOS keychain differences between an interactive shell and cron.

Script:

`tools/kickoff-2026/results/scripts/results/dispatch_workflow.py`

Token requirements:

- fine-grained PAT or GitHub App installation token
- repository: `nakamekun/zec-inc.github.io`
- permission: Actions read/write, enough to create a workflow dispatch event
- do not commit the token
- do not put the token literal in a crontab entry

Preferred local setup:

```sh
mkdir -p /Users/kt/.config/zec
chmod 700 /Users/kt/.config/zec
printf '%s\n' '<token>' > /Users/kt/.config/zec/kickoff-workflow-dispatch-token
chmod 600 /Users/kt/.config/zec/kickoff-workflow-dispatch-token
```

Dry-run check:

```sh
cd /Users/kt/zec-inc.github.io
KICKOFF_WORKFLOW_DISPATCH_TOKEN_FILE=/Users/kt/.config/zec/kickoff-workflow-dispatch-token \
python3 tools/kickoff-2026/results/scripts/results/dispatch_workflow.py --dry-run
```

Cron command:

```cron
9,19,29,39,49,59 * * * * cd /Users/kt/zec-inc.github.io && KICKOFF_WORKFLOW_DISPATCH_TOKEN_FILE=/Users/kt/.config/zec/kickoff-workflow-dispatch-token /usr/bin/python3 tools/kickoff-2026/results/scripts/results/dispatch_workflow.py >>/tmp/kickoff-results-auto-update-dispatch.log 2>&1
```

Hosted schedulers such as Cloudflare Workers Cron can use the same REST API endpoint. Store the token as a scheduler secret.

### External Cron Auth Troubleshooting

If `/tmp/kickoff-results-auto-update-dispatch.log` contains `status=missing-token`, `status=401`, or `status=403`, the external cron token is missing or lacks permission. The dispatch script logs only:

- endpoint
- HTTP status
- token presence
- token source path/env name

It does not print the token value. For a minimal cron-like check:

```sh
env -i HOME=/Users/kt PATH=/usr/bin:/bin KICKOFF_WORKFLOW_DISPATCH_TOKEN_FILE=/Users/kt/.config/zec/kickoff-workflow-dispatch-token /usr/bin/python3 /Users/kt/zec-inc.github.io/tools/kickoff-2026/results/scripts/results/dispatch_workflow.py --dry-run
```

If auth still fails, create a new fine-grained PAT or GitHub App token with workflow dispatch permission for this repository. Never write a GitHub token into this repository or directly into the crontab command.

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

## Monitoring

The updater prints and writes a temporary summary containing:

- `targetCount`
- `updatedCount`
- `skippedAlreadyFinishedCount`
- `providerFailureCount`
- `dueMatchNoUpdateCount`
- `scheduleMissSuspected`

The workflow sends Discord notifications only when `KICKOFF_DISCORD_WEBHOOK_URL` is configured as a repository secret. Notification categories are separated:

- provider取得失敗
- due matchありだが更新なし
- schedule未起動疑い
- external dispatch authentication failure

No notification secret is required for normal JSON updates.

## Local Commands

Run from the repository root:

```sh
cd /Users/kt/zec-inc.github.io
python3 tools/kickoff-2026/results/scripts/results/auto_update_results.py --dry-run
python3 tools/kickoff-2026/results/scripts/results/auto_update_results.py
python3 tools/kickoff-2026/results/scripts/results/generate_match_results.py
python3 tools/kickoff-2026/results/scripts/results/generate_group_standings.py
python3 tools/kickoff-2026/results/scripts/results/generate_match_display_overrides.py
python3 tools/kickoff-2026/results/scripts/results/deploy_generated_results.py --no-push --no-curl
KICKOFF_WORKFLOW_DISPATCH_TOKEN_FILE=/Users/kt/.config/zec/kickoff-workflow-dispatch-token python3 tools/kickoff-2026/results/scripts/results/dispatch_workflow.py --dry-run
python3 -m unittest discover -s tools/kickoff-2026/results/tests -p 'test_*.py'
```

## Fallback

Manual input is an emergency override only. If the provider breaks because the source page structure changes, update `tools/kickoff-2026/results/data/results/manual-match-results.json`, regenerate the generated JSON files, run the deploy script, and commit the result. Store only factual values: match IDs, scores, penalty scores, winner team IDs, statuses, and timestamps. Do not store official copy, images, logos, or page text.

For knockout matchup cards that cannot be inferred from group rank placeholders, update `tools/kickoff-2026/results/data/results/manual-match-display-overrides.json` with app team IDs and regenerate `matchDisplayOverrides.json`.
