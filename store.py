"""SQLite schema migrations are additive; legacy job payloads remain immutable."""
import json
import sqlite3
import time
from .network import DATA

def connect():
    c = sqlite3.connect(DATA / 'citylab.sqlite', timeout=30)
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('CREATE TABLE IF NOT EXISTS scenarios (id TEXT PRIMARY KEY, payload TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT, progress REAL, payload TEXT, error TEXT, created REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    c.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, kind TEXT, status TEXT, progress REAL, payload TEXT, detail TEXT, error TEXT, created REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS observations (id TEXT PRIMARY KEY, network TEXT, payload TEXT, created REAL)')
    c.execute('CREATE TABLE IF NOT EXISTS migrations (version INTEGER PRIMARY KEY, applied REAL, description TEXT)')
    c.execute("INSERT OR IGNORE INTO migrations VALUES (2, ?, 'Add settings, task and observation tables; legacy artifacts preserved verbatim')", (time.time(),))
    c.execute('PRAGMA user_version=2')
    c.commit()
    return c

def update_job(id, status, progress=0, error=None):
    with connect() as c:
        c.execute('UPDATE jobs SET status=?,progress=?,error=? WHERE id=?', (status, progress, error, id))

def job(id):
    with connect() as c:
        row = c.execute('SELECT id,status,progress,payload,error,created FROM jobs WHERE id=?', (id,)).fetchone()
    if not row:
        return None
    return dict(zip(['id', 'status', 'progress', 'scenario', 'error', 'created'], [row[0], row[1], row[2], json.loads(row[3]), row[4], row[5]]))

def setting(key, value=None):
    with connect() as c:
        if value is not None:
            c.execute('INSERT OR REPLACE INTO settings VALUES (?,?)', (key, json.dumps(value)))
        row = c.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return json.loads(row[0]) if row else None

def task(id):
    with connect() as c:
        r = c.execute('SELECT id,kind,status,progress,payload,detail,error,created FROM tasks WHERE id=?', (id,)).fetchone()
    if not r:
        return None
    return dict(zip(['id', 'kind', 'status', 'progress', 'spec', 'detail', 'error', 'created'], [*r[:4], json.loads(r[4]), json.loads(r[5] or '{}'), r[6], r[7]]))

def update_task(id, status, progress=0, detail=None, error=None):
    with connect() as c:
        c.execute('UPDATE tasks SET status=?,progress=?,detail=?,error=? WHERE id=?', (status, progress, json.dumps(detail or {}), error, id))
