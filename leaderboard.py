"""Neon leaderboard screen for completed solo maze runs."""

from __future__ import annotations

from pathlib import Path
import sqlite3
from typing import Any

import pygame

import config
import database


def _load_font(size: int, *, bold: bool = False) -> pygame.font.Font:
    """Load the bundled Roboto font, falling back to a system Roboto face."""
    font_path = Path(config.FONT_ROBOTO_PATH)
    try:
        font = pygame.font.Font(str(font_path), size) if font_path.is_file() else None
    except (pygame.error, OSError):
        font = None
    if font is None:
        return pygame.font.SysFont("Roboto,Arial,Segoe UI,sans-serif", size, bold=bold)
    font.set_bold(bold)
    return font


class LeaderboardScreen:
    """Filter local completed runs by maze difficulty and show their ranks."""

    DIFFICULTIES = {
        "Easy": (15, 15),
        "Medium": (31, 31),
        "Hard": (51, 51),
    }
    COLORS = {
        "background": (20, 25, 35),
        "grid": (27, 35, 49),
        "panel": (29, 38, 54),
        "panel_alt": (34, 44, 62),
        "yellow": (255, 218, 72),
        "silver": (194, 207, 220),
        "bronze": (203, 137, 89),
        "cyan": (62, 235, 239),
        "red": (239, 76, 91),
        "muted": (133, 149, 170),
        "text": (236, 243, 250),
        "dark_border": (58, 72, 91),
    }

    def __init__(self, screen: pygame.Surface) -> None:
        pygame.font.init()
        self.screen = screen
        self.title_font = _load_font(38, bold=True)
        self.header_font = _load_font(16, bold=True)
        self.body_font = _load_font(20)
        self.small_font = _load_font(15, bold=True)
        self.background_image = self._load_background()
        self.selected_difficulty = "Easy"
        self.tab_rects: dict[str, pygame.Rect] = {}
        self.back_rect = pygame.Rect(0, 0, 190, 44)
        self.rows: list[dict[str, Any]] = []
        self.top_rows: list[dict[str, Any]] = []
        self.latest_user_row: dict[str, Any] | None = None
        self.latest_user_rank: int | None = None
        self.load_error: str | None = None
        self._layout(screen.get_size())
        self._reload_data()

    @staticmethod
    def _load_background() -> pygame.Surface | None:
        path = Path(config.BASE_DIR) / "Assets" / "images" / "UI" / "leaderboard_bg.png"
        if not path.is_file():
            return None
        try:
            image = pygame.image.load(str(path))
            if pygame.display.get_surface() is not None:
                image = image.convert()
            return pygame.transform.scale(image, (config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        except (pygame.error, OSError, ValueError):
            return None

    def _layout(self, size: tuple[int, int]) -> None:
        width, height = size
        tab_width, tab_height, gap = 150, 42, 14
        total_width = len(self.DIFFICULTIES) * tab_width + (len(self.DIFFICULTIES) - 1) * gap
        left = (width - total_width) // 2
        self.tab_rects = {
            name: pygame.Rect(left + index * (tab_width + gap), int(height * 0.19), tab_width, tab_height)
            for index, name in enumerate(self.DIFFICULTIES)
        }
        self.back_rect = pygame.Rect(width // 2 - 95, height - 62, 190, 44)

    def _reload_data(self) -> None:
        """Fetch completed solo scores and calculate the selected difficulty ranks."""
        rows, cols = self.DIFFICULTIES[self.selected_difficulty]
        try:
            history = database.fetch_history(mode=getattr(database, "MODE_PLAY", "play"))
        except (sqlite3.Error, OSError) as exc:
            self.load_error = str(exc)
            history = []
        else:
            self.load_error = None

        selected = [
            row
            for row in history
            if int(row.get("maze_rows", -1)) == rows
            and int(row.get("maze_cols", -1)) == cols
            and bool(row.get("found", 1))
        ]
        ranked = sorted(
            selected,
            key=lambda row: (float(row.get("elapsed_ms", 0)), int(row.get("id", 0))),
        )
        self.rows = ranked
        self.top_rows = ranked[:5]

        # This schema does not store player accounts; every play-mode row belongs
        # to the local player, so the latest completed row is the "You" entry.
        self.latest_user_row = max(selected, key=lambda row: int(row.get("id", 0)), default=None)
        self.latest_user_rank = None
        if self.latest_user_row is not None:
            latest_id = self.latest_user_row.get("id")
            self.latest_user_rank = next(
                (
                    index
                    for index, row in enumerate(ranked, start=1)
                    if row.get("id") == latest_id
                ),
                None,
            )

    def refresh(self) -> None:
        """Reload local scores when returning to the leaderboard screen."""
        self._reload_data()

    @staticmethod
    def _format_time(elapsed_ms: Any) -> str:
        try:
            seconds = max(0.0, float(elapsed_ms)) / 1000.0
        except (TypeError, ValueError):
            seconds = 0.0
        return f"{seconds:.2f}s"

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return config.STATE_MENU

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for name, rect in self.tab_rects.items():
                if rect.collidepoint(event.pos):
                    if name != self.selected_difficulty:
                        self.selected_difficulty = name
                        self._reload_data()
                    return None
            if self.back_rect.collidepoint(event.pos):
                return config.STATE_MENU
        return None

    def update(self) -> None:
        """Keep the screen API aligned with the other game screens."""

    def _draw_background(self, target: pygame.Surface) -> None:
        if self.background_image is None:
            target.fill(self.COLORS["background"])
        else:
            target.blit(self.background_image, (0, 0))
            tint = pygame.Surface(target.get_size(), pygame.SRCALPHA)
            tint.fill((*self.COLORS["background"], 100))
            target.blit(tint, (0, 0))
        width, height = target.get_size()
        grid_color = self.COLORS["grid"]
        for x in range(0, width, 40):
            pygame.draw.line(target, grid_color, (x, 0), (x, height), 1)
        for y in range(0, height, 40):
            pygame.draw.line(target, grid_color, (0, y), (width, y), 1)

        cyan = self.COLORS["cyan"]
        yellow = self.COLORS["yellow"]
        corner = 54
        pad = 24
        pygame.draw.lines(
            target,
            cyan,
            False,
            [(pad + corner, pad), (pad, pad), (pad, pad + corner)],
            3,
        )
        pygame.draw.lines(
            target,
            yellow,
            False,
            [(width - pad - corner, height - pad), (width - pad, height - pad),
             (width - pad, height - pad - corner)],
            3,
        )

    def _draw_tabs(self, target: pygame.Surface) -> None:
        mouse_pos = pygame.mouse.get_pos()
        active_colors = {
            "Easy": (31, 166, 153),
            "Medium": (111, 84, 196),
            "Hard": self.COLORS["red"],
        }
        for name, rect in self.tab_rects.items():
            selected = name == self.selected_difficulty
            hovered = rect.collidepoint(mouse_pos)
            if selected:
                color = active_colors.get(name, (62, 81, 105))
            elif hovered:
                color = (62, 81, 105)
            else:
                color = (39, 51, 70)
            pygame.draw.rect(target, color, rect, border_radius=12)
            border = self.COLORS["text"] if selected else self.COLORS["dark_border"]
            pygame.draw.rect(target, border, rect, width=2, border_radius=12)
            label = self.body_font.render(name, True, self.COLORS["text"])
            target.blit(label, label.get_rect(center=rect.center))

    def _rank_color(self, rank: int) -> tuple[int, int, int]:
        return {
            1: self.COLORS["yellow"],
            2: self.COLORS["silver"],
            3: self.COLORS["bronze"],
        }.get(rank, self.COLORS["dark_border"])

    def _mode_color(self, mode: str) -> tuple[int, int, int]:
        if mode == "HARD":
            return self.COLORS["red"]
        if mode == "MEDIUM":
            return (111, 84, 196)
        return (31, 145, 137)

    def _draw_row(
        self,
        target: pygame.Surface,
        rect: pygame.Rect,
        rank: int,
        row: dict[str, Any],
        *,
        user_row: bool = False,
    ) -> None:
        if user_row:
            border = self.COLORS["cyan"]
            fill = (25, 58, 70)
        else:
            border = self._rank_color(rank)
            fill = self.COLORS["panel_alt"] if rank % 2 == 0 else self.COLORS["panel"]

        pygame.draw.rect(target, fill, rect, border_radius=12)
        pygame.draw.rect(target, border, rect, width=2 if rank <= 3 or user_row else 1, border_radius=12)

        rank_center = (rect.x + 34, rect.centery)
        pygame.draw.circle(target, border, rank_center, 16)
        rank_text = self.header_font.render(str(rank) if rank > 0 else "—", True, (18, 25, 35))
        target.blit(rank_text, rank_text.get_rect(center=rank_center))

        player_name = "You" if user_row else str(row.get("player_name") or "Player")
        player_text = self.body_font.render(player_name, True, self.COLORS["text"])
        target.blit(player_text, (rect.x + 78, rect.centery - player_text.get_height() // 2))

        time_text = self.body_font.render(
            self._format_time(row.get("elapsed_ms", 0)), True, self.COLORS["text"]
        )
        time_x = rect.x + int(rect.width * 0.61)
        target.blit(time_text, (time_x, rect.centery - time_text.get_height() // 2))

        mode = self.selected_difficulty.upper()
        badge_text = self.small_font.render(mode, True, self.COLORS["text"])
        badge = pygame.Rect(0, 0, badge_text.get_width() + 24, 28)
        badge.midright = (rect.right - 20, rect.centery)
        pygame.draw.rect(target, self._mode_color(mode), badge, border_radius=14)
        target.blit(badge_text, badge_text.get_rect(center=badge.center))

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        self._layout(target.get_size())
        self._draw_background(target)

        width, height = target.get_size()
        title_shadow = self.title_font.render("LEADERBOARD", True, (7, 11, 19))
        title = self.title_font.render("LEADERBOARD", True, self.COLORS["yellow"])
        target.blit(title_shadow, title_shadow.get_rect(center=(width // 2 + 3, 78)))
        target.blit(title, title.get_rect(center=(width // 2, 75)))
        self._draw_tabs(target)

        table_width = min(980, width - 72)
        table_left = (width - table_width) // 2
        headers_y = int(height * 0.315)
        row_top = headers_y + 30
        row_height = 48
        row_gap = 8

        header_color = self.COLORS["muted"]
        headers = (
            ("Rank", table_left + 18),
            ("Player", table_left + 78),
            ("Time", table_left + int(table_width * 0.61)),
            ("Mode", table_left + int(table_width * 0.82)),
        )
        for label, x in headers:
            text = self.header_font.render(label.upper(), True, header_color)
            target.blit(text, (x, headers_y))

        for index, row in enumerate(self.top_rows, start=1):
            rect = pygame.Rect(
                table_left,
                row_top + (index - 1) * (row_height + row_gap),
                table_width,
                row_height,
            )
            self._draw_row(target, rect, index, row)

        if not self.top_rows:
            empty = self.body_font.render(
                "No scores for this difficulty yet", True, self.COLORS["muted"]
            )
            target.blit(
                empty,
                empty.get_rect(center=(width // 2, row_top + row_height)),
            )

        user_y = row_top + 5 * (row_height + row_gap) + 8
        user_rect = pygame.Rect(table_left, user_y, table_width, row_height)
        if self.latest_user_row is not None and self.latest_user_rank is not None:
            self._draw_row(
                target,
                user_rect,
                self.latest_user_rank,
                self.latest_user_row,
                user_row=True,
            )
        else:
            pygame.draw.rect(target, (25, 58, 70), user_rect, border_radius=12)
            pygame.draw.rect(
                target,
                self.COLORS["cyan"],
                user_rect,
                width=2,
                border_radius=12,
            )
            rank_center = (user_rect.x + 34, user_rect.centery)
            pygame.draw.circle(target, self.COLORS["cyan"], rank_center, 16)
            dash = self.header_font.render("—", True, (18, 25, 35))
            target.blit(dash, dash.get_rect(center=rank_center))
            you_text = self.body_font.render("You", True, self.COLORS["text"])
            target.blit(you_text, (user_rect.x + 78, user_rect.centery - you_text.get_height() // 2))
            note = self.small_font.render(
                "No scores for this difficulty yet", True, self.COLORS["cyan"]
            )
            target.blit(
                note,
                note.get_rect(midright=(user_rect.right - 20, user_rect.centery)),
            )

        mouse_pos = pygame.mouse.get_pos()
        back_fill = (61, 79, 102) if self.back_rect.collidepoint(mouse_pos) else (39, 52, 71)
        pygame.draw.rect(target, back_fill, self.back_rect, border_radius=12)
        pygame.draw.rect(target, self.COLORS["cyan"], self.back_rect, width=2, border_radius=12)
        back_text = self.body_font.render("Back", True, self.COLORS["text"])
        target.blit(back_text, back_text.get_rect(center=self.back_rect.center))

        if self.load_error:
            error = self.small_font.render("Could not load leaderboard data", True, self.COLORS["red"])
            target.blit(error, error.get_rect(center=(width // 2, height - 92)))
