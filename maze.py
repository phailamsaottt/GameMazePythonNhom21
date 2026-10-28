"""
entities/maze.py - Pygame visual entity converting a 2D numerical maze matrix into wall and path surfaces.
"""

from __future__ import annotations
import math
from typing import Any, Final

import pygame

import config
from algorithms.generator import Maze, PATH, WALL
from algorithms.pathfinding import SearchStep

Color = tuple[int, int, int]


def _adjust_color(color: Color, factor: float) -> Color:
    return (
        max(0, min(255, int(color[0] * factor))),
        max(0, min(255, int(color[1] * factor))),
        max(0, min(255, int(color[2] * factor))),
    )


class MazeEntity(pygame.sprite.Sprite):
    """
    Converts a 2D numerical matrix (from algorithms/generator.py) into Pygame block surfaces.
    WALL (1) -> Wall block surface with 3D bevel.
    PATH (0) -> Passable path tile surface.
    """

    def __init__(
        self,
        maze: Maze | list[list[int]] | None = None,
        rows: int = config.DEFAULT_ROWS,
        cols: int = config.DEFAULT_COLS,
        cell_size: int | None = None,
        viewport_rect: pygame.Rect | None = None,
        start: tuple[int, int] | None = None,
        goal: tuple[int, int] | None = None,
        padding: int = 16,
    ) -> None:
        super().__init__()

        self.padding: Final[int] = padding
        self.viewport_rect = pygame.Rect(
            viewport_rect
            if viewport_rect is not None
            else (padding, padding, config.WINDOW_WIDTH - padding * 2, config.WINDOW_HEIGHT - padding * 2)
        )
        self.explicit_cell_size = cell_size

        self.rows = max(1, rows)
        self.cols = max(1, cols)
        self.grid: list[list[int]] = []
        self.start: tuple[int, int] = start or (1, 1)
        self.goal: tuple[int, int] = goal or (self.rows - 2, self.cols - 2)

        self.cell_size: int = config.CELL_SIZE
        self.offset_x: int = 0
        self.offset_y: int = 0
        self.image: pygame.Surface = pygame.Surface((1, 1))
        self.rect: pygame.Rect = self.image.get_rect()

        # Reusable overlay surface for pathfinding to avoid per-frame GC churn
        self._visited_surf: pygame.Surface | None = None

        # Reusable tile surfaces
        self.wall_tile: pygame.Surface = pygame.Surface((1, 1))
        self.path_tile: pygame.Surface = pygame.Surface((1, 1))
        self.start_tile: pygame.Surface = pygame.Surface((1, 1))
        self.goal_tile: pygame.Surface = pygame.Surface((1, 1))

        # Palette
        self.wall_color: Color = config.COLOR_WALL
        self.wall_highlight: Color = _adjust_color(config.COLOR_WALL, 1.45)
        self.wall_shadow: Color = _adjust_color(config.COLOR_WALL, 0.65)
        self.path_color: Color = config.COLOR_PATH
        self.grid_line_color: Color = _adjust_color(config.COLOR_PATH, 0.92)
        self.start_color: Color = config.COLOR_START
        self.goal_color: Color = config.COLOR_END

        if maze is not None:
            self.set_maze(maze, start=start, goal=goal)
        else:
            self.grid = [[WALL] * self.cols for _ in range(self.rows)]
            self._recalculate_geometry()
            self._bake_base_surface()

    def set_maze(
        self,
        maze: Maze | list[list[int]],
        start: tuple[int, int] | None = None,
        goal: tuple[int, int] | None = None,
    ) -> None:
        """Load numerical matrix or Maze instance from algorithms/generator.py."""
        if isinstance(maze, Maze):
            self.grid = maze.grid
            self.rows, self.cols = max(1, maze.rows), max(1, maze.cols)
            self.start, self.goal = maze.start, maze.goal
        else:
            self.grid = maze
            self.rows = max(1, len(maze))
            self.cols = max(1, len(maze[0])) if len(maze) > 0 else 1
            self.start = start or (1, 1)
            self.goal = goal or (self.rows - 2, self.cols - 2)

        self._recalculate_geometry()
        self._bake_base_surface()

    def set_viewport(self, viewport_rect: pygame.Rect) -> None:
        self.viewport_rect = pygame.Rect(viewport_rect)
        self._recalculate_geometry()
        self._bake_base_surface()

    def _recalculate_geometry(self) -> None:
        if self.explicit_cell_size is not None:
            self.cell_size = max(4, self.explicit_cell_size)
        else:
            avail_w = max(100, self.viewport_rect.width)
            avail_h = max(100, self.viewport_rect.height)
            fit_w = avail_w // max(1, self.cols)
            fit_h = avail_h // max(1, self.rows)
            self.cell_size = max(4, min(fit_w, fit_h, config.CELL_SIZE))

        w = self.cols * self.cell_size
        h = self.rows * self.cell_size
        self.offset_x = self.viewport_rect.left + (self.viewport_rect.width - w) // 2
        self.offset_y = self.viewport_rect.top + (self.viewport_rect.height - h) // 2
        self.rect = pygame.Rect(self.offset_x, self.offset_y, w, h)
        self._visited_surf = None
        self._build_tile_templates()

    def _build_tile_templates(self) -> None:
        """Create reusable wall, path, and marker block surfaces for blitting."""
        cs = self.cell_size
        bevel = max(1, cs // 7)

        # 1. Wall Block Image
        wall = pygame.Surface((cs, cs))
        wall.fill(self.wall_color)
        if bevel > 0:
            pygame.draw.rect(wall, self.wall_highlight, (0, 0, cs, bevel))
            pygame.draw.rect(wall, self.wall_highlight, (0, 0, bevel, cs))
            pygame.draw.rect(wall, self.wall_shadow, (0, cs - bevel, cs, bevel))
            pygame.draw.rect(wall, self.wall_shadow, (cs - bevel, 0, bevel, cs))
        self.wall_tile = wall

        # 2. Path Cell Image
        path = pygame.Surface((cs, cs))
        path.fill(self.path_color)
        pygame.draw.rect(path, self.grid_line_color, (0, 0, cs, cs), 1)
        self.path_tile = path

        # 3. Start & Goal Marker Tiles
        self.start_tile = self._create_marker_tile(self.start_color)
        self.goal_tile = self._create_marker_tile(self.goal_color)

    def _create_marker_tile(self, color: Color) -> pygame.Surface:
        cs = self.cell_size
        surf = pygame.Surface((cs, cs), pygame.SRCALPHA)
        pad = max(2, cs // 6)
        badge_rect = pygame.Rect(pad, pad, cs - pad * 2, cs - pad * 2)
        radius = max(2, cs // 5)

        glow_rect = pygame.Rect(pad // 2, pad // 2, cs - pad, cs - pad)
        pygame.draw.rect(surf, (*color, 75), glow_rect, border_radius=4)
        pygame.draw.rect(surf, color, badge_rect, border_radius=radius)
        pygame.draw.rect(surf, (255, 255, 255), badge_rect, width=1, border_radius=radius)
        return surf

    def _bake_base_surface(self) -> None:
        """Convert the number matrix into a composite Pygame Surface."""
        width = max(1, self.cols * self.cell_size)
        height = max(1, self.rows * self.cell_size)
        base = pygame.Surface((width, height), pygame.SRCALPHA)
        cs = self.cell_size

        # Convert matrix cells (WALL=1 -> wall_tile, PATH=0 -> path_tile)
        for r in range(self.rows):
            row_y = r * cs
            for c in range(self.cols):
                tile = self.wall_tile if self.grid[r][c] == WALL else self.path_tile
                base.blit(tile, (c * cs, row_y))

        # Blit terminal markers
        if 0 <= self.start[0] < self.rows and 0 <= self.start[1] < self.cols:
            base.blit(self.start_tile, (self.start[1] * cs, self.start[0] * cs))
        if 0 <= self.goal[0] < self.rows and 0 <= self.goal[1] < self.cols:
            base.blit(self.goal_tile, (self.goal[1] * cs, self.goal[0] * cs))

        # Perimeter border
        border_width = max(2, cs // 7)
        pygame.draw.rect(base, _adjust_color(self.wall_highlight, 1.2), (0, 0, width, height), border_width)
        self.image = base

    # -------------------------------------------------------------------------
    # Coordinate Transforms
    # -------------------------------------------------------------------------
    def grid_to_pixel_rect(self, r: int, c: int) -> pygame.Rect:
        return pygame.Rect(self.offset_x + c * self.cell_size, self.offset_y + r * self.cell_size, self.cell_size, self.cell_size)

    def grid_to_center_pos(self, r: int, c: int) -> tuple[int, int]:
        return (
            self.offset_x + c * self.cell_size + self.cell_size // 2,
            self.offset_y + r * self.cell_size + self.cell_size // 2,
        )

    def pixel_to_grid(self, px: int, py: int) -> tuple[int, int] | None:
        if not self.rect.collidepoint(px, py):
            return None
        c = (px - self.offset_x) // self.cell_size
        r = (py - self.offset_y) // self.cell_size
        return (int(r), int(c)) if 0 <= r < self.rows and 0 <= c < self.cols else None

    def is_valid_path(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols and self.grid[r][c] == PATH

    # -------------------------------------------------------------------------
    # Drawing & Overlays
    # -------------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        surface.blit(self.image, self.rect)

    def draw_pathfinding_overlay(
        self,
        surface: pygame.Surface,
        step: SearchStep,
        trace_color: Color | None = None,
        visited_color: Color = config.COLOR_VISITED,
        draw_head: bool = True,
    ) -> None:
        cs = self.cell_size
        pad = max(1, cs // 8)

        if trace_color is None:
            trace_map = {"BFS": config.COLOR_BFS_TRACE, "DFS": config.COLOR_DFS_TRACE, "A*": config.COLOR_ASTAR_TRACE}
            trace_color = trace_map.get(step.algorithm, config.COLOR_PRIMARY)

        # Visited nodes using cached alpha surface
        if step.visited:
            if self._visited_surf is None or self._visited_surf.get_size() != (self.rect.width, self.rect.height):
                self._visited_surf = pygame.Surface((self.rect.width, self.rect.height), pygame.SRCALPHA)
            else:
                self._visited_surf.fill((0, 0, 0, 0))

            v_surf = self._visited_surf
            alpha_color = (*visited_color, 110)
            inner_pad = max(1, cs // 7)
            cell_w = cs - inner_pad * 2

            for vr, vc in step.visited:
                if (vr, vc) != self.start and (vr, vc) != self.goal:
                    pygame.draw.rect(v_surf, alpha_color, (vc * cs + inner_pad, vr * cs + inner_pad, cell_w, cell_w), border_radius=2)
            surface.blit(v_surf, self.rect)

        # Frontier boundary
        if step.frontier and not step.is_done:
            frontier_color = _adjust_color(trace_color, 1.2)
            f_size = cs - pad * 2
            ox, oy = self.offset_x, self.offset_y
            for fr, fc in step.frontier:
                if (fr, fc) != self.start and (fr, fc) != self.goal:
                    pygame.draw.rect(surface, frontier_color, (ox + fc * cs + pad, oy + fr * cs + pad, f_size, f_size), width=1, border_radius=2)

        # Reconstructed solution path
        if step.path:
            self.draw_solution_path(surface, step.path, trace_color)

        # Active head
        if draw_head and not step.is_done and step.current:
            center = self.grid_to_center_pos(*step.current)
            head_rad = max(3, cs // 3)
            pulse = math.sin(pygame.time.get_ticks() * 0.012) * (cs * 0.15)
            pygame.draw.circle(surface, (255, 255, 255), center, max(head_rad + 2, int(head_rad + pulse)), width=2)
            pygame.draw.circle(surface, config.COLOR_PLAYER, center, head_rad)

    def draw_solution_path(
        self,
        surface: pygame.Surface,
        path: list[tuple[int, int]],
        color: Color,
        width: int | None = None,
    ) -> None:
        if not path or len(path) < 2:
            return
        line_w = width if width is not None else max(3, self.cell_size // 3)
        pts = [self.grid_to_center_pos(r, c) for r, c in path]
        pygame.draw.lines(surface, color, False, pts, line_w)
        joint_rad = max(2, line_w // 2)
        for pt in pts:
            pygame.draw.circle(surface, color, pt, joint_rad)

    def draw_race_overlay(
        self,
        surface: pygame.Surface,
        runners: dict[str, dict[str, Any]],
    ) -> None:
        cs = self.cell_size
        corner = max(2, cs // 3)
        ox, oy = self.offset_x, self.offset_y

        for name, data in runners.items():
            step: SearchStep | None = data.get("step")
            color: Color = data.get("color", config.COLOR_PRIMARY)
            if not step or not step.visited:
                continue

            for vr, vc in step.visited:
                if (vr, vc) == self.start or (vr, vc) == self.goal:
                    continue
                px, py = ox + vc * cs, oy + vr * cs
                if name == "BFS":
                    rect = (px, py, corner, corner)
                elif name == "DFS":
                    rect = (px + cs - corner, py, corner, corner)
                elif name == "A*":
                    rect = (px, py + cs - corner, corner, corner)
                else:
                    rect = (px + (cs - corner) // 2, py + (cs - corner) // 2, corner, corner)
                pygame.draw.rect(surface, color, rect, border_radius=1)

        for data in runners.values():
            step = data.get("step")
            color = data.get("color", config.COLOR_PRIMARY)
            if step and step.path and step.found:
                self.draw_solution_path(surface, step.path, color, width=max(2, cs // 4))

        for data in runners.values():
            step = data.get("step")
            color = data.get("color", config.COLOR_PRIMARY)
            if step and not step.is_done and step.current:
                center = self.grid_to_center_pos(*step.current)
                rad = max(3, cs // 3)
                pygame.draw.circle(surface, color, center, rad)
                pygame.draw.circle(surface, (255, 255, 255), center, rad, width=1)
