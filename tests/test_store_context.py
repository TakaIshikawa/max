"""Tests for Store context manager and transaction support."""

from __future__ import annotations

import pytest
import sqlite3

from max.store.db import Store
from max.types.signal import Signal, SignalSourceType
from max.types.buildable_unit import BuildableUnit, BuildableCategory, IdeationMode


def test_store_context_manager_basic(tmp_db: str) -> None:
    """Test that Store works as a context manager."""
    with Store(db_path=tmp_db) as store:
        assert store is not None
        assert store.conn is not None
        # Verify we can perform operations
        signals = store.get_signals()
        assert signals == []


def test_store_context_manager_closes_connection(tmp_db: str) -> None:
    """Test that Store context manager closes connection on exit."""
    store_ref = None
    with Store(db_path=tmp_db) as store:
        store_ref = store
        assert store.conn is not None

    # After exiting context, connection should be closed
    # Attempting to use it should raise an error
    with pytest.raises(sqlite3.ProgrammingError):
        store_ref.conn.execute("SELECT 1")


def test_store_context_manager_closes_on_exception(tmp_db: str) -> None:
    """Test that Store context manager closes connection even when exception occurs."""
    store_ref = None
    with pytest.raises(ValueError):
        with Store(db_path=tmp_db) as store:
            store_ref = store
            assert store.conn is not None
            raise ValueError("test exception")

    # After exception, connection should still be closed
    with pytest.raises(sqlite3.ProgrammingError):
        store_ref.conn.execute("SELECT 1")


def test_store_context_manager_does_not_suppress_exceptions(tmp_db: str) -> None:
    """Test that Store context manager does not suppress exceptions."""
    with pytest.raises(ValueError, match="test exception"):
        with Store(db_path=tmp_db) as store:
            store.get_signals()
            raise ValueError("test exception")


def test_transaction_commits_on_success(tmp_db: str) -> None:
    """Test that transaction() commits on success."""
    signal = Signal(
        id="sig-tx-001",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Test Signal",
        content="Test content",
        url="https://example.com/test-001",
        tags=["test"],
    )

    with Store(db_path=tmp_db) as store:
        with store.transaction():
            store.insert_signal(signal)

        # After successful transaction, signal should be persisted
        signals = store.get_signals()
        assert len(signals) == 1
        assert signals[0].id == "sig-tx-001"


def test_transaction_rolls_back_on_exception(tmp_db: str) -> None:
    """Test that transaction() rolls back on exception."""
    signal1 = Signal(
        id="sig-tx-002",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Test Signal 1",
        content="Test content",
        url="https://example.com/test-002",
        tags=["test"],
    )

    signal2 = Signal(
        id="sig-tx-003",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Test Signal 2",
        content="Test content",
        url="https://example.com/test-003",
        tags=["test"],
    )

    with Store(db_path=tmp_db) as store:
        # Insert first signal successfully
        store.insert_signal(signal1)
        assert store.count_signals() == 1

        # Try to insert in a transaction that fails
        with pytest.raises(ValueError):
            with store.transaction():
                store.insert_signal(signal2)
                raise ValueError("transaction failed")

        # Second signal should not be persisted due to rollback
        signals = store.get_signals()
        assert len(signals) == 1
        assert signals[0].id == "sig-tx-002"


def test_transaction_atomic_multi_step(tmp_db: str) -> None:
    """Test that nested operations within a transaction are atomic."""
    unit = BuildableUnit(
        id="bu-tx-001",
        title="Test Unit",
        one_liner="Test one-liner",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
    )

    with Store(db_path=tmp_db) as store:
        # Multi-step operation: insert unit and update status
        with store.transaction():
            store.insert_buildable_unit(unit)
            store.update_buildable_unit_status("bu-tx-001", "evaluated")

        # Both operations should be committed
        retrieved = store.get_buildable_unit("bu-tx-001")
        assert retrieved is not None
        assert retrieved.status == "evaluated"


def test_transaction_atomic_multi_step_rollback(tmp_db: str) -> None:
    """Test that all operations in a transaction are rolled back on failure."""
    unit = BuildableUnit(
        id="bu-tx-002",
        title="Test Unit 2",
        one_liner="Test one-liner 2",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
    )

    with Store(db_path=tmp_db) as store:
        # Multi-step operation that fails
        with pytest.raises(ValueError):
            with store.transaction():
                store.insert_buildable_unit(unit)
                store.update_buildable_unit_status("bu-tx-002", "evaluated")
                raise ValueError("rollback test")

        # Neither operation should be persisted
        retrieved = store.get_buildable_unit("bu-tx-002")
        assert retrieved is None

        units = store.get_buildable_units()
        assert len(units) == 0


def test_transaction_nested_operations_atomicity(tmp_db: str) -> None:
    """Test complex multi-table atomic operations within a transaction."""
    signal = Signal(
        id="sig-tx-004",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Test Signal for Unit",
        content="Test content",
        url="https://example.com/test-004",
        tags=["test"],
    )

    unit = BuildableUnit(
        id="bu-tx-003",
        title="Test Unit 3",
        one_liner="Test one-liner 3",
        category=BuildableCategory.CLI_TOOL,
        ideation_mode=IdeationMode.DIRECT,
        problem="Test problem",
        solution="Test solution",
        target_users="both",
        value_proposition="Test value",
        evidence_signals=["sig-tx-004"],
    )

    with Store(db_path=tmp_db) as store:
        with pytest.raises(ValueError):
            with store.transaction():
                # Insert signal
                store.insert_signal(signal)
                # Insert unit that references signal
                store.insert_buildable_unit(unit)
                # Update unit status
                store.update_buildable_unit_status("bu-tx-003", "evaluated")
                # Fail transaction
                raise ValueError("rollback complex operations")

        # All operations should be rolled back
        assert store.count_signals() == 0
        assert len(store.get_buildable_units()) == 0
        assert store.get_buildable_unit("bu-tx-003") is None


def test_transaction_with_context_manager(tmp_db: str) -> None:
    """Test using transaction() within Store context manager."""
    signal = Signal(
        id="sig-tx-005",
        source_type=SignalSourceType.FORUM,
        source_adapter="test",
        title="Context Manager Test",
        content="Test content",
        url="https://example.com/test-005",
        tags=["test"],
    )

    with Store(db_path=tmp_db) as store:
        # Transaction within context manager
        with store.transaction():
            store.insert_signal(signal)

        # Verify signal persisted
        signals = store.get_signals()
        assert len(signals) == 1

        # Try failed transaction
        with pytest.raises(ValueError):
            with store.transaction():
                store.update_signal_role("sig-tx-005", "important")
                raise ValueError("rollback role update")

        # First transaction should still be committed
        signals = store.get_signals()
        assert len(signals) == 1
        # But role update should be rolled back
        retrieved = store.get_signal("sig-tx-005")
        assert retrieved is not None
        assert retrieved.metadata.get("signal_role", "") == ""
