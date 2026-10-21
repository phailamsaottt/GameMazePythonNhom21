"""
algorithms/pathfinding.py
Step-by-step Pathfinding Algorithms with Python Generators.

Implements BFS, DFS, and A* using Python `yield` to output every step
for real-time visualizers and algorithm racing animations.

Follows the 'game-ai' skill principles:
- Admissible Manhattan heuristic for 4-directional grid
- Check goal on pop (never on push)
- Proper relaxation (g-cost update)
- Tie-breaking in priority queue using monotonic counter
- Robust path reconstruction from parent pointers
- Performance-friendly, structured yield data
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import heapq
import time
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple

# Constants for grid cell states
WALL: int = 1
PATH: int = 0


@dataclass
class SearchStats:
    """Performance metrics for the pathfinding search."""
    algorithm: str
    nodes_explored: int = 0
    max_frontier_size: int = 0
    path_length: int = 0
    total_cost: float = 0.0
    elapsed_time_ms: float = 0.0


@dataclass
class SearchStep:
    """
    State yielded at each step of the pathfinding generator.
    Supports both attribute access (.current) and dict access (['current']).
    """
    algorithm: str
    current: Tuple[int, int]
    visited: Set[Tuple[int, int]]
    frontier: List[Tuple[int, int]]
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]]
    path: Optional[List[Tuple[int, int]]] = None
    is_done: bool = False
    found: bool = False
    cost_so_far: Dict[Tuple[int, int], float] = field(default_factory=dict)
    stats: Optional[SearchStats] = None

    def __getitem__(self, item: str) -> Any:
        return getattr(self, item)

    def __contains__(self, item: str) -> bool:
        return hasattr(self, item)


def manhattan_distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """
    Admissible heuristic for 4-directional grid graphs.
    h(a, b) = |a.row - b.row| + |a.col - b.col|
    """
    return float(abs(a[0] - b[0]) + abs(a[1] - b[1]))


def euclidean_distance(a: Tuple[int, int], b: Tuple[int, int]) -> float:
    """Euclidean distance heuristic."""
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def reconstruct_path(
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Optional[List[Tuple[int, int]]]:
    """
    Reconstruct path backwards from goal to start using parent pointers.
    Returns list of (row, col) from start to goal inclusive, or None if unreachable.
    """
    if goal not in came_from:
        return None

    path = []
    curr: Optional[Tuple[int, int]] = goal
    while curr is not None:
        path.append(curr)
        if curr == start:
            break
        curr = came_from.get(curr)

    if not path or path[-1] != start:
        return None

    path.reverse()
    return path


def get_neighbors(
    grid: List[List[int]],
    pos: Tuple[int, int],
    rows: int,
    cols: int,
) -> List[Tuple[int, int]]:
    """
    Return passable 4-directional cardinal neighbors within bounds.
    Order: Up, Down, Left, Right for consistent deterministic expansion.
    """
    r, c = pos
    candidates = [(r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)]
    valid = []
    for nr, nc in candidates:
        if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == PATH:
            valid.append((nr, nc))
    return valid


# -----------------------------------------------------------------------------
# 1. Breadth-First Search (BFS) Generator
# -----------------------------------------------------------------------------
def bfs(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Generator[SearchStep, None, Optional[List[Tuple[int, int]]]]:
    """
    Breadth-First Search (BFS) using Python generator (yield).
    Guarantees the shortest path on unweighted graphs by expanding layer by layer.

    Yields SearchStep on every node evaluation for animation.
    Returns reconstructed path upon completion.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    # FIFO Queue
    queue: deque[Tuple[int, int]] = deque([start])
    visited: Set[Tuple[int, int]] = {start}
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    cost_so_far: Dict[Tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = len(queue)

    # Edge case: start is goal
    if start == goal:
        elapsed = (time.perf_counter() - start_time) * 1000.0
        stats = SearchStats(
            algorithm="BFS",
            nodes_explored=1,
            max_frontier_size=1,
            path_length=1,
            total_cost=0.0,
            elapsed_time_ms=elapsed,
        )
        final_step = SearchStep(
            algorithm="BFS",
            current=start,
            visited=visited,
            frontier=[],
            came_from=came_from,
            path=[start],
            is_done=True,
            found=True,
            cost_so_far=cost_so_far,
            stats=stats,
        )
        yield final_step
        return [start]

    while queue:
        current = queue.popleft()
        nodes_explored += 1

        # Check goal when popping (best practice)
        if current == goal:
            final_path = reconstruct_path(came_from, start, goal)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            stats = SearchStats(
                algorithm="BFS",
                nodes_explored=nodes_explored,
                max_frontier_size=max_frontier,
                path_length=len(final_path) if final_path else 0,
                total_cost=cost_so_far.get(goal, 0.0),
                elapsed_time_ms=elapsed,
            )
            step = SearchStep(
                algorithm="BFS",
                current=current,
                visited=visited,
                frontier=list(queue),
                came_from=came_from,
                path=final_path,
                is_done=True,
                found=True,
                cost_so_far=cost_so_far,
                stats=stats,
            )
            yield step
            return final_path

        for neighbor in get_neighbors(grid, current, rows, cols):
            if neighbor not in visited:
                visited.add(neighbor)
                came_from[neighbor] = current
                cost_so_far[neighbor] = cost_so_far[current] + 1.0
                queue.append(neighbor)

        max_frontier = max(max_frontier, len(queue))

        # Yield step state for rendering animation frame
        yield SearchStep(
            algorithm="BFS",
            current=current,
            visited=visited,
            frontier=list(queue),
            came_from=came_from,
            path=None,
            is_done=False,
            found=False,
            cost_so_far=cost_so_far,
        )

    # Exhausted frontier without finding goal
    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="BFS",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=0,
        total_cost=0.0,
        elapsed_time_ms=elapsed,
    )
    yield SearchStep(
        algorithm="BFS",
        current=start,
        visited=visited,
        frontier=[],
        came_from=came_from,
        path=None,
        is_done=True,
        found=False,
        cost_so_far=cost_so_far,
        stats=stats,
    )
    return None


