import azure.functions as func
import logging
import json
import requests
import base64
import time
from datetime import datetime, timedelta
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

app = func.FunctionApp()

# Configuration
OPENAI_API_URL = 'https://eastus2.api.cognitive.microsoft.com/openai/deployments/gpt-4o-mini/chat/completions?api-version=2024-08-01-preview'
import os
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
EMBEDDING_API_URL = 'https://eastus2.api.cognitive.microsoft.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2023-05-15'

COMPANY_ID = 'saxllp'
PUBLIC_KEY = 'Uxpk3ZrgmsAaAxxB'
PRIVATE_KEY = 'A9mQomscT5Pf1Aue'
CLIENT_ID = '4b9e4159-581e-494e-98f0-fc6af0f5a424'
API_BASE_URL = 'https://api-na.myconnectwise.net/v4_6_release/apis/3.0'
CONNECTWISE_BOARDS = ['Managed Services']

SEARCH_SERVICE_NAME = 'saxmegamind-search'
SEARCH_INDEX_NAME = 'connectwise-tickets'
SEARCH_ADMIN_KEY = os.getenv('SEARCH_ADMIN_KEY', '')
SEARCH_ENDPOINT = f'https://{SEARCH_SERVICE_NAME}.search.windows.net'

auth_string = f'{COMPANY_ID}+{PUBLIC_KEY}:{PRIVATE_KEY}'
encoded_auth = base64.b64encode(auth_string.encode()).decode()
cw_headers = {
    'Authorization': f'Basic {encoded_auth}',
    'clientId': CLIENT_ID,
    'Accept': 'application/json'
}

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX_NAME,
    credential=AzureKeyCredential(SEARCH_ADMIN_KEY)
)

def query_openai(prompt: str, user_text: str, max_retries: int = 5) -> str:
    import time
    for attempt in range(max_retries):
        try:
            response = requests.post(
                OPENAI_API_URL,
                headers={'api-key': OPENAI_API_KEY, 'Content-Type': 'application/json'},
                json={'messages': [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': user_text}
                ]},
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            if 'choices' in result and len(result['choices']) > 0:
                return result['choices'][0]['message']['content']
            else:
                logging.error(f'OpenAI API response missing choices: {result}')
                raise ValueError(f'Invalid OpenAI response: {result}')
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'Connection error, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries}): {e}')
                time.sleep(wait_time)
            else:
                logging.error(f'OpenAI connection failed after {max_retries} attempts: {e}')
                raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'Rate limit hit, retrying in {wait_time}s (attempt {attempt + 1}/{max_retries})')
                time.sleep(wait_time)
            else:
                logging.error(f'OpenAI API error: {e}')
                raise
        except Exception as e:
            logging.error(f'OpenAI API error: {e}')
            raise

def cw_api_get(uri: str, max_retries: int = 5) -> requests.Response:
    import time
    for attempt in range(max_retries):
        try:
            response = requests.get(uri, headers=cw_headers, timeout=60)
            response.raise_for_status()
            return response
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'CW API connection error, retrying in {wait_time}s: {e}')
                time.sleep(wait_time)
            else:
                logging.error(f'CW API connection failed after {max_retries} attempts: {e}')
                raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'CW rate limit, retrying in {wait_time}s')
                time.sleep(wait_time)
            else:
                raise

def get_embedding(text: str, max_retries: int = 5) -> list:
    import time
    for attempt in range(max_retries):
        try:
            response = requests.post(
                EMBEDDING_API_URL,
                headers={'api-key': OPENAI_API_KEY, 'Content-Type': 'application/json'},
                json={'input': text},
                timeout=60
            )
            response.raise_for_status()
            result = response.json()
            if 'data' in result and len(result['data']) > 0:
                return result['data'][0]['embedding']
            else:
                logging.error(f'Embedding API response: {result}')
                raise ValueError(f'Invalid embedding response: {result}')
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'Embedding connection error, retrying in {wait_time}s: {e}')
                time.sleep(wait_time)
            else:
                logging.error(f'Embedding connection failed after {max_retries} attempts: {e}')
                raise
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and attempt < max_retries - 1:
                wait_time = (2 ** attempt) * 5
                logging.warning(f'Embedding rate limit hit, retrying in {wait_time}s')
                time.sleep(wait_time)
            else:
                logging.error(f'Embedding API error: {e}')
                raise
        except Exception as e:
            logging.error(f'Embedding API error: {e}')
            raise

