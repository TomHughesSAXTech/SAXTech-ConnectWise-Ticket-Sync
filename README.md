# ConnectWise Ticket Sync

Azure Function and tooling to sync closed ConnectWise tickets into Azure AI Search with AI-generated summaries and vector embeddings.

## Components
- `function_app.py` — Python Azure Function (HTTP trigger) that:
  - Pulls closed tickets from ConnectWise (by board)
  - Summarizes problem/resolution via Azure OpenAI (GPT-4o-mini)
  - Generates embeddings via `text-embedding-3-large`
  - Uploads to Azure AI Search using `mergeOrUpload`
  - Skips unchanged tickets based on ConnectWise `_info.lastUpdated`
  - Handles OpenAI 429 rate limits (exponential backoff) and adds a small per-ticket delay
- `csv_import.py` — Local importer to load historical tickets from a CSV with pre-computed summaries (batches embeddings 50 at a time, uploads in chunks)
- `SYNC-URLS.md` — Endpoints and instructions

## Endpoints
- Incremental: `GET https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=incremental`
- Test (one ticket): `GET https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=test`
- Full (8 months): `GET https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=full`

## Current Schedule
- Cron (cron-job.org): every 2 hours, Monday–Friday, 10:00–24:00 (midnight)
  - 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00, 24:00

## Search Index
- Service: `saxmegamind-search`
- Index: `connectwise-tickets`
- Document id pattern: `<ticketNumber>-<chunkId>`

## Configuration

Set these app settings (Function App) and environment vars (local):
- `OPENAI_API_KEY`
- `SEARCH_ADMIN_KEY`

## Notes
- 2025-11-20: Imported 5,231 historical tickets from CSV (generated 5,235 docs)
- 2025-11-21: Deployed Python function, added change detection and rate-limit handling, paced per-ticket calls
