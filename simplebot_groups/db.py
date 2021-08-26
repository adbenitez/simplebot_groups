"""Database management."""

import sqlite3
from typing import List, Optional


class DBManager:
    """Database manager"""

    def __init__(self, db_path: str) -> None:
        self.db = sqlite3.connect(db_path, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.db:
            self.db.execute("PRAGMA foreign_keys = ON;")
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS groups
                (id INTEGER PRIMARY KEY,
                topic TEXT)"""
            )
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS lastseens
                (id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                addr TEXT,
                lastseen FLOAT NOT NULL,
                PRIMARY KEY(id, addr))"""
            )
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS channels
                (id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                topic TEXT,
                admin INTEGER NOT NULL,
                last_pub FLOAT NOT NULL DEFAULT 0)"""
            )
            self.db.execute(
                """CREATE TABLE IF NOT EXISTS cchats
                (id INTEGER PRIMARY KEY,
                channel INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE)"""
            )

    # ==== groups =====

    def upsert_group(self, gid: int, topic: Optional[str]) -> None:
        with self.db:
            self.db.execute(
                "REPLACE INTO groups (id, topic) VALUES (?,?)", (gid, topic)
            )

    def remove_group(self, gid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM groups WHERE id=?", (gid,))

    def get_group(self, gid: int) -> Optional[sqlite3.Row]:
        return self.db.execute("SELECT * FROM groups WHERE id=?", (gid,)).fetchone()

    def get_groups(self) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM groups").fetchall()

    def update_lastseen(self, gid: int, addr: str, lastseen: float) -> None:
        with self.db:
            self.db.execute(
                "REPLACE INTO lastseens VALUES (?,?,?)", (gid, addr, lastseen)
            )

    def remove_lastseen(self, gid: int, addr: str) -> None:
        with self.db:
            self.db.execute("DELETE FROM lastseens WHERE id=? AND addr=?", (gid, addr))

    def get_lastseens(self) -> sqlite3.Cursor:
        return self.db.execute("SELECT * FROM lastseens")

    # ==== channels =====

    def add_channel(self, name: str, topic: Optional[str], admin: int) -> None:
        with self.db:
            self.db.execute(
                "INSERT INTO channels (name, topic, admin) VALUES (?,?,?)",
                (name, topic, admin),
            )

    def remove_channel(self, cgid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM cchats WHERE channel=?", (cgid,))
            self.db.execute("DELETE FROM channels WHERE id=?", (cgid,))

    def get_channel(self, gid: int) -> Optional[sqlite3.Row]:
        r = self.db.execute("SELECT channel FROM cchats WHERE id=?", (gid,)).fetchone()
        if r:
            return self.db.execute(
                "SELECT * FROM channels WHERE id=?", (r[0],)
            ).fetchone()
        return self.db.execute(
            "SELECT * FROM channels WHERE admin=?", (gid,)
        ).fetchone()

    def get_channel_by_id(self, cgid: int) -> Optional[sqlite3.Row]:
        return self.db.execute("SELECT * FROM channels WHERE id=?", (cgid,)).fetchone()

    def get_channel_by_name(self, name: str) -> Optional[sqlite3.Row]:
        return self.db.execute(
            "SELECT * FROM channels WHERE name=?", (name,)
        ).fetchone()

    def get_channels(self) -> List[sqlite3.Row]:
        return self.db.execute("SELECT * FROM channels").fetchall()

    def set_channel_topic(self, cgid: int, topic: str) -> None:
        with self.db:
            self.db.execute("UPDATE channels SET topic=? WHERE id=?", (topic, cgid))

    def set_channel_last_pub(self, cgid: int, last_pub: float) -> None:
        with self.db:
            self.db.execute(
                "UPDATE channels SET last_pub=? WHERE id=?", (last_pub, cgid)
            )

    def add_cchat(self, gid: int, cgid: int) -> None:
        with self.db:
            self.db.execute("INSERT INTO cchats VALUES (?,?)", (gid, cgid))

    def remove_cchat(self, gid: int) -> None:
        with self.db:
            self.db.execute("DELETE FROM cchats WHERE id=?", (gid,))

    def get_cchats(self, cgid: int) -> List[int]:
        rows = self.db.execute("SELECT id FROM cchats WHERE channel=?", (cgid,))
        return [r[0] for r in rows]
