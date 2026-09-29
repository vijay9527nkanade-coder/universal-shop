#!/usr/bin/env python
"""
init_db.py — Standalone script to create all database tables directly via
             SQLAlchemy metadata (no Alembic needed).

Usage
-----
    # From the backend/ directory with your venv active:
    python init_db.py

    # Or drop-and-recreate (DESTRUCTIVE — deletes all data):
    python init_db.py --reset
"""

import argparse
import sys

from app.config import get_settings
from app.database import Base, engine
import app.models  # noqa: F401 — ensures all models are registered


def create_tables() -> None:
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    tables = list(Base.metadata.tables.keys())
    print(f"  ✓ Tables created: {', '.join(sorted(tables))}")


def drop_tables() -> None:
    print("Dropping all tables (DESTRUCTIVE)...")
    Base.metadata.drop_all(bind=engine)
    print("  ✓ All tables dropped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Initialise the database schema.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop all existing tables before recreating them (DESTRUCTIVE).",
    )
    args = parser.parse_args()

    settings = get_settings()
    print(f"Connecting to: {settings.database_url}")

    if args.reset:
        confirm = input("This will DELETE all data. Type 'yes' to continue: ")
        if confirm.strip().lower() != "yes":
            print("Aborted.")
            sys.exit(0)
        drop_tables()

    create_tables()
    print("Done.")


if __name__ == "__main__":
    main()
