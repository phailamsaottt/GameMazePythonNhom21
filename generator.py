"""
algorithms/generator.py - Procedural Maze Generation Engine.

Features:
- Deterministic seeded RNG (isolated random.Random instance; no global state mutation).
- Multi-algorithm generation: Randomized DFS (Recursive Backtracker), Prim's, and Kruskal's.
- Autonomous parameter randomization (dynamic algorithm, seed, braiding factor).
- Mathematical connectivity guarantee via BFS flood-fill and topological auto-repair.
- Interactive step-by-step generator for real-time visualization.
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random
from typing import Any, Final, Generator

# Grid cell state constants
WALL: Final[int] = 1
PATH: Final[int] = 0

# Cardinal offsets for 4-directional grid traversal
CARDINAL_OFFSETS: Final[tuple[tuple[int, int], ...]] = (
    (-1, 0),
    (1, 0),
    (0, -1),
    (0, 1),
)


class GenerationAlgorithm(str, Enum):
    """Supported maze generation strategies."""
    RANDOM = "random"     # Dynamic selection among DFS, Prim's, and Kruskal's
    DFS = "dfs"           # Recursive Backtracker (long, winding corridors)
    PRIMS = "prims"       # Randomized Prim's (branching, many junctions)
    KRUSKAL = "kruskals"   # Randomized Kruskal's (DSU spanning tree)


@dataclass(slots=True)
class Maze:
    """Represents a generated maze, its configuration, and metadata."""
    grid: list[list[int]]
    rows: int
    cols: int
    start: tuple[int, int]
    goal: tuple[int, int]
    seed: int
    algorithm: str
    algorithm_requested: str = "random"
    braid_factor: float = 0.0
    repaired: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_wall(self, r: int, c: int) -> bool:
        """Return True if cell (r, c) is a wall or out of bounds."""
        return not (0 <= r < self.rows and 0 <= c < self.cols) or self.grid[r][c] == WALL

    def is_path(self, r: int, c: int) -> bool:
        """Return True if cell (r, c) is an in-bounds passable path."""
        return 0 <= r < self.rows and 0 <= c < self.cols and self.grid[r][c] == PATH

    def in_bounds(self, r: int, c: int) -> bool:
        """Return True if coordinates (r, c) are within grid boundaries."""
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_neighbors(self, r: int, c: int) -> list[tuple[int, int]]:
        """Return passable 4-directional adjacent neighbors."""
        neighbors: list[tuple[int, int]] = []
        for dr, dc in CARDINAL_OFFSETS:
            nr, nc = r + dr, c + dc
            if 0 <= nr < self.rows and 0 <= nc < self.cols and self.grid[nr][nc] == PATH:
                neighbors.append((nr, nc))
        return neighbors

    def count_paths(self) -> int:
        """Count total passable path cells in the grid."""
        return sum(row.count(PATH) for row in self.grid)

    def count_dead_ends(self) -> int:
        """Count non-terminal path cells with only 1 passable neighbor."""
        count = 0
        grid = self.grid
        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if grid[r][c] == PATH and (r, c) != self.start and (r, c) != self.goal:
                    passable = sum(1 for dr, dc in CARDINAL_OFFSETS if grid[r + dr][c + dc] == PATH)
                    if passable == 1:
                        count += 1
        return count

    def __getitem__(self, index: int) -> list[int]:
        return self.grid[index]

    def __len__(self) -> int:
        return self.rows


@dataclass(slots=True)
class GenerationStep:
    """State yielded during animated maze generation."""
    grid: list[list[int]]
    current: tuple[int, int] | None
    carved: tuple[int, int]
    algorithm: str = "dfs"
    frontier: list[tuple[int, int]] = field(default_factory=list)
    is_done: bool = False


def _normalize_seed(seed: int | str | None) -> int:
    """
    Convert seed input into a deterministic 64-bit integer.
    If None or 'random', generates a cryptographically strong random seed.
    """
    if seed is None or str(seed).lower() == "random":
        return random.SystemRandom().randint(1, (1 << 63) - 1)
    if isinstance(seed, int):
        return seed
    hash_bytes = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:8], byteorder="big")


class DisjointSetUnion:
    """Disjoint Set Union (Union-Find) with path compression and rank optimization."""
    __slots__ = ("parent", "rank")

    def __init__(self, items: list[tuple[int, int]]) -> None:
        self.parent: dict[tuple[int, int], tuple[int, int]] = {item: item for item in items}
        self.rank: dict[tuple[int, int], int] = {item: 0 for item in items}

    def find(self, item: tuple[int, int]) -> tuple[int, int]:
        root = item
        parent = self.parent
        while parent[root] != root:
            root = parent[root]
        # Iterative two-pass path compression (avoids recursion limit)
        curr = item
        while curr != root:
            nxt = parent[curr]
            parent[curr] = root
            curr = nxt
        return root

    def union(self, a: tuple[int, int], b: tuple[int, int]) -> bool:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return False

        rank_a, rank_b = self.rank[root_a], self.rank[root_b]
        if rank_a < rank_b:
            self.parent[root_a] = root_b
        elif rank_a > rank_b:
            self.parent[root_b] = root_a
        else:
            self.parent[root_b] = root_a
            self.rank[root_a] += 1
        return True


class MazeGenerator:
    """
    Procedural maze generator supporting seed determinism and animation pipelines.
    """

    AVAILABLE_ALGORITHMS: Final[tuple[GenerationAlgorithm, ...]] = (
        GenerationAlgorithm.DFS,
        GenerationAlgorithm.PRIMS,
        GenerationAlgorithm.KRUSKAL,
    )

    def __init__(self, seed: int | str | None = None) -> None:
        self.numeric_seed = _normalize_seed(seed)
        self.rng = random.Random(self.numeric_seed)

    def generate(
        self,
        rows: int = 21,
        cols: int = 21,
        algorithm: str | GenerationAlgorithm = GenerationAlgorithm.RANDOM,
        braid_factor: float | str | None = "random",
        start: tuple[int, int] | None = None,
        goal: tuple[int, int] | None = None,
    ) -> Maze:
        """
        Generate a maze grid with full configuration and topological validation.
        """
        # Enforce minimum odd grid dimensions
        rows = max(5, int(rows) if int(rows) % 2 != 0 else int(rows) + 1)
        cols = max(5, int(cols) if int(cols) % 2 != 0 else int(cols) + 1)

        start = start if start and 0 <= start[0] < rows and 0 <= start[1] < cols else (1, 1)
        goal = goal if goal and 0 <= goal[0] < rows and 0 <= goal[1] < cols else (rows - 2, cols - 2)

        # 1. Resolve Algorithm
        algo_req = str(algorithm).lower()
        if algo_req in ("random", GenerationAlgorithm.RANDOM.value, "auto"):
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)
        elif algo_req in ("dfs", "backtracker", GenerationAlgorithm.DFS.value):
            active_algo = GenerationAlgorithm.DFS
        elif algo_req in ("prims", "prim", GenerationAlgorithm.PRIMS.value):
            active_algo = GenerationAlgorithm.PRIMS
        elif algo_req in ("kruskals", "kruskal", GenerationAlgorithm.KRUSKAL.value):
            active_algo = GenerationAlgorithm.KRUSKAL
        else:
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)

        # 2. Resolve Braid Factor
        if braid_factor is None or str(braid_factor).lower() == "random":
            active_braid = 0.0 if self.rng.random() < 0.4 else round(self.rng.uniform(0.10, 0.45), 2)
        else:
            try:
                active_braid = max(0.0, min(1.0, float(braid_factor)))
            except (ValueError, TypeError):
                active_braid = 0.0

        # 3. Generate Grid Matrix
        if active_algo == GenerationAlgorithm.DFS:
            grid = self._generate_dfs(rows, cols, start)
        elif active_algo == GenerationAlgorithm.PRIMS:
            grid = self._generate_prims(rows, cols, start)
        else:
            grid = self._generate_kruskals(rows, cols)

        grid[start[0]][start[1]] = PATH
        grid[goal[0]][goal[1]] = PATH

        # 4. Braiding (cycle injection / dead-end reduction)
        dead_ends_braided = self._apply_braid(grid, rows, cols, active_braid) if active_braid > 0.0 else 0

        # 5. Guarantee Connectivity via Auto-Repair
        repaired = self._ensure_connectivity(grid, rows, cols, start, goal)

        metadata: dict[str, Any] = {
            "algorithm_used": active_algo.value,
            "algorithm_requested": algo_req,
            "seed": self.numeric_seed,
            "braid_factor": active_braid,
            "auto_repaired": repaired,
            "dimensions": (rows, cols),
            "dead_ends_braided": dead_ends_braided,
        }

        maze = Maze(
            grid=grid,
            rows=rows,
            cols=cols,
            start=start,
            goal=goal,
            seed=self.numeric_seed,
            algorithm=active_algo.value,
            algorithm_requested=algo_req,
            braid_factor=active_braid,
            repaired=repaired,
            metadata=metadata,
        )
        metadata["path_cells"] = maze.count_paths()
        metadata["dead_ends_remaining"] = maze.count_dead_ends()
        return maze

    def generate_steps(
        self,
        rows: int = 21,
        cols: int = 21,
        algorithm: str | GenerationAlgorithm = GenerationAlgorithm.RANDOM,
        start: tuple[int, int] | None = None,
        goal: tuple[int, int] | None = None,
    ) -> Generator[GenerationStep, None, Maze]:
        """
        Yield step-by-step grid states for animated visualizers.
        """
        rows = max(5, int(rows) if int(rows) % 2 != 0 else int(rows) + 1)
        cols = max(5, int(cols) if int(cols) % 2 != 0 else int(cols) + 1)
        start = start or (1, 1)
        goal = goal or (rows - 2, cols - 2)

        algo_req = str(algorithm).lower()
        if algo_req in ("random", GenerationAlgorithm.RANDOM.value, "auto"):
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)
        elif algo_req in ("prims", "prim", GenerationAlgorithm.PRIMS.value):
            active_algo = GenerationAlgorithm.PRIMS
        elif algo_req in ("kruskals", "kruskal", GenerationAlgorithm.KRUSKAL.value):
            active_algo = GenerationAlgorithm.KRUSKAL
        else:
            active_algo = GenerationAlgorithm.DFS

        grid = [[WALL] * cols for _ in range(rows)]

        if active_algo == GenerationAlgorithm.PRIMS:
            step_gen = self._generate_prims_steps(grid, rows, cols, start)
        elif active_algo == GenerationAlgorithm.KRUSKAL:
            step_gen = self._generate_kruskals_steps(grid, rows, cols)
        else:
            step_gen = self._generate_dfs_steps(grid, rows, cols, start)

        yield from step_gen

        grid[start[0]][start[1]] = PATH
        grid[goal[0]][goal[1]] = PATH
        repaired = self._ensure_connectivity(grid, rows, cols, start, goal)

        final_maze = Maze(
            grid=grid,
            rows=rows,
            cols=cols,
            start=start,
            goal=goal,
            seed=self.numeric_seed,
            algorithm=active_algo.value,
            algorithm_requested=algo_req,
            repaired=repaired,
            metadata={"animated": True, "algorithm_used": active_algo.value},
        )
        yield GenerationStep(
            grid=grid,
            current=goal,
            carved=goal,
            algorithm=active_algo.value,
            is_done=True,
        )
        return final_maze

    # -------------------------------------------------------------------------
    # Algorithm 1: Recursive Backtracker (Randomized DFS)
    # -------------------------------------------------------------------------
    def _generate_dfs(self, rows: int, cols: int, start: tuple[int, int]) -> list[list[int]]:
        grid = [[WALL] * cols for _ in range(rows)]
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1

        stack: list[tuple[int, int]] = [(sr, sc)]
        grid[sr][sc] = PATH
        directions: Final[tuple[tuple[int, int], ...]] = ((-2, 0), (2, 0), (0, -2), (0, 2))

        while stack:
            r, c = stack[-1]
            unvisited: list[tuple[int, int, int, int]] = []
            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                    unvisited.append((dr, dc, nr, nc))

            if unvisited:
                dr, dc, nr, nc = self.rng.choice(unvisited)
                grid[r + dr // 2][c + dc // 2] = PATH
                grid[nr][nc] = PATH
                stack.append((nr, nc))
            else:
                stack.pop()

        return grid

    def _generate_dfs_steps(
        self, grid: list[list[int]], rows: int, cols: int, start: tuple[int, int]
    ) -> Generator[GenerationStep, None, None]:
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1
        stack: list[tuple[int, int]] = [(sr, sc)]
        grid[sr][sc] = PATH
        directions: Final[tuple[tuple[int, int], ...]] = ((-2, 0), (2, 0), (0, -2), (0, 2))

        yield GenerationStep(grid=grid, current=(sr, sc), carved=(sr, sc), algorithm="dfs")

        while stack:
            r, c = stack[-1]
            unvisited: list[tuple[int, int, int, int]] = []
            for dr, dc in directions:
                nr, nc = r + dr, c + dc
                if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                    unvisited.append((dr, dc, nr, nc))

            if unvisited:
                dr, dc, nr, nc = self.rng.choice(unvisited)
                carved_wall = (r + dr // 2, c + dc // 2)
                grid[carved_wall[0]][carved_wall[1]] = PATH
                grid[nr][nc] = PATH
                stack.append((nr, nc))
                yield GenerationStep(
                    grid=grid,
                    current=(nr, nc),
                    carved=carved_wall,
                    algorithm="dfs",
                    frontier=[(u[2], u[3]) for u in unvisited],
                )
            else:
                stack.pop()

    # -------------------------------------------------------------------------
    # Algorithm 2: Randomized Prim's Algorithm (O(1) swap-and-pop)
    # -------------------------------------------------------------------------
    def _generate_prims(self, rows: int, cols: int, start: tuple[int, int]) -> list[list[int]]:
        grid = [[WALL] * cols for _ in range(rows)]
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1

        grid[sr][sc] = PATH
        # Wall record: (wall_r, wall_c, target_r, target_c)
        walls: list[tuple[int, int, int, int]] = []
        for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            nr, nc = sr + dr, sc + dc
            if 1 <= nr < rows - 1 and 1 <= nc < cols - 1:
                walls.append((sr + dr // 2, sc + dc // 2, nr, nc))

        while walls:
            # O(1) random item removal via swap-with-tail
            idx = self.rng.randrange(len(walls))
            last_idx = len(walls) - 1
            walls[idx], walls[last_idx] = walls[last_idx], walls[idx]
            wr, wc, tr, tc = walls.pop()

            if grid[tr][tc] == WALL:
                grid[wr][wc] = PATH
                grid[tr][tc] = PATH

                for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    nr, nc = tr + dr, tc + dc
                    if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                        walls.append((tr + dr // 2, tc + dc // 2, nr, nc))

        return grid

    def _generate_prims_steps(
        self, grid: list[list[int]], rows: int, cols: int, start: tuple[int, int]
    ) -> Generator[GenerationStep, None, None]:
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1
        grid[sr][sc] = PATH
        walls: list[tuple[int, int, int, int]] = []
        for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2)):
            nr, nc = sr + dr, sc + dc
            if 1 <= nr < rows - 1 and 1 <= nc < cols - 1:
                walls.append((sr + dr // 2, sc + dc // 2, nr, nc))

        yield GenerationStep(grid=grid, current=(sr, sc), carved=(sr, sc), algorithm="prims")

        while walls:
            idx = self.rng.randrange(len(walls))
            last_idx = len(walls) - 1
            walls[idx], walls[last_idx] = walls[last_idx], walls[idx]
            wr, wc, tr, tc = walls.pop()

            if grid[tr][tc] == WALL:
                grid[wr][wc] = PATH
                grid[tr][tc] = PATH

                for dr, dc in ((-2, 0), (2, 0), (0, -2), (0, 2)):
                    nr, nc = tr + dr, tc + dc
                    if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                        walls.append((tr + dr // 2, tc + dc // 2, nr, nc))

                yield GenerationStep(
                    grid=grid,
                    current=(tr, tc),
                    carved=(wr, wc),
                    algorithm="prims",
                    frontier=[(w[2], w[3]) for w in walls[:25]],
                )

    # -------------------------------------------------------------------------
    # Algorithm 3: Randomized Kruskal's Algorithm (DSU)
    # -------------------------------------------------------------------------
    def _generate_kruskals(self, rows: int, cols: int) -> list[list[int]]:
        grid = [[WALL] * cols for _ in range(rows)]
        cells: list[tuple[int, int]] = []
        edges: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = []

        for r in range(1, rows - 1, 2):
            for c in range(1, cols - 1, 2):
                cell = (r, c)
                cells.append(cell)
                grid[r][c] = PATH
                if c + 2 < cols - 1:
                    edges.append((cell, (r, c + 2), (r, c + 1)))
                if r + 2 < rows - 1:
                    edges.append((cell, (r + 2, c), (r + 1, c)))

        dsu = DisjointSetUnion(cells)
        self.rng.shuffle(edges)

        for cell_a, cell_b, wall in edges:
            if dsu.union(cell_a, cell_b):
                grid[wall[0]][wall[1]] = PATH

        return grid

    def _generate_kruskals_steps(
        self, grid: list[list[int]], rows: int, cols: int
    ) -> Generator[GenerationStep, None, None]:
        cells: list[tuple[int, int]] = []
        edges: list[tuple[tuple[int, int], tuple[int, int], tuple[int, int]]] = []

        for r in range(1, rows - 1, 2):
            for c in range(1, cols - 1, 2):
                cell = (r, c)
                cells.append(cell)
                grid[r][c] = PATH
                if c + 2 < cols - 1:
                    edges.append((cell, (r, c + 2), (r, c + 1)))
                if r + 2 < rows - 1:
                    edges.append((cell, (r + 2, c), (r + 1, c)))

        dsu = DisjointSetUnion(cells)
        self.rng.shuffle(edges)

        yield GenerationStep(grid=grid, current=cells[0], carved=cells[0], algorithm="kruskals")

        for cell_a, cell_b, wall in edges:
            if dsu.union(cell_a, cell_b):
                grid[wall[0]][wall[1]] = PATH
                yield GenerationStep(
                    grid=grid,
                    current=cell_b,
                    carved=wall,
                    algorithm="kruskals",
                )

    # -------------------------------------------------------------------------
    # Braiding & Loop Creation
    # -------------------------------------------------------------------------
    def _apply_braid(
        self, grid: list[list[int]], rows: int, cols: int, factor: float
    ) -> int:
        """
        Carve open a controlled percentage of dead ends to introduce cycles.
        """
        dead_ends: list[tuple[int, int]] = []
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                if grid[r][c] == PATH:
                    walls = sum(1 for dr, dc in CARDINAL_OFFSETS if grid[r + dr][c + dc] == WALL)
                    if walls == 3:
                        dead_ends.append((r, c))

        self.rng.shuffle(dead_ends)
        carve_target = int(len(dead_ends) * max(0.0, min(1.0, factor)))
        carved_actual = 0

        for r, c in dead_ends[:carve_target]:
            # Connect to a passage 2 units away across a dividing wall
            candidates: list[tuple[int, int]] = []
            for dr, dc in CARDINAL_OFFSETS:
                wr, wc = r + dr, c + dc
                or_, oc = r + 2 * dr, c + 2 * dc
                if 1 <= or_ < rows - 1 and 1 <= oc < cols - 1 and grid[or_][oc] == PATH:
                    candidates.append((wr, wc))
            if candidates:
                wr, wc = self.rng.choice(candidates)
                if grid[wr][wc] == WALL:
                    grid[wr][wc] = PATH
                    carved_actual += 1

        return carved_actual

    # -------------------------------------------------------------------------
    # Auto-Repair & Topological Connectivity Guarantee
    # -------------------------------------------------------------------------
    def _ensure_connectivity(
        self,
        grid: list[list[int]],
        rows: int,
        cols: int,
        start: tuple[int, int],
        goal: tuple[int, int],
    ) -> bool:
        """
        Validates reachability of goal from start using an O(V + E) BFS queue.
        If blocked, carves a Manhattan corridor to the goal from the closest reached tile.
        """
        queue: deque[tuple[int, int]] = deque([start])
        visited: set[tuple[int, int]] = {start}
        reached = False

        while queue:
            curr = queue.popleft()
            if curr == goal:
                reached = True
                break

            r, c = curr
            for dr, dc in CARDINAL_OFFSETS:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == PATH:
                    if (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

        if reached:
            return False

        # Fallback if start was completely walled off or isolated
        source = min(
            visited,
            key=lambda t: abs(t[0] - goal[0]) + abs(t[1] - goal[1]),
            default=start,
        )
        cr, cc = source
        gr, gc = goal

        # Carve row corridor then column corridor, keeping inner bounds
        step_r = 1 if gr >= cr else -1
        for r in range(cr, gr + step_r, step_r):
            grid[r][cc] = PATH

        step_c = 1 if gc >= cc else -1
        for c in range(cc, gc + step_c, step_c):
            grid[gr][c] = PATH

        return True


def generate_maze(
    rows: int = 21,
    cols: int = 21,
    seed: int | str | None = None,
    algorithm: str | GenerationAlgorithm = GenerationAlgorithm.RANDOM,
    braid_factor: float | str | None = "random",
    start: tuple[int, int] | None = None,
    goal: tuple[int, int] | None = None,
) -> Maze:
    """Generate a maze with custom parameters or total randomness."""
    generator = MazeGenerator(seed=seed)
    return generator.generate(
        rows=rows,
        cols=cols,
        algorithm=algorithm,
        braid_factor=braid_factor,
        start=start,
        goal=goal,
    )


def generate_random_maze(
    rows: int = 21,
    cols: int = 21,
    start: tuple[int, int] | None = None,
    goal: tuple[int, int] | None = None,
) -> Maze:
    """Helper for 100% randomized maze generation with connectivity guarantee."""
    return generate_maze(
        rows=rows,
        cols=cols,
        seed=None,
        algorithm=GenerationAlgorithm.RANDOM,
        braid_factor="random",
        start=start,
        goal=goal,
    )
