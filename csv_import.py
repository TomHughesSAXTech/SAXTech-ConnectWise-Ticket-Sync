import csv
import json
import requests
import time
from datetime import datetime
from azure.search.documents import SearchClient
from azure.core.credentials import AzureKeyCredential

# Configuration
SEARCH_SERVICE_NAME = 'saxmegamind-search'
SEARCH_INDEX_NAME = 'connectwise-tickets'
SEARCH_ADMIN_KEY = os.getenv('SEARCH_ADMIN_KEY', '')
SEARCH_ENDPOINT = f'https://{SEARCH_SERVICE_NAME}.search.windows.net'

EMBEDDING_API_URL = 'https://eastus2.api.cognitive.microsoft.com/openai/deployments/text-embedding-3-large/embeddings?api-version=2023-05-15'
import os
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')

search_client = SearchClient(
    endpoint=SEARCH_ENDPOINT,
    index_name=SEARCH_INDEX_NAME,
    credential=AzureKeyCredential(SEARCH_ADMIN_KEY)
)

def get_embeddings_batch(texts: list, retries=3) -> list:
    """Get embeddings for multiple texts in a single API call"""
    for attempt in range(retries):
        try:
            response = requests.post(
                EMBEDDING_API_URL,
                headers={'api-key': OPENAI_API_KEY, 'Content-Type': 'application/json'},
                json={'input': texts},
                timeout=120
            )
            response.raise_for_status()
            result = response.json()
            # Return embeddings in order
            return [item['embedding'] for item in sorted(result['data'], key=lambda x: x['index'])]
        except (requests.exceptions.Timeout, requests.exceptions.RequestException) as e:
            if attempt < retries - 1:
                wait_time = (attempt + 1) * 5
                print(f"    Retry {attempt + 1}/{retries} after {wait_time}s...")
                time.sleep(wait_time)
            else:
                raise

def process_csv(csv_path: str):
    print(f"Reading CSV from {csv_path}...")
    
    # First pass: read all rows and prepare data
    all_rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
    
    print(f"Found {len(all_rows)} tickets to process")
    
    # Process in batches for embedding generation
    batch_size = 50
    documents = []
    
    for batch_start in range(0, len(all_rows), batch_size):
        batch_end = min(batch_start + batch_size, len(all_rows))
        batch_rows = all_rows[batch_start:batch_end]
        
        print(f"\nProcessing batch {batch_start // batch_size + 1}/{(len(all_rows) + batch_size - 1) // batch_size} (tickets {batch_start + 1}-{batch_end})...")
        
        # Prepare all texts for this batch
        batch_texts = []
        batch_metadata = []
        
        for row in batch_rows:
            ticket_number = row['TicketNumber']
            contact = row['Contact']
            created_date = row['CreatedDate']
            problem_summary = row['ProblemSummary']
            resolution_summary = row['ResolutionSummary']
            
            # Parse date
            try:
                closed_date = datetime.strptime(created_date, '%Y-%m-%d %H:%M:%S')
                formatted_closed_date = closed_date.isoformat() + 'Z'
            except:
                formatted_closed_date = created_date + 'Z' if 'Z' not in created_date else created_date
            
            # Create combined text for embedding
            combined_text = f'Problem: {problem_summary}\n\nResolution: {resolution_summary}'
            
            batch_texts.append(combined_text)
            batch_metadata.append({
                'ticket_number': ticket_number,
                'contact': contact,
                'closed_date': formatted_closed_date,
                'problem_summary': problem_summary,
                'resolution_summary': resolution_summary,
                'combined_text': combined_text
            })
        
        # Generate embeddings for entire batch
        print(f"  Generating {len(batch_texts)} embeddings...")
        embedding_vectors = get_embeddings_batch(batch_texts)
        
        # Create documents with embeddings
        for metadata, embedding_vector in zip(batch_metadata, embedding_vectors):
            # Chunking (keeping same logic as function)
            max_chunk_length = 2000
            chunks = []
            combined_text = metadata['combined_text']
            
            if len(combined_text) <= max_chunk_length:
                chunks.append({'chunkId': 0, 'content': combined_text})
            else:
                chunk_count = (len(combined_text) + max_chunk_length - 1) // max_chunk_length
                for i in range(chunk_count):
                    start_index = i * max_chunk_length
                    chunk_content = combined_text[start_index:start_index + max_chunk_length]
                    chunks.append({'chunkId': i, 'content': chunk_content})
            
            # Create documents for each chunk
            for chunk in chunks:
                document_id = f'{metadata["ticket_number"]}-{chunk["chunkId"]}'
                documents.append({
                    'id': document_id,
                    'ticketNumber': str(metadata['ticket_number']),
                    'contact': metadata['contact'],
                    'closedDate': metadata['closed_date'],
                    'problemSummary': metadata['problem_summary'],
                    'resolutionSummary': metadata['resolution_summary'],
                    'chunkId': chunk['chunkId'],
                    'content': chunk['content'],
                    'contentVector': embedding_vector
                })
        
        time.sleep(1)  # Brief pause between batches
    
    print(f"\nTotal tickets processed: {len(all_rows)}")
    print(f"Total documents to upload: {len(documents)}")
    
    # Upload in batches
    batch_size = 1000
    for i in range(0, len(documents), batch_size):
        batch = documents[i:i + batch_size]
        print(f"Uploading batch {i // batch_size + 1} ({len(batch)} documents)...")
        search_client.merge_or_upload_documents(documents=batch)
    
    print("\n✅ CSV import complete!")
    print(f"   Total tickets: {len(all_rows)}")
    print(f"   Documents uploaded: {len(documents)}")

if __name__ == '__main__':
    csv_path = '/Users/tom/Downloads/MegamindLLM.csv'
    process_csv(csv_path)
