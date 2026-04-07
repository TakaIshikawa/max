#!/usr/bin/env python
"""Demonstration of Store context manager and transaction support."""

from max.store.db import Store
from max.types.signal import Signal, SignalSourceType
from max.types.buildable_unit import BuildableUnit, BuildableCategory, IdeationMode


def demo_context_manager():
    """Demonstrate basic context manager usage."""
    print("=== Context Manager Demo ===")
    print("Using Store with context manager ensures automatic cleanup\n")

    # Old way (manual cleanup - risky if exception occurs)
    print("❌ Old way (manual cleanup):")
    print("   store = Store(':memory:')")
    print("   try:")
    print("       signals = store.get_signals()")
    print("   finally:")
    print("       store.close()  # Must remember to close!\n")

    # New way (automatic cleanup)
    print("✅ New way (automatic cleanup):")
    print("   with Store(':memory:') as store:")
    print("       signals = store.get_signals()")
    print("   # Connection automatically closed!\n")

    with Store(db_path=":memory:") as store:
        signals = store.get_signals()
        print(f"   Found {len(signals)} signals")


def demo_transaction():
    """Demonstrate transaction atomicity."""
    print("\n=== Transaction Demo ===")
    print("Transactions ensure all-or-nothing execution\n")

    with Store(db_path=":memory:") as store:
        # Create test data
        unit = BuildableUnit(
            id="demo-unit-001",
            title="Demo Unit",
            one_liner="Demo one-liner",
            category=BuildableCategory.CLI_TOOL,
            ideation_mode=IdeationMode.DIRECT,
            problem="Demo problem",
            solution="Demo solution",
            target_users="both",
            value_proposition="Demo value",
        )

        print("✅ Successful transaction:")
        print("   with store.transaction():")
        print("       store.insert_buildable_unit(unit)")
        print("       store.update_buildable_unit_status(unit.id, 'evaluated')")
        print("   # Both operations committed together")

        with store.transaction():
            store.insert_buildable_unit(unit)
            store.update_buildable_unit_status("demo-unit-001", "evaluated")

        retrieved = store.get_buildable_unit("demo-unit-001")
        print(f"   Unit status: {retrieved.status}\n")

        # Demonstrate rollback
        print("❌ Failed transaction (with rollback):")
        print("   with store.transaction():")
        print("       store.update_buildable_unit_status(unit.id, 'approved')")
        print("       raise ValueError('Something went wrong!')")
        print("   # Status update is rolled back")

        try:
            with store.transaction():
                store.update_buildable_unit_status("demo-unit-001", "approved")
                raise ValueError("Something went wrong!")
        except ValueError:
            pass

        retrieved = store.get_buildable_unit("demo-unit-001")
        print(f"   Unit status (unchanged): {retrieved.status}")


def demo_mcp_pattern():
    """Demonstrate the pattern used in MCP tools."""
    print("\n=== MCP Tools Pattern ===")
    print("MCP tools now use context managers for safety\n")

    print("Old pattern (manual cleanup):")
    print("   store = _get_store()")
    print("   try:")
    print("       unit = store.get_buildable_unit(id)")
    print("       return {'id': unit.id, ...}")
    print("   finally:")
    print("       store.close()\n")

    print("New pattern (automatic cleanup):")
    print("   with _get_store() as store:")
    print("       unit = store.get_buildable_unit(id)")
    print("       return {'id': unit.id, ...}")
    print("   # No manual cleanup needed!")


if __name__ == "__main__":
    print("Store Context Manager & Transaction Support Demo")
    print("=" * 50)

    demo_context_manager()
    demo_transaction()
    demo_mcp_pattern()

    print("\n" + "=" * 50)
    print("✨ All demos completed successfully!")
