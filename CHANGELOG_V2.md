# V2 changes

## Reliability and safety
- Defensive state loading and atomic JSON state writes.
- Dry-run uses a disposable ID and no longer mutates the weekly publishing plan.
- Dry-run defaults to a local test-tone engine; it never calls the YouTube upload function.
- Reuses an existing rendered file during same-run retries when the file is still present.
- Added AI script shape checks before render: title length, scene text, scene count, supported chart symbols, and chart-count limits.
- YouTube upload validates local media and metadata, retries transient resumable-upload errors, verifies the created video, and records thumbnail/caption warnings.
- Runtime Python dependencies are centralized in `requirements.txt`.
- PWA shell cache version bumped to force updated static assets.

## Dashboard
- Streamlit schedule view surfaces job errors and thumbnail/caption upload warnings.
- Existing PWA files are preserved; service worker cache cleanup is improved.

## Tests
- Corrupt state recovery.
- Atomic state persistence and settings exclusion.
- Script schema validation.
- Dry-run isolation from real publishing state.
- YouTube metadata/tag helper behavior.


## V3 — AI Presenter + Growth Intelligence

- Added optional HeyGen v3 Digital Twin provider for real talking-head/lip-synced scenes.
- Added explicit billing opt-in gate (`HEYGEN_CONFIRM_BILLING=true`) and required avatar/voice/API configuration.
- Added safe HTTPS-only download, asynchronous status polling, timeouts, temporary downloads and provider error reporting.
- Added YouTube engaged views, thumbnail impressions and impressions CTR collection where the API supports them.
- Added dashboard guidance for consent, API setup, costs and manual-first rollout.
- Default rendering remains the existing local still-host pipeline; HeyGen is never enabled automatically.
