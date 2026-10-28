"""
tests/test_console.py - Headless Console Test & Visualizer for Maze Algorithms.
"""

from __future__ import annotations
from pathlib import Path
import sys
import time

# Add project root to sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from algorithms import (
    GenerationAlgorithm,
    PATH,
    WALL,
    generate_maze,
    solve_astar,
    solve_bfs,
    solve_dfs,
)


def render_ascii(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    path: list[tuple[int, int]] | None = None,
) -> str:
    # ponytail: fixed character mapping; upgrade to ANSI colors when rich terminal output is requested.
    path_set = set(path) if path else set()
    lines: list[str] = []
    for r, row in enumerate(grid):
        line: list[str] = []
        for c, val in enumerate(row):
            pos = (r, c)
            if pos == start:
                line.append("S ")
            elif pos == goal:
                line.append("E ")
            elif pos in path_set:
                line.append("* ")
            elif val == WALL:
                line.append("# ")
            else:
                line.append("  ")
        lines.append("".join(line))
    return "\n".join(lines)


def run_tests() -> bool:
    print("=" * 65)
    print("CONSOLE MAZE ALGORITHM TEST (HEADLESS)")
    print("=" * 65)

    rows, cols = 15, 15
    print(f"\n[1] Testing Maze Generation ({rows}x{cols})...")
    for algo in [GenerationAlgorithm.DFS, GenerationAlgorithm.PRIMS, GenerationAlgorithm.KRUSKAL]:
        m = generate_maze(rows=rows, cols=cols, seed=42, algorithm=algo)
        assert m.is_path(*m.start) and m.is_path(*m.goal)
        print(f"  [OK] {algo.value.upper():<8} -> Start {m.start}, Goal {m.goal}, Paths: {m.count_paths()}")

    maze = generate_maze(rows=rows, cols=cols, seed=0, algorithm=GenerationAlgorithm.PRIMS, braid_factor=0.3)
    print(f"\nActive Maze for Pathfinding: {maze.algorithm.upper()} (Braid: {maze.braid_factor})")
    print(f"Start: {maze.start} | Goal: {maze.goal}")
    print("\nInitial Maze (# = Wall, S = Start, E = Goal):")
    print(render_ascii(maze.grid, maze.start, maze.goal))

    solvers = [
        ("BFS", solve_bfs),
        ("DFS", solve_dfs),
        ("A*", solve_astar),
    ]

    results = []
    print("\n" + "=" * 65)
    print("[2] Running Pathfinding Algorithms...")
    print("=" * 65)

    for name, fn in solvers:
        t0 = time.perf_counter()
        res = fn(maze.grid, maze.start, maze.goal)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        assert res.found, f"{name} failed to find goal"
        assert res.path is not None
        assert res.path[0] == maze.start and res.path[-1] == maze.goal

        # Validate step-by-step connectivity
        for i in range(len(res.path) - 1):
            r1, c1 = res.path[i]
            r2, c2 = res.path[i + 1]
            assert abs(r1 - r2) + abs(c1 - c2) == 1, f"{name}: Disconnected path step"
            assert maze.grid[r2][c2] == PATH or (r2, c2) == maze.goal

        nodes_explored = res.stats.nodes_explored if res.stats else len(res.visited)
        results.append((name, len(res.path), nodes_explored, elapsed_ms, res.path))
        print(f"\n--- {name} Solution (* = Path, Length: {len(res.path)}, Explored: {nodes_explored}) ---")
        print(render_ascii(maze.grid, maze.start, maze.goal, res.path))

    # Optimality verification
    bfs_len = next(r[1] for r in results if r[0] == "BFS")
    astar_len = next(r[1] for r in results if r[0] == "A*")
    assert bfs_len == astar_len, f"A* path ({astar_len}) != BFS shortest path ({bfs_len})"

    print("\n" + "=" * 65)
    print("ALGORITHM COMPARISON SUMMARY")
    print("=" * 65)
    print(f"{'Algorithm':<10} | {'Path Length':<12} | {'Nodes Explored':<15} | {'Time (ms)':<10} | {'Status':<8}")
    print("-" * 65)
    for name, plen, explored, elapsed, _ in results:
        print(f"{name:<10} | {plen:<12} | {explored:<15} | {elapsed:<10.3f} | {'PASS':<8}")
    print("-" * 65)
    print(f"Optimality check: A* ({astar_len}) == BFS ({bfs_len}) -> VERIFIED SHORTEST PATH")
    print("\nALL CONSOLE TESTS PASSED SUCCESSFULLY!")
    return True


if __name__ == "__main__":
    run_tests()
