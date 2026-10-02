from __future__ import annotations
import json, sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "videos.db"

def connect():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.row_factory = sqlite3.Row
    db.execute("PRAGMA journal_mode=WAL")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def init_db():
    with connect() as db:
        db.executescript("""
        CREATE TABLE IF NOT EXISTS sites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            domain TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS videos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            site_id INTEGER,
            title TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '其他',
            page_url TEXT NOT NULL,
            cover TEXT DEFAULT '',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(site_id) REFERENCES sites(id) ON DELETE SET NULL
        );
        CREATE TABLE IF NOT EXISTS streams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            video_id INTEGER,
            url TEXT NOT NULL,
            stream_type TEXT NOT NULL,
            referer TEXT DEFAULT '',
            user_agent TEXT DEFAULT '',
            headers_json TEXT DEFAULT '{}',
            first_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_seen TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(video_id, url),
            FOREIGN KEY(video_id) REFERENCES videos(id) ON DELETE CASCADE
        );
        CREATE INDEX IF NOT EXISTS idx_videos_category ON videos(category);
        CREATE INDEX IF NOT EXISTS idx_videos_updated ON videos(updated_at);
        CREATE INDEX IF NOT EXISTS idx_streams_video ON streams(video_id);
        """)

def upsert_video(title, category, page_url, stream):
    from urllib.parse import urlparse
    domain = urlparse(page_url).netloc or urlparse(stream["url"]).netloc
    with connect() as db:
        site = db.execute("SELECT id FROM sites WHERE domain=?", (domain,)).fetchone()
        if site:
            site_id = site["id"]
            db.execute("UPDATE sites SET last_seen=CURRENT_TIMESTAMP WHERE id=?", (site_id,))
        else:
            cur = db.execute("INSERT INTO sites(domain,name) VALUES(?,?)", (domain, domain or "unknown"))
            site_id = cur.lastrowid
        row = db.execute("SELECT id FROM videos WHERE page_url=? AND title=?", (page_url, title)).fetchone()
        if row:
            video_id = row["id"]
            db.execute("UPDATE videos SET category=?,site_id=?,updated_at=CURRENT_TIMESTAMP WHERE id=?", (category,site_id,video_id))
        else:
            cur = db.execute("INSERT INTO videos(site_id,title,category,page_url) VALUES(?,?,?,?)", (site_id,title,category,page_url))
            video_id = cur.lastrowid
        db.execute("""INSERT INTO streams(video_id,url,stream_type,referer,user_agent,headers_json)
        VALUES(?,?,?,?,?,?)
        ON CONFLICT(video_id,url) DO UPDATE SET referer=excluded.referer,user_agent=excluded.user_agent,headers_json=excluded.headers_json,last_seen=CURRENT_TIMESTAMP""",
        (video_id,stream["url"],stream["stream_type"],stream.get("referer",""),stream.get("user_agent",""),json.dumps(stream.get("headers",{}),ensure_ascii=False)))
        return int(video_id)

def list_videos(category=None, q=None, limit=100):
    sql="SELECT v.*,s.domain FROM videos v LEFT JOIN sites s ON s.id=v.site_id WHERE 1=1"
    params=[]
    if category: sql+=" AND v.category=?"; params.append(category)
    if q: sql+=" AND v.title LIKE ?"; params.append("%"+q+"%")
    sql+=" ORDER BY v.updated_at DESC LIMIT ?"; params.append(limit)
    with connect() as db:
        return [dict(r) for r in db.execute(sql,params).fetchall()]

def get_video(video_id):
    with connect() as db:
        v=db.execute("SELECT * FROM videos WHERE id=?",(video_id,)).fetchone()
        if not v: return None
        out=dict(v)
        out["streams"]=[dict(r) for r in db.execute("SELECT * FROM streams WHERE video_id=? ORDER BY id",(video_id,)).fetchall()]
        return out
