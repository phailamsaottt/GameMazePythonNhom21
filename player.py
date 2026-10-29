from __future__ import annotations

import math
from pathlib import Path
from collections.abc import Sequence
from typing import Any

import pygame

try:
	import gif_pygame
except ImportError:  # GIF support is optional; sprite-sheet animation still works.
	gif_pygame = None

try:
	import config
except ImportError:
	from . import config  # type: ignore[no-redef]


CELL_SIZE = getattr(config, "CELL_SIZE", 24)


def load_character_frames(character_dir: Path | str | None = None) -> dict[str, list[pygame.Surface]]:
	"""Tải tất cả các khung hình (frames) từ Assets/images/Character/idle và run.

	Trả về dictionary dạng: {'idle': [...], 'run': [...]}
	"""
	animations: dict[str, list[pygame.Surface]] = {"idle": [], "run": []}

	# Xác định đường dẫn gốc chứa thư mục Character
	if character_dir is not None:
		char_path = Path(character_dir)
	else:
		base_candidates = [
			Path(__file__).resolve().parent,
			getattr(config, "BASE_DIR", Path(__file__).resolve().parent),
			getattr(config, "ASSETS_DIR", Path(__file__).resolve().parent / "Assets").parent,
			Path.cwd(),
		]
		char_path = None
		for base in base_candidates:
			for asset_folder in ("Assets", "assets"):
				cand = base / asset_folder / "images" / "Character"
				if cand.exists() and cand.is_dir():
					char_path = cand
					break
			if char_path is not None:
				break

		if char_path is None:
			char_path = Path("Assets/images/Character")

	# Tải hình ảnh cho từng trạng thái: idle, run
	for state in animations.keys():
		state_dir = char_path / state
		if state_dir.exists() and state_dir.is_dir():
			valid_files = sorted(
				[f for f in state_dir.iterdir() if f.suffix.lower() in (".png", ".jpg", ".jpeg")],
				key=lambda f: f.name,
			)
			for file_path in valid_files:
				try:
					surface = pygame.image.load(str(file_path))
					if pygame.display.get_surface() is not None:
						surface = surface.convert_alpha()
					animations[state].append(surface)
				except (pygame.error, OSError):
					continue

	return animations


