# ConnectWise Ticket Sync – Runbook

## Overview
Syncs closed ConnectWise tickets to Azure AI Search with AI summaries and embeddings. Python Azure Function + local CSV bootstrap tool.

## Environments
- Azure Function: connectwise-ticket-sync (Linux, Python 3.11)
- Search: saxmegamind-search / connectwise-tickets

## Secrets (Function App settings)
- OPENAI_API_KEY
- SEARCH_ADMIN_KEY

## Schedules
- PROD (cron-job.org): Every 2 hours, Mon–Fri, 10:00–24:00
  - 10:00, 12:00, 14:00, 16:00, 18:00, 20:00, 22:00, 24:00

## Endpoints
- Incremental: GET /api/synctickets?mode=incremental
- Test (1 ticket): GET /api/synctickets?mode=test
- Full (8 months): GET /api/synctickets?mode=full

## Change detection
- Compares ConnectWise `_info.lastUpdated` to existing `closedDate` in index
- Skips unchanged tickets

## Rate limit handling
- Exponential backoff on 429s (1s, 3s, 5s, 9s, 17s)
- 1 second pacing between tickets

## Bootstrap from CSV
- csv_import.py reads MegamindLLM.csv, batches embeddings (50), uploads in chunks of 1000

## Operations
1. Verify Function App is running (portal) and app settings set
2. Trigger test: /api/synctickets?mode=test
3. Monitor logs: Application Insights (traces)
4. Search index health: document count, sample queries

## Notes
- 2025-11-20: Imported 5,231 tickets (5,235 docs)
- 2025-11-21: Change detection + rate-limit handling; schedule set to every 2 hours 10:00–24:00 M–F
