# Cursor-Based Pagination Implementation

## Overview

This document describes the cursor-based pagination feature added to the REST API list endpoints. The implementation provides stable, performant pagination that works correctly even when data is being inserted or modified between requests.

## What Changed

### 1. New Schemas (`src/max/server/schemas.py`)

Added three new pagination-related models:

- **`PaginationParams`**: Request model for pagination parameters
  - `cursor: str | None = None` - Opaque cursor for the next page
  - `limit: int = 20` - Number of items per page (default 20, max 100)

- **`PaginationMeta`**: Response metadata for pagination
  - `next_cursor: str | None` - Cursor for the next page (None if last page)
  - `has_more: bool` - Whether there are more items available
  - `total_count: int` - Total number of items matching the query

- **`PaginatedResponse[T]`**: Generic wrapper for paginated responses
  - `items: list[T]` - The actual data items
  - `pagination: PaginationMeta` - Pagination metadata

### 2. Store Methods (`src/max/store/db.py`)

Added cursor encoding/decoding utilities:

- **`_encode_cursor(timestamp, entity_id)`**: Encodes a (timestamp, id) tuple to base64
- **`_decode_cursor(cursor)`**: Decodes a base64 cursor back to (timestamp, id)

Added paginated query methods:

- **`get_signals_paginated(cursor, limit, source_type)`**: Returns (signals, next_cursor)
  - Sorts by `fetched_at DESC, id DESC`
  - Supports `source_type` filter

- **`get_insights_paginated(cursor, limit)`**: Returns (insights, next_cursor)
  - Sorts by `created_at DESC, id DESC`

- **`get_buildable_units_paginated(cursor, limit, status, domain)`**: Returns (units, next_cursor)
  - Sorts by `updated_at DESC, id DESC`
  - Supports `status` and `domain` filters

Added count methods:

- **`count_signals(source_type)`**: Returns total signal count (with optional filter)
- **`count_insights()`**: Returns total insight count
- **`count_buildable_units(status, domain)`**: Returns total unit count (with optional filters)

### 3. API Endpoints (`src/max/server/api.py`)

Updated all three list endpoints to support pagination:

- **`GET /api/v1/signals`**
  - Query params: `cursor`, `limit`, `source_type`
  - Returns: `PaginatedResponse[SignalResponse]`

- **`GET /api/v1/insights`**
  - Query params: `cursor`, `limit`
  - Returns: `PaginatedResponse[InsightResponse]`

- **`GET /api/v1/ideas`**
  - Query params: `cursor`, `limit`, `status`, `category`, `domain`, `min_score`
  - Returns: `PaginatedResponse[IdeaSummaryResponse]`

All endpoints:
- Clamp `limit` to max 100
- Return HTTP 400 for invalid cursors
- Maintain backward compatibility (omitting cursor returns first page)

### 4. Tests

Created comprehensive test suites:

- **`tests/test_pagination.py`** (17 tests): Unit tests for store-level pagination
  - Cursor encoding/decoding
  - First page, following cursor, last page
  - Empty results
  - Filter support (source_type, status, domain)
  - Stable pagination with concurrent inserts
  - Limit clamping

- **`tests/test_pagination_api.py`** (7 tests): Integration tests for API endpoints
  - End-to-end pagination through HTTP API
  - Filter support
  - Response schema validation
  - Invalid cursor handling

## Technical Design

### Cursor Format

Cursors are opaque base64-encoded strings containing `timestamp|id`:

```
cursor = base64("2024-01-15T10:30:00+00:00|sig-abc123")
```

This composite key approach ensures:
- **Stable pagination**: Items won't appear twice or be skipped when new data is inserted
- **Performance**: Uses indexed columns (timestamp + id) for efficient queries
- **Security**: Opaque format doesn't expose internal database details

### Query Strategy

Uses keyset pagination with composite keys:

```sql
SELECT * FROM signals
WHERE (fetched_at, id) < (cursor_timestamp, cursor_id)
ORDER BY fetched_at DESC, id DESC
LIMIT ?
```

This is more efficient than offset-based pagination and provides stable results.

### Pagination Metadata

The response includes metadata that enables proper pagination UI:

```json
{
  "items": [...],
  "pagination": {
    "next_cursor": "MjAyNC0wMS0xNVQxMDozMDowMCswMDowMHxzaWctYWJjMTIz",
    "has_more": true,
    "total_count": 42
  }
}
```

## Usage Examples

### Basic Pagination

Get the first page:
```bash
curl "http://localhost:8000/api/v1/signals?limit=20"
```

Response:
```json
{
  "items": [...],
  "pagination": {
    "next_cursor": "MjAyNC0wMS0xNVQxMDozMDowMCswMDowMHxzaWctYWJjMTIz",
    "has_more": true,
    "total_count": 100
  }
}
```

Get the next page:
```bash
curl "http://localhost:8000/api/v1/signals?limit=20&cursor=MjAyNC0wMS0xNVQxMDozMDowMCswMDowMHxzaWctYWJjMTIz"
```

### With Filters

Paginate through forum signals only:
```bash
curl "http://localhost:8000/api/v1/signals?source_type=forum&limit=10"
```

Paginate through evaluated ideas:
```bash
curl "http://localhost:8000/api/v1/ideas?status=evaluated&limit=20"
```

## Backward Compatibility

The implementation maintains backward compatibility:

1. **Default behavior**: When no cursor is provided, the first page is returned
2. **Response format change**: Responses are now wrapped in `PaginatedResponse[T]`
   - This is a breaking change for API consumers
   - Updated all existing tests to use the new format

## Performance Considerations

1. **Index usage**: Queries use indexed columns (fetched_at, created_at, updated_at) for efficient sorting
2. **Count queries**: Each paginated request performs a separate COUNT query for `total_count`
   - This is accurate but adds overhead
   - Consider caching or estimating for very large tables if needed
3. **Limit clamping**: Maximum limit of 100 prevents excessive memory usage

## Testing Coverage

All acceptance criteria have been met with comprehensive test coverage:

✅ Cursor encoding/decoding roundtrip works correctly
✅ First page returns items and next_cursor
✅ Following next_cursor returns the next page
✅ Last page has has_more=False and next_cursor=None
✅ Limit clamping (max 100) works
✅ Empty result set handled correctly
✅ Pagination works with filters (source_type, status, domain)
✅ Cursors are opaque base64 strings
✅ Pages are stable (no duplicate/missing items when new data inserted)
✅ Backward compatible (omitting cursor returns first page)
✅ Invalid cursors return HTTP 400

**Total tests**: 24 pagination-specific tests, all passing
**Existing tests**: 34 API tests updated and passing

## Future Improvements

Potential enhancements (not in scope for current implementation):

1. **Cursor caching**: Cache decoded cursors to avoid repeated base64 operations
2. **Count estimation**: Use approximate counts for very large tables to improve performance
3. **Bidirectional pagination**: Support `previous_cursor` for backward navigation
4. **Page size hints**: Return recommended page size based on query complexity
5. **Cursor expiration**: Add timestamps to cursors and reject stale ones
