"""
algorithms/generator.py
Procedural Maze Generation Module.

Follows the 'procedural-gen' skill principles:
- Deterministic seeded RNG (dedicated random.Random instance, never uses global random)
- Multi-algorithm randomness: DFS (Recursive Backtracker), Prim's, and Kruskal's
- Fully random mode: randomly picks algorithm, seed, braiding factor, and runs auto-repair
- Mathematical connectivity guarantee with BFS validation and auto-repair
- Step-by-step animation generators for ALL algorithms (DFS, Prim's, Kruskal's)
- Decoupled data model with rich metadata
"""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
import hashlib
import random
from typing import Any, Dict, Generator, List, Optional, Set, Tuple

# Constants for grid cell states
WALL: int = 1
PATH: int = 0


class GenerationAlgorithm(str, Enum):
    """Available maze generation algorithms."""
    RANDOM = "random"          # Fully random pick among DFS, Prim's, and Kruskal's
    DFS = "dfs"                # Recursive Backtracker (long, winding corridors)
    PRIMS = "prims"            # Randomized Prim's (branching, many junctions)
    KRUSKAL = "kruskals"        # Randomized Kruskal's (DSU spanning tree)


@dataclass
class Maze:
    """Represents a generated maze, its configuration, and metadata."""
    grid: List[List[int]]
    rows: int
    cols: int
    start: Tuple[int, int]
    goal: Tuple[int, int]
    seed: int
    algorithm: str
    algorithm_requested: str = "random"
    braid_factor: float = 0.0
    repaired: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)

    def is_wall(self, r: int, c: int) -> bool:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.grid[r][c] == WALL
        return True

    def is_path(self, r: int, c: int) -> bool:
        if 0 <= r < self.rows and 0 <= c < self.cols:
            return self.grid[r][c] == PATH
        return False

    def in_bounds(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def get_neighbors(self, r: int, c: int) -> List[Tuple[int, int]]:
        """Return passable 4-directional adjacent neighbors."""
        neighbors = []
        for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
            nr, nc = r + dr, c + dc
            if self.is_path(nr, nc):
                neighbors.append((nr, nc))
        return neighbors

    def count_paths(self) -> int:
        """Count total passable path cells."""
        return sum(row.count(PATH) for row in self.grid)

    def count_dead_ends(self) -> int:
        """Count cells that have only 1 passable neighbor (cul-de-sac)."""
        count = 0
        for r in range(1, self.rows - 1):
            for c in range(1, self.cols - 1):
                if self.grid[r][c] == PATH and (r, c) != self.start and (r, c) != self.goal:
                    if len(self.get_neighbors(r, c)) == 1:
                        count += 1
        return count

    def __getitem__(self, index: int) -> List[int]:
        return self.grid[index]

    def __len__(self) -> int:
        return self.rows


@dataclass
class GenerationStep:
    """Data yielded during animated maze generation."""
    grid: List[List[int]]
    current: Optional[Tuple[int, int]]
    carved: Tuple[int, int]
    algorithm: str = "dfs"
    frontier: List[Tuple[int, int]] = field(default_factory=list)
    is_done: bool = False


def _normalize_seed(seed: Optional[int | str]) -> int:
    """
    Convert any seed input (int, str, or None/'random') into a deterministic 64-bit integer.
    If None or 'random', generates a cryptographically random seed.
    """
    if seed is None or str(seed).lower() == "random":
        return random.SystemRandom().randint(1, 2**63 - 1)
    if isinstance(seed, int):
        return seed
    # If string, use SHA-256 for deterministic hash across runs and platforms
    hash_bytes = hashlib.sha256(str(seed).encode("utf-8")).digest()
    return int.from_bytes(hash_bytes[:8], byteorder="big")


class DisjointSetUnion:
    """Disjoint Set Union (DSU) / Union-Find with path compression and rank optimization."""

    def __init__(self, items: List[Tuple[int, int]]):
        self.parent = {item: item for item in items}
        self.rank = {item: 0 for item in items}

    def find(self, item: Tuple[int, int]) -> Tuple[int, int]:
        if self.parent[item] != item:
            self.parent[item] = self.find(self.parent[item])
        return self.parent[item]

    def union(self, a: Tuple[int, int], b: Tuple[int, int]) -> bool:
        root_a = self.find(a)
        root_b = self.find(b)
        if root_a == root_b:
            return False

        if self.rank[root_a] < self.rank[root_b]:
            self.parent[root_a] = root_b
        elif self.rank[root_a] > self.rank[root_b]:
            self.parent[root_b] = root_a
        else:
            self.parent[root_b] = root_a
            self.rank[root_a] += 1
        return True


class MazeGenerator:
    """
    Core procedural maze generator supporting fully randomized and seed-controlled pipelines.
    Follows 'procedural-gen' principles:
    - Dedicated RNG instance (no global random pollution)
    - Full reproducibility from seed
    - Dynamic algorithm selection
    - Automatic validation and topological repair
    """

    AVAILABLE_ALGORITHMS = [
        GenerationAlgorithm.DFS,
        GenerationAlgorithm.PRIMS,
        GenerationAlgorithm.KRUSKAL,
    ]

    def __init__(self, seed: Optional[int | str] = None):
        self.numeric_seed = _normalize_seed(seed)
        self.rng = random.Random(self.numeric_seed)

    def generate(
        self,
        rows: int = 21,
        cols: int = 21,
        algorithm: str | GenerationAlgorithm = GenerationAlgorithm.RANDOM,
        braid_factor: Optional[float | str] = "random",
        start: Optional[Tuple[int, int]] = None,
        goal: Optional[Tuple[int, int]] = None,
    ) -> Maze:
        """
        Generate a maze grid with full randomization support.
        
        Args:
            rows: Total grid rows (odd number >= 5 recommended).
            cols: Total grid cols (odd number >= 5 recommended).
            algorithm: 'random', 'dfs', 'prims', or 'kruskals'.
            braid_factor: 'random' or float 0.0 (pure tree) to 1.0 (no dead ends).
            start: Optional start position, defaults to (1, 1).
            goal: Optional goal position, defaults to (rows - 2, cols - 2).

        Returns:
            A populated Maze object with full audit trail and metadata.
        """
        # Ensure minimum odd dimensions
        rows = max(5, rows if rows % 2 != 0 else rows + 1)
        cols = max(5, cols if cols % 2 != 0 else cols + 1)

        start = start or (1, 1)
        goal = goal or (rows - 2, cols - 2)

        # 1. Resolve Algorithm (random or explicit)
        algo_req = str(algorithm).lower()
        if algo_req in ("random", GenerationAlgorithm.RANDOM, "auto"):
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)
        elif algo_req in ("dfs", "backtracker", GenerationAlgorithm.DFS):
            active_algo = GenerationAlgorithm.DFS
        elif algo_req in ("prims", "prim", GenerationAlgorithm.PRIMS):
            active_algo = GenerationAlgorithm.PRIMS
        elif algo_req in ("kruskals", "kruskal", GenerationAlgorithm.KRUSKAL):
            active_algo = GenerationAlgorithm.KRUSKAL
        else:
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)

        # 2. Resolve Braid Factor (random or explicit)
        if braid_factor is None or str(braid_factor).lower() == "random":
            # Weighted distribution: 40% chance pure tree (0.0), 60% chance varied loops (0.1 to 0.45)
            if self.rng.random() < 0.4:
                active_braid = 0.0
            else:
                active_braid = round(self.rng.uniform(0.10, 0.45), 2)
        else:
            active_braid = max(0.0, min(1.0, float(braid_factor)))

        # 3. Generate raw maze using the selected algorithm
        if active_algo == GenerationAlgorithm.DFS:
            grid = self._generate_dfs(rows, cols, start)
        elif active_algo == GenerationAlgorithm.PRIMS:
            grid = self._generate_prims(rows, cols, start)
        else:
            grid = self._generate_kruskals(rows, cols)

        # Ensure start and goal cells are open
        grid[start[0]][start[1]] = PATH
        grid[goal[0]][goal[1]] = PATH

        # 4. Apply Braiding (introducing cycles / removing dead ends)
        dead_ends_before = 0
        if active_braid > 0.0:
            dead_ends_before = self._apply_braid(grid, rows, cols, active_braid)

        # 5. Auto-Repair & Connectivity Verification
        repaired = self._ensure_connectivity(grid, rows, cols, start, goal)

        # Construct metadata bundle
        metadata = {
            "algorithm_used": active_algo.value,
            "algorithm_requested": algo_req,
            "seed": self.numeric_seed,
            "braid_factor": active_braid,
            "auto_repaired": repaired,
            "dimensions": (rows, cols),
            "dead_ends_braided": dead_ends_before,
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
        start: Optional[Tuple[int, int]] = None,
        goal: Optional[Tuple[int, int]] = None,
    ) -> Generator[GenerationStep, None, Maze]:
        """
        Yield step-by-step grid states for animated maze generation visualizers.
        Supports DFS, Prim's, and Kruskal's animations, randomly or explicitly.
        """
        rows = max(5, rows if rows % 2 != 0 else rows + 1)
        cols = max(5, cols if cols % 2 != 0 else cols + 1)
        start = start or (1, 1)
        goal = goal or (rows - 2, cols - 2)

        algo_req = str(algorithm).lower()
        if algo_req in ("random", GenerationAlgorithm.RANDOM, "auto"):
            active_algo = self.rng.choice(self.AVAILABLE_ALGORITHMS)
        elif algo_req in ("prims", "prim", GenerationAlgorithm.PRIMS):
            active_algo = GenerationAlgorithm.PRIMS
        elif algo_req in ("kruskals", "kruskal", GenerationAlgorithm.KRUSKAL):
            active_algo = GenerationAlgorithm.KRUSKAL
        else:
            active_algo = GenerationAlgorithm.DFS

        grid = [[WALL for _ in range(cols)] for _ in range(rows)]

        if active_algo == GenerationAlgorithm.PRIMS:
            step_gen = self._generate_prims_steps(grid, rows, cols, start)
        elif active_algo == GenerationAlgorithm.KRUSKAL:
            step_gen = self._generate_kruskals_steps(grid, rows, cols)
        else:
            step_gen = self._generate_dfs_steps(grid, rows, cols, start)

        for step in step_gen:
            yield step

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
    def _generate_dfs(self, rows: int, cols: int, start: Tuple[int, int]) -> List[List[int]]:
        grid = [[WALL for _ in range(cols)] for _ in range(rows)]
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1

        stack = [(sr, sc)]
        grid[sr][sc] = PATH
        directions = [(-2, 0), (2, 0), (0, -2), (0, 2)]

        while stack:
            r, c = stack[-1]
            unvisited = []
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
        self, grid: List[List[int]], rows: int, cols: int, start: Tuple[int, int]
    ) -> Generator[GenerationStep, None, None]:
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1
        stack = [(sr, sc)]
        grid[sr][sc] = PATH
        directions = [(-2, 0), (2, 0), (0, -2), (0, 2)]

        yield GenerationStep(grid=grid, current=(sr, sc), carved=(sr, sc), algorithm="dfs")

        while stack:
            r, c = stack[-1]
            unvisited = []
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
    # Algorithm 2: Randomized Prim's Algorithm
    # -------------------------------------------------------------------------
    def _generate_prims(self, rows: int, cols: int, start: Tuple[int, int]) -> List[List[int]]:
        grid = [[WALL for _ in range(cols)] for _ in range(rows)]
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1

        grid[sr][sc] = PATH
        walls = []
        for dr, dc in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            nr, nc = sr + dr, sc + dc
            if 1 <= nr < rows - 1 and 1 <= nc < cols - 1:
                walls.append((sr + dr // 2, sc + dc // 2, sr, sc, nr, nc))

        while walls:
            idx = self.rng.randrange(len(walls))
            wr, wc, _, _, tr, tc = walls.pop(idx)

            if grid[tr][tc] == WALL:
                grid[wr][wc] = PATH
                grid[tr][tc] = PATH

                for dr, dc in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                    nr, nc = tr + dr, tc + dc
                    if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                        walls.append((tr + dr // 2, tc + dc // 2, tr, tc, nr, nc))

        return grid

    def _generate_prims_steps(
        self, grid: List[List[int]], rows: int, cols: int, start: Tuple[int, int]
    ) -> Generator[GenerationStep, None, None]:
        sr = start[0] if start[0] % 2 != 0 else start[0] + 1
        sc = start[1] if start[1] % 2 != 0 else start[1] + 1
        grid[sr][sc] = PATH
        walls = []
        for dr, dc in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
            nr, nc = sr + dr, sc + dc
            if 1 <= nr < rows - 1 and 1 <= nc < cols - 1:
                walls.append((sr + dr // 2, sc + dc // 2, sr, sc, nr, nc))

        yield GenerationStep(grid=grid, current=(sr, sc), carved=(sr, sc), algorithm="prims")

        while walls:
            idx = self.rng.randrange(len(walls))
            wr, wc, _, _, tr, tc = walls.pop(idx)

            if grid[tr][tc] == WALL:
                grid[wr][wc] = PATH
                grid[tr][tc] = PATH

                for dr, dc in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                    nr, nc = tr + dr, tc + dc
                    if 1 <= nr < rows - 1 and 1 <= nc < cols - 1 and grid[nr][nc] == WALL:
                        walls.append((tr + dr // 2, tc + dc // 2, tr, tc, nr, nc))

                yield GenerationStep(
                    grid=grid,
                    current=(tr, tc),
                    carved=(wr, wc),
                    algorithm="prims",
                    frontier=[(w[4], w[5]) for w in walls[:25]],
                )

    # -------------------------------------------------------------------------
    # Algorithm 3: Randomized Kruskal's Algorithm (DSU)
    # -------------------------------------------------------------------------
    def _generate_kruskals(self, rows: int, cols: int) -> List[List[int]]:
        grid = [[WALL for _ in range(cols)] for _ in range(rows)]
        cells = []
        edges = []

        for r in range(1, rows - 1, 2):
            for c in range(1, cols - 1, 2):
                cells.append((r, c))
                grid[r][c] = PATH
                if c + 2 < cols - 1:
                    edges.append(((r, c), (r, c + 2), (r, c + 1)))
                if r + 2 < rows - 1:
                    edges.append(((r, c), (r + 2, c), (r + 1, c)))

        dsu = DisjointSetUnion(cells)
        self.rng.shuffle(edges)

        for cell_a, cell_b, wall in edges:
            if dsu.union(cell_a, cell_b):
                grid[wall[0]][wall[1]] = PATH

        return grid

    def _generate_kruskals_steps(
        self, grid: List[List[int]], rows: int, cols: int
    ) -> Generator[GenerationStep, None, None]:
        cells = []
        edges = []

        for r in range(1, rows - 1, 2):
            for c in range(1, cols - 1, 2):
                cells.append((r, c))
                grid[r][c] = PATH
                if c + 2 < cols - 1:
                    edges.append(((r, c), (r, c + 2), (r, c + 1)))
                if r + 2 < rows - 1:
                    edges.append(((r, c), (r + 2, c), (r + 1, c)))

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
        self, grid: List[List[int]], rows: int, cols: int, factor: float
    ) -> int:
        """
        Remove some dead ends to introduce cycles/loops into the maze.
        Returns the number of dead-ends carved open.
        """
        dead_ends = []
        for r in range(1, rows - 1):
            for c in range(1, cols - 1):
                if grid[r][c] == PATH:
                    wall_count = 0
                    for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                        if grid[r + dr][c + dc] == WALL:
                            wall_count += 1
                    if wall_count == 3:
                        dead_ends.append((r, c))

        self.rng.shuffle(dead_ends)
        carve_count = int(len(dead_ends) * max(0.0, min(1.0, factor)))
        carved_actual = 0

        for r, c in dead_ends[:carve_count]:
            wall_neighbors = []
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                wr, wc = r + dr, c + dc
                or_, oc = r + 2 * dr, c + 2 * dc
                if 1 <= or_ < rows - 1 and 1 <= oc < cols - 1 and grid[or_][oc] == PATH:
                    wall_neighbors.append((wr, wc))
            if wall_neighbors:
                wr, wc = self.rng.choice(wall_neighbors)
                grid[wr][wc] = PATH
                carved_actual += 1

        return carved_actual

    # -------------------------------------------------------------------------
    # Auto-Repair & Topological Connectivity Guarantee
    # -------------------------------------------------------------------------
    def _ensure_connectivity(
        self,
        grid: List[List[int]],
        rows: int,
        cols: int,
        start: Tuple[int, int],
        goal: Tuple[int, int],
    ) -> bool:
        """
        Validates that goal is reachable from start via BFS flood fill.
        If any obstruction prevents reaching the goal, intelligently carves
        a connecting path and returns True (indicating auto-repair occurred).
        """
        queue = [start]
        visited: Set[Tuple[int, int]] = {start}
        reached = False

        while queue:
            curr = queue.pop(0)
            if curr == goal:
                reached = True
                break

            r, c = curr
            for dr, dc in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                nr, nc = r + dr, c + dc
                if 0 <= nr < rows and 0 <= nc < cols and grid[nr][nc] == PATH:
                    if (nr, nc) not in visited:
                        visited.add((nr, nc))
                        queue.append((nr, nc))

        if reached:
            return False  # No repair was needed

        # Topological Auto-Repair: carve path from the closest visited cell to goal
        closest_tile = min(
            visited,
            key=lambda t: abs(t[0] - goal[0]) + abs(t[1] - goal[1])
        )
        cr, cc = closest_tile
        gr, gc = goal

        # Carve row corridor then column corridor
        step_r = 1 if gr >= cr else -1
        for r in range(cr, gr + step_r, step_r):
            grid[r][cc] = PATH

        step_c = 1 if gc >= cc else -1
        for c in range(cc, gc + step_c, step_c):
            grid[gr][c] = PATH

        return True  # Auto-repaired successfully


def generate_maze(
    rows: int = 21,
    cols: int = 21,
    seed: Optional[int | str] = None,
    algorithm: str | GenerationAlgorithm = GenerationAlgorithm.RANDOM,
    braid_factor: Optional[float | str] = "random",
    start: Optional[Tuple[int, int]] = None,
    goal: Optional[Tuple[int, int]] = None,
) -> Maze:
    """
    Generate a maze with total randomness or explicit parameter control.
    Defaults to selecting a random algorithm (DFS, Prim's, Kruskal's),
    random seed, and random braiding factor, with guaranteed auto-repair.
    """
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
    start: Optional[Tuple[int, int]] = None,
    goal: Optional[Tuple[int, int]] = None,
) -> Maze:
    """
    Explicit helper for 100% unpredictable, randomized maze creation.
    Randomizes algorithm, seed, and braiding factor while ensuring connectivity.
    """
    return generate_maze(
        rows=rows,
        cols=cols,
        seed=None,
        algorithm=GenerationAlgorithm.RANDOM,
        braid_factor="random",
        start=start,
        goal=goal,
    )
