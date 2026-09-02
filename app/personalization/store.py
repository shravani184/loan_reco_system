"""
Persistence of pseudonymous interaction history.

This module PERSISTS. It does not score, rank, or decide anything (CONTEXT.md
section 10). It is the storage half of a feature source.

PRIVACY IS A SCHEMA PROPERTY HERE, not a convention. The tables below hold
pseudonymous identifiers and derived numeric aggregates only. There is no column for
a name, contact detail, identity number or free text, so there is no code path that
could persist one. tests/test_personalization.py asserts this against the live
sqlite schema.

Stdlib sqlite3 only. SQLAlchemy is not a serving dependency and adding one to hold
four tables would spend the memory budget (CONTEXT.md 17.2). The SQL is plain enough
to port to Postgres, which is why the connection target comes from a URL in config
rather than a bare path.
"""

import sqlite3
import time
from pathlib import Path

from app.config import settings
from app.schemas.enums import FeedbackEventType, FinancingStrategy, LoanPurpose

_SQLITE_PREFIX = "sqlite:///"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id      TEXT PRIMARY KEY,
    created_at   REAL NOT NULL,
    last_seen_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS profile_snapshots (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id             TEXT NOT NULL,
    snapshot_at         REAL NOT NULL,
    monthly_income      REAL NOT NULL,
    monthly_expenses    REAL NOT NULL,
    existing_emi        REAL NOT NULL,
    disposable_income   REAL NOT NULL,
    debt_burden_ratio   REAL NOT NULL,
    credit_score        INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_history (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      TEXT NOT NULL,
    at           REAL NOT NULL,
    product_id   TEXT,
    purpose      TEXT NOT NULL,
    amount       REAL NOT NULL,
    tenure       INTEGER,
    strategy     TEXT NOT NULL,
    suitability  REAL,
    status       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     TEXT NOT NULL,
    at          REAL NOT NULL,
    product_id  TEXT,
    event_type  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_snapshots_user ON profile_snapshots(user_id);
CREATE INDEX IF NOT EXISTS idx_history_user   ON recommendation_history(user_id);
CREATE INDEX IF NOT EXISTS idx_feedback_user  ON feedback_events(user_id);
"""

TABLES = (
    "users",
    "profile_snapshots",
    "recommendation_history",
    "feedback_events",
)


def _path_from_url(db_url: str) -> str:
    """
    sqlite:///data/personalization.db -> data/personalization.db
    sqlite:///:memory:                -> :memory:

    A non-sqlite URL is rejected loudly rather than silently misread. Postgres
    support is a driver change, not a silent fallback to a local file.
    """
    if not db_url.startswith(_SQLITE_PREFIX):
        raise ValueError(
            f"only sqlite URLs are supported by this store, got: {db_url!r}"
        )
    return db_url[len(_SQLITE_PREFIX) :]


class PersonalizationStore:
    """
    A connection to one personalization database.

    The URL is a parameter rather than a global read so tests can point at a temp
    file and never touch data/.
    """

    def __init__(self, db_url: str | None = None) -> None:
        self.db_path = _path_from_url(db_url or settings.PERSONALIZATION_DB_URL)
        if self.db_path != ":memory:":
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        # A single connection: :memory: databases vanish when their last connection
        # closes, and one connection per store keeps that case usable in tests.
        self._connection = sqlite3.connect(self.db_path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(_SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "PersonalizationStore":
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    # ------------------------------------------------------------------- writes

    def upsert_user(self, user_id: str, at: float | None = None) -> None:
        at = time.time() if at is None else at
        self._connection.execute(
            """
            INSERT INTO users (user_id, created_at, last_seen_at)
            VALUES (?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET last_seen_at = excluded.last_seen_at
            """,
            (user_id, at, at),
        )
        self._connection.commit()

    def record_profile_snapshot(
        self,
        user_id: str,
        monthly_income: float,
        monthly_expenses: float,
        existing_emi: float,
        disposable_income: float,
        debt_burden_ratio: float,
        credit_score: int,
        at: float | None = None,
    ) -> None:
        """One row per pipeline run. This is what session_count counts."""
        at = time.time() if at is None else at
        self.upsert_user(user_id, at)
        self._connection.execute(
            """
            INSERT INTO profile_snapshots (
                user_id, snapshot_at, monthly_income, monthly_expenses,
                existing_emi, disposable_income, debt_burden_ratio, credit_score
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                at,
                monthly_income,
                monthly_expenses,
                existing_emi,
                disposable_income,
                debt_burden_ratio,
                credit_score,
            ),
        )
        self._connection.commit()

    def record_recommendation(
        self,
        user_id: str,
        purpose: LoanPurpose,
        amount: float,
        strategy: FinancingStrategy,
        status: str,
        product_id: str | None = None,
        tenure: int | None = None,
        suitability: float | None = None,
        at: float | None = None,
    ) -> None:
        """
        product_id and tenure are nullable because the no-loan candidate
        (LIQUIDATE_100) has neither — the same shape rule the Candidate schema
        enforces.
        """
        at = time.time() if at is None else at
        self.upsert_user(user_id, at)
        self._connection.execute(
            """
            INSERT INTO recommendation_history (
                user_id, at, product_id, purpose, amount, tenure,
                strategy, suitability, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                at,
                product_id,
                purpose.value,
                amount,
                tenure,
                strategy.value,
                suitability,
                status,
            ),
        )
        self._connection.commit()

    def record_feedback_event(
        self,
        user_id: str,
        event_type: FeedbackEventType,
        product_id: str | None = None,
        at: float | None = None,
    ) -> None:
        at = time.time() if at is None else at
        self.upsert_user(user_id, at)
        self._connection.execute(
            "INSERT INTO feedback_events (user_id, at, product_id, event_type) "
            "VALUES (?, ?, ?, ?)",
            (user_id, at, product_id, event_type.value),
        )
        self._connection.commit()

    # -------------------------------------------------------------------- reads

    def user_exists(self, user_id: str) -> bool:
        row = self._connection.execute(
            "SELECT 1 FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return row is not None

    def session_count(self, user_id: str) -> int:
        row = self._connection.execute(
            "SELECT COUNT(*) AS n FROM profile_snapshots WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        return int(row["n"])

    def recommendations(self, user_id: str) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT * FROM recommendation_history WHERE user_id = ?", (user_id,)
            )
        )

    def feedback_events(self, user_id: str) -> list[sqlite3.Row]:
        return list(
            self._connection.execute(
                "SELECT * FROM feedback_events WHERE user_id = ?", (user_id,)
            )
        )

    # ----------------------------------------------------------------- deletion

    def delete_user(self, user_id: str) -> int:
        """
        Erase every row for a user, across every table.

        Part of the layer's contract, not a later addition (CONTEXT.md section 10).
        Returns the number of rows removed so a caller can log the erasure.
        """
        removed = 0
        for table in TABLES:
            cursor = self._connection.execute(
                f"DELETE FROM {table} WHERE user_id = ?", (user_id,)
            )
            removed += cursor.rowcount
        self._connection.commit()
        return removed
