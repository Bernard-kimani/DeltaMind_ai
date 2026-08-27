from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.db.models import Base

settings = get_settings()
_is_sqlite = settings.database_url.startswith("sqlite")

# check_same_thread/timeout only matter for SQLite; ignored by Postgres
# engines. `timeout` (seconds) is sqlite3's own busy-wait before raising
# "database is locked" — needed now that two independent OS processes (the
# Track 1 and Track 4 loop subprocesses) can both write to this file
# concurrently, on top of the FastAPI process's own reads. Default SQLite
# journal mode + a 0s busy_timeout would surface as real, likely errors
# under that load, not a theoretical edge case.
_connect_args = {"check_same_thread": False, "timeout": 30} if _is_sqlite else {}
engine = create_engine(settings.database_url, connect_args=_connect_args)

if _is_sqlite:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragmas(dbapi_connection, connection_record) -> None:
        cursor = dbapi_connection.cursor()
        # WAL lets readers (dashboard queries) proceed without blocking on a
        # concurrent writer (either loop process), and vice versa — the
        # default rollback-journal mode serializes all of it.
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()

SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def init_db() -> None:
    Base.metadata.create_all(bind=engine)


def get_session() -> Session:
    return SessionLocal()
