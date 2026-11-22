# S DEEP Cloud — V2 hardening release

Hindi finance YouTube production pipeline + Streamlit dashboard.

## What changed in V2

- State loading now tolerates malformed/missing JSON; state writes are atomic.
- `dryrun` now creates a disposable `dryrun_YYYYMMDD_HHMMSS` job outside the real publishing schedule.
- Dry-run defaults to a local test tone (`DRYRUN_ENGINE=test`) and never calls the YouTube upload API.
- Existing rendered video files are reused on a retry when still present.
- YouTube upload validates the input file/title/timezone, retries transient chunk failures, verifies the created video, and reports thumbnail/caption failures instead of silently hiding them.
- Runtime dependencies are centralized in `requirements.txt`.
- PWA service worker cache version is bumped so users receive the updated dashboard shell.
- Added automated safety/helper tests under `tests/`.

## Install

```bash
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Install FFmpeg and ensure both `ffmpeg` and `ffprobe` are on PATH.

## Run modes

```bash
python run.py dryrun   # creates a disposable preview; no YouTube upload
python run.py daily    # production mode: may upload and schedule videos
python run.py weekly   # fetches YouTube analytics and writes REPORT.md
```

`dryrun` needs a working Gemini API key and news feeds to create a real script. It uses a test-tone audio track by default so CI can test rendering without depending on external TTS. Set `DRYRUN_ENGINE=edge` if you explicitly want to test Hindi speech generation.

## Environment / GitHub secrets

Required for script generation:
- `GEMINI_API_KEY`

Required for production YouTube upload and analytics:
- `YT_CLIENT_ID`
- `YT_CLIENT_SECRET`
- `YT_REFRESH_TOKEN`

Optional:
- `ENGINE=edge` (`edge`, `gtts`, `xtts`, or `test`)
- `VOICE=hi-IN-MadhurNeural`
- `GEMINI_MODEL=gemini-2.5-flash`
- `VOICE_REF=/path/to/reference.wav` (XTTS only)
- `INTRO=true`
- `DRYRUN_ENGINE=test`

**Important:** GitHub Actions schedule invokes `daily` mode, which is production mode and can upload/schedule videos. Keep the workflow disabled until credentials, channel settings, and content review process have been verified. A manual `dryrun` does not upload.

## Dashboard

- `dashboard.py` is the Streamlit dashboard and reads the `data/` files committed by GitHub Actions.
- The separate PWA files (`index.html`, `manifest.webmanifest`, `sw.js`, icons) are a static front-end shell. They are not a live API-connected control panel by themselves.
- For the Streamlit Run tab, configure `GH_REPO` and `GH_TOKEN` in Streamlit secrets. Use a narrowly scoped token with Actions workflow dispatch permission only. Never place tokens in client-side HTML/JavaScript.

## Tests

```bash
python -m unittest discover -s tests -v
```

Tests are offline and do not require Gemini or YouTube credentials.

## Deployment notes

- Put `weekly.yml` at `.github/workflows/weekly.yml` in the GitHub repository.
- Store credentials only in GitHub Actions / Streamlit secrets.
- XTTS-v2 has licensing restrictions; review the model's current license and your intended commercial use before enabling it.
- Market charts from Yahoo Finance are historical/delayed data; label them as such and verify current values before making time-sensitive claims.


## V3 — AI presenter + growth intelligence (optional)

### Real talking-head presenter (HeyGen Digital Twin)

The existing still-photo host remains the default. To render genuine lip-synced presenter scenes, the pipeline now supports an optional HeyGen v3 Digital Twin provider. This is a paid external API and is deliberately disabled unless all four environment variables are supplied:

- `ENGINE=heygen`
- `HEYGEN_API_KEY`
- `HEYGEN_AVATAR_ID` — your own/consented Digital Twin look ID
- `HEYGEN_VOICE_ID`
- `HEYGEN_CONFIRM_BILLING=true` — explicit billing opt-in gate

Optional:
- `HEYGEN_ENGINE=heygen-avatar-6` (must be supported by the selected avatar look)
- `HEYGEN_MOTION_PROMPT` — restrained presenter movement direction

Create a Digital Twin only from a person who has provided the required consent. Do not use another person's likeness or voice without permission. HeyGen API credits are billed separately; check your current account pricing and balance before enabling. Each script scene creates a separate avatar render, so a long video can consume multiple scene renders. Start with one short manual test and review its output before enabling any scheduled workflow.

Do not set `ENGINE=heygen` in GitHub Actions until the avatar, voice, account credits, output quality and billing are confirmed. `HEYGEN_CONFIRM_BILLING=true` is an intentional second opt-in, not a payment cap.

For a controlled one-Short preview in GitHub Actions, keep `ENGINE=edge` for production and temporarily set the repository variable `DRYRUN_ENGINE=heygen`; run only the `dryrun` workflow mode, inspect/download the artifact, then restore `DRYRUN_ENGINE=test`. The dry-run path never calls the YouTube upload API. Do not set `ENGINE=heygen` until you intentionally want production render jobs to use the paid provider.

### Added growth metrics

The analytics collector now requests thumbnail impressions, impressions click-through rate and engaged views where the account/API report makes them available. Some metrics may be unavailable for certain formats, videos, permissions or reporting windows; blank values mean unavailable, not zero. Shorts "viewed vs swiped away" is not inferred from engaged views and must be checked in YouTube Studio when the API does not expose the exact metric.

### HeyGen API references

- Digital Twin video creation and polling: https://developers.heygen.com/generate-avatar-video
- HeyGen API credits/pricing: https://help.heygen.com/en/articles/10060327-heygen-api-pricing-explained
- YouTube Analytics metrics: https://developers.google.com/youtube/analytics/metrics
