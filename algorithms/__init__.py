"""
algorithms package.

Provides:
- Maze generator (DFS / Recursive Backtracker, Prim's, Kruskal's, seeded RNG, braiding, connectivity guarantee)
- Step-by-step pathfinding generators (BFS, DFS, A*) with yield for real-time visualization and racing.
"""

from algorithms.generator import (
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
    manhattan_distance,
    reconstruct_path,
    solve_astar,
    solve_bfs,
    solve_dfs,
)

__all__ = [
    # Generator
    "WALL",
    "PATH",
    "GenerationAlgorithm",
    "Maze",
    "MazeGenerator",
    "GenerationStep",
    "generate_maze",
    "generate_random_maze",
    # Pathfinding
    "SearchStats",
    "SearchStep",
    "bfs",
    "dfs",
    "astar",
    "manhattan_distance",
    "euclidean_distance",
    "reconstruct_path",
    "solve_bfs",
    "solve_dfs",
    "solve_astar",
]
