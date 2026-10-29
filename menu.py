from __future__ import annotations

from pathlib import Path
from typing import Any

import pygame

import config


def _load_font(size: int) -> pygame.font.Font:
    """Nạp font từ config.FONTS_DIR nếu có, ngược lại dùng System Font dự phòng."""
    fonts_dir = Path(config.FONTS_DIR)
    ttf = next(iter(sorted(fonts_dir.glob("*.ttf"))), None) if fonts_dir.is_dir() else None
    if ttf is not None:
        try:
            return pygame.font.Font(str(ttf), size)
        except Exception:
            pass
    return pygame.font.SysFont("arial,segoeui,tahoma,dejavusans", size, bold=True)


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
    ) -> None:
        self.x = int(x)
        self.y = int(y)
        self.width = int(width)
        self.height = int(height)
        self.text = text
        self.font = font
        self.target_state = target_state

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
        if self.base_image is not None:
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
        self.title_font = _load_font(config.FONT_SIZE_TITLE)

        self.click_sound = _load_sound()

     
        self.background = self._load_background()

   
        self.logo_banner = self._load_logo_banner()

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

    def _load_logo_banner(self) -> pygame.Surface | None:
        """Nạp logo_banner.png nếu có để làm tiêu đề phong cách pixel."""
        banner_path = config.IMAGES_DIR / "UI" / "logo_banner.png"
        if not banner_path.exists():
            banner_path = config.BASE_DIR / "Assets" / "images" / "UI" / "logo_banner.png"

        if banner_path.exists():
            try:
                img = pygame.image.load(str(banner_path))
              
                w, h = img.get_size()
                target_w = 420
                target_h = int(h * (target_w / w))
                return pygame.transform.scale(img, (target_w, target_h))
            except Exception:
                pass
        return None

    def _create_buttons(self) -> list[Button]:
        """Tạo 4 nút căn giữa màn hình theo chiều ngang, xếp dọc với khoảng cách đều."""
        button_specs = [
            ("PLAY", config.STATE_PLAYING),
            ("2 PLAYERS", config.STATE_RACE),
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
        if self.logo_banner is not None:
            banner_rect = self.logo_banner.get_rect(center=(center_x, 150))
            surface.blit(self.logo_banner, banner_rect)
        else:
            # Tiêu đề dạng text retro
            title_text = config.GAME_TITLE
            shadow = self.title_font.render(title_text, True, (20, 20, 28))
            shadow_rect = shadow.get_rect(center=(center_x + 3, 143))
            surface.blit(shadow, shadow_rect)

            title_surf = self.title_font.render(title_text, True, config.COLOR_PRIMARY)
            title_rect = title_surf.get_rect(center=(center_x, 140))
            surface.blit(title_surf, title_rect)

    def _draw_footer(self, surface: pygame.Surface) -> None:
      
        tip_text = "Dùng chuột để chọn hoặc nhấn ESC để thoát"
        tip_surf = self.font.render(tip_text, True, (130, 130, 150))
        tip_rect = tip_surf.get_rect(center=(config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT - 40))
        surface.blit(tip_surf, tip_rect)
