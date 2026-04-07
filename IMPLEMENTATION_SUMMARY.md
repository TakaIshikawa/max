# Store Context Manager & Transaction Protocol Implementation

## Overview

This implementation adds context manager support (`__enter__`/`__exit__`) and transaction handling to the `Store` class, eliminating connection leaks and enabling atomic multi-step operations.

## Changes Made

### 1. Store Class (`src/max/store/db.py`)

#### Context Manager Protocol
- **Added `__enter__` method**: Returns `self` to enable `with` statement usage
- **Added `__exit__` method**: Calls `self.close()` and does NOT suppress exceptions (returns `False`)
- **Benefits**:
  - Automatic connection cleanup on normal exit
  - Automatic cleanup even when exceptions occur
  - Prevents resource leaks from forgotten `store.close()` calls

#### Transaction Support
- **Added `transaction()` context manager**: Provides atomic BEGIN/COMMIT/ROLLBACK semantics
- **Added `_commit()` helper method**: Checks `_in_transaction` flag to prevent auto-commits during transactions
- **Modified all commit sites**: Changed `self.conn.commit()` → `self._commit()` throughout the Store class
- **Implementation details**:
  - Sets `_in_transaction` flag to defer commits
  - Manages SQLite isolation level to control autocommit behavior
  - Commits only at transaction boundary (on success)
  - Rolls back all operations on exception
  - Restores isolation level and transaction flag in finally block

### 2. MCP Tools (`src/max/server/mcp_tools.py`)

Refactored all 11 tool and resource functions to use context manager pattern:

**Tools:**
- `search_ideas()`
- `get_idea()`
- `get_spec()`
- `contribute_signal()`
- `contribute_idea()`
- `evaluate_idea()`
- `find_similar()`
- `get_stats()`

**Resources:**
- `ideas_list()`
- `idea_detail()`
- `spec_detail()`

**Pattern change:**
```python
# Before (manual cleanup with try/finally)
store = _get_store()
try:
    unit = store.get_buildable_unit(id)
    return {"id": unit.id, ...}
finally:
    store.close()

# After (automatic cleanup with context manager)
with _get_store() as store:
    unit = store.get_buildable_unit(id)
    return {"id": unit.id, ...}
```

### 3. Tests (`tests/test_store_context.py`)

Added comprehensive test coverage with 10 test cases:

#### Context Manager Tests (4 tests)
1. `test_store_context_manager_basic`: Verifies Store works as context manager
2. `test_store_context_manager_closes_connection`: Verifies connection closes on exit
3. `test_store_context_manager_closes_on_exception`: Verifies cleanup happens even on exception
4. `test_store_context_manager_does_not_suppress_exceptions`: Verifies exceptions propagate

#### Transaction Tests (6 tests)
1. `test_transaction_commits_on_success`: Verifies successful transaction commits
2. `test_transaction_rolls_back_on_exception`: Verifies failed transaction rolls back
3. `test_transaction_atomic_multi_step`: Verifies multi-step operations commit atomically
4. `test_transaction_atomic_multi_step_rollback`: Verifies multi-step rollback atomicity
5. `test_transaction_nested_operations_atomicity`: Verifies complex multi-table atomicity
6. `test_transaction_with_context_manager`: Verifies transaction works within context manager

## Usage Examples

### Context Manager
```python
# Automatic cleanup
with Store(db_path=":memory:") as store:
    signals = store.get_signals()
    # ... do work ...
# Connection automatically closed
```

### Transaction
```python
with Store(db_path=":memory:") as store:
    # Atomic multi-step operation
    with store.transaction():
        store.insert_buildable_unit(unit)
        store.update_buildable_unit_status(unit.id, "evaluated")
        store.insert_evaluation(evaluation)
    # All committed together

    # Failed transaction (rolls back)
    try:
        with store.transaction():
            store.update_buildable_unit_status(unit.id, "approved")
            raise ValueError("something went wrong")
    except ValueError:
        pass
    # Status update rolled back
```

### MCP Tools Pattern
```python
def contribute_signal(title: str, content: str, url: str) -> dict:
    with _get_store() as store:
        signal = Signal(title=title, content=content, url=url)
        signal = store.insert_signal(signal)
        return {"id": signal.id, "status": "created"}
```

## Test Results

All tests pass successfully:
- **13 existing Store tests**: ✅ All passing (backward compatibility verified)
- **10 new context manager/transaction tests**: ✅ All passing
- **12 MCP tools tests**: ✅ All passing (refactored code verified)

**Total: 35/35 tests passing**

## Benefits

### Before
- ❌ Manual `store.close()` required in every function
- ❌ Connection leaks possible on exceptions
- ❌ No transaction support for atomic operations
- ❌ Risky multi-step operations (partial success possible)

### After
- ✅ Automatic cleanup with `with` statements
- ✅ Guaranteed connection cleanup even on exceptions
- ✅ Transaction support for atomic multi-step operations
- ✅ Rollback on failure ensures data consistency
- ✅ Backward compatible (existing code still works)

## Files Modified

1. `src/max/store/db.py`: Added context manager protocol, transaction support, `_commit()` helper
2. `src/max/server/mcp_tools.py`: Refactored 11 functions to use context manager pattern
3. `tests/test_store_context.py`: Added 10 comprehensive tests (new file)
4. `examples/store_context_demo.py`: Added demonstration script (new file)

## Migration Guide

Existing code continues to work without changes:
```python
# Old code still works
store = Store()
store.insert_signal(signal)
store.close()
```

But new code should use context managers:
```python
# Recommended pattern
with Store() as store:
    store.insert_signal(signal)
```

For multi-step atomic operations, use transactions:
```python
with Store() as store:
    with store.transaction():
        store.insert_signal(signal)
        store.mark_signals_synthesized([signal.id])
```
