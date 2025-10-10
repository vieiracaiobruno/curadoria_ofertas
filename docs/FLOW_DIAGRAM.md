# Link Collection Flow Diagram

## Before (Legacy)

```
┌─────────────────┐
│   MLCollector   │
│                 │
│ 1. Scan pages   │
│ 2. Extract URLs │
│ 3. Parse each   │──┐ Sequential processing
│    product      │  │ All URLs in memory
│ 4. Return data  │  │ No retry logic
└────────┬────────┘  │ No deduplication
         │           │
         v           │
  ┌──────────────┐   │
  │ All Products │◄──┘
  │   in Memory  │
  └──────┬───────┘
         │
         v
  ┌──────────────┐
  │   Process    │
  │   Offers     │
  └──────────────┘
```

## After (New Implementation)

```
┌─────────────────────────────────────────────────────────────────┐
│                        PHASE 1: COLLECTION                       │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────┐
│   MLCollector   │
│                 │
│ 1. Scan pages   │     Fast operation
│ 2. Extract URLs │     No parsing
│ 3. Return links │     Low memory
└────────┬────────┘
         │
         v
    [List of URLs]
         │
         v
┌─────────────────┐
│ LinkCollector   │
│    Service      │
│                 │
│ • Check active  │
│ • Skip dupes    │──────────────────────────┐
│ • Insert new    │                          │
└────────┬────────┘                          │
         │                                   │
         v                                   │
  ┌──────────────┐                           │
  │ links_coleta │ ◄──────────────────────── │ Persistent Storage
  │   (Table)    │                           │ Deduplication
  │              │                           │ TTL Management
  │ • url        │                           │
  │ • source     │                           │
  │ • ativo      │                           │
  │ • tentativas │                           │
  └──────┬───────┘                           │
         │                                   │
         │                                   │
┌─────────────────────────────────────────────────────────────────┐
│                        PHASE 2: PARSING                          │
└─────────────────────────────────────────────────────────────────┘
         │
         v
  ┌──────────────┐
  │  LinkParser  │
  │              │
  │ 1. Cleanup   │──► Remove expired links (TTL)
  │    expired   │
  │              │
  │ 2. Get active│──► WHERE ativo = true
  │    links     │
  │              │
  │ 3. Spawn     │──► Create N Chrome workers
  │    workers   │
  └──────┬───────┘
         │
         v
    ┌────────────────────────────────────────┐
    │      Parallel Processing               │
    │                                        │
    │  ┌──────────┐  ┌──────────┐  ┌──────────┐
    │  │ Worker 1 │  │ Worker 2 │  │ Worker N │
    │  │  Chrome  │  │  Chrome  │  │  Chrome  │
    │  └────┬─────┘  └────┬─────┘  └────┬─────┘
    │       │             │             │
    │       v             v             v
    │  ┌─────────┐   ┌─────────┐   ┌─────────┐
    │  │MLParser │   │MLParser │   │MLParser │
    │  │ Parse   │   │ Parse   │   │ Parse   │
    │  │ Link    │   │ Link    │   │ Link    │
    │  └────┬────┘   └────┬────┘   └────┬────┘
    │       │             │             │
    └───────┼─────────────┼─────────────┼──────┘
            │             │             │
            └─────────────┴─────────────┘
                          │
                          v
                  ┌───────────────┐
                  │ Mark Results  │
                  │               │
                  │ Success:      │
                  │  ativo=false  │
                  │  timestamp    │
                  │               │
                  │ Failure:      │
                  │  ativo=true   │
                  │  tentativas++ │
                  └───────┬───────┘
                          │
                          v
                  ┌───────────────┐
                  │ Parsed Items  │
                  └───────┬───────┘
                          │
┌─────────────────────────────────────────────────────────────────┐
│                  PHASE 3: PROCESS & PUBLISH                      │
└─────────────────────────────────────────────────────────────────┘
                          │
                          v
                  ┌───────────────┐
                  │ OfferProcessor│
                  │               │
                  │ • Validate    │
                  │ • Save        │
                  │ • Tag         │
                  └───────┬───────┘
                          │
                          v
                  ┌───────────────┐
                  │   Validator   │
                  │               │
                  │ • Check rules │
                  │ • Approve     │
                  └───────┬───────┘
                          │
                          v
                  ┌───────────────┐
                  │   Publisher   │
                  │               │
                  │ • Format      │
                  │ • Post        │
                  └───────────────┘
```

## Key Improvements

### 1. Separation of Concerns
- **Collection**: Fast scanning, no parsing
- **Storage**: Persistent, deduplicated
- **Parsing**: Parallel, retryable

### 2. Parallel Processing
```
Before: Sequential (1 at a time)
[Link 1] → [Link 2] → [Link 3] → [Link 4]
Time: ~8 seconds

After: Parallel (3 workers)
[Link 1]
[Link 2]  ← Processing simultaneously
[Link 3]
Time: ~3 seconds
```

### 3. Retry Logic
```
Attempt 1: [Parse] → FAIL → ativo=true, tentativas=1
           ↓
           Wait for next run
           ↓
Attempt 2: [Parse] → FAIL → ativo=true, tentativas=2
           ↓
           Wait for next run
           ↓
Attempt 3: [Parse] → SUCCESS → ativo=false, processed_at=NOW
```

### 4. Deduplication
```
Run 1: 
  Links: [A, B, C]
  Database: [A, B, C] (inserted)

Run 2:
  Links: [B, C, D]  
  Database: [A, B, C, D] (only D inserted, B & C skipped)
```

### 5. TTL Cleanup
```
Day 0: Link created (criado_em = 2025-01-01)
       ativo = true
       
Day 1: Still active, attempting parse
       ativo = true
       
Day 2: TTL expired
       Link deleted by cleanup_expired_links()
```

## Benefits Summary

| Feature | Before | After |
|---------|--------|-------|
| **Processing** | Sequential | Parallel (3x faster) |
| **Duplicates** | Possible | Prevented |
| **Failed Links** | Lost | Retry automatically |
| **Memory** | All in RAM | Database-backed |
| **Scalability** | Limited | Easy to scale |
| **Debugging** | Hard | Easy (separate phases) |

## Configuration Impact

```python
# More workers = Faster parsing (but more resources)
LINK_PARSER_WORKERS = 1   # ~30 seconds for 10 links
LINK_PARSER_WORKERS = 3   # ~10 seconds for 10 links ✓
LINK_PARSER_WORKERS = 5   # ~6 seconds for 10 links

# Longer TTL = More retries
LINK_PARSER_TTL_DAYS = 0.5  # 12 hours
LINK_PARSER_TTL_DAYS = 1    # 24 hours ✓ (recommended)
LINK_PARSER_TTL_DAYS = 3    # 72 hours
```
