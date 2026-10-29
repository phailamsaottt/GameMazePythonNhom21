from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
import sqlite3
from typing import Any, Iterable, Iterator, Mapping, Protocol
import uuid

from config import DB_PATH

MODE_RACE = "race"
MODE_PLAY = "play"
PLAYER_NAME = "PLAYER"
SOLVER_NAMES = ("BFS", "DFS", "A*")

SCHEMA = """
CREATE TABLE IF NOT EXISTS play_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id         TEXT    NOT NULL,
    played_at       TEXT    NOT NULL,
    mode            TEXT    NOT NULL CHECK (mode IN ('race', 'play')),
    maze_seed       TEXT    NOT NULL,
    maze_algorithm  TEXT    NOT NULL,
    maze_rows       INTEGER NOT NULL,
    maze_cols       INTEGER NOT NULL,
    braid_factor    REAL    NOT NULL DEFAULT 0,
    solver          TEXT    NOT NULL,
    found           INTEGER NOT NULL DEFAULT 1,
    nodes_explored  INTEGER NOT NULL DEFAULT 0,
    path_length     INTEGER NOT NULL DEFAULT 0,
    elapsed_ms      REAL    NOT NULL DEFAULT 0,
    max_frontier    INTEGER NOT NULL DEFAULT 0,
    is_winner       INTEGER NOT NULL DEFAULT 0,
    player_name     TEXT    NOT NULL DEFAULT 'PLAYER'
);
CREATE INDEX IF NOT EXISTS idx_history_race ON play_history(race_id);
CREATE INDEX IF NOT EXISTS idx_history_mode ON play_history(mode);
"""

_COLUMNS = (
    "race_id", "played_at", "mode", "maze_seed", "maze_algorithm", "maze_rows",
    "maze_cols", "braid_factor", "solver", "found", "nodes_explored",
    "path_length", "elapsed_ms", "max_frontier", "is_winner",
)
_INSERT_SQL = (
    f"INSERT INTO play_history ({', '.join(_COLUMNS)}) "
    f"VALUES ({', '.join('?' for _ in _COLUMNS)})"
)
_INSERT_PLAY_SQL = (
    f"INSERT INTO play_history ({', '.join((*_COLUMNS, 'player_name'))}) "
    f"VALUES ({', '.join('?' for _ in range(len(_COLUMNS) + 1))})"
)


class MazeLike(Protocol):
    seed: int
    algorithm: str
    rows: int
    cols: int
    braid_factor: float


@contextmanager
def get_connection(db_path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    path = Path(db_path) if db_path else Path(DB_PATH)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        conn.executescript(SCHEMA)
        columns = {row[1] for row in conn.execute("PRAGMA table_info(play_history)")}
        if "player_name" not in columns:
            conn.execute(
                "ALTER TABLE play_history ADD COLUMN player_name TEXT NOT NULL DEFAULT 'PLAYER'"
            )
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db(db_path: str | Path | None = None) -> None:
    with get_connection(db_path):
        pass


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _maze_fields(maze: MazeLike) -> tuple[str, str, int, int, float]:
    return (
        str(maze.seed),
        str(maze.algorithm),
        int(maze.rows),
        int(maze.cols),
        float(maze.braid_factor),
    )


def save_race(
    maze: MazeLike,
    results: Iterable[Mapping[str, Any]],
    winner: str | None = None,
    db_path: str | Path | None = None,
) -> str:
    results = list(results)
    if not results:
        raise ValueError("save_race() requires at least one solver result")

    race_id = uuid.uuid4().hex
    played_at = _now()
    maze_part = _maze_fields(maze)

    rows = [
        (
            race_id, played_at, MODE_RACE, *maze_part,
            str(r["solver"]),
            1 if r.get("found", True) else 0,
            int(r.get("nodes_explored", 0)),
            int(r.get("path_length", 0)),
            float(r.get("elapsed_ms", 0.0)),
            int(r.get("max_frontier", 0)),
            1 if winner is not None and r["solver"] == winner else 0,
        )
        for r in results
    ]
    with get_connection(db_path) as conn:
        conn.executemany(_INSERT_SQL, rows)
    return race_id


def save_play(
    maze: MazeLike,
    steps: int,
    elapsed_ms: float,
    completed: bool = True,
    db_path: str | Path | None = None,
    player_name: str = PLAYER_NAME,
) -> str:
    race_id = uuid.uuid4().hex
    row = (
        race_id, _now(), MODE_PLAY, *_maze_fields(maze),
        PLAYER_NAME, 1 if completed else 0, 0, int(steps), float(elapsed_ms), 0, 0,
        str(player_name).strip() or PLAYER_NAME,
    )
    with get_connection(db_path) as conn:
        conn.execute(_INSERT_PLAY_SQL, row)
    return race_id


def clear_history(db_path: str | Path | None = None) -> None:
    with get_connection(db_path) as conn:
        conn.execute("DELETE FROM play_history")


def fetch_history(
    mode: str | None = None,
    limit: int | None = None,
    db_path: str | Path | None = None,
) -> list[dict[str, Any]]:
    sql = "SELECT * FROM play_history"
    params: list[Any] = []
    if mode:
        sql += " WHERE mode = ?"
        params.append(mode)
    sql += " ORDER BY id DESC"
    if limit is not None:
        sql += " LIMIT ?"
        params.append(int(limit))
    with get_connection(db_path) as conn:
        return [dict(row) for row in conn.execute(sql, params)]


def fetch_race(race_id: str, db_path: str | Path | None = None) -> list[dict[str, Any]]:
    with get_connection(db_path) as conn:
        cur = conn.execute(
            "SELECT * FROM play_history WHERE race_id = ? ORDER BY id ASC", (race_id,)
        )
        return [dict(row) for row in cur]


def fetch_recent_race_ids(
    limit: int = 10,
    mode: str | None = None,
    db_path: str | Path | None = None,
) -> list[str]:
    sql = "SELECT race_id FROM play_history"
    params: list[Any] = []
    if mode:
        sql += " WHERE mode = ?"
        params.append(mode)
    sql += " GROUP BY race_id ORDER BY MAX(id) DESC LIMIT ?"
    params.append(int(limit))
    with get_connection(db_path) as conn:
        return [row["race_id"] for row in conn.execute(sql, params)]


def get_latest_race_id(
    mode: str | None = None, db_path: str | Path | None = None
) -> str | None:
    ids = fetch_recent_race_ids(limit=1, mode=mode, db_path=db_path)
    return ids[0] if ids else None
