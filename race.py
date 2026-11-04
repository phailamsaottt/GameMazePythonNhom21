from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, NamedTuple

import pygame

import config
import database
import records
from generator import PATH, WALL, Maze, generate_maze
from pathfinding import astar, bfs, dfs, solve_astar, solve_bfs, solve_dfs

Color = tuple[int, int, int]
Cell = tuple[int, int]


@dataclass(frozen=True, slots=True)
class SolverSpec:
    name: str
    generator_fn: Callable[..., Any]
    direct_fn: Callable[..., Any]
    color: Color


SOLVERS: tuple[SolverSpec, ...] = (
    SolverSpec("BFS", bfs, solve_bfs, config.COLOR_BFS_TRACE),
    SolverSpec("DFS", dfs, solve_dfs, config.COLOR_DFS_TRACE),
    SolverSpec("A*", astar, solve_astar, config.COLOR_ASTAR_TRACE),
)


class Fonts(NamedTuple):
    small: pygame.font.Font
    medium: pygame.font.Font
    large: pygame.font.Font


@lru_cache(maxsize=None)
def _load_font(size: int) -> pygame.font.Font:
    roboto_path = Path(config.FONT_ROBOTO_PATH)
    if roboto_path.is_file():
        try:
            return pygame.font.Font(str(roboto_path), size)
        except (pygame.error, OSError):
            pass
    return pygame.font.SysFont("Roboto,Arial,Segoe UI,sans-serif", size)


