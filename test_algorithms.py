"""
Unit tests for algorithms/generator.py and algorithms/pathfinding.py
"""

import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from algorithms import (
    GenerationAlgorithm,
    MazeGenerator,
    PATH,
    WALL,
    astar,
    bfs,
    dfs,
    generate_maze,
    generate_random_maze,
    solve_astar,
    solve_bfs,
    solve_dfs,
)


def test_seed_determinism():
    """Verify that identical seeds produce identical grids."""
    seed = "test_seed_alpha_42"
    maze1 = generate_maze(rows=21, cols=21, seed=seed, algorithm="dfs")
    maze2 = generate_maze(rows=21, cols=21, seed=seed, algorithm="dfs")
    assert maze1.grid == maze2.grid, "Mazes with same seed must be strictly identical"
    assert maze1.seed == maze2.seed


def test_different_seeds_differ():
    """Verify that different seeds produce different mazes."""
    maze1 = generate_maze(rows=21, cols=21, seed=11111, algorithm="dfs")
    maze2 = generate_maze(rows=21, cols=21, seed=99999, algorithm="dfs")
    assert maze1.grid != maze2.grid, "Different seeds should produce different mazes"


def test_generation_algorithms():
    """Verify all algorithms (DFS, Prim's, Kruskal's) generate connected mazes."""
    for algo in [GenerationAlgorithm.DFS, GenerationAlgorithm.PRIMS, GenerationAlgorithm.KRUSKAL]:
        maze = generate_maze(rows=25, cols=25, seed=42, algorithm=algo)
        assert maze.is_path(maze.start[0], maze.start[1])
        assert maze.is_path(maze.goal[0], maze.goal[1])
        
        # Test pathfinding reaches goal
        res = solve_bfs(maze.grid, maze.start, maze.goal)
        assert res.found, f"Goal must be reachable for algorithm: {algo}"
        assert res.path is not None and len(res.path) > 0
        assert res.path[0] == maze.start
        assert res.path[-1] == maze.goal


def test_pathfinding_generators():
    """Verify BFS, DFS, and A* generator yielding mechanism."""
    maze = generate_maze(rows=21, cols=21, seed=12345, algorithm="dfs")
    start = maze.start
    goal = maze.goal

    for name, func in [("BFS", bfs), ("DFS", dfs), ("A*", astar)]:
        gen = func(maze.grid, start, goal)
        steps = []
        final_step = None
        for step in gen:
            steps.append(step)
            assert step.algorithm in ("BFS", "DFS", "A*")
            assert isinstance(step.current, tuple)
            assert isinstance(step.visited, set)
            if step.is_done:
                final_step = step

        assert len(steps) > 0, f"{name} must yield at least one step"
        assert final_step is not None, f"{name} must yield a final step"
        assert final_step.is_done, f"{name} final step must have is_done=True"
        assert final_step.found, f"{name} must find path to goal"
        assert final_step.path is not None
        assert final_step.path[0] == start
        assert final_step.path[-1] == goal
        assert final_step.stats is not None
        assert final_step.stats.nodes_explored > 0


def test_astar_optimality():
    """Verify A* path length matches BFS shortest path length."""
    maze = generate_maze(rows=25, cols=25, seed=777, algorithm="prims", braid_factor=0.3)
    bfs_result = solve_bfs(maze.grid, maze.start, maze.goal)
    astar_result = solve_astar(maze.grid, maze.start, maze.goal)

    assert bfs_result.found and astar_result.found
    assert bfs_result.path is not None and astar_result.path is not None
    assert len(bfs_result.path) == len(astar_result.path), (
        f"A* path length ({len(astar_result.path)}) must match BFS shortest path length ({len(bfs_result.path)})"
    )


