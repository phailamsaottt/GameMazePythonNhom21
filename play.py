"""Player-controlled maze gameplay, timer, and animated solver comparison."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterator, Protocol

import pygame

import config
import database
from player import Player
from generator import WALL, generate_maze
from pathfinding import SearchStep, astar, bfs, dfs, reconstruct_path


class MazeLike(Protocol):
    grid: list[list[int]]
    start: tuple[int, int]
    goal: tuple[int, int]
    seed: int | str
    algorithm: str
    rows: int
    cols: int
    braid_factor: float


@dataclass
class SolverRun:
    name: str
    color: tuple[int, int, int]
    steps: Iterator[SearchStep]
    current_pos: tuple[int, int] | None = None
    final_path: list[tuple[int, int]] | None = None
    latest: SearchStep | None = None
    step_count: int = 0
    nodes_explored: int = 0
    rank: int | None = None
    finished: bool = False


def _load_roboto_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Use the bundled Roboto font for gameplay text."""
    roboto_path = Path(config.FONT_ROBOTO_PATH)
    try:
        font = pygame.font.Font(str(roboto_path), size) if roboto_path.is_file() else None
    except (pygame.error, OSError):
        font = None
    if font is None:
        return pygame.font.SysFont("Roboto,Arial,Segoe UI,sans-serif", size, bold=bold)
    font.set_bold(bold)
    return font


def _load_victory_sound() -> pygame.mixer.Sound | None:
    """Load the finish cue when audio is available; remain silent otherwise."""
    try:
        if pygame.mixer.get_init() is None:
            pygame.mixer.init()
    except pygame.error:
        return None

    base_dir = Path(config.BASE_DIR)
    candidates = (
        base_dir / "Assets" / "sounds" / "finish.mp3",
        base_dir / "Assets" / "sounds" / "finish.MP3",
        base_dir / "assets" / "sounds" / "finish.mp3",
    )
    for sound_path in candidates:
        if sound_path.is_file():
            try:
                return pygame.mixer.Sound(str(sound_path))
            except (pygame.error, OSError):
                continue
    return None