class Player(pygame.sprite.Sprite):


	DIRECTIONS = ("UP", "DOWN", "LEFT", "RIGHT")

	def __init__(
		self,
		start_grid_x: int = 0,
		start_grid_y: int = 0,
		speed: float = 3.0,
		player_size: int | None = None,
		animation_speed: float = 0.15,
		controls: str = "wasd",
		character_id: int = 1,
		spawn_offset: tuple[float, float] = (0.0, 0.0),
	) -> None:
		super().__init__()
		if controls not in ("wasd", "arrows"):
			raise ValueError("controls must be 'wasd' or 'arrows'")
		if character_id not in (1, 2):
			raise ValueError("character_id must be 1 or 2")
		self.controls = controls
		self.character_id = character_id
		self.use_gif = bool(character_id == 2 and gif_pygame is not None)
		self.spawn_offset = (float(spawn_offset[0]), float(spawn_offset[1]))
		self.speed = float(speed)
		# Keep the sprite close to a full maze tile while using a smaller AABB
		# for collision checks, so the larger art does not snag on wall corners.
		default_visual_scale = 1.6 if character_id == 2 else 0.95
		self.visual_size = max(1, int(player_size or CELL_SIZE * default_visual_scale))
		self.hitbox_size = max(1, int(CELL_SIZE * 0.65))
		# Compatibility for callers that still inspect the old attribute.
		self.player_size = self.visual_size

		# Tọa độ và hướng
		self.direction = "DOWN"
		self.is_moving = False
		self.facing_right = True  
		self.flip = False         # Cờ lật sprite khi quay sang trái

		# Animation
		self.state = "idle"       # Trạng thái mặc định là 'idle'
		self.frame_index = 0.0    # Vị trí frame hiện tại
		self.animation_speed = float(animation_speed)  # Tốc độ chuyển frame

		# Tải Sprite vào dictionary {'idle': [...], 'run': [...]}
		self.animations = self.load_animations()
		self._sprites = self.animations  # Tương thích ngược

		# Thiết lập hình ảnh ban đầu và rect
		self._init_first_frame()
		self.reset_position(start_grid_x, start_grid_y)

	@property
	def status(self) -> str:
		"""Bí danh cho self.state để hỗ trợ cả hai quy ước đặt tên."""
		return self.state

	@status.setter
	def status(self, value: str) -> None:
		self.state = value

	@property
	def anim_speed(self) -> float:
		"""Bí danh cho self.animation_speed để tương thích ngược."""
		return self.animation_speed

	@anim_speed.setter
	def anim_speed(self, value: float) -> None:
		self.animation_speed = float(value)

	@property
	def anim_index(self) -> int:
		"""Bí danh cho self.frame_index dưới dạng int để tương thích ngược."""
		return int(self.frame_index)

	@anim_index.setter
	def anim_index(self, value: int | float) -> None:
		self.frame_index = float(value)

	def load_animations(self) -> dict[str, list[Any]]:
		"""Tải tất cả các hình ảnh từ Assets/images/Character/idle và Assets/images/Character/run."""
		if self.use_gif:
			character_dir = Path(config.BASE_DIR) / "Assets" / "images" / "Character"
			gif_animations: dict[str, list[Any]] = {"idle": [], "run": []}
			for state, filename in (("idle", "Idle_2.gif"), ("run", "Run_2.gif")):
				gif_path = character_dir / filename
				try:
					if gif_path.is_file():
						gif = gif_pygame.load(str(gif_path))
						# These GIFs have large transparent margins. Crop to the
						# animated character before scaling, or the character itself
						# remains tiny even when the GIF canvas fills the tile.
						frames = [frame for frame, _duration in gif.frames]
						bounds = self._union_visible_bounds(frames)
						cropped_frames = []
						for frame, duration in gif.frames:
							crop = bounds.clip(frame.get_rect())
							visible = frame.subsurface(crop).copy() if crop.w and crop.h else frame
							cropped_frames.append((self._scale_surface_to_tile(visible), duration))
						gif = gif_pygame.GIFPygame(cropped_frames, loops=gif.loops[1])
						gif_animations[state].append(gif)
				except Exception:
					pass
			return gif_animations

		animations: dict[str, list[Any]] = load_character_frames()
		for state, frames in animations.items():
			animations[state] = self._fit_animation_frames(frames)

		# Dự phòng nếu không tìm thấy ảnh
		for state, color in (("idle", (40, 120, 230)), ("run", (230, 120, 40))):
			if not animations.get(state):
				fallback = pygame.Surface((self.visual_size, self.visual_size), pygame.SRCALPHA)
				fallback.fill(color)
				animations.setdefault(state, []).append(fallback)

		return animations

	@staticmethod
	def _union_visible_bounds(frames: Sequence[pygame.Surface]) -> pygame.Rect:
		"""Return one alpha-aware crop shared by every frame of an animation."""
		bounds = [frame.get_bounding_rect(min_alpha=1) for frame in frames]
		bounds = [rect for rect in bounds if rect.width and rect.height]
		if not bounds:
			return frames[0].get_rect()
		return bounds[0].unionall(bounds[1:])

	def _fit_surface(self, surface: pygame.Surface) -> pygame.Surface:
		"""Scale the visible sprite (not its transparent padding) to a tile."""
		visible_bounds = surface.get_bounding_rect(min_alpha=1)
		if visible_bounds.width and visible_bounds.height:
			surface = surface.subsurface(visible_bounds).copy()
		return self._scale_surface_to_tile(surface)

	def _scale_surface_to_tile(self, surface: pygame.Surface) -> pygame.Surface:
		"""Scale a tightly cropped character while preserving its aspect ratio."""
		width, height = surface.get_size()
		if width <= 0 or height <= 0:
			return pygame.Surface((self.visual_size, self.visual_size), pygame.SRCALPHA)
		scale = self.visual_size / max(width, height)
		target_size = (max(1, round(width * scale)), max(1, round(height * scale)))
		return pygame.transform.scale(surface, target_size)

	def _fit_animation_frames(
		self, frames: Sequence[pygame.Surface]
	) -> list[pygame.Surface]:
		"""Crop a shared transparent border and scale each frame to tile height."""
		if not frames:
			return []
		bounds = self._union_visible_bounds(frames)
		result = []
		for frame in frames:
			crop = bounds.clip(frame.get_rect())
			visible = frame.subsurface(crop).copy() if crop.width and crop.height else frame
			result.append(self._scale_surface_to_tile(visible))
		return result

	def _init_first_frame(self) -> None:
		"""Khởi tạo frame ảnh đầu tiên cho Player."""
		frames = self.animations.get(self.state) or self.animations.get("idle")
		if frames:
			self.image = self._animation_surface(frames[0])
		else:
			self.image = pygame.Surface((self.visual_size, self.visual_size), pygame.SRCALPHA)
			self.image.fill((40, 120, 230))
		self.rect = self.image.get_rect()

	def reset_position(self, start_grid_x: int, start_grid_y: int) -> None:
		"""Đặt lại vị trí của player tại ô lưới chỉ định và reset animation/trạng thái."""
		self.grid_x = int(start_grid_x)
		self.grid_y = int(start_grid_y)
		self.x = (self.grid_x + 0.5) * CELL_SIZE
		self.y = (self.grid_y + 0.5) * CELL_SIZE
		self.x += self.spawn_offset[0]
		self.y += self.spawn_offset[1]
		self.is_moving = False
		self.state = "idle"
		self.frame_index = 0.0
		self.facing_right = True
		self.flip = False

		if hasattr(self, "image") and self.image is not None:
			self.rect = self.image.get_rect(center=(round(self.x), round(self.y)))

	def get_input(self, keys: Any = None) -> tuple[float, float]:
		"""Nhận input từ phím mũi tên hoặc A/D (và W/S), cập nhật trạng thái và cờ lật sprite.

		- Trạng thái mặc định là 'idle'.
		- Khi di chuyển, trạng thái chuyển sang 'run'.
		- Khi không bấm phím di chuyển, trạng thái trở về 'idle'.
		- Khi di chuyển sang trái, lật hình ảnh (flip).
		"""
		if keys is None:
			keys = pygame.key.get_pressed()

		dx = 0.0
		dy = 0.0

		if self.controls == "wasd":
			is_left = bool(keys[pygame.K_a])
			is_right = bool(keys[pygame.K_d])
			is_up = bool(keys[pygame.K_w])
			is_down = bool(keys[pygame.K_s])
		else:
			is_left = bool(keys[pygame.K_LEFT])
			is_right = bool(keys[pygame.K_RIGHT])
			is_up = bool(keys[pygame.K_UP])
			is_down = bool(keys[pygame.K_DOWN])

		# Xử lý di chuyển ngang & hướng mặt
		if is_left and not is_right:
			dx -= 1.0
			self.facing_right = False
			self.flip = True
		elif is_right and not is_left:
			dx += 1.0
			self.facing_right = True
			self.flip = False

		# Xử lý di chuyển dọc
		if is_up and not is_down:
			dy -= 1.0
		elif is_down and not is_up:
			dy += 1.0

		# Cập nhật trạng thái (State): idle hoặc run
		prev_state = self.state
		if dx != 0.0 or dy != 0.0:
			self.state = "run"
			self.is_moving = True
		else:
			self.state = "idle"
			self.is_moving = False

		# Khi đổi trạng thái, reset frame_index về 0 để animation chạy từ đầu
		if self.state != prev_state:
			self.frame_index = 0.0

		return dx, dy

	def animate(self) -> None:
		"""Tự động tăng self.frame_index và cập nhật self.image dựa trên trạng thái hiện tại.

		- Nếu frame_index vượt quá số lượng ảnh, reset nó về 0 (loop animation).
		- Nếu nhân vật quay sang trái, lật ngược sprite bằng pygame.transform.flip.
		"""
		frames = self.animations.get(self.state, [])
		if not frames:
			frames = self.animations.get("idle", [])
			if not frames:
				return
		if self._is_gif(frames[0]):
			current_frame = self._animation_surface(frames[0])
			self.image = (
				pygame.transform.flip(current_frame, True, False)
				if not self.facing_right or self.flip
				else current_frame
			)
			self.rect = self.image.get_rect(center=(round(self.x), round(self.y)))
			return

		# Tự động tăng frame_index theo animation_speed
		self.frame_index += self.animation_speed

		# Loop animation: Nếu vượt quá số lượng frame, reset về 0
		if self.frame_index >= len(frames):
			self.frame_index = 0.0

		current_frame = frames[int(self.frame_index)]

		# Lật hình ảnh (Flip): nếu nhân vật quay mặt sang trái
		if not self.facing_right or self.flip:
			self.image = pygame.transform.flip(current_frame, True, False)
		else:
			self.image = current_frame

		# Giữ tâm rect tại vị trí (x, y) của nhân vật
		self.rect = self.image.get_rect(center=(round(self.x), round(self.y)))

	@staticmethod
	def _is_gif(animation: Any) -> bool:
		return gif_pygame is not None and isinstance(animation, gif_pygame.GIFPygame)

	@staticmethod
	def _animation_surface(animation: Any) -> pygame.Surface:
		return animation.current_surface if Player._is_gif(animation) else animation

	def check_collision(
		self,
		next_x: float,
		next_y: float,
		maze_matrix: Sequence[Sequence[int]] | None,
	) -> bool:
		"""Kiểm tra xem AABB của player có va chạm tường hoặc vượt ngoài mê cung hay không."""
		if maze_matrix is None or not maze_matrix or not maze_matrix[0]:
			return False
		# A slightly inset collision box prevents the visible sprite corners from
		# catching on wall corners while the sprite still keeps its full size.
		half = self.hitbox_size / 2
		left = math.floor((next_x - half) / CELL_SIZE)
		right = math.floor((next_x + half - 1e-6) / CELL_SIZE)
		top = math.floor((next_y - half) / CELL_SIZE)
		bottom = math.floor((next_y + half - 1e-6) / CELL_SIZE)
		height = len(maze_matrix)
		width = len(maze_matrix[0])
		for row in range(top, bottom + 1):
			for col in range(left, right + 1):
				if row < 0 or row >= height or col < 0 or col >= len(maze_matrix[row]):
					return True
				if maze_matrix[row][col] == 1:
					return True
		return False

	def update(
		self,
		keys: Any = None,
		maze_matrix: Sequence[Sequence[int]] | None = None,
		dt: float | None = None,
	) -> None:
		"""Cập nhật vị trí, kiểm tra va chạm tường và chạy animation."""
		dx, dy = self.get_input(keys)

		if self.is_moving:
			if dx and dy:
				dx *= math.sqrt(0.5)
				dy *= math.sqrt(0.5)

			if abs(dx) >= abs(dy):
				self.direction = "RIGHT" if dx > 0 else "LEFT"
			else:
				self.direction = "DOWN" if dy > 0 else "UP"

			distance = self.speed * (max(0.0, dt) * 60 if dt is not None else 1.0)
			move_x, move_y = dx * distance, dy * distance
			max_substep = max(1.0, self.hitbox_size * 0.25)
			steps_x = max(1, math.ceil(abs(move_x) / max_substep))
			steps_y = max(1, math.ceil(abs(move_y) / max_substep))
			step_x = move_x / steps_x
			step_y = move_y / steps_y

			# Resolve the complete X movement before attempting Y. Small substeps
			# avoid tunnelling during a slow frame; a blocked axis is rolled back
			# while the other axis can still slide along the wall.
			for _ in range(steps_x):
				previous_x = self.x
				self.x += step_x
				if self.check_collision(self.x, self.y, maze_matrix):
					self.x = previous_x
					break

			for _ in range(steps_y):
				previous_y = self.y
				self.y += step_y
				if self.check_collision(self.x, self.y, maze_matrix):
					self.y = previous_y
					break

			self.grid_x = int(self.x // CELL_SIZE)
			self.grid_y = int(self.y // CELL_SIZE)

		# Cập nhật animation khung hình tiếp theo
		self.animate()

	def draw(
		self,
		surface: pygame.Surface,
		offset_x: float = 0,
		offset_y: float = 0,
		visual_scale: float = 1.0,
	) -> None:
		"""Vẽ frame hiện tại ở tâm vị trí player với camera offsets."""
		visual_scale = max(0.01, float(visual_scale))
		frames = self.animations.get(self.state) or self.animations.get("idle", [])
		if frames and self._is_gif(frames[0]):
			animation = frames[0]
			center = (round(self.x + offset_x), round(self.y + offset_y))
			frame = animation.current_surface
			# Render to a temporary surface so GIF animation advances and can be
			# flipped/scaled before being placed on screen.
			frame_surface = pygame.Surface(frame.get_size(), pygame.SRCALPHA)
			animation.render(frame_surface, (0, 0))
			if not self.facing_right or self.flip:
				frame_surface = pygame.transform.flip(frame_surface, True, False)
			if visual_scale != 1.0:
				scaled_size = (
					max(1, round(frame_surface.get_width() * visual_scale)),
					max(1, round(frame_surface.get_height() * visual_scale)),
				)
				frame_surface = pygame.transform.scale(frame_surface, scaled_size)
			surface.blit(frame_surface, frame_surface.get_rect(center=center))
			return
		if hasattr(self, "image") and self.image is not None:
			image = self.image
			if visual_scale != 1.0:
				scaled_size = (
					max(1, round(image.get_width() * visual_scale)),
					max(1, round(image.get_height() * visual_scale)),
				)
				image = pygame.transform.scale(image, scaled_size)
			draw_rect = image.get_rect(center=(round(self.x + offset_x), round(self.y + offset_y)))
			surface.blit(image, draw_rect)
		else:
			rect = pygame.Rect(0, 0, self.visual_size, self.visual_size)
			rect.center = (round(self.x + offset_x), round(self.y + offset_y))
			pygame.draw.rect(surface, (40, 120, 230), rect, border_radius=max(1, self.visual_size // 6))
