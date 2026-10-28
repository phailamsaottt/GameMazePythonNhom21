from pathlib import Path
import pygame 

# PATHS

BASE_DIR = Path(__file__).resolve().parent


ASSETS_DIR = BASE_DIR / "assets"
IMAGES_DIR = ASSETS_DIR / "images"
SOUNDS_DIR = ASSETS_DIR / "sounds"
FONTS_DIR  = ASSETS_DIR / "fonts"


DB_PATH = BASE_DIR / "maze_game.db"



# CỬA SỔ HIỂN THỊ

WINDOW_WIDTH  = 1280
WINDOW_HEIGHT = 720
FPS           = 60
GAME_TITLE    = "Maze Game"



# 3.CẤU HÌNH MÊ CUNG 

CELL_SIZE = 24  


DEFAULT_ROWS = 21
DEFAULT_COLS = 21


MAZE_PRESETS = {
    "Dễ (Small)": (15, 15),
    "Trung bình (Medium)": (25, 25),
    "Khó (Large)": (35, 35)
}



# MÀU 


COLOR_BG          = (30, 30, 40)       
COLOR_TEXT        = (240, 240, 240)   
COLOR_PRIMARY     = (41, 128, 185)    
COLOR_HOVER       = (52, 152, 219)   
COLOR_PANEL_BG    = (45, 45, 60)     


COLOR_WALL        = (20, 20, 30)       
COLOR_PATH        = (230, 230, 230)    
COLOR_START       = (46, 204, 113)     
COLOR_END         = (231, 76, 60)    
COLOR_PLAYER      = (241, 196, 15)   


COLOR_BFS_TRACE   = (52, 152, 219)  
COLOR_DFS_TRACE   = (155, 89, 182)     
COLOR_ASTAR_TRACE = (230, 126, 34)     
COLOR_VISITED     = (180, 220, 180)    



# TRẠNG THÁI 

STATE_MENU        = "STATE_MENU"
STATE_SELECT_SIZE = "STATE_SELECT_SIZE"
STATE_PLAYING     = "STATE_PLAYING"
STATE_RACE        = "STATE_RACE"
STATE_RESULT      = "STATE_RESULT"



# CẤU HÌNH FONT VÀ ÂM THANH

FONT_SIZE_SMALL  = 18
FONT_SIZE_MEDIUM = 24
FONT_SIZE_LARGE  = 36
FONT_SIZE_TITLE  = 54

DEFAULT_VOLUME   = 0.5 