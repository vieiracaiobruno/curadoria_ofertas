# Quick Start: Using the Link Collection System

## Overview

The link collection system separates URL collection from data parsing, enabling better performance, retry logic, and parallel processing.

## Running the Pipeline

### Standard Usage

Run the complete pipeline:

```bash
python3 run_pipeline.py
```

This executes all phases:
1. Collect links from sources (e.g., Mercado Livre)
2. Save links to database (prevents duplicates)
3. Parse links in parallel (multiple Chrome sessions)
4. Process offers
5. Validate
6. Publish
7. Analyze metrics

### Configuration

Set these environment variables or add to `config_vars` table:

```bash
# Link parser settings
LINK_PARSER_WORKERS=3      # Number of parallel Chrome sessions (default: 3)
LINK_PARSER_TTL_DAYS=1     # Days before expired links are deleted (default: 1)

# ML collector settings
ML_MAX_PAGES=1             # Number of listing pages to scan (default: 1)
ML_REQUEST_DELAY_SEC=2     # Delay between requests (default: 2)
ML_ENRICH_WORKERS=1        # Parallel workers for legacy mode (default: 1)
```

## Database Setup

Create database tables:

```bash
python3 backend/db/create_tables.py
```

This creates all tables including the new `links_coleta` table.

## Testing

### Unit Tests

Test link collection components:

```bash
python3 test_link_collection.py
```

Tests:
- Link collection and storage
- Duplicate prevention
- TTL cleanup
- Success/failure marking
- Attempt counter

### Integration Tests

Test complete flow:

```bash
python3 test_integration_flow.py
```

Tests:
- End-to-end collection → parsing flow
- Duplicate handling across runs
- Retry logic

## Manual Operations

### Check Pending Links

```python
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta

db = SessionLocal()
pending = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
print(f"Pending links: {pending}")
db.close()
```

### Manually Clean Expired Links

```python
from backend.db.database import SessionLocal
from backend.modules.services.link_parser import LinkParser

db = SessionLocal()
parser = LinkParser(db)
parser.cleanup_expired_links()
db.close()
```

### Reset Failed Links

If you want to retry all failed links:

```python
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta

db = SessionLocal()
# Reset attempt counter for all active links
db.query(LinkColeta).filter(LinkColeta.ativo == True).update({"tentativas": 0})
db.commit()
db.close()
```

### View Link Statistics

```python
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta

db = SessionLocal()
total = db.query(LinkColeta).count()
active = db.query(LinkColeta).filter(LinkColeta.ativo == True).count()
processed = db.query(LinkColeta).filter(LinkColeta.ativo == False).count()

print(f"Total links: {total}")
print(f"Active (pending): {active}")
print(f"Processed: {processed}")
db.close()
```

## Troubleshooting

### Links Not Being Collected

Check if collector is configured correctly:
```bash
# Check ML collector settings
python3 -c "from backend.modules.utils.config import get_config; print('Pages:', get_config('ML_MAX_PAGES', '1'))"
```

### Links Not Being Parsed

Check pending links:
```python
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta

db = SessionLocal()
pending = db.query(LinkColeta).filter(LinkColeta.ativo == True).all()
for link in pending[:5]:  # Show first 5
    print(f"ID: {link.id}, URL: {link.url}, Attempts: {link.tentativas}")
db.close()
```

### Too Many Failed Attempts

View links with high attempt counts:
```python
from backend.db.database import SessionLocal
from backend.models.models import LinkColeta

db = SessionLocal()
failed = db.query(LinkColeta).filter(
    LinkColeta.ativo == True,
    LinkColeta.tentativas > 3
).all()
print(f"Links with >3 attempts: {len(failed)}")
db.close()
```

### Duplicate Links Error

The system automatically prevents duplicates. If you see this error:
1. Check if the link already exists and is active
2. Wait for the TTL to expire (default: 1 day)
3. Or manually mark old links as inactive

## Performance Tuning

### Increase Parallel Workers

For faster parsing, increase workers (requires more memory/CPU):

```python
# In config_vars or environment
LINK_PARSER_WORKERS=5  # Up to 10 recommended
```

### Adjust TTL

For faster cleanup:
```python
LINK_PARSER_TTL_DAYS=0.5  # 12 hours
```

For longer retry window:
```python
LINK_PARSER_TTL_DAYS=3  # 3 days
```

### Batch Size

Process links in batches:
```python
from backend.modules.services.link_parser import LinkParser

parser = LinkParser(db)
pending = parser.get_pending_links(limit=100)  # Process only 100 at a time
```

## Next Steps

- Read [LINK_COLLECTION.md](LINK_COLLECTION.md) for architecture details
- Check logs in `logs/` directory for debugging
- Monitor database size and cleanup old links periodically
- Add more collectors for other sources (Amazon, etc.)

## Support

For issues or questions:
1. Check logs: `tail -f logs/pipeline.log`
2. Run tests to verify setup
3. Review documentation in `docs/`
