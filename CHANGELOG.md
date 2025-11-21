# Changelog

## 2025-11-21
- Moved secrets (OpenAI/Search keys) to environment variables to satisfy GitHub push protection
- Added change-detection to skip unchanged tickets using ConnectWise `_info.lastUpdated` vs existing `closedDate` in index
- Fixed Azure Search iteration (`SearchItemPaged` -> `next(iter(results))`)
- Added exponential backoff for OpenAI 429s + 1s per-ticket pacing
- Deployed Python function to Linux consumption (Azure Functions v4)
- Updated schedule to every 2 hours from 10:00 to 24:00, Monday–Friday

## 2025-11-20
- Imported 5,231 historical tickets via `csv_import.py` (batched embeddings 50 at a time) — 5,235 docs uploaded
- Migrated from PowerShell to Node.js, then to Python due to runtime issues
- Created `SYNC-URLS.md` with endpoints
