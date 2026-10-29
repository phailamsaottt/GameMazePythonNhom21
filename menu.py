from __future__ import annotations

from pathlib import Path
from typing import Any

import pygame

try:
    import gif_pygame
except ImportError:
    gif_pygame = None

import config
from player import Player


def _load_font(size: int) -> pygame.font.Font:
    """Load the project's Roboto font, with a Roboto system-font fallback."""
    roboto_path = Path(config.FONT_ROBOTO_PATH)
    if roboto_path.is_file():
        try:
            return pygame.font.Font(str(roboto_path), size)
        except Exception:
            pass
    return pygame.font.SysFont("Roboto,Arial,Segoe UI,sans-serif", size)


def _load_title_font(size: int) -> pygame.font.Font:
    """Load Jim Nightshade for the on-screen game title."""
    title_path = Path(config.FONT_JIM_NIGHTSHADE_PATH)
    if title_path.is_file():
        try:
            return pygame.font.Font(str(title_path), size)
        except Exception:
            pass
    return _load_font(size)


def _load_sound() -> pygame.mixer.Sound | None:
    """Nạp âm thanh click từ config.SOUNDS_DIR nếu có."""
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except Exception:
            return None

    sounds_dir = Path(config.SOUNDS_DIR)
    candidates = (
        "click.wav",
        "click.mp3",
        "click.ogg",
        "Wood Block1.mp3",
        "Retro1.mp3",
        "Minimalist1.mp3",
    )
    for name in candidates:
        sound_path = sounds_dir / name
        if sound_path.exists():
            try:
                snd = pygame.mixer.Sound(str(sound_path))
                snd.set_volume(getattr(config, "DEFAULT_VOLUME", 0.5))
                return snd
            except Exception:
                continue
    return None


