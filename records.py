from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import database
from database import MODE_PLAY, MODE_RACE, SOLVER_NAMES

DbPath = str | Path | None

ALGO_LABELS: dict[str, str] = {"dfs": "DFS", "prims": "Prim", "kruskals": "Kruskal"}


def format_int(n: float | int) -> str:
    return f"{int(n):,}".replace(",", ".")


def format_ms(ms: float) -> str:
    if ms < 1.0:
        return f"{ms * 1000:.0f} µs"
    if ms < 1000.0:
        return f"{ms:.2f} ms"
    return f"{ms / 1000.0:.2f} s"


def format_datetime(iso: str) -> str:
    try:
        return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return iso


def format_maze(row: dict[str, Any]) -> str:
    algo = ALGO_LABELS.get(str(row["maze_algorithm"]).lower(), str(row["maze_algorithm"]))
    return f"{row['maze_rows']}x{row['maze_cols']} · {algo} · braid {row['braid_factor']:.2f}"


@dataclass(slots=True)
class SolverRow:
    solver: str
    found: bool
    is_winner: bool
    nodes_explored: int
    path_length: int
    elapsed_ms: float
    max_frontier: int
    nodes_text: str
    path_text: str
    time_text: str
    frontier_text: str
    status_text: str


@dataclass(slots=True)
class RaceResult:
    race_id: str
    played_at_text: str
    maze_text: str
    seed_text: str
    winner: str | None
    rows: list[SolverRow]
    insights: list[str] = field(default_factory=list)


@dataclass(slots=True)
class SolverStat:
    solver: str
    races: int
    wins: int
    win_rate: float
    avg_nodes: float
    avg_path: float
    avg_time_ms: float
    best_nodes: int
    best_time_ms: float

    @property
    def win_rate_text(self) -> str:
        return f"{self.win_rate:.0f}%"

    @property
    def avg_nodes_text(self) -> str:
        return format_int(self.avg_nodes)

    @property
    def avg_path_text(self) -> str:
        return f"{self.avg_path:.1f}"

    @property
    def avg_time_text(self) -> str:
        return format_ms(self.avg_time_ms)


@dataclass(slots=True)
class HistoryEntry:
    race_id: str
    date_text: str
    mode_text: str
    maze_text: str
    winner_text: str
    summary_text: str


@dataclass(slots=True)
class PlayerBest:
    size_text: str
    plays: int
    completed: int
    best_steps: int | None
    best_time_text: str


@dataclass(slots=True)
class OverallSummary:
    total_races: int
    total_plays: int
    top_solver: str | None
    top_solver_wins: int
    solver_stats: list[SolverStat]
    player_bests: list[PlayerBest]


def _solver_row(r: dict[str, Any]) -> SolverRow:
    found = bool(r["found"])
    winner = bool(r["is_winner"])
    return SolverRow(
        solver=r["solver"],
        found=found,
        is_winner=winner,
        nodes_explored=r["nodes_explored"],
        path_length=r["path_length"],
        elapsed_ms=r["elapsed_ms"],
        max_frontier=r["max_frontier"],
        nodes_text=format_int(r["nodes_explored"]),
        path_text=f"{r['path_length']} ô" if found else "—",
        time_text=format_ms(r["elapsed_ms"]),
        frontier_text=format_int(r["max_frontier"]),
        status_text="THẮNG" if winner else ("Hoàn thành" if found else "Không có đường"),
    )


def _names(rows: list[dict[str, Any]], key: str, best: float) -> str:
    return " & ".join(r["solver"] for r in rows if r[key] == best)


def _build_insights(rows: list[dict[str, Any]]) -> list[str]:
    ok = [r for r in rows if r["found"]]
    if not ok:
        return ["Không thuật toán nào tìm được đường đi."]

    best_nodes = min(r["nodes_explored"] for r in ok)
    best_path = min(r["path_length"] for r in ok)
    best_time = min(r["elapsed_ms"] for r in ok)

    out = [
        f"Duyệt ít node nhất: {_names(ok, 'nodes_explored', best_nodes)} ({format_int(best_nodes)} node)",
        f"Đường đi ngắn nhất: {_names(ok, 'path_length', best_path)} ({best_path} ô)",
        f"Giải nhanh nhất: {_names(ok, 'elapsed_ms', best_time)} ({format_ms(best_time)})",
    ]
    for r in ok:
        diff = r["path_length"] - best_path
        if diff > 0:
            out.append(f"{r['solver']} đi dài hơn đường tối ưu {diff} ô")
    return out


