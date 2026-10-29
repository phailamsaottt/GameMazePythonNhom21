from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
import sqlite3
from typing import Any, Callable, NamedTuple

import pygame

import config
import database
import records
from player import Player
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


def _load_victory_sound() -> pygame.mixer.Sound | None:
    """Load the finish cue safely, returning None if audio is unavailable."""
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
        self.state = "playing"
        self.winner_index: int | None = None
        self.record_save_error: str | None = None
        self.victory_sound = _load_victory_sound()
        self.victory_sound_played = False
        self.elapsed_time = 0.0
        self.final_elapsed_ms: int | None = None
        self.hud_idle_time = 0.0

        self.fonts = Fonts(
            _load_font(config.FONT_SIZE_SMALL),
            _load_font(config.FONT_SIZE_MEDIUM),
            _load_font(config.FONT_SIZE_LARGE),
        )
        self.timer_font = _load_font(28)
        self.victory_font = _load_font(34)
        self.cell_size = max(1, int(config.CELL_SIZE))
        self.wall_tile = self._load_map_tile("wall.png", config.COLOR_WALL)
        self.path_tile = self._load_map_tile("path.png", config.COLOR_PATH)
        self.finish_tile = self._load_map_tile("finish.png", config.COLOR_END)
        panel_path = Path(config.BASE_DIR) / "Assets" / "images" / "UI" / "panel.png"
        self.victory_panel = self._load_image(panel_path)
        if self.victory_panel is None:
            self.victory_panel = pygame.Surface((560, 300), pygame.SRCALPHA)
            self.victory_panel.fill((8, 12, 20, 230))
        else:
            self.victory_panel = pygame.transform.scale(self.victory_panel, (560, 300))

        self.back_button = pygame.Rect(screen.get_width() // 2 - 120, screen.get_height() // 2 + 100, 240, 48)
        self._map_cache: dict[int, pygame.Surface] = {}

    @staticmethod
    def _load_image(path: Path) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(path))
            return image.convert_alpha() if pygame.display.get_surface() else image.copy()
        except (pygame.error, OSError, ValueError):
            return None

    def _load_map_tile(self, filename: str, fallback_color: tuple[int, int, int]) -> pygame.Surface:
        candidates = (
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

    def _elapsed_ms(self) -> int:
        if self.final_elapsed_ms is not None:
            return self.final_elapsed_ms
        return max(0, round(self.elapsed_time * 1000))

    @staticmethod
    def _format_time(milliseconds: int) -> str:
        minutes, remaining = divmod(milliseconds, 60_000)
        seconds, millis = divmod(remaining, 1_000)
        return f"{minutes:02}:{seconds:02}.{millis:03}"

    def _finish(self, player_index: int) -> None:
        if self.state != "playing":
            return
        self.final_elapsed_ms = self._elapsed_ms()
        self.winner_index = player_index
        self.state = "victory"
        if not self.victory_sound_played:
            self.victory_sound_played = True
            if self.victory_sound is not None:
                try:
                    self.victory_sound.play()
                except pygame.error:
                    pass
        try:
            database.save_play(
                self.maze,
                steps=0,
                elapsed_ms=self.final_elapsed_ms,
                player_name=self.player_names[player_index],
            )
        except (sqlite3.Error, OSError, ValueError) as exc:
            self.record_save_error = str(exc)

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return config.STATE_MENU
        if self.state == "victory":
            if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return config.STATE_MENU
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if self.back_button.collidepoint(event.pos):
                    return config.STATE_MENU
        return None

    def update(self, dt: float) -> None:
        if self.state != "playing":
            return
        frame_time = max(0.0, float(dt))
        self.elapsed_time += frame_time
        self.hud_idle_time += frame_time
        keys = pygame.key.get_pressed()
        for player in self.players:
            player.update(keys, self.maze.grid, dt)

        goal_row, goal_col = self.maze.goal
        for index, player in enumerate(self.players):
            if player.grid_x == goal_col and player.grid_y == goal_row:
                self._finish(index)
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
        timer = self.timer_font.render(self._format_time(self._elapsed_ms()), True, (120, 255, 120))
        timer_rect = pygame.Rect(0, 0, timer.get_width() + 28, timer.get_height() + 14)
        timer_rect.midtop = (width // 2, 12)
        timer_card = pygame.Surface(timer_rect.size, pygame.SRCALPHA)
        pygame.draw.rect(timer_card, (8, 12, 10, 220), timer_card.get_rect(), border_radius=8)
        screen.blit(timer_card, timer_rect)
        screen.blit(timer, timer.get_rect(center=timer_rect.center))

        accents = ((72, 218, 255), (255, 184, 86))
        screen_margin = 16
        card_height = 56
        portrait_size = 40
        gap = 9
        max_card_width = max(112, (width - timer_rect.width - 48) // 2)

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
            pygame.draw.rect(card, (9, 14, 24, 222), card.get_rect(), border_radius=9)
            pygame.draw.rect(card, (*accents[index], 150), card.get_rect(), 1, border_radius=9)
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
            pygame.draw.rect(badge, (12, 18, 27, 210), badge.get_rect(), border_radius=6)
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

        if self.state == "victory" and self.winner_index is not None:
            overlay = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 165))
            screen.blit(overlay, (0, 0))
            panel_rect = self.victory_panel.get_rect(center=screen.get_rect().center)
            screen.blit(self.victory_panel, panel_rect)
            winner = self.player_names[self.winner_index]
            winner_text = self.victory_font.render(f"{winner} WINS!", True, (255, 220, 90))
            time_text = self.fonts.medium.render(
                f"Completion Time: {self._format_time(self._elapsed_ms())}",
                True,
                (240, 245, 250),
            )
            screen.blit(winner_text, winner_text.get_rect(center=(panel_rect.centerx, panel_rect.centery - 55)))
            screen.blit(time_text, time_text.get_rect(center=(panel_rect.centerx, panel_rect.centery + 5)))
            hover = self.back_button.collidepoint(pygame.mouse.get_pos())
            fill = (54, 112, 142) if hover else (38, 80, 108)
            pygame.draw.rect(screen, fill, self.back_button, border_radius=10)
            pygame.draw.rect(screen, (100, 225, 240), self.back_button, width=2, border_radius=10)
            back_text = self.fonts.medium.render("Return to Menu", True, (255, 255, 255))
            screen.blit(back_text, back_text.get_rect(center=self.back_button.center))
            hint = self.fonts.small.render("Press ENTER or ESC to return", True, (185, 195, 208))
            screen.blit(hint, hint.get_rect(center=(screen.get_width() // 2, screen.get_height() - 18)))


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