class Button:
    """Lớp Button có thể tái sử dụng theo phong cách pixel-art retro."""

    def __init__(
        self,
        x: int,
        y: int,
        width: int,
        height: int,
        text: str,
        font: pygame.font.Font,
        base_image: pygame.Surface | None = None,
        hover_image: pygame.Surface | None = None,
        target_state: str | None = None,
        color_theme: tuple[
            tuple[int, int, int],
            tuple[int, int, int],
            tuple[int, int, int],
            tuple[int, int, int],
        ] | None = None,
    ) -> None:
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.text = text
        self.font = font
        self.target_state = target_state
        self.color_theme = color_theme

        self.rect = pygame.Rect(self.x, self.y, self.width, self.height)
        self.is_hovered: bool = False

        # Xử lý hình ảnh nếu được cung cấp
        self.base_image = (
            pygame.transform.scale(base_image, (self.width, self.height))
            if base_image is not None
            else None
        )
        self.hover_image = (
            pygame.transform.scale(hover_image, (self.width, self.height))
            if hover_image is not None
            else None
        )

        # Nếu có base_image nhưng chưa có hover_image, tự tạo hiệu ứng sáng khi hover
        if self.base_image is not None and self.hover_image is None:
            hover_surf = self.base_image.copy()
            overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
            overlay.fill((255, 255, 255, 45))
            hover_surf.blit(overlay, (0, 0))
            self.hover_image = hover_surf

    def check_hover(self, mouse_pos: tuple[int, int]) -> bool:
        """Kiểm tra chuột có đang hover qua button hay không."""
        self.is_hovered = self.rect.collidepoint(mouse_pos)
        return self.is_hovered

    def update(self, mouse_pos: tuple[int, int] | None = None) -> bool:
        """Cập nhật trạng thái hover."""
        if mouse_pos is None:
            mouse_pos = pygame.mouse.get_pos()
        return self.check_hover(mouse_pos)

    def is_clicked(self, pos: tuple[int, int]) -> bool:
        """Kiểm tra xem tọa độ pos có nằm trong button hay không."""
        return self.rect.collidepoint(pos)

    def handle_event(self, event: pygame.event.Event) -> bool:
        """Xử lý sự kiện click chuột trái."""
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            return self.is_clicked(event.pos)
        return False

    def draw(self, surface: pygame.Surface) -> None:
        """Vẽ button lên surface với hiệu ứng gỗ retro và text căn giữa hoàn hảo."""
        # 1. Vẽ nền button (Sprite hoặc fallback Rect)
        if self.color_theme is not None:
            base_color, hover_color, border_color, _text_color = self.color_theme
            fill = hover_color if self.is_hovered else base_color
            pygame.draw.rect(surface, fill, self.rect, border_radius=12)
            pygame.draw.rect(surface, border_color, self.rect, width=3, border_radius=12)
            pygame.draw.line(
                surface,
                tuple(min(255, channel + 28) for channel in fill),
                (self.rect.left + 12, self.rect.top + 5),
                (self.rect.right - 12, self.rect.top + 5),
                2,
            )
        elif self.base_image is not None:
            if self.is_hovered and self.hover_image is not None:
                surface.blit(self.hover_image, self.rect)
            else:
                surface.blit(self.base_image, self.rect)
        else:
            # Fallback: Vẽ Rect màu gỗ (139, 90, 43), đổi màu sáng hơn khi hover
            wood_color = (170, 115, 60) if self.is_hovered else (139, 90, 43)
            dark_border = (75, 45, 20)
            highlight_color = (200, 145, 90) if self.is_hovered else (175, 120, 70)
            shadow_color = (95, 55, 25)

            # Khối thân gỗ chính
            pygame.draw.rect(surface, wood_color, self.rect, border_radius=6)

            # Viền pixel-art bao quanh
            pygame.draw.rect(surface, dark_border, self.rect, width=3, border_radius=6)

            # Hiệu ứng nổi 3D vân gỗ: viền trên và trái sáng
            pygame.draw.line(
                surface,
                highlight_color,
                (self.rect.left + 3, self.rect.top + 3),
                (self.rect.right - 4, self.rect.top + 3),
                2,
            )
            pygame.draw.line(
                surface,
                highlight_color,
                (self.rect.left + 3, self.rect.top + 3),
                (self.rect.left + 3, self.rect.bottom - 4),
                2,
            )

            # Viền dưới và phải bóng tối
            pygame.draw.line(
                surface,
                shadow_color,
                (self.rect.left + 3, self.rect.bottom - 4),
                (self.rect.right - 4, self.rect.bottom - 4),
                2,
            )
            pygame.draw.line(
                surface,
                shadow_color,
                (self.rect.right - 4, self.rect.top + 3),
                (self.rect.right - 4, self.rect.bottom - 4),
                2,
            )

        # 2. Render text căn giữa hoàn hảo
        if self.color_theme is not None:
            text_color = self.color_theme[3]
        else:
            text_color = (255, 235, 180) if self.is_hovered else (245, 245, 245)

        # Đổ bóng chữ tạo độ sâu pixel-art
        shadow_surface = self.font.render(self.text, True, (40, 25, 15))
        shadow_rect = shadow_surface.get_rect(
            center=(self.rect.centerx + 1, self.rect.centery + 2)
        )
        surface.blit(shadow_surface, shadow_rect)

        # Chữ chính
        text_surface = self.font.render(self.text, True, text_color)
        text_rect = text_surface.get_rect(center=self.rect.center)
        surface.blit(text_surface, text_rect)


