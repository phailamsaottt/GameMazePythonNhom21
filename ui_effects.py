"""Shared hover and click effects for interactive game controls."""

from pathlib import Path

import pygame

import config

try:
    import gif_pygame
except ImportError:
    gif_pygame = None


_arrow_animation = None
_click_sound: pygame.mixer.Sound | None = None
_sound_loaded = False


def _load_arrow():
    global _arrow_animation
    if _arrow_animation is not None or gif_pygame is None:
        return _arrow_animation
    candidates = (
        Path(config.IMAGES_DIR) / "UI" / "arrow.gif",
        Path(config.BASE_DIR) / "assets" / "images" / "UI" / "arrow.gif",
    )
    for path in candidates:
        if path.is_file():
            try:
                animation = gif_pygame.load(str(path))
                scaled = gif_pygame.transform.scale(animation, (54, 30))
                _arrow_animation = scaled if scaled is not None else animation
                break
            except Exception:
                continue
    return _arrow_animation


def draw_hover_arrow(surface: pygame.Surface, rect: pygame.Rect, hovered: bool | None = None) -> None:
    if hovered is None:
        hovered = rect.collidepoint(pygame.mouse.get_pos())
    if not hovered:
        return
    animation = _load_arrow()
    if animation is None:
        return
    try:
        animation.render(surface, (max(8, rect.left - 66), rect.centery - 15))
    except (pygame.error, AttributeError, TypeError):
        return


def play_ui_click() -> None:
    global _click_sound, _sound_loaded
    if not _sound_loaded:
        _sound_loaded = True
        try:
            if not pygame.mixer.get_init():
                pygame.mixer.init()
        except pygame.error:
            return
        sounds_dir = Path(config.SOUNDS_DIR)
        for filename in (
            "click.wav", "click.mp3", "click.ogg",
            "Wood Block1.mp3", "Retro1.mp3", "Minimalist1.mp3",
        ):
            path = sounds_dir / filename
            if not path.is_file():
                continue
            try:
                _click_sound = pygame.mixer.Sound(str(path))
                _click_sound.set_volume(getattr(config, "DEFAULT_VOLUME", 0.5))
                break
            except (pygame.error, OSError):
                continue
    if _click_sound is not None:
        try:
            _click_sound.play()
        except pygame.error:
            pass


def confirm_dialog_rects(size: tuple[int, int]) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    width, height = size
    panel = pygame.Rect(0, 0, min(520, width - 32), min(260, height - 32))
    panel.center = (width // 2, height // 2)
    button_width = min(190, max(120, (panel.width - 54) // 2))
    button_height = 52
    gap = 18
    total = button_width * 2 + gap
    left = panel.centerx - total // 2
    top = panel.bottom - 78
    return (
        panel,
        pygame.Rect(left, top, button_width, button_height),
        pygame.Rect(left + button_width + gap, top, button_width, button_height),
    )


def draw_confirm_dialog(
    surface: pygame.Surface,
    title_font: pygame.font.Font,
    button_font: pygame.font.Font,
    selected: int,
) -> None:
    overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
    overlay.fill((0, 0, 0, 180))
    surface.blit(overlay, (0, 0))

    panel, continue_rect, exit_rect = confirm_dialog_rects(surface.get_size())
    pygame.draw.rect(surface, (29, 38, 55), panel, border_radius=18)
    pygame.draw.rect(surface, (100, 210, 230), panel, width=3, border_radius=18)
    title = title_font.render("YOU GIVE UP?", True, (255, 235, 190))
    surface.blit(title, title.get_rect(center=(panel.centerx, panel.top + 72)))

    mouse_pos = pygame.mouse.get_pos()
    hover_exists = continue_rect.collidepoint(mouse_pos) or exit_rect.collidepoint(mouse_pos)
    for index, (rect, label) in enumerate(((continue_rect, "CONTINUE"), (exit_rect, "EXIT"))):
        hovered = rect.collidepoint(mouse_pos)
        active = hovered if hover_exists else index == selected
        fill = (48, 132, 112) if index == 0 else (142, 67, 67)
        if active:
            fill = (65, 173, 145) if index == 0 else (190, 81, 81)
        border = (160, 240, 220) if index == 0 else (255, 175, 160)
        pygame.draw.rect(surface, fill, rect, border_radius=10)
        pygame.draw.rect(surface, border if active else (100, 115, 135), rect, width=2, border_radius=10)
        text = button_font.render(label, True, (255, 255, 255))
        surface.blit(text, text.get_rect(center=rect.center))
        draw_hover_arrow(surface, rect, active)
