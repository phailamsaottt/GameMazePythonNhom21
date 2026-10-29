"""Player-controlled maze gameplay screen."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

import pygame

import config

try:
    from player_3 import Player
except ModuleNotFoundError as exc:
    if exc.name != "player_3":
        raise
    # This checkout keeps the same player implementation in player.py.
    from player import Player

try:
    from generator_3 import WALL, generate_maze
except ModuleNotFoundError as exc:
    if exc.name != "generator_3":
        raise
    # This checkout keeps the same maze generator in generator.py.
    from generator import WALL, generate_maze


class MazeLike(Protocol):
    grid: list[list[int]]
    start: tuple[int, int]
    goal: tuple[int, int]


class PlayingScreen:
    """Render and update one playable maze, including its victory screen."""

    MAZE_ROWS = 21
    MAZE_COLS = 21
    PANEL_MAX_SIZE = (560, 320)

    def __init__(self, screen: pygame.Surface | None = None) -> None:
        self.screen = screen
        self.state = "playing"
        self.maze = generate_maze(rows=self.MAZE_ROWS, cols=self.MAZE_COLS)
        self.player = self._make_player(self.maze)

        cell_size = max(1, int(config.CELL_SIZE))
        self.wall_tile = self._load_tile(
            "wall.png", cell_size, getattr(config, "COLOR_WALL", (24, 24, 32))
        )
        self.path_tile = self._load_tile(
            "path.png", cell_size, getattr(config, "COLOR_PATH", (230, 230, 230))
        )
        self.finish_icon = self._load_tile(
            "finish.png", cell_size, getattr(config, "COLOR_END", (231, 76, 60))
        )
        self.panel_img = self._load_panel()

        title_size = int(getattr(config, "FONT_SIZE_TITLE", 52))
        message_size = int(getattr(config, "FONT_SIZE_MEDIUM", 30))
        if pygame.font.get_init():
            self.title_font = pygame.font.Font(None, title_size)
            self.message_font = pygame.font.Font(None, message_size)
        else:
            pygame.font.init()
            self.title_font = pygame.font.Font(None, title_size)
            self.message_font = pygame.font.Font(None, message_size)

    @staticmethod
    def _make_player(maze: MazeLike) -> Player:
        """Create a player at the maze start (maze coordinates are row, column)."""
        start_row, start_col = maze.start
        return Player(start_grid_x=start_col, start_grid_y=start_row)

    @staticmethod
    def _asset_candidates(*parts: str) -> tuple[Path, ...]:
        base = Path(config.BASE_DIR)
        # Include both spellings because the existing project assets use "Map"
        # while other environments may store the folder as the requested "map".
        return (
            base / "Assets" / "images" / "map" / Path(*parts),
            base / "Assets" / "images" / "Map" / Path(*parts),
            base / "assets" / "images" / "map" / Path(*parts),
            Path(__file__).resolve().parent / "Assets" / "images" / "Map" / Path(*parts),
        )

    @staticmethod
    def _load_image(path: Path) -> pygame.Surface | None:
        try:
            image = pygame.image.load(str(path))
            if pygame.display.get_surface() is not None:
                image = image.convert_alpha()
            else:
                image = image.copy()
            return image
        except (pygame.error, OSError, ValueError):
            return None

    @classmethod
    def _load_tile(
        cls, filename: str, cell_size: int, fallback_color: tuple[int, int, int]
    ) -> pygame.Surface:
        for path in cls._asset_candidates(filename):
            if not path.is_file():
                continue
            image = cls._load_image(path)
            if image is not None:
                return pygame.transform.scale(image, (cell_size, cell_size))

        fallback = pygame.Surface((cell_size, cell_size), pygame.SRCALPHA)
        fallback.fill((*fallback_color, 255))
        return fallback

    def _load_panel(self) -> pygame.Surface:
        screen = self.screen
        if screen is None:
            screen = pygame.display.get_surface()
        screen_size = (
            screen.get_size()
            if screen is not None
            else (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
        )
        panel_size = (
            max(1, min(self.PANEL_MAX_SIZE[0], screen_size[0] - 40)),
            max(1, min(self.PANEL_MAX_SIZE[1], screen_size[1] - 40)),
        )

        panel_path = Path(config.BASE_DIR) / "Assets" / "images" / "UI" / "panel.png"
        panel_image = self._load_image(panel_path) if panel_path.is_file() else None
        if panel_image is not None:
            return pygame.transform.scale(panel_image, panel_size)

        fallback = pygame.Surface(panel_size, pygame.SRCALPHA)
        fallback.fill((0, 0, 0, 220))
        return fallback

    def reset(self) -> None:
        """Start a fresh maze when the player chooses Play again."""
        self.maze = generate_maze(rows=self.MAZE_ROWS, cols=self.MAZE_COLS)
        self.player = self._make_player(self.maze)
        self.state = "playing"

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if self.state == "playing":
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return config.STATE_MENU
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
        if self.state != "playing":
            return

        keys = pygame.key.get_pressed()
        self.player.update(keys, self.maze.grid, dt)
        goal_row, goal_col = self.maze.goal
        if self.player.grid_x == goal_col and self.player.grid_y == goal_row:
            self.state = "victory"

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen
        if target is None:
            target = self.screen
        if target is None:
            target = pygame.display.get_surface()
        if target is None:
            raise RuntimeError("PlayingScreen.draw() requires a display surface")

        target.fill(getattr(config, "COLOR_BG", (30, 30, 40)))
        grid = self.maze.grid
        rows = len(grid)
        cols = max((len(row) for row in grid), default=0)
        cell_size = max(1, int(config.CELL_SIZE))
        offset_x = (target.get_width() - cols * cell_size) // 2
        offset_y = (target.get_height() - rows * cell_size) // 2

        for row_index, row in enumerate(grid):
            for col_index, cell in enumerate(row):
                tile = self.wall_tile if cell == WALL else self.path_tile
                target.blit(
                    tile,
                    (offset_x + col_index * cell_size, offset_y + row_index * cell_size),
                )

        goal_row, goal_col = self.maze.goal
        target.blit(
            self.finish_icon,
            (offset_x + goal_col * cell_size, offset_y + goal_row * cell_size),
        )
        self.player.draw(target, offset_x, offset_y)

        if self.state == "victory":
            overlay = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 150))
            target.blit(overlay, (0, 0))

            panel_rect = self.panel_img.get_rect(center=target.get_rect().center)
            target.blit(self.panel_img, panel_rect)

            title = self.title_font.render("Congratulations!", True, (255, 255, 255))
            message = self.message_font.render(
                "Click to return to Menu", True, (240, 240, 240)
            )
            title_rect = title.get_rect(center=(panel_rect.centerx, panel_rect.centery - 24))
            message_rect = message.get_rect(center=(panel_rect.centerx, panel_rect.centery + 30))
            target.blit(title, title_rect)
            target.blit(message, message_rect)