class MenuScreen:
 

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        pygame.font.init()

  
        self.font = _load_font(config.FONT_SIZE_MEDIUM)
        self.title_font = _load_title_font(int(config.FONT_SIZE_TITLE * 1.6))

        self.click_sound = _load_sound()

     
        self.background = self._load_background()

   
        self.buttons: list[Button] = self._create_buttons()

    def _load_background(self) -> pygame.Surface | None:
      
        bg_candidates = [
            config.IMAGES_DIR / "menu_bg.png",
            config.BASE_DIR / "Assets" / "images" / "menu_bg.png",
            config.BASE_DIR / "assets" / "images" / "menu_bg.png",
            config.IMAGES_DIR / "UI" / "menu_bg.png",
        ]
        for bg_path in bg_candidates:
            if bg_path.exists():
                try:
                    img = pygame.image.load(str(bg_path))
                    return pygame.transform.scale(
                        img, (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
                    )
                except Exception:
                    continue
        return None

    def _create_buttons(self) -> list[Button]:
        """Tạo 4 nút căn giữa màn hình theo chiều ngang, xếp dọc với khoảng cách đều."""
        button_specs = [
            ("PLAY", config.STATE_SELECT_SIZE),
            ("2 PLAYERS", config.STATE_NAME_INPUT),
            ("LEADERBOARD", config.STATE_RESULT),
            ("EXIT", "QUIT"),
        ]

        btn_width = 300
        btn_height = 58
        btn_padding = 20

        # Căn giữa theo chiều ngang
        start_x = (config.WINDOW_WIDTH - btn_width) // 2

        # Bắt đầu xếp từ phía dưới tiêu đề
        start_y = 280

        # Thử tìm ảnh nút gỗ nếu có
        button_img_path = config.IMAGES_DIR / "UI" / "button_wood.png"
        base_img = None
        if button_img_path.exists():
            try:
                base_img = pygame.image.load(str(button_img_path)).convert_alpha()
            except Exception:
                base_img = None

        buttons: list[Button] = []
        for i, (text, target_state) in enumerate(button_specs):
            y = start_y + i * (btn_height + btn_padding)
            btn = Button(
                x=start_x,
                y=y,
                width=btn_width,
                height=btn_height,
                text=text,
                font=self.font,
                base_image=base_img,
                target_state=target_state,
            )
            buttons.append(btn)
        return buttons

    def handle_event(self, event: pygame.event.Event) -> str | None:
        """Xử lý sự kiện click chuột trên các nút Menu.

        Trả về trạng thái tiếp theo (ví dụ: STATE_PLAYING, STATE_RACE, STATE_RESULT, 'QUIT')
        hoặc None nếu không có nút nào được nhấn.
        """
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.buttons:
                if button.is_clicked(event.pos):
                    if self.click_sound is not None:
                        try:
                            self.click_sound.play()
                        except Exception:
                            pass
                    return button.target_state

        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            return "QUIT"

        return None

    def update(self) -> None:
        """Cập nhật trạng thái hover của các nút."""
        mouse_pos = pygame.mouse.get_pos()
        for button in self.buttons:
            button.update(mouse_pos)

    def draw(self, screen: pygame.Surface | None = None) -> None:
        """Vẽ toàn bộ giao diện Menu."""
        target_screen = screen if screen is not None else self.screen

        # 1. Vẽ Background
        if self.background is not None:
            target_screen.blit(self.background, (0, 0))
        else:
            target_screen.fill(config.COLOR_BG)
            self._draw_background_pattern(target_screen)

        # 2. Vẽ Tiêu đề / Logo
        self._draw_title(target_screen)

        # 3. Vẽ các nút
        for button in self.buttons:
            button.draw(target_screen)

        # 4. Gợi ý điều khiển chân trang
        self._draw_footer(target_screen)

    def _draw_background_pattern(self, surface: pygame.Surface) -> None:
        """Trang trí lưới pixel tinh tế khi chưa có ảnh background."""
        grid_size = 48
        color_line = (38, 38, 52)
        for x in range(0, config.WINDOW_WIDTH, grid_size):
            pygame.draw.line(surface, color_line, (x, 0), (x, config.WINDOW_HEIGHT))
        for y in range(0, config.WINDOW_HEIGHT, grid_size):
            pygame.draw.line(surface, color_line, (0, y), (config.WINDOW_WIDTH, y))

    def _draw_title(self, surface: pygame.Surface) -> None:
        center_x = config.WINDOW_WIDTH // 2
        title_text = "Maze Game"
        shadow = self.title_font.render(title_text, True, (20, 20, 28))
        shadow_rect = shadow.get_rect(center=(center_x + 3, 147))
        surface.blit(shadow, shadow_rect)

        title_surface = self.title_font.render(title_text, True, config.COLOR_PRIMARY)
        title_rect = title_surface.get_rect(center=(center_x, 144))
        surface.blit(title_surface, title_rect)

    def _draw_footer(self, surface: pygame.Surface) -> None:
      
        tip_text = "Click to choose or press ESC to exit"
        tip_surf = self.font.render(tip_text, True, (130, 130, 150))
        tip_rect = tip_surf.get_rect(center=(config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT - 40))
        surface.blit(tip_surf, tip_rect)


class SelectSizeScreen:
    """Difficulty chooser that returns the selected maze dimensions."""

    CHOICES = (
        ("EASY (15x15)", (15, 15)),
        ("MEDIUM (31x31)", (31, 31)),
        ("HARD (51x51)", (51, 51)),
    )
    DIFFICULTY_THEMES = (
        ((39, 137, 78), (52, 165, 96), (143, 225, 154), (255, 255, 255)),
        ((202, 151, 34), (230, 177, 45), (255, 228, 126), (40, 34, 18)),
        ((170, 49, 57), (210, 62, 68), (255, 145, 145), (255, 255, 255)),
    )

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = _load_font(config.FONT_SIZE_MEDIUM)
        self.title_font = _load_font(config.FONT_SIZE_LARGE)
        self.click_sound = _load_sound()
        self.selected_size: tuple[int, int] | None = None

        self.background = self._load_background()
        self.button_image = self._load_button_image()
        button_width, button_height = 340, 64
        gap = 22
        total_height = len(self.CHOICES) * button_height + (len(self.CHOICES) - 1) * gap
        first_y = (config.WINDOW_HEIGHT - total_height) // 2 + 45
        left = (config.WINDOW_WIDTH - button_width) // 2
        self.buttons: list[Button] = []
        self._sizes_by_button: dict[int, tuple[int, int]] = {}

        for index, (label, dimensions) in enumerate(self.CHOICES):
            button = Button(
                x=left,
                y=first_y + index * (button_height + gap),
                width=button_width,
                height=button_height,
                text=label,
                font=self.font,
                color_theme=self.DIFFICULTY_THEMES[index],
                target_state=config.STATE_SOLO_SETUP,
            )
            self.buttons.append(button)
            self._sizes_by_button[id(button)] = dimensions

    @staticmethod
    def _load_background() -> pygame.Surface | None:
        candidates = (
            config.BASE_DIR / "Assets" / "images" / "UI" / "menu_bg.png",
            config.BASE_DIR / "Assets" / "images" / "menu_bg.png",
            config.IMAGES_DIR / "UI" / "menu_bg.png",
        )
        for path in candidates:
            if path.is_file():
                try:
                    image = pygame.image.load(str(path))
                    return pygame.transform.scale(
                        image, (config.WINDOW_WIDTH, config.WINDOW_HEIGHT)
                    )
                except (pygame.error, OSError, ValueError):
                    continue
        return None

    @staticmethod
    def _load_button_image() -> pygame.Surface | None:
        candidates = (
            config.BASE_DIR / "Assets" / "images" / "UI" / "button.png",
            config.BASE_DIR / "Assets" / "images" / "UI" / "button_wood.png",
            config.IMAGES_DIR / "UI" / "button.png",
        )
        for path in candidates:
            if path.is_file():
                try:
                    image = pygame.image.load(str(path))
                    if pygame.display.get_surface() is not None:
                        image = image.convert_alpha()
                    return image
                except (pygame.error, OSError, ValueError):
                    continue
        return None

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            self.selected_size = None
            return config.STATE_MENU

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for button in self.buttons:
                if button.is_clicked(event.pos):
                    self.selected_size = self._sizes_by_button[id(button)]
                    if self.click_sound is not None:
                        try:
                            self.click_sound.play()
                        except pygame.error:
                            pass
                    return config.STATE_SOLO_SETUP
        return None

    def update(self) -> None:
        mouse_pos = pygame.mouse.get_pos()
        for button in self.buttons:
            button.update(mouse_pos)

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        if self.background is None:
            target.fill(config.COLOR_BG)
        else:
            target.blit(self.background, (0, 0))

        title = self.title_font.render("SELECT DIFFICULTY", True, config.COLOR_TEXT)
        target.blit(title, title.get_rect(center=(target.get_width() // 2, 190)))
        for button in self.buttons:
            button.draw(target)

        hint = self.font.render("Press ESC to return", True, (180, 180, 195))
        target.blit(
            hint,
            hint.get_rect(center=(target.get_width() // 2, target.get_height() - 38)),
        )


class SoloSetupScreen:
    """Choose the maze difficulty and solo character before starting."""

    def __init__(
        self,
        screen: pygame.Surface,
        maze_size: tuple[int, int],
    ) -> None:
        self.screen = screen
        self.maze_size = (int(maze_size[0]), int(maze_size[1]))
        self.font = _load_font(config.FONT_SIZE_MEDIUM)
        self.small_font = _load_font(config.FONT_SIZE_SMALL)
        self.title_font = _load_title_font(config.FONT_SIZE_LARGE)
        self.player_name = ""
        self.name_active = True
        self.name_rect = pygame.Rect(config.WINDOW_WIDTH // 2 - 220, 235, 440, 58)
        self.character_id = 1
        self.preview_size = min(112, max(72, int(config.CELL_SIZE * 4)))
        self.preview_players = {
            character_id: Player(
                character_id=character_id,
                player_size=self.preview_size,
            )
            for character_id in (1, 2)
        }
        self.preview_center = (config.WINDOW_WIDTH // 2, 425)
        self.arrow_size = 64
        self.left_arrow_rect = pygame.Rect(
            self.preview_center[0] - self.preview_size // 2 - 94,
            self.preview_center[1] - self.arrow_size // 2,
            self.arrow_size,
            self.arrow_size,
        )
        self.right_arrow_rect = pygame.Rect(
            self.preview_center[0] + self.preview_size // 2 + 30,
            self.preview_center[1] - self.arrow_size // 2,
            self.arrow_size,
            self.arrow_size,
        )
        self.start_button = Button(
            config.WINDOW_WIDTH // 2 - 150,
            555,
            300,
            60,
            "START GAME",
            self.font,
            target_state=config.STATE_PLAYING,
        )
        self.selected_name: str | None = None
        self.selected_character_id: int | None = None

    def _start(self) -> str | None:
        name = self.player_name.strip()
        if not name:
            self.name_active = True
            return None
        self.selected_name = name
        self.selected_character_id = self.character_id
        return config.STATE_PLAYING

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return config.STATE_SELECT_SIZE
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                return self._start()
            if event.key == pygame.K_TAB:
                self.name_active = not self.name_active
                return None
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT):
                self.character_id = 2 if self.character_id == 1 else 1
                return None
            if self.name_active:
                if event.key == pygame.K_BACKSPACE:
                    self.player_name = self.player_name[:-1]
                elif event.unicode and event.unicode.isprintable() and len(self.player_name) < 24:
                    self.player_name += event.unicode
                return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.name_rect.collidepoint(event.pos):
                self.name_active = True
                return None
            if self.left_arrow_rect.collidepoint(event.pos) or self.right_arrow_rect.collidepoint(event.pos):
                self.character_id = 2 if self.character_id == 1 else 1
                self.name_active = False
                return None
            if self.start_button.is_clicked(event.pos):
                return self._start()
        return None

    def update(self) -> None:
        self.start_button.update()
        self.preview_players[self.character_id].animate()

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        target.fill(config.COLOR_BG)
        title = self.title_font.render("SOLO MODE", True, config.COLOR_TEXT)
        target.blit(title, title.get_rect(center=(target.get_width() // 2, 125)))
        mode_names = {(15, 15): "EASY", (31, 31): "MEDIUM", (51, 51): "HARD"}
        mode_colors = {
            "EASY": (95, 220, 135),
            "MEDIUM": (255, 195, 75),
            "HARD": (255, 105, 105),
        }
        mode = mode_names.get(self.maze_size, "CUSTOM")
        mode_prefix = self.small_font.render("MODE: ", True, (175, 185, 200))
        mode_label = self.small_font.render(mode, True, mode_colors.get(mode, (190, 200, 215)))
        mode_width = mode_prefix.get_width() + mode_label.get_width()
        mode_left = target.get_width() // 2 - mode_width // 2
        target.blit(mode_prefix, (mode_left, 175))
        target.blit(mode_label, (mode_left + mode_prefix.get_width(), 175))

        name_label = self.font.render("Player name", True, config.COLOR_TEXT)
        target.blit(name_label, (self.name_rect.left, self.name_rect.top - 34))
        pygame.draw.rect(target, (40, 49, 68), self.name_rect, border_radius=10)
        border_color = config.COLOR_HOVER if self.name_active else (90, 105, 128)
        pygame.draw.rect(target, border_color, self.name_rect, width=2, border_radius=10)
        shown_name = self.player_name or "Enter your name..."
        name_color = config.COLOR_TEXT if self.player_name else (145, 155, 170)
        name_surface = self.font.render(shown_name, True, name_color)
        target.blit(name_surface, (self.name_rect.left + 16, self.name_rect.centery - name_surface.get_height() // 2))
        if self.name_active and pygame.time.get_ticks() // 500 % 2 == 0:
            cursor_x = self.name_rect.left + 16 + self.font.size(self.player_name)[0] + 2
            pygame.draw.line(target, config.COLOR_TEXT, (cursor_x, self.name_rect.top + 14), (cursor_x, self.name_rect.bottom - 14), 2)

        character_label = self.font.render("Choose your character", True, config.COLOR_TEXT)
        target.blit(character_label, character_label.get_rect(center=(target.get_width() // 2, 350)))
        for rect, symbol in ((self.left_arrow_rect, "<"), (self.right_arrow_rect, ">")):
            pygame.draw.rect(target, (43, 57, 77), rect, border_radius=12)
            pygame.draw.rect(target, (100, 210, 235), rect, width=2, border_radius=12)
            arrow = self.title_font.render(symbol, True, (240, 245, 250))
            target.blit(arrow, arrow.get_rect(center=rect.center))

        preview = self.preview_players[self.character_id]
        preview.draw(target, self.preview_center[0] - preview.x, self.preview_center[1] - preview.y)
        selected = self.small_font.render(f"Character {self.character_id}", True, (210, 220, 230))
        target.blit(selected, selected.get_rect(center=(target.get_width() // 2, 500)))
        self.start_button.draw(target)
        hint = self.small_font.render("Use arrows or click to choose  |  ESC: back", True, (165, 175, 190))
        target.blit(hint, hint.get_rect(center=(target.get_width() // 2, target.get_height() - 28)))


class NameInputScreen:
    """Collect two local player names before starting a two-player race."""

    def __init__(self, screen: pygame.Surface) -> None:
        self.screen = screen
        self.font = _load_font(config.FONT_SIZE_MEDIUM)
        self.title_font = _load_font(config.FONT_SIZE_LARGE)
        self.player_names = ["Player 1", "Player 2"]
        self.active_field = 0
        self.field_rects = [
            pygame.Rect(config.WINDOW_WIDTH // 2 - 220, 280, 440, 58),
            pygame.Rect(config.WINDOW_WIDTH // 2 - 220, 390, 440, 58),
        ]
        self.preview_size = 60
        self.player1_preview = self._load_player1_preview()
        self.player2_preview_gif = self._load_player2_preview_gif()
        self.player2_preview_fallback = self._make_preview_fallback((255, 175, 75))
        self.start_button = Button(
            config.WINDOW_WIDTH // 2 - 150,
            500,
            300,
            60,
            "START RACE",
            self.font,
            target_state=config.STATE_RACE,
        )
        self.selected_names: tuple[str, str] | None = None

    def _make_preview_fallback(self, color: tuple[int, int, int]) -> pygame.Surface:
        preview = pygame.Surface((self.preview_size, self.preview_size), pygame.SRCALPHA)
        pygame.draw.circle(preview, color, preview.get_rect().center, self.preview_size // 2)
        return preview

    def _fit_preview(self, image: pygame.Surface) -> pygame.Surface:
        fitted = pygame.Surface((self.preview_size, self.preview_size), pygame.SRCALPHA)
        image_w, image_h = image.get_size()
        scale = min(self.preview_size / max(1, image_w), self.preview_size / max(1, image_h))
        scaled_size = (max(1, round(image_w * scale)), max(1, round(image_h * scale)))
        scaled = pygame.transform.smoothscale(image, scaled_size)
        fitted.blit(scaled, scaled.get_rect(center=fitted.get_rect().center))
        return fitted

    def _load_player1_preview(self) -> pygame.Surface:
        character_dir = Path(config.BASE_DIR) / "Assets" / "images" / "Character"
        candidates = (
            character_dir / "idle",
            Path(config.BASE_DIR) / "assets" / "images" / "Character" / "idle",
        )
        for directory in candidates:
            if not directory.is_dir():
                continue
            for image_path in sorted(directory.glob("*")):
                if image_path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
                    continue
                try:
                    image = pygame.image.load(str(image_path)).convert_alpha()
                    return self._fit_preview(image)
                except (pygame.error, OSError, ValueError):
                    continue
        return self._make_preview_fallback((80, 175, 255))

    def _load_player2_preview_gif(self) -> Any | None:
        if gif_pygame is None:
            return None
        candidates = (
            Path(config.BASE_DIR) / "Assets" / "images" / "Character" / "Idle_2.gif",
            Path(config.BASE_DIR) / "assets" / "images" / "Character" / "Idle_2.gif",
        )
        for gif_path in candidates:
            if not gif_path.is_file():
                continue
            try:
                animation = gif_pygame.load(str(gif_path))
                scaled = gif_pygame.transform.scale(
                    animation, (self.preview_size, self.preview_size)
                )
                return scaled if scaled is not None else animation
            except Exception:
                continue
        return None

    def _start(self) -> str:
        normalized = [name.strip() or f"Player {index + 1}" for index, name in enumerate(self.player_names)]
        self.player_names = normalized
        self.selected_names = (normalized[0], normalized[1])
        return config.STATE_RACE

    def handle_event(self, event: pygame.event.Event) -> str | None:
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                return config.STATE_MENU
            if event.key == pygame.K_TAB:
                self.active_field = 1 - self.active_field
                return None
            if event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                if self.active_field == 0:
                    self.active_field = 1
                    return None
                return self._start()
            if event.key == pygame.K_BACKSPACE:
                self.player_names[self.active_field] = self.player_names[self.active_field][:-1]
                return None
            if event.unicode and event.unicode.isprintable():
                name = self.player_names[self.active_field]
                if len(name) < 18:
                    self.player_names[self.active_field] = name + event.unicode
                return None

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for index, rect in enumerate(self.field_rects):
                if rect.collidepoint(event.pos):
                    self.active_field = index
                    return None
            if self.start_button.is_clicked(event.pos):
                return self._start()
        return None

    def update(self) -> None:
        self.start_button.update()

    def draw(self, screen: pygame.Surface | None = None) -> None:
        target = screen if screen is not None else self.screen
        target.fill(config.COLOR_BG)
        title = self.title_font.render("PLAYER NAMES", True, config.COLOR_TEXT)
        target.blit(title, title.get_rect(center=(target.get_width() // 2, 145)))

        for index, (label, rect) in enumerate(zip(("Player 1 Name", "Player 2 Name"), self.field_rects)):
            label_surface = self.font.render(label, True, config.COLOR_TEXT)
            target.blit(label_surface, (rect.left, rect.top - 34))
            preview_rect = pygame.Rect(
                rect.left - self.preview_size - 14,
                rect.centery - self.preview_size // 2,
                self.preview_size,
                self.preview_size,
            )
            pygame.draw.circle(target, (42, 53, 71), preview_rect.center, self.preview_size // 2 + 4)
            if index == 0:
                target.blit(self.player1_preview, preview_rect)
            elif self.player2_preview_gif is not None:
                self.player2_preview_gif.render(target, preview_rect.topleft)
            else:
                target.blit(self.player2_preview_fallback, preview_rect)

            fill = (45, 56, 76) if index == self.active_field else (34, 42, 58)
            border = config.COLOR_HOVER if index == self.active_field else (88, 105, 128)
            pygame.draw.rect(target, fill, rect, border_radius=10)
            pygame.draw.rect(target, border, rect, width=2, border_radius=10)
            name = self.player_names[index]
            shown_name = name if name else "Type a name..."
            color = config.COLOR_TEXT if name else (150, 160, 175)
            text = self.font.render(shown_name, True, color)
            target.blit(text, (rect.left + 16, rect.centery - text.get_height() // 2))
            if index == self.active_field and pygame.time.get_ticks() // 500 % 2 == 0:
                cursor_x = rect.left + 16 + self.font.size(name)[0] + 2
                pygame.draw.line(target, config.COLOR_TEXT, (cursor_x, rect.top + 14), (cursor_x, rect.bottom - 14), 2)

        self.start_button.draw(target)
        hint = self.font.render("TAB: switch player  |  ENTER: next / start  |  ESC: menu", True, (170, 180, 195))
        target.blit(hint, hint.get_rect(center=(target.get_width() // 2, target.get_height() - 38)))
