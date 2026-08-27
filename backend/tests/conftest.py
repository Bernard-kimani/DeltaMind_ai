"""Ensures every table exists before any DB-touching test runs.
Base.metadata.create_all() only creates missing tables (never alters
existing ones — see db/session.py), so this is safe to call against the
same real dev DB the app itself uses (no separate test-DB fixture in this
project)."""

from app.db.session import init_db

init_db()