def mix(a: Color, b: Color, t: float) -> Color:
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def compute_cell_size(rows: int, cols: int, max_w: int, max_h: int) -> int:
    return max(2, min(max_w // cols, max_h // rows))


def draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Color,
    pos: tuple[int, int],
    anchor: str = "topleft",
) -> pygame.Rect:
    img = font.render(text, True, color)
    rect = img.get_rect(**{anchor: pos})
    surface.blit(img, rect)
    return rect


class SolverPanel:
    PAD = 10
    TITLE_H = 34
    STATS_H = 112

    def __init__(self, spec: SolverSpec, maze: Maze, rect: pygame.Rect, cell: int, fonts: Fonts) -> None:
        self.spec = spec
        self.maze = maze
        self.rect = rect
        self.cell = cell
        self.fonts = fonts

        grid_w = maze.cols * cell
        self.origin = (rect.x + (rect.w - grid_w) // 2, rect.y + self.TITLE_H + self.PAD)
        self.visited_color = mix(config.COLOR_PATH, spec.color, 0.40)
        self.frontier_color = mix(config.COLOR_PATH, spec.color, 0.75)
        self.base = self._render_base()
        self.reset()

    def reset(self) -> None:
        m = self.maze
        self.generator = self.spec.generator_fn(m.grid, m.start, m.goal)
        self.trace = pygame.Surface((m.cols * self.cell, m.rows * self.cell), pygame.SRCALPHA)
        self.last_step: Any = None
        self.steps = 0
        self.finished = False
        self.found = False
        self.finish_tick = 0
        self.path: list[Cell] | None = None
        self.final_stats: Any = None
        self.rank = 0

    def _render_base(self) -> pygame.Surface:
        m, cell = self.maze, self.cell
        surf = pygame.Surface((m.cols * cell, m.rows * cell))
        surf.fill(config.COLOR_WALL)
        for r in range(m.rows):
            for c in range(m.cols):
                if m.grid[r][c] == PATH:
                    pygame.draw.rect(surf, config.COLOR_PATH, (c * cell, r * cell, cell, cell))
        for pos, color in ((m.start, config.COLOR_START), (m.goal, config.COLOR_END)):
            pygame.draw.rect(surf, color, (pos[1] * cell, pos[0] * cell, cell, cell))
        return surf

    def _paint(self, cell_pos: Cell, color: Color) -> None:
        r, c = cell_pos
        pygame.draw.rect(self.trace, color, (c * self.cell, r * self.cell, self.cell, self.cell))

    def advance(self, tick: int) -> None:
        if self.finished:
            return
        try:
            step = next(self.generator)
        except StopIteration:
            self.finished = True
            self.finish_tick = tick
            return

        self.steps += 1
        self.last_step = step
        special = (self.maze.start, self.maze.goal)
        if step.current not in special:
            self._paint(step.current, self.visited_color)

        if step.is_done:
            self.finished = True
            self.found = bool(step.found)
            self.finish_tick = tick
            self.path = step.path
            if self.path:
                for pos in self.path:
                    if pos not in special:
                        self._paint(pos, self.spec.color)

    def draw(self, screen: pygame.Surface, is_winner: bool) -> None:
        f = self.fonts
        border = config.COLOR_PLAYER if is_winner else self.spec.color
        pygame.draw.rect(screen, config.COLOR_PANEL_BG, self.rect, border_radius=10)
        pygame.draw.rect(screen, border, self.rect, width=3 if is_winner else 2, border_radius=10)

        draw_text(screen, self.spec.name, f.large, self.spec.color,
                  (self.rect.x + 14, self.rect.y + 4))
        if self.finished:
            status = f"Rank {self.rank}" if self.rank else "Finished"
        else:
            status = "Searching..."
        draw_text(screen, status, f.small, config.COLOR_TEXT,
                  (self.rect.right - 14, self.rect.y + 14), anchor="topright")

        screen.blit(self.base, self.origin)
        screen.blit(self.trace, self.origin)

        if not self.finished and self.last_step is not None:
            ox, oy = self.origin
            cell = self.cell
            for r, c in self.last_step.frontier:
                pygame.draw.rect(screen, self.frontier_color, (ox + c * cell, oy + r * cell, cell, cell))
            cr, cc = self.last_step.current
            pygame.draw.rect(screen, config.COLOR_TEXT, (ox + cc * cell, oy + cr * cell, cell, cell))

        self._draw_stats(screen)

    def _draw_stats(self, screen: pygame.Surface) -> None:
        f = self.fonts
        y = self.origin[1] + self.maze.rows * self.cell + 12
        left, right = self.rect.x + 14, self.rect.right - 14

        if self.final_stats is not None:
            nodes = self.final_stats.nodes_explored
            frontier_label = "Max frontier"
            frontier = self.final_stats.max_frontier_size
            time_text = records.format_ms(self.final_stats.elapsed_time_ms)
        else:
            nodes = self.steps
            frontier_label = "Current frontier"
            frontier = len(self.last_step.frontier) if self.last_step is not None else 0
            time_text = "—"
        if self.finished and self.found and self.path:
            path_text = f"{len(self.path)} cells"
        else:
            path_text = "—"

        lines = (
            ("Nodes explored", records.format_int(nodes)),
            (frontier_label, records.format_int(frontier)),
            ("Path length", path_text),
            ("Solve time", time_text),
        )
        for label, value in lines:
            draw_text(screen, label, f.small, config.COLOR_TEXT, (left, y))
            draw_text(screen, value, f.small, self.spec.color, (right, y), anchor="topright")
            y += f.small.get_linesize() + 4


class RaceScreen:
    HEADER_H = 64
    GAP = 12
    SPEED_LEVELS: tuple[int, ...] = (1, 2, 4, 8, 16, 32, 64)

    def __init__(
        self,
        screen: pygame.Surface,
        maze: Maze | None = None,
        rows: int = config.DEFAULT_ROWS,
        cols: int = config.DEFAULT_COLS,
        db_path: str | Path | None = None,
    ) -> None:
        pygame.font.init()
        self.screen = screen
        self.db_path = db_path
        self.fonts = Fonts(
            _load_font(config.FONT_SIZE_SMALL),
            _load_font(config.FONT_SIZE_MEDIUM),
            _load_font(config.FONT_SIZE_LARGE),
        )
        self.maze: Maze = maze or generate_maze(rows=rows, cols=cols)
        self.speed_idx = 2
        self.paused = False
        self.next_state: str | None = None
        self.panels: list[SolverPanel] = []
        self.tick = 0
        self.winner: str | None = None
        self.race_id: str | None = None
        self.results: list[dict[str, Any]] = []
        self._build_panels()

    def _build_panels(self) -> None:
        w, h = self.screen.get_size()
        n = len(SOLVERS)
        gap = self.GAP
        panel_w = (w - gap * (n + 1)) // n
        panel_h = h - self.HEADER_H - gap

        avail_w = panel_w - 2 * SolverPanel.PAD
        avail_h = panel_h - SolverPanel.TITLE_H - SolverPanel.STATS_H - 2 * SolverPanel.PAD
        cell = compute_cell_size(self.maze.rows, self.maze.cols, avail_w, avail_h)

        self.panels = [
            SolverPanel(
                spec,
                self.maze,
                pygame.Rect(gap + i * (panel_w + gap), self.HEADER_H, panel_w, panel_h),
                cell,
                self.fonts,
            )
            for i, spec in enumerate(SOLVERS)
        ]
        self.tick = 0
        self.winner = None
        self.race_id = None
        self.results = []
        self.paused = False

    def restart(self) -> None:
        for p in self.panels:
            p.reset()
        self.tick = 0
        self.winner = None
        self.race_id = None
        self.results = []
        self.paused = False

    def new_maze(self) -> None:
        self.maze = generate_maze(rows=self.maze.rows, cols=self.maze.cols)
        self._build_panels()

    @property
    def speed(self) -> int:
        return self.SPEED_LEVELS[self.speed_idx]

    @property
    def finished(self) -> bool:
        return all(p.finished for p in self.panels)

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type != pygame.KEYDOWN:
            return None
        key = event.key
        if key == pygame.K_ESCAPE:
            self.next_state = config.STATE_MENU
        elif key in (pygame.K_RETURN, pygame.K_KP_ENTER) and self.finished:
            self.next_state = config.STATE_RESULT
        elif key == pygame.K_SPACE and not self.finished:
            self.paused = not self.paused
        elif key in (pygame.K_UP, pygame.K_RIGHT):
            self.speed_idx = min(self.speed_idx + 1, len(self.SPEED_LEVELS) - 1)
        elif key in (pygame.K_DOWN, pygame.K_LEFT):
            self.speed_idx = max(self.speed_idx - 1, 0)
        elif key == pygame.K_r:
            self.restart()
        elif key == pygame.K_n:
            self.new_maze()
        return self.next_state

    def update(self) -> None:
        if self.paused or self.finished:
            return
        for _ in range(self.speed):
            self.tick += 1
            for panel in self.panels:
                if not panel.finished:
                    panel.advance(self.tick)
            if self.finished:
                self._finalize()
                break

    def _finalize(self) -> None:
        m = self.maze
        for panel in self.panels:
            res = panel.spec.direct_fn(m.grid, m.start, m.goal)
            panel.final_stats = res.stats
            panel.found = bool(res.found)

        order = sorted(
            range(len(self.panels)),
            key=lambda i: (
                not self.panels[i].found,
                self.panels[i].finish_tick,
                len(self.panels[i].path) if self.panels[i].path else 10**9,
                i,
            ),
        )
        for rank, i in enumerate(order, start=1):
            self.panels[i].rank = rank

        best = self.panels[order[0]]
        self.winner = best.spec.name if best.found else None

        self.results = [
            {
                "solver": p.spec.name,
                "found": p.found,
                "nodes_explored": p.final_stats.nodes_explored,
                "path_length": p.final_stats.path_length,
                "elapsed_ms": p.final_stats.elapsed_time_ms,
                "max_frontier": p.final_stats.max_frontier_size,
            }
            for p in self.panels
        ]
        try:
            self.race_id = database.save_race(m, self.results, self.winner, db_path=self.db_path)
        except Exception as exc:
            print(f"[race] Could not save history: {exc}")
            self.race_id = None

    def draw(self) -> None:
        f = self.fonts
        screen = self.screen
        screen.fill(config.COLOR_BG)

        m = self.maze
        algo = records.ALGO_LABELS.get(str(m.algorithm).lower(), str(m.algorithm))
        draw_text(screen, "Algorithm Race: BFS vs DFS vs A*", f.medium, config.COLOR_TEXT, (self.GAP, 8))
        draw_text(
            screen,
            f"Maze {m.rows}x{m.cols} · {algo} · braid {m.braid_factor:.2f} · seed {m.seed}",
            f.small, config.COLOR_TEXT, (self.GAP, 38),
        )

        right = screen.get_width() - self.GAP
        if self.finished:
            msg = f"Winner: {self.winner}" if self.winner else "No path found"
            draw_text(screen, msg, f.medium, config.COLOR_PLAYER, (right, 8), anchor="topright")
            draw_text(screen, "ENTER: results · R: restart · N: new maze",
                      f.small, config.COLOR_TEXT, (right, 38), anchor="topright")
        else:
            state = "PAUSED" if self.paused else f"Speed x{self.speed}"
            draw_text(screen, state, f.medium, config.COLOR_PLAYER, (right, 8), anchor="topright")
            draw_text(screen, "SPACE: pause · ←/→: speed · R: restart · N: new · ESC: menu",
                      f.small, config.COLOR_TEXT, (right, 38), anchor="topright")

        for panel in self.panels:
            panel.draw(screen, is_winner=self.finished and panel.rank == 1 and panel.found)



class AutoSolveRaceView:
    """Render the solo auto-solve search in three side-by-side panels."""

    def __init__(
        self,
        wall_tile: pygame.Surface,
        path_tile: pygame.Surface,
        finish_icon: pygame.Surface,
        panel_title_font: pygame.font.Font,
        panel_metric_font: pygame.font.Font,
        hud_font: pygame.font.Font,
    ) -> None:
        self.wall_tile = wall_tile
        self.path_tile = path_tile
        self.finish_icon = finish_icon
        self.panel_title_font = panel_title_font
        self.panel_metric_font = panel_metric_font
        self.hud_font = hud_font
        self._tile_variants: dict[int, tuple[pygame.Surface, pygame.Surface, pygame.Surface]] = {}
        self._maze_layers: dict[int, pygame.Surface] = {}
        self.maze: Maze | Any | None = None
        self.solver_runs: list[Any] = []

    def clear_cache(self) -> None:
        self._tile_variants.clear()
        self._maze_layers.clear()

    def draw(self, target: pygame.Surface, maze: Maze, solver_runs: list[Any]) -> None:
        self.maze = maze
        self.solver_runs = solver_runs
        self._draw_auto_solve_split_view(target)

    def _get_tile_variants(
        self, size: int
    ) -> tuple[pygame.Surface, pygame.Surface, pygame.Surface]:
        if size not in self._tile_variants:
            self._tile_variants[size] = tuple(
                pygame.transform.scale(tile, (size, size))
                for tile in (self.wall_tile, self.path_tile, self.finish_icon)
            )  # type: ignore[assignment]
        return self._tile_variants[size]

    def _get_maze_layer(
        self, cell: int, rows: int, cols: int
    ) -> pygame.Surface:
        layer = self._maze_layers.get(cell)
        if layer is not None:
            return layer

        wall_tile, path_tile, _ = self._get_tile_variants(cell)
        layer = pygame.Surface((cols * cell, rows * cell))
        for row_index, row in enumerate(self.maze.grid):
            for col_index, value in enumerate(row):
                tile = wall_tile if value == WALL else path_tile
                layer.blit(tile, (col_index * cell, row_index * cell))
        self._maze_layers[cell] = layer
        return layer

    @staticmethod
    def _brighten(color: tuple[int, int, int], amount: int = 70) -> tuple[int, int, int]:
        return tuple(min(255, channel + amount) for channel in color)

    def _draw_solver_panel(
        self,
        target: pygame.Surface,
        panel_x: int,
        panel_width: int,
        panel_height: int,
        run: Any,
    ) -> None:
        """Render one algorithm and its own scaled maze/search layer."""
        panel = pygame.Surface((panel_width, panel_height))
        panel.fill((17, 23, 35))
        accent = run.color
        panel_rect = panel.get_rect()
        pygame.draw.rect(panel, accent, panel_rect, width=2)

        pad = 12
        header = pygame.Rect(pad, pad, max(1, panel_width - pad * 2), 98)
        pygame.draw.rect(panel, (31, 41, 59), header, border_radius=12)
        pygame.draw.rect(panel, accent, header, width=2, border_radius=12)

        title = self.panel_title_font.render(run.name, True, accent)
        panel.blit(title, (header.x + 12, header.y + 7))

        if run.rank is not None:
            rank_label = f"TOP {run.rank}"
            rank_fill = accent
        elif run.finished:
            rank_label = "NO PATH"
            rank_fill = (78, 88, 105)
        else:
            rank_label = "RUNNING"
            rank_fill = (47, 66, 91)
        badge_text = self.panel_metric_font.render(rank_label, True, (15, 22, 32))
        badge = pygame.Rect(0, 0, badge_text.get_width() + 18, 26)
        badge.topright = (header.right - 10, header.y + 10)
        pygame.draw.rect(panel, rank_fill, badge, border_radius=10)
        panel.blit(badge_text, badge_text.get_rect(center=badge.center))

        path_steps = "—"
        if run.final_path is not None:
            path_steps = str(max(0, len(run.final_path) - 1))
        nodes_text = self.panel_metric_font.render(
            f"Nodes explored: {run.nodes_explored:,}", True, (231, 238, 247)
        )
        path_text = self.panel_metric_font.render(
            f"Path steps: {path_steps}", True, (177, 192, 210)
        )
        panel.blit(nodes_text, (header.x + 12, header.y + 48))
        panel.blit(path_text, (header.x + 12, header.y + 72))

        rows = len(self.maze.grid)
        cols = max((len(row) for row in self.maze.grid), default=0)
        footer_height = 44
        grid_top = header.bottom + 12
        grid_bottom = panel_height - footer_height - 12
        available_width = max(1, panel_width - pad * 2)
        available_height = max(1, grid_bottom - grid_top)
        mini_cell_size = max(
            1,
            min(available_width // max(1, cols), available_height // max(1, rows)),
        )
        grid_width = cols * mini_cell_size
        grid_height = rows * mini_cell_size
        grid_x = (panel_width - grid_width) // 2
        grid_y = grid_top + (available_height - grid_height) // 2

        panel.blit(
            self._get_maze_layer(mini_cell_size, rows, cols),
            (grid_x, grid_y),
        )
        _, _, finish_icon = self._get_tile_variants(mini_cell_size)
        goal_row, goal_col = self.maze.goal
        panel.blit(
            finish_icon,
            (grid_x + goal_col * mini_cell_size, grid_y + goal_row * mini_cell_size),
        )

        search_layer = pygame.Surface((grid_width, grid_height), pygame.SRCALPHA)
        latest = run.latest
        if latest is not None:
            visited_size = max(1, round(mini_cell_size * 0.8))
            visited_inset = (mini_cell_size - visited_size) // 2
            for row, col in latest.visited:
                if 0 <= row < rows and 0 <= col < cols:
                    pygame.draw.rect(
                        search_layer,
                        (*accent, 88),
                        (
                            col * mini_cell_size + visited_inset,
                            row * mini_cell_size + visited_inset,
                            visited_size,
                            visited_size,
                        ),
                    )

            frontier_size = max(1, round(mini_cell_size * 0.84))
            frontier_inset = (mini_cell_size - frontier_size) // 2
            frontier_color = self._brighten(accent, 55)
            for row, col in latest.frontier:
                if 0 <= row < rows and 0 <= col < cols:
                    pygame.draw.rect(
                        search_layer,
                        (*frontier_color, 235),
                        (
                            col * mini_cell_size + frontier_inset,
                            row * mini_cell_size + frontier_inset,
                            frontier_size,
                            frontier_size,
                        ),
                        width=max(1, mini_cell_size // 4),
                    )

        if run.final_path:
            path_points = [
                (
                    round((col + 0.5) * mini_cell_size),
                    round((row + 0.5) * mini_cell_size),
                )
                for row, col in run.final_path
                if 0 <= row < rows and 0 <= col < cols
            ]
            if len(path_points) >= 2:
                pygame.draw.lines(
                    search_layer,
                    (*self._brighten(accent, 95), 245),
                    False,
                    path_points,
                    width=max(2, mini_cell_size // 2),
                )
            for point in path_points:
                pygame.draw.circle(
                    search_layer,
                    self._brighten(accent, 95),
                    point,
                    max(1, mini_cell_size // 4),
                )

        if run.current_pos is not None:
            head_row, head_col = run.current_pos
            if 0 <= head_row < rows and 0 <= head_col < cols:
                head_center = (
                    round((head_col + 0.5) * mini_cell_size),
                    round((head_row + 0.5) * mini_cell_size),
                )
                pygame.draw.circle(
                    search_layer,
                    (255, 255, 255),
                    head_center,
                    max(2, round(mini_cell_size * 0.3)),
                )
                pygame.draw.circle(
                    search_layer,
                    accent,
                    head_center,
                    max(2, round(mini_cell_size * 0.3)),
                    width=1,
                )

        panel.blit(search_layer, (grid_x, grid_y))
        target.blit(panel, (panel_x, 0))

    def _draw_auto_solve_split_view(self, target: pygame.Surface) -> None:
        """Show BFS, DFS and A* in independent, equally sized maze panels."""
        target.fill((13, 18, 29))
        width, height = target.get_size()
        footer_height = 42
        panel_height = max(1, height - footer_height)
        base_width = width // 3

        for index, run in enumerate(self.solver_runs[:3]):
            panel_x = index * base_width
            panel_width = base_width if index < 2 else width - panel_x
            self._draw_solver_panel(target, panel_x, panel_width, panel_height, run)

        for divider_x in (base_width, base_width * 2):
            pygame.draw.line(target, (67, 82, 104), (divider_x, 0), (divider_x, panel_height), 2)

        footer = pygame.Rect(0, panel_height, width, footer_height)
        pygame.draw.rect(target, (22, 29, 43), footer)
        pygame.draw.line(target, (60, 77, 101), footer.topleft, footer.topright, 1)
        instruction = self.hud_font.render(
            "Press 'F' to Resume Play | ESC for Menu",
            True,
            (225, 235, 246),
        )
        target.blit(instruction, instruction.get_rect(center=footer.center))





def __getattr__(name: str) -> Any:
    if name == "TwoPlayerScreen":
        from play import TwoPlayerScreen
        return TwoPlayerScreen
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def main() -> None:
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.GAME_TITLE)
    clock = pygame.time.Clock()

    race = RaceScreen(screen, rows=25, cols=25)
    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif race.handle_event(event) in (config.STATE_MENU, config.STATE_RESULT):
                running = False
        race.update()
        race.draw()
        pygame.display.flip()
        clock.tick(config.FPS)
    pygame.quit()

    if race.next_state == config.STATE_RESULT and race.race_id:
        result = records.get_race_result(race.race_id)
        if result:
            print(f"\n{result.maze_text} (seed {result.seed_text}) - {result.played_at_text}")
            for row in result.rows:
                print(f"  {row.solver:<3} {row.status_text:<10} {row.nodes_text:>6} node  "
                      f"{row.path_text:>7}  {row.time_text}")
            for line in result.insights:
                print(f"  - {line}")


if __name__ == "__main__":
    main()
