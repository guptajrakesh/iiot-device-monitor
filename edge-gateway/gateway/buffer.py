import json
import sqlite3
import time


class LocalBuffer:
    """Disk-backed queue so readings survive a WAN/broker outage instead of
    being silently dropped - critical for OT reliability expectations."""

    def __init__(self, db_path: str = "/tmp/gateway_buffer.db"):
        self.conn = sqlite3.connect(db_path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS pending ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, payload TEXT, created_at REAL)"
        )
        self.conn.commit()

    def enqueue(self, payload: dict):
        self.conn.execute(
            "INSERT INTO pending (payload, created_at) VALUES (?, ?)",
            (json.dumps(payload), time.time()),
        )
        self.conn.commit()

    def pending_batch(self, limit: int = 100):
        cur = self.conn.execute("SELECT id, payload FROM pending ORDER BY id LIMIT ?", (limit,))
        return cur.fetchall()

    def remove(self, ids: list[int]):
        self.conn.executemany("DELETE FROM pending WHERE id = ?", [(i,) for i in ids])
        self.conn.commit()

    def count(self) -> int:
        return self.conn.execute("SELECT COUNT(*) FROM pending").fetchone()[0]
