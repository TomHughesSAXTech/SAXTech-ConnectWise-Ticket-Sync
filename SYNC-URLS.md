# ConnectWise Ticket Sync - Python Function

## Function URLs

### Incremental Sync (7 days)
```
https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=incremental
```

### Full Sync (8 months)
```
https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=full
```

## Configuration

**Boards Synced:**
- Parsippany Service Desk
- Managed Services

**Sync Behavior:**
- **Create**: New closed tickets are added to the index
- **Update**: Modified tickets are re-processed with `mergeOrUpload`
- **Delete**: Reopened tickets are removed from the index

**Azure Search Index:** `connectwise-tickets`
**Search Service:** `saxmegamind-search`

## Usage

### Initial Setup
1. Run the **Full Sync** URL to hydrate the index with 8 months of historical data
2. This will take approximately 5-10 minutes depending on ticket volume

### Daily Sync
1. Set up a cron job at https://cron-job.org
2. Use the **Incremental Sync** URL
3. Schedule: Daily at off-peak hours (e.g., 2 AM)
4. This syncs the last 7 days to catch any updates or new closures

## Testing

The function is deployed and working. To test:

```bash
# Test incremental sync (allow 5-10 minutes)
curl "https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=incremental" --max-time 600

# Test full sync (allow 10-15 minutes)
curl "https://connectwise-ticket-sync.azurewebsites.net/api/synctickets?mode=full" --max-time 900
```

## Response Format

Success response:
```json
{
  "syncMode": "incremental",
  "totalTicketsProcessed": 42,
  "documentsUploaded": 67,
  "ticketsDeleted": 2,
  "dateRange": {
    "from": "2025-11-13",
    "to": "2025-11-20"
  }
}
```

## Notes

- Runtime: Python 3.11 on Linux consumption plan
- Function timeout: 10 minutes
- The function processes tickets in batches and uploads to Azure Search in chunks of 1000 documents
- AI summarization uses GPT-4o-mini for problem/resolution summaries
- Vector embeddings use text-embedding-3-large for semantic search
