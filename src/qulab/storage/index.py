"""Lightweight SQLite run index."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .events import to_jsonable


class RunIndex:
    """SQLite index for runs, points, data keys, and artifacts."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    experiment_name TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    ended_at TEXT,
                    status TEXT NOT NULL,
                    run_path TEXT NOT NULL,
                    metadata_json TEXT
                );
                CREATE TABLE IF NOT EXISTS data_keys (
                    run_id TEXT NOT NULL,
                    key TEXT NOT NULL,
                    kind TEXT,
                    unit TEXT,
                    shape_json TEXT,
                    uri TEXT,
                    PRIMARY KEY (run_id, key)
                );
                CREATE TABLE IF NOT EXISTS points (
                    run_id TEXT NOT NULL,
                    point_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    coords_json TEXT,
                    started_at TEXT,
                    completed_at TEXT,
                    PRIMARY KEY (run_id, point_id)
                );
                CREATE TABLE IF NOT EXISTS artifacts (
                    run_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    kind TEXT,
                    uri TEXT,
                    hash TEXT,
                    PRIMARY KEY (run_id, name)
                );
                """
            )

    def upsert_run(
        self,
        *,
        run_id: str,
        experiment_name: str,
        started_at: str,
        ended_at: str | None,
        status: str,
        run_path: Path,
        metadata: dict[str, Any],
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO runs (run_id, experiment_name, started_at, ended_at, status, run_path, metadata_json)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    experiment_name=excluded.experiment_name,
                    started_at=excluded.started_at,
                    ended_at=excluded.ended_at,
                    status=excluded.status,
                    run_path=excluded.run_path,
                    metadata_json=excluded.metadata_json
                """,
                (
                    run_id,
                    experiment_name,
                    started_at,
                    ended_at,
                    status,
                    str(run_path),
                    json.dumps(to_jsonable(metadata), sort_keys=True),
                ),
            )

    def upsert_point(
        self,
        *,
        run_id: str,
        point_id: str,
        status: str,
        coords: dict[str, Any],
        started_at: str | None,
        completed_at: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO points (run_id, point_id, status, coords_json, started_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, point_id) DO UPDATE SET
                    status=excluded.status,
                    coords_json=excluded.coords_json,
                    started_at=COALESCE(points.started_at, excluded.started_at),
                    completed_at=excluded.completed_at
                """,
                (
                    run_id,
                    point_id,
                    status,
                    json.dumps(to_jsonable(coords), sort_keys=True),
                    started_at,
                    completed_at,
                ),
            )

    def upsert_data_key(
        self,
        *,
        run_id: str,
        key: str,
        kind: str | None,
        unit: str | None,
        shape: Any,
        uri: str | None,
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO data_keys (run_id, key, kind, unit, shape_json, uri)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(run_id, key) DO UPDATE SET
                    kind=excluded.kind,
                    unit=excluded.unit,
                    shape_json=excluded.shape_json,
                    uri=excluded.uri
                """,
                (run_id, key, kind, unit, json.dumps(to_jsonable(shape), sort_keys=True), uri),
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path)