def get_race_result(race_id: str | None = None, db_path: DbPath = None) -> RaceResult | None:
    if race_id is None:
        race_id = database.get_latest_race_id(mode=MODE_RACE, db_path=db_path)
        if race_id is None:
            return None

    raw = database.fetch_race(race_id, db_path=db_path)
    if not raw:
        return None

    first = raw[0]
    ordered = sorted(
        raw,
        key=lambda r: (not r["found"], not r["is_winner"], r["nodes_explored"], r["path_length"]),
    )
    winner = next((r["solver"] for r in raw if r["is_winner"]), None)
    return RaceResult(
        race_id=race_id,
        played_at_text=format_datetime(first["played_at"]),
        maze_text=format_maze(first),
        seed_text=str(first["maze_seed"]),
        winner=winner,
        rows=[_solver_row(r) for r in ordered],
        insights=_build_insights(raw),
    )


def get_solver_stats(db_path: DbPath = None) -> list[SolverStat]:
    rows = database.fetch_history(mode=MODE_RACE, db_path=db_path)
    stats: list[SolverStat] = []
    for name in SOLVER_NAMES:
        mine = [r for r in rows if r["solver"] == name]
        ok = [r for r in mine if r["found"]]
        races = len(mine)
        wins = sum(1 for r in mine if r["is_winner"])
        n_ok = len(ok)
        stats.append(
            SolverStat(
                solver=name,
                races=races,
                wins=wins,
                win_rate=(wins / races * 100.0) if races else 0.0,
                avg_nodes=(sum(r["nodes_explored"] for r in ok) / n_ok) if n_ok else 0.0,
                avg_path=(sum(r["path_length"] for r in ok) / n_ok) if n_ok else 0.0,
                avg_time_ms=(sum(r["elapsed_ms"] for r in ok) / n_ok) if n_ok else 0.0,
                best_nodes=min((r["nodes_explored"] for r in ok), default=0),
                best_time_ms=min((r["elapsed_ms"] for r in ok), default=0.0),
            )
        )
    return stats


def get_player_bests(db_path: DbPath = None) -> list[PlayerBest]:
    rows = database.fetch_history(mode=MODE_PLAY, db_path=db_path)
    by_size: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for r in rows:
        by_size.setdefault((r["maze_rows"], r["maze_cols"]), []).append(r)

    bests: list[PlayerBest] = []
    for (rows_n, cols_n), items in sorted(by_size.items()):
        done = [r for r in items if r["found"]]
        bests.append(
            PlayerBest(
                size_text=f"{rows_n}x{cols_n}",
                plays=len(items),
                completed=len(done),
                best_steps=min((r["path_length"] for r in done), default=None),
                best_time_text=format_ms(min(r["elapsed_ms"] for r in done)) if done else "—",
            )
        )
    return bests


def get_overall_summary(db_path: DbPath = None) -> OverallSummary:
    stats = get_solver_stats(db_path)
    top = max(stats, key=lambda s: s.wins)
    return OverallSummary(
        total_races=len(database.fetch_recent_race_ids(10**9, MODE_RACE, db_path)),
        total_plays=len(database.fetch_recent_race_ids(10**9, MODE_PLAY, db_path)),
        top_solver=top.solver if top.wins > 0 else None,
        top_solver_wins=top.wins,
        solver_stats=stats,
        player_bests=get_player_bests(db_path),
    )


def get_history_table(limit: int = 10, db_path: DbPath = None) -> list[HistoryEntry]:
    entries: list[HistoryEntry] = []
    for race_id in database.fetch_recent_race_ids(limit=limit, db_path=db_path):
        rows = database.fetch_race(race_id, db_path=db_path)
        if not rows:
            continue
        first = rows[0]
        if first["mode"] == MODE_PLAY:
            status = "Hoàn thành" if first["found"] else "Bỏ dở"
            entries.append(
                HistoryEntry(
                    race_id=race_id,
                    date_text=format_datetime(first["played_at"]),
                    mode_text="Tự chơi",
                    maze_text=format_maze(first),
                    winner_text=status,
                    summary_text=f"{first['path_length']} bước · {format_ms(first['elapsed_ms'])}",
                )
            )
        else:
            win = next((r for r in rows if r["is_winner"]), None)
            entries.append(
                HistoryEntry(
                    race_id=race_id,
                    date_text=format_datetime(first["played_at"]),
                    mode_text="Đua thuật toán",
                    maze_text=format_maze(first),
                    winner_text=win["solver"] if win else "—",
                    summary_text=(
                        f"{win['path_length']} ô · {format_int(win['nodes_explored'])} node"
                        if win else "—"
                    ),
                )
            )
    return entries