"""URL shortener with click analytics. FastAPI + SQLite."""
from __future__ import annotations
import re
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import RedirectResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, field_validator
from pathlib import Path
from .shortcode import encode

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
URL_RE = re.compile(r"^https?://[^\s/$.?#].[^\s]*$", re.IGNORECASE)


class ShortenIn(BaseModel):
    url: str
    @field_validator("url")
    @classmethod
    def valid(cls, v: str) -> str:
        if not URL_RE.match(v):
            raise ValueError("must be a valid http(s) URL")
        return v


class ShortenOut(BaseModel):
    code: str
    short_url: str
    target: str


def _db(path: str) -> sqlite3.Connection:
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS links (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target TEXT NOT NULL,
            code TEXT UNIQUE,
            created TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS clicks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            link_id INTEGER NOT NULL REFERENCES links(id),
            ts TEXT NOT NULL,
            referrer TEXT
        );
    """)
    conn.commit()
    return conn


def create_app(db_path: str = "urls.db") -> FastAPI:
    conn = _db(db_path)
    app = FastAPI(title="URL Shortener", version="1.0.0")

    def now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @app.post("/api/shorten", response_model=ShortenOut)
    def shorten(body: ShortenIn, request: Request):
        cur = conn.execute("INSERT INTO links (target, created) VALUES (?, ?)",
                           (body.url, now()))
        link_id = cur.lastrowid
        code = encode(link_id + 1000)  # offset so codes aren't trivially 1,2,3
        conn.execute("UPDATE links SET code = ? WHERE id = ?", (code, link_id))
        conn.commit()
        base = str(request.base_url).rstrip("/")
        return {"code": code, "short_url": f"{base}/{code}", "target": body.url}

    @app.get("/api/stats/{code}")
    def stats(code: str):
        link = conn.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
        if not link:
            raise HTTPException(404, "unknown code")
        total = conn.execute("SELECT COUNT(*) c FROM clicks WHERE link_id = ?",
                            (link["id"],)).fetchone()["c"]
        by_day = conn.execute(
            "SELECT substr(ts,1,10) d, COUNT(*) c FROM clicks WHERE link_id = ? GROUP BY d ORDER BY d",
            (link["id"],)).fetchall()
        return {"code": code, "target": link["target"], "clicks": total,
                "by_day": [{"date": r["d"], "clicks": r["c"]} for r in by_day]}

    @app.get("/api/links")
    def links():
        rows = conn.execute("""
            SELECT l.code, l.target, l.created, COUNT(c.id) clicks
            FROM links l LEFT JOIN clicks c ON c.link_id = l.id
            WHERE l.code IS NOT NULL GROUP BY l.id ORDER BY l.id DESC
        """).fetchall()
        return [dict(r) for r in rows]

    @app.get("/{code}")
    def follow(code: str, request: Request):
        link = conn.execute("SELECT * FROM links WHERE code = ?", (code,)).fetchone()
        if not link:
            raise HTTPException(404, "unknown short link")
        conn.execute("INSERT INTO clicks (link_id, ts, referrer) VALUES (?, ?, ?)",
                     (link["id"], now(), request.headers.get("referer")))
        conn.commit()
        return RedirectResponse(link["target"], status_code=302)

    if STATIC_DIR.exists():
        @app.get("/")
        def index():
            return FileResponse(STATIC_DIR / "index.html")
        app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    return app


app = create_app()
