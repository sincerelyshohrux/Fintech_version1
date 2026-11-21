"""SQLite storage: hash-chained audit log, actions, consent, settings, uploads, resolved findings."""
import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from app.config import settings

GENESIS = "0" * 64

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    profile_id TEXT NOT NULL,
    actor TEXT NOT NULL,         -- user | agent | policy | system | bank
    event TEXT NOT NULL,
    payload TEXT NOT NULL,       -- canonical JSON
    prev_hash TEXT NOT NULL,
    hash TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS actions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    profile_id TEXT NOT NULL,
    type TEXT NOT NULL,
    params TEXT NOT NULL,
    proposal TEXT NOT NULL,
    amount INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,        -- advice | proposed | executed | failed | rejected | undone
    mode TEXT NOT NULL,          -- manual | auto
    created_by TEXT NOT NULL,    -- user | agent
    created_at TEXT NOT NULL,
    executed_at TEXT,
    undo_until TEXT,
    result TEXT
);
CREATE TABLE IF NOT EXISTS settings (
    profile_id TEXT PRIMARY KEY,
    autonomy TEXT NOT NULL DEFAULT 'one_click',
    auto_limit INTEGER NOT NULL DEFAULT 500000
);
CREATE TABLE IF NOT EXISTS consent (
    profile_id TEXT PRIMARY KEY,
    granted_at TEXT,
    revoked_at TEXT
);
CREATE TABLE IF NOT EXISTS uploads (
    profile_id TEXT PRIMARY KEY,
    source TEXT NOT NULL,        -- sample | csv
    statement TEXT,              -- JSON (csv only)
    loaded_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS resolved (
    profile_id TEXT NOT NULL,
    finding_id TEXT NOT NULL,
    action_id INTEGER NOT NULL,
    PRIMARY KEY (profile_id, finding_id)
);
"""


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@contextmanager
def connect():
    settings.database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_path)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA)


def reset_all() -> None:
    with connect() as conn:
        for table in ("audit", "actions", "settings", "consent", "uploads", "resolved"):
            conn.execute(f"DELETE FROM {table}")
        conn.execute("DELETE FROM sqlite_sequence")


# ------------------------------------------------------------------ audit (hash chain)

def _canonical(d: dict) -> str:
    return json.dumps(d, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _entry_hash(prev_hash: str, ts: str, profile_id: str, actor: str, event: str, payload: str) -> str:
    body = _canonical({"ts": ts, "profile_id": profile_id, "actor": actor, "event": event, "payload": payload})
    return hashlib.sha256((prev_hash + body).encode()).hexdigest()


def audit(profile_id: str, actor: str, event: str, payload: dict) -> int:
    with connect() as conn:
        row = conn.execute("SELECT hash FROM audit ORDER BY id DESC LIMIT 1").fetchone()
        prev = row["hash"] if row else GENESIS
        ts = now_iso()
        body = _canonical(payload)
        h = _entry_hash(prev, ts, profile_id, actor, event, body)
        cur = conn.execute(
            "INSERT INTO audit (ts, profile_id, actor, event, payload, prev_hash, hash) VALUES (?,?,?,?,?,?,?)",
            (ts, profile_id, actor, event, body, prev, h))
        return cur.lastrowid


def audit_list(limit: int = 200, profile_id: str | None = None) -> list[dict]:
    with connect() as conn:
        if profile_id:
            rows = conn.execute("SELECT * FROM audit WHERE profile_id = ? ORDER BY id DESC LIMIT ?", (profile_id, limit))
        else:
            rows = conn.execute("SELECT * FROM audit ORDER BY id DESC LIMIT ?", (limit,))
        return [dict(r) | {"payload": json.loads(r["payload"])} for r in rows]


def audit_verify() -> dict:
    """Recompute the chain. Returns the first broken entry, if any."""
    with connect() as conn:
        rows = conn.execute("SELECT * FROM audit ORDER BY id ASC").fetchall()
    prev = GENESIS
    for r in rows:
        expected = _entry_hash(prev, r["ts"], r["profile_id"], r["actor"], r["event"], r["payload"])
        if r["prev_hash"] != prev or r["hash"] != expected:
            return {"ok": False, "checked": len(rows), "broken_id": r["id"],
                    "message": f"#{r['id']} yozuv o'zgartirilgan — zanjir buzilgan"}
        prev = r["hash"]
    return {"ok": True, "checked": len(rows), "broken_id": None, "message": f"{len(rows)} ta yozuv — zanjir butun"}


_tamper_backup: dict | None = None


def audit_tamper_demo() -> dict:
    """DEMO ONLY: silently edit one entry's payload (without fixing hashes) to show detection."""
    global _tamper_backup
    with connect() as conn:
        rows = conn.execute("SELECT id, payload FROM audit ORDER BY id DESC LIMIT 3").fetchall()
        if not rows:
            return {"ok": False, "message": "Jurnal bo'sh"}
        target = rows[-1]
        _tamper_backup = {"id": target["id"], "payload": target["payload"]}
        data = json.loads(target["payload"])
        data["tampered"] = "summa 100 000 000 so'm ga o'zgartirildi"
        conn.execute("UPDATE audit SET payload = ? WHERE id = ?", (_canonical(data), target["id"]))
    return {"ok": True, "tampered_id": target["id"]}


def audit_restore_demo() -> dict:
    global _tamper_backup
    if not _tamper_backup:
        return {"ok": False}
    with connect() as conn:
        conn.execute("UPDATE audit SET payload = ? WHERE id = ?", (_tamper_backup["payload"], _tamper_backup["id"]))
    restored, _tamper_backup = _tamper_backup["id"], None
    return {"ok": True, "restored_id": restored}


# ------------------------------------------------------------------ actions

def _action_row(r: sqlite3.Row) -> dict:
    d = dict(r)
    for k in ("params", "proposal", "result"):
        d[k] = json.loads(d[k]) if d[k] else None
    return d


def action_create(profile_id: str, type_: str, params: dict, proposal: dict, amount: int,
                  status: str, mode: str, created_by: str) -> dict:
    with connect() as conn:
        cur = conn.execute(
            """INSERT INTO actions (profile_id, type, params, proposal, amount, status, mode, created_by, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (profile_id, type_, _canonical(params), _canonical(proposal), amount, status, mode, created_by, now_iso()))
        return action_get(cur.lastrowid, conn)


def action_get(action_id: int, conn=None) -> dict | None:
    if conn is None:
        with connect() as c:
            return action_get(action_id, c)
    r = conn.execute("SELECT * FROM actions WHERE id = ?", (action_id,)).fetchone()
    return _action_row(r) if r else None


def action_update(action_id: int, **fields) -> dict:
    sets, vals = [], []
    for k, v in fields.items():
        sets.append(f"{k} = ?")
        vals.append(_canonical(v) if isinstance(v, (dict, list)) else v)
    with connect() as conn:
        conn.execute(f"UPDATE actions SET {', '.join(sets)} WHERE id = ?", (*vals, action_id))
        return action_get(action_id, conn)


def actions_list(profile_id: str, limit: int = 30) -> list[dict]:
    with connect() as conn:
        rows = conn.execute("SELECT * FROM actions WHERE profile_id = ? ORDER BY id DESC LIMIT ?", (profile_id, limit))
        return [_action_row(r) for r in rows]


def active_deposits(profile_id: str) -> list[dict]:
    out = []
    for a in actions_list(profile_id, limit=500):
        if a["type"] == "open_deposit" and a["status"] == "executed":
            p = a["proposal"]
            out.append({"action_id": a["id"], "amount": p["amount"], "expected_earnings": p["expected_earnings"],
                        "return_date": p["return_date"], "instrument_name": p["instrument_name"]})
    return out


# ------------------------------------------------------------------ settings / consent / uploads / resolved

def get_settings(profile_id: str) -> dict:
    with connect() as conn:
        r = conn.execute("SELECT * FROM settings WHERE profile_id = ?", (profile_id,)).fetchone()
        return dict(r) if r else {"profile_id": profile_id, "autonomy": "one_click", "auto_limit": 500_000}


def put_settings(profile_id: str, autonomy: str, auto_limit: int) -> dict:
    with connect() as conn:
        conn.execute("""INSERT INTO settings (profile_id, autonomy, auto_limit) VALUES (?,?,?)
                        ON CONFLICT(profile_id) DO UPDATE SET autonomy = excluded.autonomy, auto_limit = excluded.auto_limit""",
                     (profile_id, autonomy, auto_limit))
    return get_settings(profile_id)


def get_consent(profile_id: str) -> dict:
    with connect() as conn:
        r = conn.execute("SELECT * FROM consent WHERE profile_id = ?", (profile_id,)).fetchone()
    granted = bool(r and r["granted_at"] and not r["revoked_at"])
    return {"profile_id": profile_id, "granted": granted, "granted_at": r["granted_at"] if r else None,
            "revoked_at": r["revoked_at"] if r else None}


def set_consent(profile_id: str, granted: bool) -> dict:
    with connect() as conn:
        if granted:
            conn.execute("""INSERT INTO consent (profile_id, granted_at, revoked_at) VALUES (?, ?, NULL)
                            ON CONFLICT(profile_id) DO UPDATE SET granted_at = excluded.granted_at, revoked_at = NULL""",
                         (profile_id, now_iso()))
        else:
            conn.execute("UPDATE consent SET revoked_at = ? WHERE profile_id = ?", (now_iso(), profile_id))
    return get_consent(profile_id)


def get_upload(profile_id: str) -> dict | None:
    with connect() as conn:
        r = conn.execute("SELECT * FROM uploads WHERE profile_id = ?", (profile_id,)).fetchone()
    if not r:
        return None
    return {"source": r["source"], "loaded_at": r["loaded_at"],
            "statement": json.loads(r["statement"]) if r["statement"] else None}


def set_upload(profile_id: str, source: str, statement: list[dict] | None) -> None:
    with connect() as conn:
        conn.execute("""INSERT INTO uploads (profile_id, source, statement, loaded_at) VALUES (?,?,?,?)
                        ON CONFLICT(profile_id) DO UPDATE SET source = excluded.source, statement = excluded.statement,
                        loaded_at = excluded.loaded_at""",
                     (profile_id, source, json.dumps(statement) if statement else None, now_iso()))


def resolved_ids(profile_id: str) -> set[str]:
    with connect() as conn:
        return {r["finding_id"] for r in conn.execute("SELECT finding_id FROM resolved WHERE profile_id = ?", (profile_id,))}


def resolve(profile_id: str, finding_id: str, action_id: int) -> None:
    with connect() as conn:
        conn.execute("INSERT OR REPLACE INTO resolved (profile_id, finding_id, action_id) VALUES (?,?,?)",
                     (profile_id, finding_id, action_id))


def unresolve_by_action(action_id: int) -> None:
    with connect() as conn:
        conn.execute("DELETE FROM resolved WHERE action_id = ?", (action_id,))


def delete_profile_data(profile_id: str) -> None:
    """Wipe everything stored for a profile except the (masked) audit trail."""
    with connect() as conn:
        for table in ("actions", "settings", "consent", "uploads", "resolved"):
            conn.execute(f"DELETE FROM {table} WHERE profile_id = ?", (profile_id,))
