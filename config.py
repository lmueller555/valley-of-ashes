import pygame

# Screen and UI layout
SCREEN_WIDTH = 1600
SCREEN_HEIGHT = 900
MAP_VIEW_HEIGHT = int(SCREEN_HEIGHT * 0.80)
RIBBON_HEIGHT = SCREEN_HEIGHT - MAP_VIEW_HEIGHT
MAP_VIEW_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, MAP_VIEW_HEIGHT)
RIBBON_RECT = pygame.Rect(0, MAP_VIEW_HEIGHT, SCREEN_WIDTH, RIBBON_HEIGHT)

# Map dimensions
MAP_W = 3000
MAP_H = 4200
MID_Y = MAP_H // 2

# Colors
COLOR_BG = (22, 22, 24)
COLOR_RIBBON = (30, 30, 35)
COLOR_TERRAIN = (52, 52, 58)
COLOR_RIFT = (80, 50, 40)
COLOR_CROSSING = (90, 90, 98)
COLOR_LANE = (90, 120, 150)
COLOR_PLAYER = (36, 180, 190)
COLOR_ENEMY = (200, 70, 70)
COLOR_NEUTRAL = (210, 180, 60)
COLOR_WHITE = (230, 230, 230)
COLOR_DEBUG = (180, 180, 200)
COLOR_TOWER = (130, 110, 80)
COLOR_DESTROYED = (70, 60, 60)

# Rift and cliffs
CLIFF_BELT_WIDTH = 120
RIFT_TOP = 1980
RIFT_BOTTOM = 2220
CROSSING_W = 420
CROSSING_H = RIFT_BOTTOM - RIFT_TOP
X_W = 750
X_C = 1500
X_E = 2250

# Crossing rectangles (x0, y0, x1, y1)
CROSSINGS = [
    (540, RIFT_TOP, 960, RIFT_BOTTOM),
    (1290, RIFT_TOP, 1710, RIFT_BOTTOM),
    (2040, RIFT_TOP, 2460, RIFT_BOTTOM),
]

# Lane waypoints (south to north)
LANE_WAYPOINTS = {
    "WEST": [
        (750, 3600), (720, 3100), (700, 2650), (750, 2300), (750, 2100),
        (750, 1900), (800, 1550), (820, 1100), (750, 600), (750, 420)
    ],
    "CENTER": [
        (1500, 3600), (1500, 3150), (1500, 2700), (1500, 2350), (1500, 2100),
        (1500, 1850), (1500, 1500), (1500, 1050), (1500, 600), (1500, 420)
    ],
    "EAST": [
        (2250, 3600), (2280, 3100), (2300, 2650), (2250, 2300), (2250, 2100),
        (2250, 1900), (2200, 1550), (2180, 1100), (2250, 600), (2250, 420)
    ],
}

# Base rectangles
S_BASE_RECT = pygame.Rect(900, 3650, 1200, 530)
N_BASE_RECT = pygame.Rect(900, 20, 1200, 530)
S_KEEP_RECT = pygame.Rect(1200, 3850, 600, 270)
N_KEEP_RECT = pygame.Rect(1200, 80, 600, 270)
S_BOSS_SPAWN = (1500, 3990)
N_BOSS_SPAWN = (1500, 210)

# Graveyards
GY_SPAWN_RADIUS = 80
GY_CENTER_SPAWN_RADIUS = 90
GY_CAPTURE_RADIUS = 220
GY_CENTER_CAPTURE_RADIUS = 260
GRAVEYARDS_SOUTH = {
    "GY_S_HOME": (1500, 3400),
    "GY_S_WEST_FORWARD": (750, 2720),
    "GY_S_EAST_FORWARD": (2250, 2720),
    "GY_CENTER": (1500, 2100),
}
GRAVEYARDS_NORTH = {
    "GY_N_HOME": (1500, 800),
    "GY_N_WEST_FORWARD": (750, 1480),
    "GY_N_EAST_FORWARD": (2250, 1480),
    "GY_CENTER": (1500, 2100),
}

# Tower data
TOWER_CORE_IMPASSABLE_RADIUS_PX = 22
TOWER_CAPTURE_RADIUS_PX = 120
TOWER_POSITIONS_SOUTH = {
    "T_S_W_REAR": (950, 3300),
    "T_S_E_REAR": (2050, 3300),
    "T_S_W_FORWARD": (520, 2500),
    "T_S_E_FORWARD": (2480, 2500),
}
TOWER_APPROACH_SOUTH = {
    "T_S_W_REAR": (950, 3150),
    "T_S_E_REAR": (2050, 3150),
    "T_S_W_FORWARD": (650, 2600),
    "T_S_E_FORWARD": (2350, 2600),
}

# Captain bunkers
BUNKER_WALL_THICKNESS = 18
BUNKER_GATE_WIDTH = 260
S_BUNKER_RECT = pygame.Rect(1100, 2860, 800, 320)
S_BUNKER_CENTER = (1500, 3020)
S_BUNKER_APPROACH_SOUTH = (1500, 3250)
S_BUNKER_APPROACH_NORTH = (1500, 2790)

# Starting resources
STARTING_GOLD_PLAYER = 120
STARTING_GOLD_ENEMY = 120

# Camera constants
ZOOM_MIN = 0.35
ZOOM_MAX = 2.5
PAN_SPEED = 600  # pixels per second for keyboard WASD

# Debug
SHOW_DEBUG = True


def mirror_y(y: float) -> float:
    return MAP_H - y


def mirrored_position(pos):
    x, y = pos
    return x, mirror_y(y)


def build_north_towers():
    return {key.replace("S", "N"): (pos[0], mirror_y(pos[1])) for key, pos in TOWER_POSITIONS_SOUTH.items()}


def build_north_tower_approaches():
    return {key.replace("S", "N"): (pos[0], mirror_y(pos[1])) for key, pos in TOWER_APPROACH_SOUTH.items()}


def apply_screen_resolution(width: int, height: int):
    global SCREEN_WIDTH, SCREEN_HEIGHT, MAP_VIEW_HEIGHT, RIBBON_HEIGHT, MAP_VIEW_RECT, RIBBON_RECT

    SCREEN_WIDTH = width
    SCREEN_HEIGHT = height
    MAP_VIEW_HEIGHT = int(SCREEN_HEIGHT * 0.80)
    RIBBON_HEIGHT = SCREEN_HEIGHT - MAP_VIEW_HEIGHT
    MAP_VIEW_RECT = pygame.Rect(0, 0, SCREEN_WIDTH, MAP_VIEW_HEIGHT)
    RIBBON_RECT = pygame.Rect(0, MAP_VIEW_HEIGHT, SCREEN_WIDTH, RIBBON_HEIGHT)
