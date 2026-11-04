"""Solo and local two-player maze gameplay screens."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Iterator, NamedTuple, Protocol

import pygame
try:
    import gif_pygame
except ImportError:
    gif_pygame = None

import config
import database
from player import Player
from generator import WALL, generate_maze
from pathfinding import SearchStep, astar, bfs, dfs, reconstruct_path
from race import AutoSolveRaceView
from ui_effects import (
    confirm_dialog_rects,
    draw_confirm_dialog,
    draw_hover_arrow,
    play_ui_click,
)

Color = tuple[int, int, int]


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


def _draw_gif(animation, target: pygame.Surface, position: tuple[int, int], size: int) -> bool:
    """Advance and draw a gif_pygame animation scaled to the requested tile."""
    if animation is None or gif_pygame is None:
        return False
    try:
        frame = animation.current_surface
        frame_surface = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
        animation.render(frame_surface, (0, 0))
        scaled = pygame.transform.scale(frame_surface, (size, size))
        target.blit(scaled, position)
        return True
    except (pygame.error, AttributeError, TypeError, ValueError):
        return False


class GameplayFonts(NamedTuple):
    small: pygame.font.Font
    medium: pygame.font.Font
    large: pygame.font.Font


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
        self.current_level = 1
        self.max_levels = 3
        self.state = "countdown"
        self.show_confirm_popup = False
        self.confirm_selected = 0
        self.confirm_return_state = self.state
        self.confirm_elapsed_ms = 0
        self.countdown_elapsed = 0.0
        self.total_elapsed_ms = 0
        self._level_time_committed = False
        self.maze: MazeLike = generate_maze(rows=self.rows, cols=self.cols)
        self.player = self._make_player(self.maze, self.character_id)

        self.cell_size = max(1, int(config.CELL_SIZE))
        self.finish_animation = None
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
        self.auto_solve_view = AutoSolveRaceView(
            self.wall_tile,
            self.path_tile,
            self.finish_icon,
            self.panel_title_font,
            self.panel_metric_font,
            self.hud_font,
        )

        self.start_time = pygame.time.get_ticks()
        self.hud_idle_time = 0.0
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
            controls="both",
            character_id=character_id,
        )

    def _asset_candidates(self, *parts: str) -> tuple[Path, ...]:
        base = Path(config.BASE_DIR)
        relative = Path(*parts)
        return (
            base / "Assets" / "images" / "Map" / f"Map{self.current_level}" / relative,
            base / "Assets" / "images" / "map" / f"Map{self.current_level}" / relative,
            base / "assets" / "images" / "map" / f"Map{self.current_level}" / relative,
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

    def _load_tile(self, filename: str, fallback_color: tuple[int, int, int]) -> pygame.Surface:
        if filename == "finish.png":
            self.finish_animation = None
            if gif_pygame is not None:
                for gif_path in self._asset_candidates("finish.gif"):
                    if not gif_path.is_file():
                        continue
                    try:
                        self.finish_animation = gif_pygame.load(str(gif_path))
                        frame = self.finish_animation.current_surface
                        return pygame.transform.scale(frame, (self.cell_size, self.cell_size))
                    except Exception:
                        self.finish_animation = None
        for path in self._asset_candidates(filename):
            if path.is_file():
                image = self._load_image(path)
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
        ui_dir = Path(config.BASE_DIR) / "Assets" / "images" / "UI"
        panel = None
        for filename in ("congrats_panel.png", "panel.png"):
            panel_path = ui_dir / filename
            if panel_path.is_file():
                panel = self._load_image(panel_path)
                if panel is not None:
                    break
        if panel is not None:
            scale = min(panel_size[0] / panel.get_width(), panel_size[1] / panel.get_height())
            size = (max(1, round(panel.get_width() * scale)), max(1, round(panel.get_height() * scale)))
            return pygame.transform.smoothscale(panel, size)

        fallback = pygame.Surface(panel_size, pygame.SRCALPHA)
        fallback.fill((0, 0, 0, 220))
        return fallback

    @property
    def elapsed_time_ms(self) -> int:
        if self.show_confirm_popup:
            return self.confirm_elapsed_ms
        if self.final_time_ms is not None:
            return self.final_time_ms
        if self.frozen_elapsed_ms is not None:
            return self.frozen_elapsed_ms
        if self.state == "countdown":
            return 0
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
        self.current_level = 1
        self.total_elapsed_ms = 0
        self.countdown_elapsed = 0.0
        self._level_time_committed = False
        self.state = "countdown"
        self.start_time = 0
        self.final_time_ms = None
        self.frozen_elapsed_ms = None
        self._solver_accumulator = 0.0
        self.record_save_error = None
        self._record_save_attempted = False
        self.victory_sound_played = False
        self.wall_tile = self._load_tile("wall.png", getattr(config, "COLOR_WALL", (24, 24, 32)))
        self.path_tile = self._load_tile("path.png", getattr(config, "COLOR_PATH", (230, 230, 230)))
        self.finish_icon = self._load_tile("finish.png", getattr(config, "COLOR_END", (231, 76, 60)))
        self.auto_solve_view = AutoSolveRaceView(
            self.wall_tile, self.path_tile, self.finish_icon,
            self.panel_title_font, self.panel_metric_font, self.hud_font,
        )
        self.solver_runs.clear()
        self.solver_rankings.clear()
        self._maze_layers.clear()
        self.auto_solve_view.clear_cache()

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

    def _start_level(self, level: int) -> None:
        self.current_level = level
        self.maze = generate_maze(rows=self.rows, cols=self.cols)
        self.player = self._make_player(self.maze, self.character_id)
        self.wall_tile = self._load_tile("wall.png", getattr(config, "COLOR_WALL", (24, 24, 32)))
        self.path_tile = self._load_tile("path.png", getattr(config, "COLOR_PATH", (230, 230, 230)))
        self.finish_icon = self._load_tile("finish.png", getattr(config, "COLOR_END", (231, 76, 60)))
        self._tile_variants.clear()
        self._maze_layers.clear()
        self.auto_solve_view = AutoSolveRaceView(
            self.wall_tile, self.path_tile, self.finish_icon,
            self.panel_title_font, self.panel_metric_font, self.hud_font,
        )
        self.countdown_elapsed = 0.0
        self.start_time = 0
        self.frozen_elapsed_ms = None
        self._level_time_committed = False
        self.state = "countdown"

    def _finish_game(self) -> None:
        if self.state not in ("playing", "auto_solving"):
            return
        if not self._level_time_committed:
            self.total_elapsed_ms += self.elapsed_time_ms
            self._level_time_committed = True
        if self.current_level < self.max_levels:
            self._start_level(self.current_level + 1)
            return
        self.final_time_ms = self.total_elapsed_ms
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
        if self.show_confirm_popup:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self._resume_from_confirm()
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    self.confirm_selected = 1 - self.confirm_selected
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.confirm_selected == 0:
                        self._resume_from_confirm()
                    else:
                        return config.STATE_MENU
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                size = self.screen.get_size() if self.screen else (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
                _, continue_rect, exit_rect = confirm_dialog_rects(size)
                if continue_rect.collidepoint(event.pos):
                    play_ui_click()
                    self._resume_from_confirm()
                elif exit_rect.collidepoint(event.pos):
                    play_ui_click()
                    return config.STATE_MENU
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self._open_confirm()
            return None

        if self.state == "countdown":
            return None
        if self.state == "auto_solving":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                self._toggle_auto_solve()
                return None
            return None

        if self.state == "playing":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_f:
                self._toggle_auto_solve()
                return None
            if (
                event.type == pygame.MOUSEBUTTONDOWN
                and event.button == 1
                and self.find_path_button_rect.collidepoint(event.pos)
            ):
                play_ui_click()
                self._toggle_auto_solve()
                return None
            return None

        if self.state == "victory":
            if event.type == pygame.MOUSEBUTTONDOWN:
                play_ui_click()
                return config.STATE_MENU
            if event.type == pygame.KEYDOWN and event.key in (
                pygame.K_RETURN,
                pygame.K_KP_ENTER,
                pygame.K_ESCAPE,
            ):
                return config.STATE_MENU
        return None

    def update(self, dt: float) -> None:
        if self.show_confirm_popup:
            return
        frame_dt = max(0.0, float(dt))
        self.hud_idle_time += frame_dt
        if self.state == "countdown":
            self.countdown_elapsed += frame_dt
            if self.countdown_elapsed >= 4.0:
                self.start_time = pygame.time.get_ticks()
                self.state = "playing"
            return
        if self.state == "auto_solving":
            self._solver_accumulator += frame_dt
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

    def _open_confirm(self) -> None:
        elapsed_ms = self.elapsed_time_ms
        self.show_confirm_popup = True
        self.confirm_selected = 0
        self.confirm_return_state = self.state
        self.confirm_elapsed_ms = elapsed_ms

    def _resume_from_confirm(self) -> None:
        self.show_confirm_popup = False
        if self.confirm_return_state == "playing":
            self.start_time = pygame.time.get_ticks() - self.confirm_elapsed_ms
        self.state = self.confirm_return_state

    def _draw_confirm_popup(self, target: pygame.Surface) -> None:
        draw_confirm_dialog(target, self.title_font, self.message_font, self.confirm_selected)

    def _display_geometry(
        self, target: pygame.Surface, rows: int, cols: int
    ) -> tuple[int, float, int, int]:
        base_cell = max(1, int(config.CELL_SIZE))
        rows = max(1, rows)
        cols = max(1, cols)
        width, height = target.get_size()

        # Keep a clear band for the timer and bottom controls while allowing
        # small mazes to use more of the available window. The same square
        # cell size is used on both axes, so the maze aspect ratio is unchanged.
        usable_width = max(1, int(width * 0.92))
        usable_height = max(1, int(height * 0.70))
        fit_cell = max(1, min(usable_width // cols, usable_height // rows))

        # Never make a maze smaller than the existing fit. This keeps Medium
        # and Hard layouts that already fill the window at their current size.
        current_cell = max(1, min(base_cell, width // cols, height // rows))
        cell = max(current_cell, fit_cell)
        scale = cell / base_cell
        offset_x = (width - cols * cell) // 2
        offset_y = (height - rows * cell) // 2
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
        badge.blit(name, (name_pad_x, name_pad_y))
        badge_rect = badge.get_rect(
            midbottom=(center[0], center[1] - shown_image_height // 2 - 5)
        )
        target.blit(badge, badge_rect)

    def _draw_timer(self, target: pygame.Surface) -> None:
        name = self.hud_font.render(self.player_name, True, (230, 235, 245))
        timer = self.timer_font.render(self.format_time(self.elapsed_time_ms), True, (120, 255, 120))
        portrait_size = 48
        portrait = self._idle_portrait(portrait_size)
        gap = 10
        text_width = max(name.get_width(), timer.get_width())
        width = portrait_size + gap + text_width + 24
        height = max(portrait_size, name.get_height() + timer.get_height() + 4) + 16
        # Keep the timer together with the Find Path control in the lower-right
        # HUD area, outside the maze's top edge where it could hide cells.
        button_rect = self.find_path_button_rect
        rect = pygame.Rect(0, 0, width, height)
        rect.bottomright = (
            button_rect.right,
            max(0, button_rect.top - 8),
        )
        card = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(card, (12, 20, 30, 205), card.get_rect(), border_radius=10)
        pygame.draw.rect(card, (78, 190, 220, 210), card.get_rect(), width=2, border_radius=10)
        card.blit(portrait, (8, (height - portrait_size) // 2))
        text_x = 8 + portrait_size + gap
        card.blit(name, (text_x, (height - name.get_height() - timer.get_height() - 4) // 2))
        card.blit(timer, (text_x, (height + name.get_height() - timer.get_height() + 4) // 2))
        target.blit(card, rect)

    def _idle_portrait(self, size: int = 64) -> pygame.Surface:
        """Return a scaled, animated idle portrait for the solo player."""
        frames = self.player.animations.get("idle", [])
        source: pygame.Surface | None = None
        if frames:
            first = frames[0]
            if Player._is_gif(first):
                source = first.current_surface
                frame = pygame.Surface(source.get_size(), pygame.SRCALPHA)
                first.render(frame, (0, 0))
                source = frame
            else:
                duration = max(0.05, float(getattr(self.player, "animation_speed", 0.15)))
                source = frames[int(self.hud_idle_time / duration) % len(frames)]
        if source is None:
            source = getattr(self.player, "image", None)

        portrait = pygame.Surface((size, size), pygame.SRCALPHA)
        if source is None:
            pygame.draw.circle(portrait, (100, 190, 230), portrait.get_rect().center, size // 3)
            return portrait
        width, height = source.get_size()
        scale = min(size / max(1, width), size / max(1, height))
        scaled_size = (max(1, round(width * scale)), max(1, round(height * scale)))
        scaled = pygame.transform.smoothscale(source, scaled_size)
        portrait.blit(scaled, scaled.get_rect(center=portrait.get_rect().center))
        return portrait

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
        label = "FIND PATH (F)"
        pygame.draw.rect(target, fill, self.find_path_button_rect, border_radius=6)
        pygame.draw.rect(
            target,
            (220, 230, 220),
            self.find_path_button_rect,
            width=2,
            border_radius=6,
        )
        draw_hover_arrow(target, self.find_path_button_rect, hovered)
        text = self.hud_font.render(label, True, (255, 255, 255))
        target.blit(text, text.get_rect(center=self.find_path_button_rect.center))

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        if target is None:
            target = pygame.display.get_surface()
        if target is None:
            raise RuntimeError("PlayingScreen.draw() requires a display surface")

        if self.state == "auto_solving":
            self.auto_solve_view.draw(target, self.maze, self.solver_runs)
            if self.show_confirm_popup:
                self._draw_confirm_popup(target)
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
        _draw_gif(self.finish_animation, target,
                  (offset_x + goal_col * cell, offset_y + goal_row * cell), cell)
        self._draw_player_scaled(target, scale, offset_x, offset_y)
        if self.state == "playing":
            self._draw_find_path_button(target)
            self._draw_timer(target)

        if self.state == "victory":
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            target.blit(overlay, (0, 0))

            panel_rect = self.panel_img.get_rect(center=target.get_rect().center)
            target.blit(self.panel_img, panel_rect)
            title = self.title_font.render("Congratulations!", True, (255, 255, 255))
            target.blit(title, title.get_rect(center=(panel_rect.centerx, panel_rect.centery - 105)))
            portrait = self._idle_portrait(72)
            target.blit(portrait, portrait.get_rect(center=(panel_rect.centerx, panel_rect.centery - 28)))
            final_time = self.timer_font.render(
                self.format_time(self.elapsed_time_ms), True, (120, 255, 120)
            )
            name = self.message_font.render(self.player_name, True, (255, 255, 255))
            target.blit(final_time, final_time.get_rect(center=(panel_rect.centerx, panel_rect.centery + 38)))
            target.blit(name, name.get_rect(center=(panel_rect.centerx, panel_rect.centery + 78)))

        if self.state == "countdown":
            self._draw_countdown(target)

        if self.state == "playing":
            level_text = self.message_font.render(
                f"LEVEL {self.current_level}/{self.max_levels}", True, (255, 220, 90)
            )
            target.blit(level_text, (16, 16))
        if self.show_confirm_popup:
            self._draw_confirm_popup(target)

    def _draw_countdown(self, target: pygame.Surface) -> None:
        elapsed = min(3.999, max(0.0, self.countdown_elapsed))
        label = ("3", "2", "1", "START!")[int(elapsed)]
        fade = min(255, int(min(elapsed % 1.0, 1.0 - (elapsed % 1.0)) * 510 + 90))
        text = self.title_font.render(label, True, (255, 255, 255))
        text.set_alpha(fade)
        target.blit(text, text.get_rect(center=target.get_rect().center))
        level = self.message_font.render(f"LEVEL {self.current_level}", True, (255, 220, 90))
        target.blit(level, level.get_rect(center=(target.get_width() // 2, target.get_height() // 2 + 64)))


class TwoPlayerScreen:
    """Local two-player maze race with independent controls and one shared clock."""

    def __init__(
        self,
        screen: pygame.Surface,
        player1_name: str = "Player 1",
        player2_name: str = "Player 2",
        rows: int = config.DEFAULT_ROWS,
        cols: int = config.DEFAULT_COLS,
    ) -> None:
        self.screen = screen
        self.rows = int(rows)
        self.cols = int(cols)
        self.current_level = 1
        self.max_levels = 3
        self.maze = generate_maze(rows=rows, cols=cols)
        self.player_names = (
            player1_name.strip() or "Player 1",
            player2_name.strip() or "Player 2",
        )
        start_row, start_col = self.maze.start
        self.players = (
            Player(start_col, start_row, controls="wasd", character_id=1, spawn_offset=(-2.5, 0)),
            Player(start_col, start_row, controls="arrows", character_id=2, spawn_offset=(2.5, 0)),
        )
        self.state = "countdown"
        self.countdown_elapsed = 0.0
        self.show_confirm_popup = False
        self.confirm_selected = 0
        self.confirm_return_state = self.state
        self.confirm_elapsed_ms = 0
        self.level_elapsed = [0.0, 0.0]
        self.total_time_p1 = 0
        self.total_time_p2 = 0
        self.reached_goal = [False, False]
        self.winner_index: int | None = None
        self.record_save_error: str | None = None
        self.victory_sound = _load_victory_sound()
        self.victory_sound_played = False
        self.final_elapsed_ms: int | None = None
        self.hud_idle_time = 0.0

        self.fonts = GameplayFonts(
            _load_roboto_font(config.FONT_SIZE_SMALL),
            _load_roboto_font(config.FONT_SIZE_MEDIUM),
            _load_roboto_font(config.FONT_SIZE_LARGE),
        )
        self.timer_font = _load_roboto_font(28)
        self.victory_font = _load_roboto_font(34)
        self.cell_size = max(1, int(config.CELL_SIZE))
        self.finish_animation = None
        self.wall_tile = self._load_map_tile("wall.png", config.COLOR_WALL)
        self.path_tile = self._load_map_tile("path.png", config.COLOR_PATH)
        self.finish_tile = self._load_map_tile("finish.png", config.COLOR_END)
        ui_dir = Path(config.BASE_DIR) / "Assets" / "images" / "UI"
        self.victory_panel = None
        for filename in ("congrats_panel.png", "panel.png"):
            self.victory_panel = self._load_image(ui_dir / filename)
            if self.victory_panel is not None:
                break
        if self.victory_panel is None:
            self.victory_panel = pygame.Surface((560, 300), pygame.SRCALPHA)
            self.victory_panel.fill((8, 12, 20, 230))
        else:
            scale = min(560 / self.victory_panel.get_width(), 340 / self.victory_panel.get_height())
            panel_size = (
                max(1, round(self.victory_panel.get_width() * scale)),
                max(1, round(self.victory_panel.get_height() * scale)),
            )
            self.victory_panel = pygame.transform.smoothscale(self.victory_panel, panel_size)

        panel_bottom = screen.get_height() // 2 + self.victory_panel.get_height() // 2
        self.back_button = pygame.Rect(screen.get_width() // 2 - 120, panel_bottom + 18, 240, 48)
        self._map_cache: dict[int, pygame.Surface] = {}

    @staticmethod
    def _load_image(path: Path) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(path))
            return image.convert_alpha() if pygame.display.get_surface() else image.copy()
        except (pygame.error, OSError, ValueError):
            return None

    def _load_map_tile(self, filename: str, fallback_color: tuple[int, int, int]) -> pygame.Surface:
        if filename == "finish.png":
            self.finish_animation = None
            if gif_pygame is not None:
                gif_candidates = (
                    Path(config.BASE_DIR) / "Assets" / "images" / "Map" / f"Map{self.current_level}" / "finish.gif",
                    Path(config.BASE_DIR) / "Assets" / "images" / "map" / f"Map{self.current_level}" / "finish.gif",
                    Path(config.BASE_DIR) / "assets" / "images" / "map" / f"Map{self.current_level}" / "finish.gif",
                )
                for gif_path in gif_candidates:
                    if not gif_path.is_file():
                        continue
                    try:
                        self.finish_animation = gif_pygame.load(str(gif_path))
                        frame = self.finish_animation.current_surface
                        return pygame.transform.scale(frame, (self.cell_size, self.cell_size))
                    except Exception:
                        self.finish_animation = None
        candidates = (
            Path(config.BASE_DIR) / "Assets" / "images" / "Map" / f"Map{self.current_level}" / filename,
            Path(config.BASE_DIR) / "Assets" / "images" / "map" / f"Map{self.current_level}" / filename,
            Path(config.BASE_DIR) / "assets" / "images" / "map" / f"Map{self.current_level}" / filename,
            Path(config.BASE_DIR) / "Assets" / "images" / "map" / filename,
            Path(config.BASE_DIR) / "Assets" / "images" / "Map" / filename,
        )
        for path in candidates:
            if path.is_file():
                image = self._load_image(path)
                if image is not None:
                    return pygame.transform.scale(image, (self.cell_size, self.cell_size))
        fallback = pygame.Surface((self.cell_size, self.cell_size))
        fallback.fill(fallback_color)
        return fallback

    def _elapsed_ms(self, player_index: int | None = None) -> int:
        if player_index is None:
            return max(0, round(max(self.level_elapsed) * 1000))
        return max(0, round(self.level_elapsed[player_index] * 1000))

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        minutes, remaining = divmod(milliseconds, 60_000)
        seconds, millis = divmod(remaining, 1_000)
        return f"{minutes:02}:{seconds:02}.{millis:03}"

    def _finish_player_level(self, player_index: int) -> None:
        if self.state != "playing" or self.reached_goal[player_index]:
            return
        self.reached_goal[player_index] = True
        elapsed = self._elapsed_ms(player_index)
        if player_index == 0:
            self.total_time_p1 += elapsed
        else:
            self.total_time_p2 += elapsed
        if not all(self.reached_goal):
            return

        if self.current_level < self.max_levels:
            self._start_next_level()
            return

        self.final_elapsed_ms = self.total_time_p1 + self.total_time_p2
        if self.total_time_p1 < self.total_time_p2:
            self.winner_index = 0
        elif self.total_time_p2 < self.total_time_p1:
            self.winner_index = 1
        else:
            self.winner_index = None
        self.state = "victory"
        if not self.victory_sound_played:
            self.victory_sound_played = True
            if self.victory_sound is not None:
                try:
                    self.victory_sound.play()
                except pygame.error:
                    pass
        try:
            database.save_play(self.maze, steps=0, elapsed_ms=self.total_time_p1, player_name=self.player_names[0])
            database.save_play(self.maze, steps=0, elapsed_ms=self.total_time_p2, player_name=self.player_names[1])
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.record_save_error = str(exc)

    def _start_next_level(self) -> None:
        self.current_level += 1
        self.maze = generate_maze(rows=self.rows, cols=self.cols)
        start_row, start_col = self.maze.start
        self.players = (
            Player(start_col, start_row, controls="wasd", character_id=1, spawn_offset=(-2.5, 0)),
            Player(start_col, start_row, controls="arrows", character_id=2, spawn_offset=(2.5, 0)),
        )
        self.wall_tile = self._load_map_tile("wall.png", config.COLOR_WALL)
        self.path_tile = self._load_map_tile("path.png", config.COLOR_PATH)
        self.finish_tile = self._load_map_tile("finish.png", config.COLOR_END)
        self._map_cache.clear()
        self.level_elapsed = [0.0, 0.0]
        self.reached_goal = [False, False]
        self.countdown_elapsed = 0.0
        self.state = "countdown"

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if self.show_confirm_popup:
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    self.show_confirm_popup = False
                elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN):
                    self.confirm_selected = 1 - self.confirm_selected
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if self.confirm_selected == 0:
                        self.show_confirm_popup = False
                    else:
                        return config.STATE_MENU
                return None
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                _, continue_rect, exit_rect = confirm_dialog_rects(self.screen.get_size())
                if continue_rect.collidepoint(event.pos):
                    play_ui_click()
                    self.show_confirm_popup = False
                elif exit_rect.collidepoint(event.pos):
                    play_ui_click()
                    return config.STATE_MENU
            return None

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.show_confirm_popup = True
            self.confirm_selected = 0
            return None
        if self.state == "countdown":
            return None
        if self.state == "victory":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return config.STATE_MENU
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.back_button.collidepoint(event.pos):
                    play_ui_click()
                    return config.STATE_MENU
        return None

    def update(self, dt: float) -> None:
        frame_time = max(0.0, float(dt))
        if self.show_confirm_popup:
            return
        self.hud_idle_time += frame_time
        if self.state == "countdown":
            self.countdown_elapsed += frame_time
            if self.countdown_elapsed >= 4.0:
                self.state = "playing"
            return
        if self.state != "playing":
            return
        keys = pygame.key.get_pressed()
        goal_row, goal_col = self.maze.goal
        for index, player in enumerate(self.players):
            if self.reached_goal[index]:
                continue
            self.level_elapsed[index] += frame_time
            player.update(keys, self.maze.grid, dt)
            if player.grid_x == goal_col and player.grid_y == goal_row:
                self._finish_player_level(index)
                if self.state != "playing":
                    break

    def _scaled_map(self, cell: int, rows: int, cols: int) -> pygame.Surface:
        cached = self._map_cache.get(cell)
        if cached is not None:
            return cached
        wall = pygame.transform.scale(self.wall_tile, (cell, cell))
        path = pygame.transform.scale(self.path_tile, (cell, cell))
        result = pygame.Surface((cols * cell, rows * cell))
        for row_index, row in enumerate(self.maze.grid):
            for col_index, value in enumerate(row):
                result.blit(wall if value == WALL else path, (col_index * cell, row_index * cell))
        self._map_cache[cell] = result
        return result

    def _idle_portrait(self, player_index: int, size: int = 40) -> pygame.Surface:
        """Render a player's idle animation into a compact HUD portrait."""
        player = self.players[player_index]
        idle_frames = player.animations.get("idle", [])
        if idle_frames:
            if Player._is_gif(idle_frames[0]):
                animation = idle_frames[0]
                source = animation.current_surface
                frame = pygame.Surface(source.get_size(), pygame.SRCALPHA)
                animation.render(frame, (0, 0))
                source = frame
            else:
                frame_duration = max(0.05, float(getattr(player, "animation_speed", 0.15)))
                frame_index = int(self.hud_idle_time / frame_duration) % len(idle_frames)
                source = idle_frames[frame_index]
        else:
            source = getattr(player, "image", None)

        portrait = pygame.Surface((size, size), pygame.SRCALPHA)
        if source is None:
            pygame.draw.circle(portrait, (220, 225, 235), portrait.get_rect().center, size // 3)
            return portrait

        source_width, source_height = source.get_size()
        scale = min(size / max(1, source_width), size / max(1, source_height))
        fitted_size = (
            max(1, round(source_width * scale)),
            max(1, round(source_height * scale)),
        )
        fitted = pygame.transform.scale(source, fitted_size)
        portrait.blit(fitted, fitted.get_rect(center=portrait.get_rect().center))
        return portrait

    @staticmethod
    def _fit_hud_name(
        font: pygame.font.Font,
        text: str,
        color: Color,
        max_width: int,
    ) -> pygame.Surface:
        shown = text
        rendered = font.render(shown, True, color)
        while rendered.get_width() > max_width and shown:
            shown = shown[:-1]
            rendered = font.render(shown.rstrip() + "...", True, color)
        return rendered

    def _draw_top_hud(self, screen: pygame.Surface) -> None:
        """Draw both player name cards and the shared green race timer."""
        width = screen.get_width()
        accents = ((72, 218, 255), (255, 184, 86))
        screen_margin = 16
        card_height = 56
        portrait_size = 40
        gap = 9
        max_card_width = max(112, (width - 48) // 2)

        for index, right_aligned in ((0, False), (1, True)):
            name = self._fit_hud_name(
                self.fonts.medium,
                self.player_names[index],
                accents[index],
                max(20, max_card_width - 20 - portrait_size - gap),
            )
            card_width = min(
                max_card_width,
                name.get_width() + 20 + portrait_size + gap,
            )
            card = pygame.Surface((card_width, card_height), pygame.SRCALPHA)
            portrait = self._idle_portrait(index, portrait_size)

            if right_aligned:
                portrait_rect = portrait.get_rect(midright=(card_width - 8, card_height // 2))
                name_rect = name.get_rect(
                    midright=(portrait_rect.left - gap, card_height // 2)
                )
                card_x = width - screen_margin - card_width
            else:
                portrait_rect = portrait.get_rect(midleft=(8, card_height // 2))
                name_rect = name.get_rect(
                    midleft=(portrait_rect.right + gap, card_height // 2)
                )
                card_x = screen_margin

            card.blit(portrait, portrait_rect)
            card.blit(name, name_rect)
            screen.blit(card, (card_x, 12))

            accumulated = self.total_time_p1 if index == 0 else self.total_time_p2
            elapsed = accumulated + (0 if self.reached_goal[index] else self._elapsed_ms(index))
            timer_text = self._format_time(elapsed)
            if self.reached_goal[index]:
                timer_text = f"DONE  {timer_text}"
            timer = self.fonts.small.render(timer_text, True, accents[index])
            timer_y = 12 + card_height + 4
            if right_aligned:
                screen.blit(timer, timer.get_rect(topright=(width - screen_margin, timer_y)))
            else:
                screen.blit(timer, (screen_margin, timer_y))

    def draw(self) -> None:
        screen = self.screen
        screen.fill(config.COLOR_BG)
        rows, cols = self.maze.rows, self.maze.cols
        cell = max(1, min(self.cell_size, screen.get_width() // cols, screen.get_height() // rows))
        offset_x = (screen.get_width() - cols * cell) // 2
        offset_y = (screen.get_height() - rows * cell) // 2
        screen.blit(self._scaled_map(cell, rows, cols), (offset_x, offset_y))

        finish = pygame.transform.scale(self.finish_tile, (cell, cell))
        goal_row, goal_col = self.maze.goal
        screen.blit(finish, (offset_x + goal_col * cell, offset_y + goal_row * cell))
        _draw_gif(self.finish_animation, screen,
                  (offset_x + goal_col * cell, offset_y + goal_row * cell), cell)

        players_near_each_other = (
            abs(self.players[0].x - self.players[1].x) < self.cell_size
            and abs(self.players[0].y - self.players[1].y) < self.cell_size
        )
        for player_index, player in enumerate(self.players):
            # Player coordinates use the base CELL_SIZE; scale positions and
            # sprite dimensions together so large mazes remain legible.
            scale = cell / self.cell_size
            player.draw(
                screen,
                offset_x - player.x * (1 - scale),
                offset_y - player.y * (1 - scale),
                visual_scale=scale,
            )
            sprite = getattr(player, "image", None)
            sprite_height = sprite.get_height() if sprite is not None else player.visual_size
            center = (
                round(offset_x + player.x * scale),
                round(offset_y + player.y * scale),
            )
            name_surface = self.fonts.small.render(
                self.player_names[player_index],
                True,
                (250, 250, 255),
            )
            badge = pygame.Surface(
                (name_surface.get_width() + 14, name_surface.get_height() + 8),
                pygame.SRCALPHA,
            )
            badge.blit(name_surface, (7, 4))
            badge_y = center[1] - round(sprite_height * scale) // 2 - 4
            if players_near_each_other:
                if player_index == 0:
                    badge_rect = badge.get_rect(bottomright=(center[0] - 5, badge_y))
                else:
                    badge_rect = badge.get_rect(bottomleft=(center[0] + 5, badge_y))
            else:
                badge_rect = badge.get_rect(midbottom=(center[0], badge_y))
            # At the maze's top edge, put the avatar label below the sprite so
            # it stays clear of the fixed HUD cards and timer.
            if badge_rect.top < 72:
                label_y = center[1] + round(sprite_height * scale) // 2 + 4
                if players_near_each_other and player_index == 0:
                    badge_rect = badge.get_rect(topright=(center[0] - 5, label_y))
                elif players_near_each_other:
                    badge_rect = badge.get_rect(topleft=(center[0] + 5, label_y))
                else:
                    badge_rect = badge.get_rect(midtop=(center[0], label_y))
            badge_rect.clamp_ip(screen.get_rect())
            screen.blit(badge, badge_rect)

        self._draw_top_hud(screen)

        if self.state == "countdown":
            elapsed = min(3.999, max(0.0, self.countdown_elapsed))
            label = ("3", "2", "1", "START!")[int(elapsed)]
            fade = min(255, int(min(elapsed % 1.0, 1.0 - (elapsed % 1.0)) * 510 + 90))
            countdown = self.victory_font.render(label, True, (255, 255, 255))
            countdown.set_alpha(fade)
            screen.blit(countdown, countdown.get_rect(center=screen.get_rect().center))
            level = self.fonts.medium.render(
                f"LEVEL {self.current_level}/{self.max_levels}", True, (255, 220, 90)
            )
            screen.blit(level, level.get_rect(center=(screen.get_width() // 2, screen.get_height() // 2 + 58)))

        if self.state == "victory":
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 165))
            screen.blit(overlay, (0, 0))
            panel_rect = self.victory_panel.get_rect(center=screen.get_rect().center)
            screen.blit(self.victory_panel, panel_rect)
            winner_label = (
                f"OVERALL WINNER: {self.player_names[self.winner_index]}"
                if self.winner_index is not None else "OVERALL RESULT: TIE"
            )
            winner_text = self.fonts.medium.render(winner_label, True, (255, 220, 90))
            total = self.total_time_p1 if self.winner_index == 0 else self.total_time_p2
            time_label = (
                f"Total Time (3 Maps): {self._format_time(total)}"
                if self.winner_index is not None else
                f"P1 {self._format_time(self.total_time_p1)}  |  P2 {self._format_time(self.total_time_p2)}"
            )
            time_text = self.fonts.small.render(time_label, True, (255, 255, 255))
            screen.blit(winner_text, winner_text.get_rect(center=(panel_rect.centerx, panel_rect.centery - 60)))
            if self.winner_index is not None:
                portrait = self._idle_portrait(self.winner_index, 76)
                screen.blit(portrait, portrait.get_rect(center=(panel_rect.centerx, panel_rect.centery + 18)))
            screen.blit(time_text, time_text.get_rect(center=(panel_rect.centerx, panel_rect.centery + 92)))
            hover = self.back_button.collidepoint(pygame.mouse.get_pos())
            fill = (54, 112, 142) if hover else (38, 80, 108)
            pygame.draw.rect(screen, fill, self.back_button, border_radius=10)
            pygame.draw.rect(screen, (100, 225, 240), self.back_button, width=2, border_radius=10)
            draw_hover_arrow(screen, self.back_button, hover)
            back_text = self.fonts.medium.render("Return to Menu", True, (255, 255, 255))
            screen.blit(back_text, back_text.get_rect(center=self.back_button.center))
            hint = self.fonts.small.render("Press ENTER or ESC to return", True, (185, 195, 208))
            screen.blit(hint, hint.get_rect(center=(screen.get_width() // 2, screen.get_height() - 18)))
        if self.show_confirm_popup:
            draw_confirm_dialog(screen, self.victory_font, self.fonts.medium, self.confirm_selected)
