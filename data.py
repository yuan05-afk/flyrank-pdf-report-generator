"""
Data layer — a small SQLite dataset the report aggregates over.

Simulates FlyRank-style page audits so the report has something real to
GROUP BY / COUNT / AVG. Seeded once on first run.
"""

from __future__ import annotations

import random
import sqlite3
from pathlib import Path
from typing import Any

DB_PATH = Path(__file__).resolve().parent / "data.db"

CATEGORIES = ["blog", "product", "landing", "docs", "pricing"]


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db(seed_rows: int = 60) -> None:
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS page_audits (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                url          TEXT NOT NULL,
                category     TEXT NOT NULL,
                seo_score    INTEGER NOT NULL,
                issues       INTEGER NOT NULL,
                audited_at   TEXT NOT NULL DEFAULT (datetime('now'))
            )
            """
        )
        count = conn.execute("SELECT COUNT(*) AS c FROM page_audits").fetchone()["c"]
        if count == 0:
            rng = random.Random(42)  # deterministic seed for reproducible demos
            rows = []
            for i in range(1, seed_rows + 1):
                cat = rng.choice(CATEGORIES)
                score = rng.randint(35, 99)
                issues = max(0, (100 - score) // 10 + rng.randint(0, 3))
                rows.append((f"https://example.com/{cat}/page-{i}", cat, score, issues))
            conn.executemany(
                "INSERT INTO page_audits (url, category, seo_score, issues) VALUES (?, ?, ?, ?)",
                rows,
            )
        conn.commit()


def overall_summary() -> dict[str, Any]:
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS total,
                   ROUND(AVG(seo_score), 1) AS avg_score,
                   SUM(issues) AS total_issues,
                   MIN(seo_score) AS worst,
                   MAX(seo_score) AS best
            FROM page_audits
            """
        ).fetchone()
    return dict(row)


def summary_by_category() -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT category,
                   COUNT(*) AS pages,
                   ROUND(AVG(seo_score), 1) AS avg_score,
                   SUM(issues) AS issues
            FROM page_audits
            GROUP BY category
            ORDER BY avg_score DESC
            """
        ).fetchall()
    return [dict(r) for r in rows]


def worst_pages(limit: int = 10) -> list[dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT url, category, seo_score, issues
            FROM page_audits
            ORDER BY seo_score ASC, issues DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]