# -----------------------------------------------------------------------------
# 2. Depth-First Search (DFS) Generator
# -----------------------------------------------------------------------------
def dfs(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> Generator[SearchStep, None, Optional[List[Tuple[int, int]]]]:
    """
    Depth-First Search (DFS) using Python generator (yield).
    Explores deeply along corridors before backtracking.

    Yields SearchStep on every node evaluation for animation.
    Returns reconstructed path upon completion.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    # LIFO Stack
    stack: List[Tuple[int, int]] = [start]
    visited: Set[Tuple[int, int]] = set()
    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    cost_so_far: Dict[Tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = len(stack)

    while stack:
        current = stack.pop()

        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1

        # Check goal when popped
        if current == goal:
            final_path = reconstruct_path(came_from, start, goal)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            stats = SearchStats(
                algorithm="DFS",
                nodes_explored=nodes_explored,
                max_frontier_size=max_frontier,
                path_length=len(final_path) if final_path else 0,
                total_cost=cost_so_far.get(goal, 0.0),
                elapsed_time_ms=elapsed,
            )
            step = SearchStep(
                algorithm="DFS",
                current=current,
                visited=visited,
                frontier=list(stack),
                came_from=came_from,
                path=final_path,
                is_done=True,
                found=True,
                cost_so_far=cost_so_far,
                stats=stats,
            )
            yield step
            return final_path

        # Push neighbors to stack (reverse order so cardinal exploration maintains priority)
        neighbors = get_neighbors(grid, current, rows, cols)
        for neighbor in reversed(neighbors):
            if neighbor not in visited:
                if neighbor not in came_from:
                    came_from[neighbor] = current
                    cost_so_far[neighbor] = cost_so_far[current] + 1.0
                stack.append(neighbor)

        max_frontier = max(max_frontier, len(stack))

        yield SearchStep(
            algorithm="DFS",
            current=current,
            visited=visited,
            frontier=list(stack),
            came_from=came_from,
            path=None,
            is_done=False,
            found=False,
            cost_so_far=cost_so_far,
        )

    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="DFS",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=0,
        total_cost=0.0,
        elapsed_time_ms=elapsed,
    )
    yield SearchStep(
        algorithm="DFS",
        current=start,
        visited=visited,
        frontier=[],
        came_from=came_from,
        path=None,
        is_done=True,
        found=False,
        cost_so_far=cost_so_far,
        stats=stats,
    )
    return None


# -----------------------------------------------------------------------------
# 3. A* Search (A-Star) Generator
# -----------------------------------------------------------------------------
def astar(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
    heuristic: Callable[[Tuple[int, int], Tuple[int, int]], float] = manhattan_distance,
) -> Generator[SearchStep, None, Optional[List[Tuple[int, int]]]]:
    """
    A* Search algorithm using Python generator (yield).
    Maintains a priority queue sorted by f(n) = g(n) + h(n).
    Guarantees optimal shortest path when heuristic is admissible.

    Includes monotonic tie-breaker counter and subtle directional tie-breaking
    to avoid wandering along equal-f corridors.

    Yields SearchStep on every node evaluation for animation.
    Returns reconstructed path upon completion.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    # Priority queue: (f_score, tie_breaker_counter, node)
    counter = 0
    initial_h = heuristic(start, goal)
    # Tie-breaking scale: prefer paths closer to goal among equal f-costs
    frontier: List[Tuple[float, int, Tuple[int, int]]] = [(initial_h, counter, start)]

    came_from: Dict[Tuple[int, int], Optional[Tuple[int, int]]] = {start: None}
    cost_so_far: Dict[Tuple[int, int], float] = {start: 0.0}
    visited: Set[Tuple[int, int]] = set()

    nodes_explored = 0
    max_frontier = len(frontier)

    while frontier:
        f_val, _, current = heapq.heappop(frontier)

        # Skip if already closed with equal or better cost
        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1

        # Check goal on pop (game-ai best practice)
        if current == goal:
            final_path = reconstruct_path(came_from, start, goal)
            elapsed = (time.perf_counter() - start_time) * 1000.0
            stats = SearchStats(
                algorithm="A*",
                nodes_explored=nodes_explored,
                max_frontier_size=max_frontier,
                path_length=len(final_path) if final_path else 0,
                total_cost=cost_so_far.get(goal, 0.0),
                elapsed_time_ms=elapsed,
            )
            step = SearchStep(
                algorithm="A*",
                current=current,
                visited=visited,
                frontier=[node for _, _, node in frontier],
                came_from=came_from,
                path=final_path,
                is_done=True,
                found=True,
                cost_so_far=cost_so_far,
                stats=stats,
            )
            yield step
            return final_path

        current_g = cost_so_far[current]

        for neighbor in get_neighbors(grid, current, rows, cols):
            new_g = current_g + 1.0  # Uniform cost per step in grid

            # Relaxation: accept this step if cheaper or previously unreached
            if neighbor not in cost_so_far or new_g < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_g
                came_from[neighbor] = current
                h = heuristic(neighbor, goal)
                # Subtle tie-breaker multiplier (1.0001) directs search towards goal
                f = new_g + h * 1.0001
                counter += 1
                heapq.heappush(frontier, (f, counter, neighbor))

        max_frontier = max(max_frontier, len(frontier))

        # Yield state for visualization frame
        yield SearchStep(
            algorithm="A*",
            current=current,
            visited=visited,
            frontier=[node for _, _, node in frontier],
            came_from=came_from,
            path=None,
            is_done=False,
            found=False,
            cost_so_far=cost_so_far,
        )

    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="A*",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=0,
        total_cost=0.0,
        elapsed_time_ms=elapsed,
    )
    yield SearchStep(
        algorithm="A*",
        current=start,
        visited=visited,
        frontier=[],
        came_from=came_from,
        path=None,
        is_done=True,
        found=False,
        cost_so_far=cost_so_far,
        stats=stats,
    )
    return None


# -----------------------------------------------------------------------------
# Convenience Solver Wrappers (Non-generator, direct execution)
# -----------------------------------------------------------------------------
def solve_bfs(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> SearchStep:
    """Run BFS to completion and return the final SearchStep."""
    gen = bfs(grid, start, goal)
    last_step: Optional[SearchStep] = None
    for step in gen:
        last_step = step
    return last_step  # type: ignore[return-value]


def solve_dfs(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
) -> SearchStep:
    """Run DFS to completion and return the final SearchStep."""
    gen = dfs(grid, start, goal)
    last_step: Optional[SearchStep] = None
    for step in gen:
        last_step = step
    return last_step  # type: ignore[return-value]


def solve_astar(
    grid: List[List[int]],
    start: Tuple[int, int],
    goal: Tuple[int, int],
    heuristic: Callable[[Tuple[int, int], Tuple[int, int]], float] = manhattan_distance,
) -> SearchStep:
    """Run A* to completion and return the final SearchStep."""
    gen = astar(grid, start, goal, heuristic)
    last_step: Optional[SearchStep] = None
    for step in gen:
        last_step = step
    return last_step  # type: ignore[return-value]