class PlayingScreen:
    """Render and update a maze selected from the difficulty screen."""

    DEFAULT_ROWS = 21
    DEFAULT_COLS = 21
    PANEL_MAX_SIZE = (560, 340)
    SOLVER_STEP_INTERVAL_MS = 30
    SOLVER_COLORS = {
        "BFS": (0, 230, 255),    # Cyan
        "DFS": (185, 75, 245),   # Purple
        "A*": (255, 145, 0),     # Orange
    }

    def __init__(
        self,
        screen: pygame.Surface | None = None,
        rows: int = DEFAULT_ROWS,
        cols: int = DEFAULT_COLS,
        player_name: str = "Player",
        character_id: int = 1,
    ) -> None:
        self.screen = screen
        self.rows = int(rows)
        self.cols = int(cols)
        self.player_name = str(player_name).strip() or "Player"
        self.character_id = int(character_id)
        if self.character_id not in (1, 2):
            raise ValueError("character_id must be 1 or 2")
        self.state = "playing"
        self.maze: MazeLike = generate_maze(rows=self.rows, cols=self.cols)
        self.player = self._make_player(self.maze, self.character_id)

        self.cell_size = max(1, int(config.CELL_SIZE))
        self.wall_tile = self._load_tile(
            "wall.png", getattr(config, "COLOR_WALL", (24, 24, 32))
        )
        self.path_tile = self._load_tile(
            "path.png", getattr(config, "COLOR_PATH", (230, 230, 230))
        )
        self.finish_icon = self._load_tile(
            "finish.png", getattr(config, "COLOR_END", (231, 76, 60))
        )
        self.panel_img = self._load_panel()
        self._tile_variants: dict[int, tuple[pygame.Surface, pygame.Surface, pygame.Surface]] = {}
        self._maze_layers: dict[int, pygame.Surface] = {}

        title_size = int(getattr(config, "FONT_SIZE_TITLE", 54))
        medium_size = int(getattr(config, "FONT_SIZE_MEDIUM", 24))
        pygame.font.init()
        self.title_font = _load_roboto_font(title_size, bold=True)
        self.message_font = _load_roboto_font(medium_size)
        self.timer_font = _load_roboto_font(28, bold=True)
        self.hud_font = _load_roboto_font(18, bold=True)
        self.panel_title_font = _load_roboto_font(24, bold=True)
        self.panel_metric_font = _load_roboto_font(15, bold=True)

        self.start_time = pygame.time.get_ticks()
        self.final_time_ms: int | None = None
        self.frozen_elapsed_ms: int | None = None
        self._solver_accumulator = 0.0
        self.record_save_error: str | None = None
        self._record_save_attempted = False
        self.victory_sound = _load_victory_sound()
        self.victory_sound_played = False

        # Auto-Solve Race panel state
        self.solver_runs: list[SolverRun] = []
        self.solver_rankings: list[str] = []

        self.find_path_button_rect = pygame.Rect(
            max(12, config.WINDOW_WIDTH - 212),
            max(12, config.WINDOW_HEIGHT - 54),
            min(200, max(1, config.WINDOW_WIDTH - 24)),
            42,
        )

    @staticmethod
    def _make_player(maze: MazeLike, character_id: int = 1) -> Player:
        """Maze coordinates are (row, column); Player takes (x=column, y=row)."""
        start_row, start_col = maze.start
        return Player(
            start_grid_x=start_col,
            start_grid_y=start_row,
            character_id=character_id,
        )

    @staticmethod
    def _asset_candidates(*parts: str) -> tuple[Path, ...]:
        base = Path(config.BASE_DIR)
        relative = Path(*parts)
        return (
            base / "Assets" / "images" / "map" / relative,
            base / "Assets" / "images" / "Map" / relative,
            base / "assets" / "images" / "map" / relative,
            Path(__file__).resolve().parent / "Assets" / "images" / "Map" / relative,
        )

    @staticmethod
    def _load_image(path: Path) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(path))
            return image.convert_alpha() if pygame.display.get_surface() else image.copy()
        except (pygame.error, OSError, ValueError):
            return None

    @classmethod
    def _load_tile(cls, filename: str, fallback_color: tuple[int, int, int]) -> pygame.Surface:
        for path in cls._asset_candidates(filename):
            if path.is_file():
                image = cls._load_image(path)
                if image is not None:
                    return pygame.transform.scale(image, (max(1, int(config.CELL_SIZE)),) * 2)

        fallback = pygame.Surface((max(1, int(config.CELL_SIZE)),) * 2, pygame.SRCALPHA)
        fallback.fill((*fallback_color, 255))
        return fallback

    def _load_panel(self) -> pygame.Surface:
        display = self.screen if self.screen is not None else pygame.display.get_surface()
        screen_width, screen_height = (
            display.get_size()
            if display is not None
            else (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        )
        panel_size = (
            max(1, min(self.PANEL_MAX_SIZE[0], screen_width - 40)),
            max(1, min(self.PANEL_MAX_SIZE[1], screen_height - 40)),
        )
        panel_path = Path(config.BASE_DIR) / "Assets" / "images" / "UI" / "panel.png"
        panel = self._load_image(panel_path) if panel_path.is_file() else None
        if panel is not None:
            return pygame.transform.scale(panel, panel_size)

        fallback = pygame.Surface(panel_size, pygame.SRCALPHA)
        fallback.fill((0, 0, 0, 220))
        return fallback

    @property
    def elapsed_time_ms(self) -> int:
        if self.final_time_ms is not None:
            return self.final_time_ms
        if self.frozen_elapsed_ms is not None:
            return self.frozen_elapsed_ms
        return max(0, pygame.time.get_ticks() - self.start_time)

    @staticmethod
    def format_time(milliseconds: int) -> str:
        minutes, remainder = divmod(max(0, milliseconds), 60_000)
        seconds, millis = divmod(remainder, 1_000)
        return f"{minutes:02}:{seconds:02}.{millis:03}"

    def reset(self, rows: int | None = None, cols: int | None = None) -> None:
        """Start a new maze, optionally using a newly selected difficulty."""
        if rows is not None:
            self.rows = int(rows)
        if cols is not None:
            self.cols = int(cols)
        self.maze = generate_maze(rows=self.rows, cols=self.cols)
        self.player = self._make_player(self.maze, self.character_id)
        self.state = "playing"
        self.start_time = pygame.time.get_ticks()
        self.final_time_ms = None
        self.frozen_elapsed_ms = None
        self._solver_accumulator = 0.0
        self.record_save_error = None
        self._record_save_attempted = False
        self.victory_sound_played = False
        self.solver_runs.clear()
        self.solver_rankings.clear()
        self._maze_layers.clear()

    def _save_completed_run(self) -> None:
        if self._record_save_attempted:
            return
        self._record_save_attempted = True
        try:
            database.save_play(
                self.maze,
                steps=0,
                elapsed_ms=self.elapsed_time_ms,
                player_name=self.player_name,
            )
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.record_save_error = str(exc)

    def _finish_game(self) -> None:
        if self.state == "victory":
            return
        self.final_time_ms = max(0, pygame.time.get_ticks() - self.start_time)
        self.state = "victory"
        self._play_victory_sound()
        self._save_completed_run()

    def _play_victory_sound(self) -> None:
        if self.victory_sound_played:
            return
        self.victory_sound_played = True
        if self.victory_sound is not None:
            try:
                self.victory_sound.play()
            except pygame.error:
                pass

    def _start_auto_solve(self) -> None:
        # The player's coordinates are (x=column, y=row), while solvers use
        # (row, column), matching Maze.start and Maze.goal.
        start = (self.player.grid_y, self.player.grid_x)
        goal = self.maze.goal
        grid = self.maze.grid

        self.solver_runs = [
            SolverRun(
                name="BFS",
                color=self.SOLVER_COLORS["BFS"],
                steps=bfs(grid, start, goal),
                current_pos=start,
            ),
            SolverRun(
                name="DFS",
                color=self.SOLVER_COLORS["DFS"],
                steps=dfs(grid, start, goal),
                current_pos=start,
            ),
            SolverRun(
                name="A*",
                color=self.SOLVER_COLORS["A*"],
                steps=astar(grid, start, goal),
                current_pos=start,
            ),
        ]
        self.solver_rankings.clear()
        self.frozen_elapsed_ms = self.elapsed_time_ms
        self.state = "auto_solving"
        self._solver_accumulator = 0.0

    def _toggle_auto_solve(self) -> None:
        if self.state == "auto_solving":
            frozen_time = self.elapsed_time_ms
            self.start_time = pygame.time.get_ticks() - frozen_time
            self.frozen_elapsed_ms = None
            self.state = "playing"
            self._solver_accumulator = 0.0
        elif self.state == "playing":
            self._start_auto_solve()

    def _advance_auto_solve(self) -> None:
        """Advance each unfinished solver by exactly one generator yield."""
        for run in self.solver_runs:
            if run.finished:
                continue
            try:
                step = next(run.steps)
            except StopIteration:
                run.finished = True
                continue

            run.latest = step
            run.current_pos = step.current
            run.step_count += 1
            run.nodes_explored = max(
                run.nodes_explored,
                len(step.visited),
                step.stats.nodes_explored if step.stats is not None else 0,
            )

            if step.is_done:
                run.finished = True
                if step.found:
                    run.rank = len(self.solver_rankings) + 1
                    self.solver_rankings.append(run.name)
                    if step.path:
                        run.final_path = list(step.path)
                    elif step.current == self.maze.goal:
                        start = (self.player.grid_y, self.player.grid_x)
                        run.final_path = reconstruct_path(step.came_from, start, self.maze.goal)

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if self.state == "auto_solving":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return config.STATE_MENU
            if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                self._toggle_auto_solve()
                return None
            return None

        if self.state == "playing":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return config.STATE_MENU
            if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                self._toggle_auto_solve()
                return None
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.find_path_button_rect.collidepoint(event.pos)
            ):
                self._toggle_auto_solve()
                return None
            return None

        if self.state == "victory":
            if event.type == pygame.MOUSEBUTTONDOWN:
                return config.STATE_MENU
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
                pygame.K_ESCAPE,
            ):
                return config.STATE_MENU
        return None

    def update(self, dt: float) -> None:
        if self.state == "auto_solving":
            self._solver_accumulator += max(0.0, dt)
            interval = self.SOLVER_STEP_INTERVAL_MS / 1000.0
            if self._solver_accumulator >= interval:
                self._solver_accumulator %= interval
                self._advance_auto_solve()
            return

        if self.state != "playing":
            return

        keys = pygame.key.get_pressed()
        self.player.update(keys, self.maze.grid, dt)
        goal_row, goal_col = self.maze.goal
        if self.player.grid_x == goal_col and self.player.grid_y == goal_row:
            self._finish_game()

    def _display_geometry(
        self, target: pygame.Surface, rows: int, cols: int
    ) -> tuple[int, float, int, int]:
        base_cell = max(1, int(config.CELL_SIZE))
        cell = max(1, min(base_cell, target.get_width() // max(1, cols), target.get_height() // max(1, rows)))
        scale = cell / base_cell
        offset_x = (target.get_width() - cols * cell) // 2
        offset_y = (target.get_height() - rows * cell) // 2
        return cell, scale, offset_x, offset_y

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
        run: SolverRun,
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

    def _draw_player_scaled(
        self, target: pygame.Surface, scale: float, offset_x: int, offset_y: int
    ) -> None:
        image = getattr(self.player, "image", None)
        if image is None:
            self.player.draw(target, offset_x, offset_y)
            image = getattr(self.player, "image", None)
            if image is None:
                return
        else:
            if scale != 1.0:
                size = (
                    max(1, round(image.get_width() * scale)),
                    max(1, round(image.get_height() * scale)),
                )
                image = pygame.transform.scale(image, size)
            center = (
                round(offset_x + self.player.x * scale),
                round(offset_y + self.player.y * scale),
            )
            target.blit(image, image.get_rect(center=center))

        center = (
            round(offset_x + self.player.x * scale),
            round(offset_y + self.player.y * scale),
        )
        shown_image_height = max(1, round(image.get_height() * scale))
        name = self.hud_font.render(self.player_name, True, (245, 248, 255))
        name_pad_x, name_pad_y = 8, 4
        badge = pygame.Surface(
            (name.get_width() + name_pad_x * 2, name.get_height() + name_pad_y * 2),
            pygame.SRCALPHA,
        )
        pygame.draw.rect(badge, (12, 18, 27, 205), badge.get_rect(), border_radius=6)
        badge.blit(name, (name_pad_x, name_pad_y))
        badge_rect = badge.get_rect(
            midbottom=(center[0], center[1] - shown_image_height // 2 - 5)
        )
        target.blit(badge, badge_rect)

    def _draw_timer(self, target: pygame.Surface) -> None:
        name = self.hud_font.render(self.player_name, True, (230, 235, 245))
        timer = self.timer_font.render(self.format_time(self.elapsed_time_ms), True, (120, 255, 120))
        gap = 12
        width = name.get_width() + timer.get_width() + gap + 24
        height = max(name.get_height(), timer.get_height()) + 12
        background = pygame.Surface((width, height), pygame.SRCALPHA)
        background.fill((8, 12, 10, 210))
        rect = background.get_rect(midtop=(target.get_width() // 2, 12))
        target.blit(background, rect)
        content_width = name.get_width() + gap + timer.get_width()
        left = rect.centerx - content_width // 2
        target.blit(name, name.get_rect(midleft=(left, rect.centery)))
        target.blit(timer, timer.get_rect(midleft=(left + name.get_width() + gap, rect.centery)))

    def _draw_find_path_button(self, target: pygame.Surface) -> None:
        width = min(200, max(1, target.get_width() - 24))
        height = min(42, max(1, target.get_height() - 24))
        self.find_path_button_rect = pygame.Rect(
            target.get_width() - width - 12,
            target.get_height() - height - 12,
            width,
            height,
        )
        hovered = self.find_path_button_rect.collidepoint(pygame.mouse.get_pos())
        fill = (30, 105, 86) if not hovered else (42, 145, 112)
        label = "TÌM ĐƯỜNG ĐI (F)"
        pygame.draw.rect(target, fill, self.find_path_button_rect, border_radius=6)
        pygame.draw.rect(
            target,
            (220, 230, 220),
            self.find_path_button_rect,
            width=2,
            border_radius=6,
        )
        text = self.hud_font.render(label, True, (255, 255, 255))
        target.blit(text, text.get_rect(center=self.find_path_button_rect.center))

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        if target is None:
            target = pygame.display.get_surface()
        if target is None:
            raise RuntimeError("PlayingScreen.draw() requires a display surface")

        if self.state == "auto_solving":
            self._draw_auto_solve_split_view(target)
            return

        target.fill(getattr(config, "COLOR_BG", (30, 30, 40)))
        grid = self.maze.grid
        rows = len(grid)
        cols = max((len(row) for row in grid), default=0)
        cell, scale, offset_x, offset_y = self._display_geometry(target, rows, cols)
        _, _, finish_icon = self._get_tile_variants(cell)
        target.blit(self._get_maze_layer(cell, rows, cols), (offset_x, offset_y))

        goal_row, goal_col = self.maze.goal
        target.blit(
            finish_icon,
            (offset_x + goal_col * cell, offset_y + goal_row * cell),
        )
        self._draw_player_scaled(target, scale, offset_x, offset_y)
        if self.state == "playing":
            self._draw_timer(target)
            self._draw_find_path_button(target)

        if self.state == "victory":
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            target.blit(overlay, (0, 0))

            panel_rect = self.panel_img.get_rect(center=target.get_rect().center)
            target.blit(self.panel_img, panel_rect)
            title = self.title_font.render("Congratulations!", True, (255, 255, 255))
            final_time = self.timer_font.render(
                self.format_time(self.elapsed_time_ms), True, (120, 255, 120)
            )
            message = self.message_font.render(
                "Click to return to Menu", True, (240, 240, 240)
            )
            target.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.centery - 72)))
            target.blit(final_time, final_time.get_rect(center=(panel_rect.centerx, panel_rect.centery - 8)))
            target.blit(message, message.get_rect(center=(panel_rect.centerx, panel_rect.centery + 62)))