def test_braiding():
    """Verify braid factor creates loops without breaking pathfinding."""
    maze_pure = generate_maze(rows=21, cols=21, seed=100, braid_factor=0.0)
    maze_braid = generate_maze(rows=21, cols=21, seed=100, braid_factor=0.5)

    pure_paths = sum(row.count(PATH) for row in maze_pure.grid)
    braid_paths = sum(row.count(PATH) for row in maze_braid.grid)

    assert braid_paths >= pure_paths, "Braided maze should have equal or more path cells (loops carved)"
    res = solve_astar(maze_braid.grid, maze_braid.start, maze_braid.goal)
    assert res.found


def test_animated_generation():
    """Verify animated maze generation step yielding."""
    generator = MazeGenerator(seed=42)
    step_count = 0
    final_step = None
    for step in generator.generate_steps(rows=15, cols=15, algorithm="dfs"):
        step_count += 1
        assert isinstance(step.grid, list)
        if step.is_done:
            final_step = step

    assert step_count > 10, "Generation should yield multiple steps"
    assert final_step is not None and final_step.is_done


def test_total_randomness():
    """Verify that random mode produces diverse algorithms, seeds, and braid factors."""
    algorithms_seen = set()
    seeds_seen = set()
    braid_factors_seen = set()

    for _ in range(40):
        maze = generate_random_maze(rows=17, cols=17)
        algorithms_seen.add(maze.algorithm)
        seeds_seen.add(maze.seed)
        braid_factors_seen.add(maze.braid_factor)
        assert maze.is_path(maze.start[0], maze.start[1])
        assert maze.is_path(maze.goal[0], maze.goal[1])

        # Guarantee solvability
        res = solve_astar(maze.grid, maze.start, maze.goal)
        assert res.found, f"Random maze must always be solvable! (algo={maze.algorithm})"

    # Across 40 random runs, we should see multiple algorithms (DFS, Prim's, Kruskal's)
    assert len(algorithms_seen) >= 2, f"Should observe varied algorithms: {algorithms_seen}"
    assert len(seeds_seen) == 40, "Each random maze should have a unique random seed"
    assert len(braid_factors_seen) >= 2, "Braid factors should have random variation"


def test_auto_repair():
    """Verify that auto-repair successfully repairs disconnected mazes."""
    generator = MazeGenerator(seed=999)
    maze = generator.generate(rows=21, cols=21, algorithm="dfs")

    # Deliberately block all exits from start to force a disconnection
    sr, sc = maze.start
    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
        if maze.in_bounds(sr + dr, sc + dc):
            maze.grid[sr + dr][sc + dc] = WALL

    # Verify start is isolated
    res_before = solve_bfs(maze.grid, maze.start, maze.goal)
    assert not res_before.found, "Maze should be disconnected after walls placed"

    # Run auto-repair
    repaired = generator._ensure_connectivity(maze.grid, maze.rows, maze.cols, maze.start, maze.goal)
    assert repaired, "Auto-repair must report that it performed a repair"

    # Verify that goal is now reachable
    res_after = solve_bfs(maze.grid, maze.start, maze.goal)
    assert res_after.found, "Maze must be solvable after auto-repair"
    assert res_after.path is not None


if __name__ == "__main__":
    print("Running algorithms test suite...")
    test_seed_determinism()
    print("PASS: test_seed_determinism")
    test_different_seeds_differ()
    print("PASS: test_different_seeds_differ")
    test_generation_algorithms()
    print("PASS: test_generation_algorithms (DFS, Prim's, Kruskal's)")
    test_pathfinding_generators()
    print("PASS: test_pathfinding_generators (BFS, DFS, A*)")
    test_astar_optimality()
    print("PASS: test_astar_optimality (A* == BFS shortest path)")
    test_braiding()
    print("PASS: test_braiding")
    test_animated_generation()
    print("PASS: test_animated_generation")
    test_total_randomness()
    print("PASS: test_total_randomness")
    test_auto_repair()
    print("PASS: test_auto_repair")
    print("\nALL TESTS PASSED SUCCESSFULLY!")