@app.route(route="synctickets", methods=["GET", "POST"], auth_level=func.AuthLevel.ANONYMOUS)
def sync_tickets(req: func.HttpRequest) -> func.HttpResponse:
    logging.info('ConnectWise Ticket Sync started')

    sync_mode = req.params.get('mode', 'incremental')
    
    # Test mode: just 1 day, 1 ticket max
    if sync_mode == 'test':
        days_ago = 1
    else:
        days_ago = 240 if sync_mode == 'full' else 7
    target_since = (datetime.utcnow() - timedelta(days=days_ago)).date()
    target_until = datetime.utcnow().date()

    logging.info(f'{sync_mode.upper()} SYNC MODE: Gathering tickets from last {days_ago} days')
    logging.info(f'Date range: {target_since} through {target_until}')

    all_documents = []
    deleted_ticket_ids = []
    total_tickets_processed = 0
    skipped_tickets = 0

    try:
        for board in CONNECTWISE_BOARDS:
            logging.info(f'Processing board: {board}')

            next_day = target_until + timedelta(days=1)
            filter_str = f"board/name='{board}' and closedDate >= [{target_since}] and closedDate < [{next_day}]"
            page_size = 250
            page = 1

            while True:
                uri = f'{API_BASE_URL}/service/tickets?conditions={requests.utils.quote(filter_str)}&pageSize={page_size}&page={page}'
                response = cw_api_get(uri)
                tickets = response.json()

                if not tickets:
                    break

                page += 1

                for ticket in tickets:
                    # Test mode: only process 1 ticket
                    if sync_mode == 'test' and total_tickets_processed >= 1:
                        break
                    
                    ticket_id = ticket['id']
                    summary = ticket['summary']
                    contact = ticket.get('contact', {}).get('name', 'Unknown')
                    closed_date = datetime.fromisoformat(ticket['closedDate'].replace('Z', '+00:00'))
                    formatted_closed_date = closed_date.isoformat()
                    status = ticket.get('status', {}).get('name', 'Unknown')
                    
                    # Get lastUpdated from ticket
                    last_updated = ticket.get('_info', {}).get('lastUpdated', ticket['closedDate'])
                    last_updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    
                    # Check if ticket exists in index and compare lastUpdated
                    try:
                        existing_paged = search_client.search(
                            search_text='*',
                            filter=f"ticketNumber eq '{ticket_id}'",
                            select=['closedDate'],
                            top=1
                        )
                        existing_doc = next(iter(existing_paged), None)
                        
                        if existing_doc and existing_doc.get('closedDate'):
                            existing_date = datetime.fromisoformat(str(existing_doc['closedDate']).replace('Z', '+00:00'))
                            # Skip if ticket hasn't been updated since we last processed it
                            if last_updated_dt <= existing_date:
                                skipped_tickets += 1
                                logging.info(f'Skipping Ticket #{ticket_id} - no changes since last sync')
                                continue
                    except Exception as e:
                        logging.warning(f'Could not check existing ticket #{ticket_id}: {e}')
                    
                    total_tickets_processed += 1
                    logging.info(f'Processing Ticket #{ticket_id} (Status: {status})')

                    # If ticket is not closed, mark for deletion
                    if 'closed' not in status.lower() and 'completed' not in status.lower():
                        logging.info(f'Ticket #{ticket_id} is not closed, marking for deletion')
                        deleted_ticket_ids.append(ticket_id)
                        continue

                    notes_uri = f'{API_BASE_URL}/service/tickets/{ticket_id}/allnotes'
                    notes_response = cw_api_get(notes_uri)
                    notes = notes_response.json()

                    if not notes:
                        continue

                    valid_notes = [n for n in notes if n.get('text', '').strip()]
                    if not valid_notes:
                        continue

                    sorted_notes = sorted(valid_notes, key=lambda n: n['_info']['dateEntered'])
                    oldest_note = sorted_notes[0]
                    remaining_notes = sorted_notes[1:]

                    problem_text = f"{summary}\n{oldest_note['text']}"
                    resolution_text = '\n'.join([n['text'] for n in remaining_notes])

                    description_prompt = 'You are an IT support summarizer. Based ONLY on the provided ticket summary and first note, rephrase them into a clear, professional description of the problem. Focus on what the user\'s issue is. DO NOT suggest any solutions, actions, or troubleshooting.'
                    resolution_prompt = 'You are an IT support summarizer. Based ONLY on the later notes, summarize any actions taken or resolutions provided. Keep it factual, neutral, and professional. DO NOT suggest additional troubleshooting or make assumptions beyond what is stated.'

                    ai_description = query_openai(description_prompt, problem_text)
                    ai_resolution = query_openai(resolution_prompt, resolution_text) if resolution_text else 'No additional notes found.'

                    combined_text = f'Problem: {ai_description}\n\nResolution: {ai_resolution}'
                    embedding_vector = get_embedding(combined_text)

                    # Chunking
                    max_chunk_length = 2000
                    chunks = []

                    if len(combined_text) <= max_chunk_length:
                        chunks.append({'chunkId': 0, 'content': combined_text})
                    else:
                        chunk_count = (len(combined_text) + max_chunk_length - 1) // max_chunk_length
                        for i in range(chunk_count):
                            start_index = i * max_chunk_length
                            chunk_content = combined_text[start_index:start_index + max_chunk_length]
                            chunks.append({'chunkId': i, 'content': chunk_content})

                    # Create documents
                    for chunk in chunks:
                        document_id = f'{ticket_id}-{chunk["chunkId"]}'
                        all_documents.append({
                            'id': document_id,
                            'ticketNumber': str(ticket_id),
                            'contact': contact,
                            'closedDate': formatted_closed_date,
                            'problemSummary': ai_description,
                            'resolutionSummary': ai_resolution,
                            'chunkId': chunk['chunkId'],
                            'content': chunk['content'],
                            'contentVector': embedding_vector
                        })
                    
                    # Small delay between tickets to avoid rate limits (3 OpenAI calls per ticket)
                    time.sleep(1)

                if len(tickets) < page_size:
                    break

        logging.info(f'Total tickets processed: {total_tickets_processed}')
        logging.info(f'Tickets skipped (unchanged): {skipped_tickets}')
        logging.info(f'Total documents to upload: {len(all_documents)}')
        logging.info(f'Tickets to delete: {len(deleted_ticket_ids)}')

        # Delete reopened tickets
        if deleted_ticket_ids:
            logging.info('Deleting documents for reopened/deleted tickets')
            for ticket_id in deleted_ticket_ids:
                search_results = search_client.search(
                    search_text='*',
                    filter=f"ticketNumber eq '{ticket_id}'",
                    select=['id']
                )
                delete_ids = [result['id'] for result in search_results]
                if delete_ids:
                    search_client.delete_documents(documents=[{'id': doc_id} for doc_id in delete_ids])
                    logging.info(f'Deleted {len(delete_ids)} documents for ticket #{ticket_id}')

        # Upload documents
        if all_documents:
            logging.info('Uploading documents to Azure Search')
            batch_size = 1000
            for i in range(0, len(all_documents), batch_size):
                batch = all_documents[i:i + batch_size]
                search_client.merge_or_upload_documents(documents=batch)
                logging.info(f'Uploaded batch {i // batch_size + 1} ({len(batch)} documents)')

        summary = {
            'syncMode': sync_mode,
            'totalTicketsProcessed': total_tickets_processed,
            'ticketsSkipped': skipped_tickets,
            'documentsUploaded': len(all_documents),
            'ticketsDeleted': len(deleted_ticket_ids),
            'dateRange': {
                'from': str(target_since),
                'to': str(target_until)
            }
        }

        logging.info('Sync completed successfully')
        return func.HttpResponse(
            json.dumps(summary, indent=2),
            status_code=200,
            mimetype='application/json'
        )

    except Exception as e:
        logging.error(f'Error during sync: {e}', exc_info=True)
        return func.HttpResponse(
            json.dumps({'error': str(e)}),
            status_code=500,
            mimetype='application/json'
        )


