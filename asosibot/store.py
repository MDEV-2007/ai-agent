"""ASOSIBOT xotirasi — lokal SQLite. tasks / reminders / notes / events.

Har chaqiruvda o'z ulanishini ochadi (thread'lar orasida xavfsiz — Telegram
bot va scheduler thread'lari bir vaqtda yozishi mumkin). Barcha sana/vaqt ISO
matn ko'rinishida saqlanadi.
"""
import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

DB_PATH = Path(os.getenv("ASOSIBOT_DB", str(Path(__file__).resolve().parent.parent / "asosibot.db")))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Jadvallarni yaratadi (mavjud bo'lsa tegmaydi)."""
    with _conn() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL DEFAULT 'local',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                category TEXT DEFAULT 'personal',
                status TEXT DEFAULT 'pending',
                priority TEXT DEFAULT 'medium',
                due TEXT,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL DEFAULT 'local',
                message TEXT NOT NULL,
                scheduled_time TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                repeat_type TEXT DEFAULT 'once',
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL DEFAULT 'local',
                title TEXT DEFAULT '',
                content TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner TEXT NOT NULL DEFAULT 'local',
                title TEXT NOT NULL,
                start_time TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# --------------------------------------------------------------------- TASKS
def add_task(owner, title, description="", category="personal", priority="medium",
             due=None, tags=None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO tasks (owner,title,description,category,status,priority,due,tags,created_at)"
            " VALUES (?,?,?,?,'pending',?,?,?,?)",
            (owner, title, description, category, priority, due, json.dumps(tags or []), _now()),
        )
        return cur.lastrowid


def list_tasks(owner, status=None, category=None) -> List[sqlite3.Row]:
    q = "SELECT * FROM tasks WHERE owner=?"
    params = [owner]
    if status:
        q += " AND status=?"
        params.append(status)
    if category:
        q += " AND category=?"
        params.append(category)
    q += " ORDER BY CASE priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, id DESC"
    with _conn() as c:
        return c.execute(q, params).fetchall()


def _find_task(c, owner, query):
    """Sarlavhasi bo'yicha eng mos vazifani topadi (qism-matn, katta-kichik farqsiz)."""
    row = c.execute(
        "SELECT * FROM tasks WHERE owner=? AND lower(title) LIKE ? ORDER BY id DESC LIMIT 1",
        (owner, f"%{(query or '').lower().strip()}%"),
    ).fetchone()
    return row


def mark_task_done(owner, query) -> Optional[str]:
    with _conn() as c:
        row = _find_task(c, owner, query)
        if not row:
            return None
        c.execute("UPDATE tasks SET status='done' WHERE id=?", (row["id"],))
        return row["title"]


def delete_task(owner, query) -> Optional[str]:
    with _conn() as c:
        row = _find_task(c, owner, query)
        if not row:
            return None
        c.execute("DELETE FROM tasks WHERE id=?", (row["id"],))
        return row["title"]


# ----------------------------------------------------------------- REMINDERS
def add_reminder(owner, message, scheduled_time, repeat_type="once") -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO reminders (owner,message,scheduled_time,status,repeat_type,created_at)"
            " VALUES (?,?,?,'pending',?,?)",
            (owner, message, scheduled_time, repeat_type, _now()),
        )
        return cur.lastrowid


def list_reminders(owner, status="pending") -> List[sqlite3.Row]:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM reminders WHERE owner=? AND status=? ORDER BY scheduled_time",
            (owner, status),
        ).fetchall()


def cancel_reminder(owner, query) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM reminders WHERE owner=? AND status='pending' AND lower(message) LIKE ?"
            " ORDER BY id DESC LIMIT 1",
            (owner, f"%{(query or '').lower().strip()}%"),
        ).fetchone()
        if not row:
            return None
        c.execute("UPDATE reminders SET status='cancelled' WHERE id=?", (row["id"],))
        return row["message"]


def due_reminders(now_iso) -> List[sqlite3.Row]:
    """Vaqti kelgan, hali ishga tushmagan reminder'lar (scheduler uchun)."""
    with _conn() as c:
        return c.execute(
            "SELECT * FROM reminders WHERE status='pending' AND scheduled_time<=? ORDER BY scheduled_time",
            (now_iso,),
        ).fetchall()


def mark_reminder_triggered(reminder_id) -> None:
    with _conn() as c:
        c.execute("UPDATE reminders SET status='triggered' WHERE id=?", (reminder_id,))


# --------------------------------------------------------------------- NOTES
def write_note(owner, content, title="", tags=None) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO notes (owner,title,content,tags,created_at,updated_at) VALUES (?,?,?,?,?,?)",
            (owner, title, content, json.dumps(tags or []), _now(), _now()),
        )
        return cur.lastrowid


def search_notes(owner, query) -> List[sqlite3.Row]:
    like = f"%{(query or '').lower().strip()}%"
    with _conn() as c:
        return c.execute(
            "SELECT * FROM notes WHERE owner=? AND (lower(content) LIKE ? OR lower(title) LIKE ? OR lower(tags) LIKE ?)"
            " ORDER BY id DESC",
            (owner, like, like, like),
        ).fetchall()


def list_notes(owner) -> List[sqlite3.Row]:
    with _conn() as c:
        return c.execute("SELECT * FROM notes WHERE owner=? ORDER BY id DESC", (owner,)).fetchall()


def delete_note(owner, query) -> Optional[str]:
    with _conn() as c:
        like = f"%{(query or '').lower().strip()}%"
        row = c.execute(
            "SELECT * FROM notes WHERE owner=? AND (lower(content) LIKE ? OR lower(title) LIKE ?)"
            " ORDER BY id DESC LIMIT 1",
            (owner, like, like),
        ).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM notes WHERE id=?", (row["id"],))
        return row["title"] or row["content"][:40]


# -------------------------------------------------------------------- EVENTS
def add_event(owner, title, start_time) -> int:
    with _conn() as c:
        cur = c.execute(
            "INSERT INTO events (owner,title,start_time,created_at) VALUES (?,?,?,?)",
            (owner, title, start_time, _now()),
        )
        return cur.lastrowid


def list_events(owner) -> List[sqlite3.Row]:
    with _conn() as c:
        return c.execute(
            "SELECT * FROM events WHERE owner=? ORDER BY start_time", (owner,)
        ).fetchall()


def delete_event(owner, query) -> Optional[str]:
    with _conn() as c:
        row = c.execute(
            "SELECT * FROM events WHERE owner=? AND lower(title) LIKE ? ORDER BY id DESC LIMIT 1",
            (owner, f"%{(query or '').lower().strip()}%"),
        ).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM events WHERE id=?", (row["id"],))
        return row["title"]


init_db()
