"""
algorithms/pathfinding.py - Step-by-Step Pathfinding Generators & Solvers.

Implements BFS, DFS, and A* search algorithms with Python generators (`yield`)
for real-time GUI visualization, algorithm race modes, and fast direct solvers.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
import heapq
import time
from typing import Any, Callable, Final, Generator

# Grid cell state constants
WALL: Final[int] = 1
PATH: Final[int] = 0

_SEARCH_STEP_FIELDS: Final[frozenset[str]] = frozenset({
    "algorithm",
    "current",
    "visited",
    "frontier",
    "came_from",
    "path",
    "is_done",
    "found",
    "cost_so_far",
    "stats",
})


@dataclass(slots=True)
class SearchStats:
    """Performance telemetry for pathfinding executions."""
    algorithm: str
    nodes_explored: int = 0
    max_frontier_size: int = 0
    path_length: int = 0
    total_cost: float = 0.0
    elapsed_time_ms: float = 0.0


@dataclass(slots=True)
class SearchStep:
    """
    Search state yielded at each step of the generator.
    Supports both attribute access (.current) and dict access (['current']).
    """
    algorithm: str
    current: tuple[int, int]
    visited: set[tuple[int, int]]
    frontier: list[tuple[int, int]]
    came_from: dict[tuple[int, int], tuple[int, int] | None]
    path: list[tuple[int, int]] | None = None
    is_done: bool = False
    found: bool = False
    cost_so_far: dict[tuple[int, int], float] = field(default_factory=dict)
    stats: SearchStats | None = None

    def __getitem__(self, item: str) -> Any:
        try:
            return getattr(self, item)
        except AttributeError:
            raise KeyError(item) from None

    def __contains__(self, item: str) -> bool:
        return item in _SEARCH_STEP_FIELDS


def manhattan_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    """Admissible L1 Manhattan distance heuristic for 4-directional grids."""
    return float(abs(a[0] - b[0]) + abs(a[1] - b[1]))


def euclidean_distance(a: tuple[int, int], b: tuple[int, int]) -> float:
    """L2 Euclidean distance heuristic."""
    return float(((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5)


def reconstruct_path(
    came_from: dict[tuple[int, int], tuple[int, int] | None],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> list[tuple[int, int]] | None:
    """
    Reconstruct the path from goal back to start with cycle protection.
    Returns list of (row, col) from start to goal inclusive, or None if unreachable.
    """
    if goal not in came_from:
        return None

    path: list[tuple[int, int]] = []
    curr: tuple[int, int] | None = goal
    visited_cells: set[tuple[int, int]] = set()

    while curr is not None and curr not in visited_cells:
        visited_cells.add(curr)
        path.append(curr)
        if curr == start:
            path.reverse()
            return path
        curr = came_from.get(curr)

    return None


def get_neighbors(
    grid: list[list[int]],
    pos: tuple[int, int],
    rows: int,
    cols: int,
) -> list[tuple[int, int]]:
    """
    Return passable 4-directional cardinal neighbors within grid bounds.
    Order: Up, Down, Left, Right for consistent deterministic expansion.
    """
    r, c = pos
    valid: list[tuple[int, int]] = []
    if r > 0 and grid[r - 1][c] == PATH:
        valid.append((r - 1, c))
    if r + 1 < rows and grid[r + 1][c] == PATH:
        valid.append((r + 1, c))
    if c > 0 and grid[r][c - 1] == PATH:
        valid.append((r, c - 1))
    if c + 1 < cols and grid[r][c + 1] == PATH:
        valid.append((r, c + 1))
    return valid


# -----------------------------------------------------------------------------
# 1. Breadth-First Search (BFS) Generator
# -----------------------------------------------------------------------------
def bfs(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> Generator[SearchStep, None, list[tuple[int, int]] | None]:
    """
    Breadth-First Search generator yielding SearchStep for animation.
    Guarantees shortest path on unweighted graphs.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    queue: deque[tuple[int, int]] = deque([start])
    visited: set[tuple[int, int]] = {start}
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = 1

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
        yield SearchStep(
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
        return [start]

    while queue:
        current = queue.popleft()
        nodes_explored += 1

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

        current_cost = cost_so_far[current] + 1.0
        for neighbor in get_neighbors(grid, current, rows, cols):
            if neighbor not in visited:
                visited.add(neighbor)
                came_from[neighbor] = current
                cost_so_far[neighbor] = current_cost
                queue.append(neighbor)

        max_frontier = max(max_frontier, len(queue))

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
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> Generator[SearchStep, None, list[tuple[int, int]] | None]:
    """
    Depth-First Search generator yielding SearchStep for animation.
    Explores deeply along corridors before backtracking.
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    stack: list[tuple[int, int]] = [start]
    in_stack: set[tuple[int, int]] = {start}
    visited: set[tuple[int, int]] = set()
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = 1

    while stack:
        current = stack.pop()
        in_stack.discard(current)

        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1

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

        current_cost = cost_so_far[current] + 1.0
        # Push in reverse cardinal order to maintain Up/Down/Left/Right priority
        for neighbor in reversed(get_neighbors(grid, current, rows, cols)):
            if neighbor not in visited and neighbor not in in_stack:
                came_from[neighbor] = current
                cost_so_far[neighbor] = current_cost
                stack.append(neighbor)
                in_stack.add(neighbor)

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
# 3. A* Search Generator
# -----------------------------------------------------------------------------
def astar(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    heuristic: Callable[[tuple[int, int], tuple[int, int]], float] = manhattan_distance,
) -> Generator[SearchStep, None, list[tuple[int, int]] | None]:
    """
    A* Search generator yielding SearchStep for animation.
    Maintains min-heap priority queue sorted by f(n) = g(n) + h(n).
    """
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    counter = 0
    initial_h = heuristic(start, goal)
    # Priority heap entry: (f_score, tie_breaker_id, node)
    frontier: list[tuple[float, int, tuple[int, int]]] = [(initial_h, counter, start)]

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}
    visited: set[tuple[int, int]] = set()

    nodes_explored = 0
    max_frontier = 1

    while frontier:
        _, _, current = heapq.heappop(frontier)

        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1

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
        new_g = current_g + 1.0

        for neighbor in get_neighbors(grid, current, rows, cols):
            if neighbor in visited:
                continue

            if neighbor not in cost_so_far or new_g < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_g
                came_from[neighbor] = current
                h = heuristic(neighbor, goal)
                # Subtle tie-breaker multiplier pushes exploration along direct corridors
                f = new_g + h * 1.0001
                counter += 1
                heapq.heappush(frontier, (f, counter, neighbor))

        max_frontier = max(max_frontier, len(frontier))

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
# Direct Solver Wrappers (Fast non-generator execution)
# -----------------------------------------------------------------------------
def solve_bfs(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> SearchStep:
    """Run BFS directly to completion with high performance and return final SearchStep."""
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    queue: deque[tuple[int, int]] = deque([start])
    visited: set[tuple[int, int]] = {start}
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = 1
    found = False
    current = start

    while queue:
        current = queue.popleft()
        nodes_explored += 1
        if current == goal:
            found = True
            break

        current_cost = cost_so_far[current] + 1.0
        for neighbor in get_neighbors(grid, current, rows, cols):
            if neighbor not in visited:
                visited.add(neighbor)
                came_from[neighbor] = current
                cost_so_far[neighbor] = current_cost
                queue.append(neighbor)

        if len(queue) > max_frontier:
            max_frontier = len(queue)

    final_path = reconstruct_path(came_from, start, goal) if found else None
    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="BFS",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=len(final_path) if final_path else 0,
        total_cost=cost_so_far.get(goal, 0.0),
        elapsed_time_ms=elapsed,
    )
    return SearchStep(
        algorithm="BFS",
        current=current,
        visited=visited,
        frontier=list(queue),
        came_from=came_from,
        path=final_path,
        is_done=True,
        found=found,
        cost_so_far=cost_so_far,
        stats=stats,
    )


def solve_dfs(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> SearchStep:
    """Run DFS directly to completion with high performance and return final SearchStep."""
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    stack: list[tuple[int, int]] = [start]
    in_stack: set[tuple[int, int]] = {start}
    visited: set[tuple[int, int]] = set()
    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}

    nodes_explored = 0
    max_frontier = 1
    found = False
    current = start

    while stack:
        current = stack.pop()
        in_stack.discard(current)
        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1
        if current == goal:
            found = True
            break

        current_cost = cost_so_far[current] + 1.0
        for neighbor in reversed(get_neighbors(grid, current, rows, cols)):
            if neighbor not in visited and neighbor not in in_stack:
                came_from[neighbor] = current
                cost_so_far[neighbor] = current_cost
                stack.append(neighbor)
                in_stack.add(neighbor)

        if len(stack) > max_frontier:
            max_frontier = len(stack)

    final_path = reconstruct_path(came_from, start, goal) if found else None
    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="DFS",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=len(final_path) if final_path else 0,
        total_cost=cost_so_far.get(goal, 0.0),
        elapsed_time_ms=elapsed,
    )
    return SearchStep(
        algorithm="DFS",
        current=current,
        visited=visited,
        frontier=list(stack),
        came_from=came_from,
        path=final_path,
        is_done=True,
        found=found,
        cost_so_far=cost_so_far,
        stats=stats,
    )


def solve_astar(
    grid: list[list[int]],
    start: tuple[int, int],
    goal: tuple[int, int],
    heuristic: Callable[[tuple[int, int], tuple[int, int]], float] = manhattan_distance,
) -> SearchStep:
    """Run A* directly to completion with high performance and return final SearchStep."""
    rows = len(grid)
    cols = len(grid[0]) if rows > 0 else 0
    start_time = time.perf_counter()

    counter = 0
    initial_h = heuristic(start, goal)
    frontier: list[tuple[float, int, tuple[int, int]]] = [(initial_h, counter, start)]

    came_from: dict[tuple[int, int], tuple[int, int] | None] = {start: None}
    cost_so_far: dict[tuple[int, int], float] = {start: 0.0}
    visited: set[tuple[int, int]] = set()

    nodes_explored = 0
    max_frontier = 1
    found = False
    current = start

    while frontier:
        _, _, current = heapq.heappop(frontier)
        if current in visited:
            continue

        visited.add(current)
        nodes_explored += 1
        if current == goal:
            found = True
            break

        current_g = cost_so_far[current]
        new_g = current_g + 1.0

        for neighbor in get_neighbors(grid, current, rows, cols):
            if neighbor in visited:
                continue

            if neighbor not in cost_so_far or new_g < cost_so_far[neighbor]:
                cost_so_far[neighbor] = new_g
                came_from[neighbor] = current
                h = heuristic(neighbor, goal)
                f = new_g + h * 1.0001
                counter += 1
                heapq.heappush(frontier, (f, counter, neighbor))

        if len(frontier) > max_frontier:
            max_frontier = len(frontier)

    final_path = reconstruct_path(came_from, start, goal) if found else None
    elapsed = (time.perf_counter() - start_time) * 1000.0
    stats = SearchStats(
        algorithm="A*",
        nodes_explored=nodes_explored,
        max_frontier_size=max_frontier,
        path_length=len(final_path) if final_path else 0,
        total_cost=cost_so_far.get(goal, 0.0),
        elapsed_time_ms=elapsed,
    )
    return SearchStep(
        algorithm="A*",
        current=current,
        visited=visited,
        frontier=[node for _, _, node in frontier],
        came_from=came_from,
        path=final_path,
        is_done=True,
        found=found,
        cost_so_far=cost_so_far,
        stats=stats,
    )
