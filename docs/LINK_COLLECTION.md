# Link Collection and Parsing Architecture

## Overview

This document describes the new two-phase link collection and parsing architecture implemented to improve performance and reliability of the offer collection pipeline.

## Architecture

### Phase 1: Link Collection
- Collectors (e.g., `MLCollector`) scan listing pages and extract product URLs
- URLs are saved to the `links_coleta` database table with their source
- No product data is fetched at this stage (fast operation)

### Phase 2: Link Parsing
- Links are read from the `links_coleta` table
- Multiple Chrome sessions run in parallel to parse product details
- Parsed data is processed through the offer pipeline
- Successfully parsed links are marked as inactive
- Failed links remain active for retry on next run

## Database Schema

### `links_coleta` Table

| Column | Type | Description |
|--------|------|-------------|
| `id` | INTEGER | Primary key |
| `url` | VARCHAR | Product URL to be parsed |
| `source` | VARCHAR | Origin of the link (e.g., "mercadolivre") |
| `ativo` | BOOLEAN | True if link still needs processing |
| `criado_em` | DATETIME | Creation timestamp |
| `processado_em` | DATETIME | Last successful processing timestamp |
| `tentativas` | INTEGER | Number of parse attempts |

**Constraints:**
- Unique constraint on `(url, source)` prevents duplicate links
- Indexed on: `id`, `url`, `source`, `ativo`, `criado_em`

## Components

### 1. LinkCollectorService (`link_collector_service.py`)

Manages link insertion into the database:
- Prevents duplicate links (checks if URL+source already exists and is active)
- Returns statistics on inserted/duplicate/error counts

**Usage:**
```python
from backend.modules.services.link_collector_service import LinkCollectorService

service = LinkCollectorService(db_session)
links = [
    {"url_base": "https://...", "source": "mercadolivre"},
    # ...
]
stats = service.save_links(links)
print(f"Inserted: {stats['inserted']}, Duplicates: {stats['duplicates']}")
```

### 2. LinkParser (`link_parser.py`)

Processes links from the database in parallel:
- Reads active links from table
- Cleans up expired links (TTL)
- Spawns multiple Chrome sessions for parallel parsing
- Marks links as inactive after successful parse
- Keeps links active and increments `tentativas` on failure

**Configuration:**
- `LINK_PARSER_WORKERS`: Number of parallel parsing workers (default: 3)
- `LINK_PARSER_TTL_DAYS`: Time-to-live in days for active links (default: 1)

**Usage:**
```python
from backend.modules.services.link_parser import LinkParser

parser = LinkParser(db_session)

# Cleanup expired links
parser.cleanup_expired_links()

# Get pending links
links = parser.get_pending_links()

# Parse in parallel
def parse_link(link, client):
    # Your parsing logic here
    return parsed_data

results = parser.parse_links_parallel(links, parse_link)
```

### 3. MLParser (`ml_parser.py`)

Mercado Livre-specific parser:
- Extracts all product details from ML product pages
- Handles JSON parsing from `__PRELOADED_STATE__`
- Extracts prices, images, seller info, affiliate links
- Separated from collector for reusability

**Usage:**
```python
from backend.modules.parsers.ml_parser import MLParser

parser = MLParser()
data = parser.parse(link_coleta_object, selenium_client)
```

### 4. Modified MLCollector

The `MLCollector.run_collection()` now only collects links without enrichment:

```python
from backend.modules.collectors.ml_collector import MLCollector

collector = MLCollector()
links = collector.run_collection()  # Returns list of {"url_base": ..., "source": ...}
```

For legacy behavior (collect + enrich in one step), use:
```python
items = collector.run_collection_legacy()  # Not recommended
```

## Pipeline Flow

The updated `run_pipeline.py` now follows this sequence:

1. **Collect Links**: `MLCollector.run_collection()` → list of URLs
2. **Save to DB**: `LinkCollectorService.save_links()` → prevents duplicates
3. **Parse Links**: `LinkParser.parse_links_parallel()` → parallel enrichment
4. **Process Offers**: `OfferProcessor.process_item()` → validate & save
5. **Validate**: Standard validation logic
6. **Publish**: Standard publication logic
7. **Metrics**: Standard metrics analysis

## Benefits

1. **No Duplicates**: Links are deduplicated at the database level
2. **Parallel Processing**: Multiple Chrome sessions parse links simultaneously
3. **Retry Logic**: Failed links remain active for automatic retry
4. **TTL Management**: Expired links are automatically cleaned up
5. **Source Tracking**: Each link knows its origin for correct parser selection
6. **Scalability**: Easy to add new collectors and parsers
7. **Debugging**: Link collection and parsing are separate, easier to debug

## Configuration

Add these to your `config_vars` table or environment:

```python
LINK_PARSER_WORKERS = 3        # Number of parallel Chrome sessions
LINK_PARSER_TTL_DAYS = 1       # Days before expired links are deleted
```

## Testing

Run the test suite:

```bash
python3 test_link_collection.py
```

Tests cover:
- Link collection and storage
- Duplicate prevention
- TTL cleanup
- Success/failure marking
- Attempt counter

## Migration from Legacy Code

If you have existing code using the old approach:

**Before:**
```python
collector = MLCollector()
items = collector.run_collection()  # Collected + enriched
```

**After:**
```python
# Phase 1: Collect
collector = MLCollector()
links = collector.run_collection()

# Phase 2: Save
link_service = LinkCollectorService(db)
link_service.save_links(links)

# Phase 3: Parse
parser = LinkParser(db)
pending = parser.get_pending_links()
ml_parser = MLParser()
items = parser.parse_links_parallel(pending, ml_parser.parse)
```

## Future Enhancements

- [ ] Add priority field to parse important links first
- [ ] Add retry limit (max tentativas before giving up)
- [ ] Add metrics dashboard for link processing stats
- [ ] Support for multiple sources in parallel
- [ ] Add webhook notifications for parsing failures
