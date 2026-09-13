# config.py
"""
Configuration and constants for the Kinetic Engine.
Restored exactly from original Kinetic settings.
"""

# Screen & Abstract Physics (For dynamic scaling)
BASE_W, BASE_H = 1280, 720
FPS = 60
CLASH_WINDOW = 152      
PENALTY_TIME = 1500     

# Animation Speeds (in milliseconds)
ANIMATION_SPEED = 0.15
SCOOP_SPEED = 416
FLIP_SPEED = 500
NEAT_SPEED = 500
PAUSE_DURATION = 333
PENALTY_RETRACT_SPEED = 1033

# Colors
BG_COLOR = (30, 30, 30)
ERROR_COLOR = (200, 50, 50) 
TEXT_COLOR = (255, 255, 255)
BUTTON_COLOR = (50, 50, 200)
BUTTON_HOVER_COLOR = (70, 70, 220)
CARD_BG = (250, 250, 250)
CARD_BACK = (120, 30, 30)

# Game States & Modes
STATE_MENU = "MENU"
STATE_HELP = "HELP"
STATE_DEALING = "DEALING"
STATE_PLAYING = "PLAYING"
STATE_SCOOPING = "SCOOPING"
STATE_GAME_OVER = "GAME_OVER"
STATE_BOT_SELECT = "BOT_SELECT"

# Multiplayer UI States
STATE_MP_MODE_SELECT = "MP_MODE_SELECT"
STATE_ONLINE_WIP = "ONLINE_WIP"
STATE_MATCH_STARTING = "MATCH_STARTING"
STATE_LAN_CONNECTING = "LAN_CONNECTING"
STATE_LAN_PEER_PICKER = "LAN_PEER_PICKER"

# --- LAN Networking ---
LAN_DISCOVERY_PORT = 47921
LAN_GAME_PORT = 47922
LAN_BROADCAST_INTERVAL_MS = 750
LAN_DISCOVERY_TIMEOUT_MS = 60000  # Extended to 60 seconds
LAN_MULTI_PEER_WINDOW_MS = 2000

MODE_SINGLE = "SINGLE_PLAYER"
MODE_BOT = "VS_COMPUTER"
MODE_LAN = "LAN"
MODE_ONLINE = "ONLINE"

# Bot difficulty levels
BOT_EASY = "BOT_EASY"
BOT_MEDIUM = "BOT_MEDIUM"
BOT_HARD = "BOT_HARD"

# Input Delay for deterministic network resolution (Option B)
INPUT_DELAY_MS = 32

# Synchronized sequence start buffer
SEQUENCE_START_DELAY_MS = 200