@app.route(route="ping", methods=["GET"], auth_level=func.AuthLevel.ANONYMOUS)
def ping(req: func.HttpRequest) -> func.HttpResponse:
    """Health check endpoint"""
    return func.HttpResponse(
        json.dumps({'ok': True, 'time': datetime.utcnow().isoformat() + '+00:00'}),
        status_code=200,
        mimetype='application/json'
    )


def _do_timer_sync():
    """Shared sync logic for timer triggers"""
    logging.info('Timer trigger: ConnectWise Ticket Sync started')
    
    # Get sync configuration from environment
    sync_mode = os.getenv('TIMER_SYNC_MODE', 'incremental')
    incremental_days = int(os.getenv('INCREMENTAL_DAYS', '80'))
    backfill_until = os.getenv('BACKFILL_UNTIL_UTC', None)
    
    if sync_mode == 'incremental':
        days_ago = incremental_days
    else:
        days_ago = 240
    
    target_since = (datetime.utcnow() - timedelta(days=days_ago)).date()
    target_until = datetime.utcnow().date()
    
    # If backfill date is set, use it
    if backfill_until:
        try:
            backfill_dt = datetime.fromisoformat(backfill_until.replace('Z', '+00:00'))
            target_since = backfill_dt.date()
            logging.info(f'Using backfill date: {target_since}')
        except Exception as e:
            logging.warning(f'Could not parse BACKFILL_UNTIL_UTC: {e}')
    
    logging.info(f'Timer sync mode: {sync_mode.upper()}, days: {days_ago}')
    logging.info(f'Date range: {target_since} through {target_until}')

    all_documents = []
    deleted_ticket_ids = []
    total_tickets_processed = 0
    skipped_tickets = 0
    total_uploaded = 0

    try:
        for board in CONNECTWISE_BOARDS:
            logging.info(f'Processing board: {board}')

            next_day = target_until + timedelta(days=1)
            filter_str = f"board/name='{board}' and closedDate >= [{target_since}] and closedDate < [{next_day}]"
            page_size = 250
            page = 1

            while True:
                uri = f'{API_BASE_URL}/service/tickets?conditions={requests.utils.quote(filter_str)}&pageSize={page_size}&page={page}'
                response = cw_api_get(uri)
                tickets = response.json()

                if not tickets:
                    break

                page += 1

                for ticket in tickets:
                    ticket_id = ticket['id']
                    summary = ticket['summary']
                    contact = ticket.get('contact', {}).get('name', 'Unknown')
                    closed_date = datetime.fromisoformat(ticket['closedDate'].replace('Z', '+00:00'))
                    formatted_closed_date = closed_date.isoformat()
                    status = ticket.get('status', {}).get('name', 'Unknown')
                    
                    last_updated = ticket.get('_info', {}).get('lastUpdated', ticket['closedDate'])
                    last_updated_dt = datetime.fromisoformat(last_updated.replace('Z', '+00:00'))
                    
                    try:
                        existing_paged = search_client.search(
                            search_text='*',
                            filter=f"ticketNumber eq '{ticket_id}'",
                            select=['closedDate'],
                            top=1
                        )
                        existing_doc = next(iter(existing_paged), None)
                        
                        if existing_doc and existing_doc.get('closedDate'):
                            existing_date = datetime.fromisoformat(str(existing_doc['closedDate']).replace('Z', '+00:00'))
                            if last_updated_dt <= existing_date:
                                skipped_tickets += 1
                                logging.info(f'Skipping Ticket #{ticket_id} - no changes since last sync')
                                continue
                    except Exception as e:
                        logging.warning(f'Could not check existing ticket #{ticket_id}: {e}')
                    
                    total_tickets_processed += 1
                    logging.info(f'Processing Ticket #{ticket_id} (Status: {status})')

                    if 'closed' not in status.lower() and 'completed' not in status.lower():
                        logging.info(f'Ticket #{ticket_id} is not closed, marking for deletion')
                        deleted_ticket_ids.append(ticket_id)
                        continue

                    notes_uri = f'{API_BASE_URL}/service/tickets/{ticket_id}/allnotes'
                    notes_response = cw_api_get(notes_uri)
                    notes = notes_response.json()

                    if not notes:
                        continue

                    valid_notes = [n for n in notes if n.get('text', '').strip()]
                    if not valid_notes:
                        continue

                    sorted_notes = sorted(valid_notes, key=lambda n: n['_info']['dateEntered'])
                    oldest_note = sorted_notes[0]
                    remaining_notes = sorted_notes[1:]

                    problem_text = f"{summary}\n{oldest_note['text']}"
                    resolution_text = '\n'.join([n['text'] for n in remaining_notes])

                    description_prompt = 'You are an IT support summarizer. Based ONLY on the provided ticket summary and first note, rephrase them into a clear, professional description of the problem. Focus on what the user\'s issue is. DO NOT suggest any solutions, actions, or troubleshooting.'
                    resolution_prompt = 'You are an IT support summarizer. Based ONLY on the later notes, summarize any actions taken or resolutions provided. Keep it factual, neutral, and professional. DO NOT suggest additional troubleshooting or make assumptions beyond what is stated.'

                    ai_description = query_openai(description_prompt, problem_text)
                    ai_resolution = query_openai(resolution_prompt, resolution_text) if resolution_text else 'No additional notes found.'

                    combined_text = f'Problem: {ai_description}\n\nResolution: {ai_resolution}'
                    embedding_vector = get_embedding(combined_text)

                    max_chunk_length = 2000
                    chunks = []

                    if len(combined_text) <= max_chunk_length:
                        chunks.append({'chunkId': 0, 'content': combined_text})
                    else:
                        chunk_count = (len(combined_text) + max_chunk_length - 1) // max_chunk_length
                        for i in range(chunk_count):
                            start_index = i * max_chunk_length
                            chunk_content = combined_text[start_index:start_index + max_chunk_length]
                            chunks.append({'chunkId': i, 'content': chunk_content})

                    for chunk in chunks:
                        document_id = f'{ticket_id}-{chunk["chunkId"]}'
                        all_documents.append({
                            'id': document_id,
                            'ticketNumber': str(ticket_id),
                            'contact': contact,
                            'closedDate': formatted_closed_date,
                            'problemSummary': ai_description,
                            'resolutionSummary': ai_resolution,
                            'chunkId': chunk['chunkId'],
                            'content': chunk['content'],
                            'contentVector': embedding_vector
                        })
                    
                    # Upload in small batches to avoid timeout losing all work
                    if len(all_documents) >= 10:
                        logging.info(f'Uploading batch of {len(all_documents)} documents...')
                        search_client.merge_or_upload_documents(documents=all_documents)
                        total_uploaded += len(all_documents)
                        all_documents = []
                    
                    time.sleep(1)

                if len(tickets) < page_size:
                    break

        # Upload any remaining documents
        if all_documents:
            logging.info(f'Uploading final batch of {len(all_documents)} documents...')
            search_client.merge_or_upload_documents(documents=all_documents)
            total_uploaded += len(all_documents)

        logging.info(f'Timer sync completed: {total_tickets_processed} processed, {skipped_tickets} skipped, {total_uploaded} uploaded')

    except Exception as e:
        logging.error(f'Timer sync error: {e}', exc_info=True)
        raise


@app.timer_trigger(schedule="0 0 7-18 * * *", arg_name="timer", run_on_startup=False)
def sync_tickets_timer_business(timer: func.TimerRequest) -> None:
    """Hourly sync during business hours (7am-6pm UTC)"""
    _do_timer_sync()


@app.timer_trigger(schedule="0 0 19,22,1,4 * * *", arg_name="timer", run_on_startup=False)
def sync_tickets_timer_offhours(timer: func.TimerRequest) -> None:
    """Every 3 hours during off-hours (7pm, 10pm, 1am, 4am UTC)"""
    _do_timer_sync()
