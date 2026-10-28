"""
algorithms - High-Performance Procedural Maze Generation and Pathfinding.

Modules:
- generator: Procedural maze generation (DFS, Prim's, Kruskal's, braiding, auto-repair).
- pathfinding: Step-by-step pathfinding generators (BFS, DFS, A*) and fast direct solvers.
"""

from __future__ import annotations

from algorithms.generator import (
    CARDINAL_OFFSETS,
    GenerationAlgorithm,
    GenerationStep,
    Maze,
    MazeGenerator,
    PATH,
    WALL,
    generate_maze,
    generate_random_maze,
)
from algorithms.pathfinding import (
    SearchStats,
    SearchStep,
    astar,
    bfs,
    dfs,
    euclidean_distance,
    get_neighbors,
    manhattan_distance,
    reconstruct_path,
    solve_astar,
    solve_bfs,
    solve_dfs,
)

__all__: tuple[str, ...] = (
    # Grid states & topology
    "WALL",
    "PATH",
    "CARDINAL_OFFSETS",
    # Generator
    "GenerationAlgorithm",
    "Maze",
    "MazeGenerator",
    "GenerationStep",
    "generate_maze",
    "generate_random_maze",
    # Pathfinding
    "SearchStats",
    "SearchStep",
    "get_neighbors",
    "bfs",
    "dfs",
    "astar",
    "manhattan_distance",
    "euclidean_distance",
    "reconstruct_path",
    "solve_bfs",
    "solve_dfs",
    "solve_astar",
)
