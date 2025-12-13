from dataclasses import dataclass, field
from typing import List, Tuple

import pygame

import config


@dataclass
class Graveyard:
    gy_id: str
    pos: Tuple[float, float]
    spawn_radius: float
    capture_radius: float
    starting_owner: str


@dataclass
class Tower:
    tower_id: str
    faction_owner: str
    center: Tuple[float, float]
    approach_point: Tuple[float, float]
    core_radius: float = config.TOWER_CORE_IMPASSABLE_RADIUS_PX
    capture_radius: float = config.TOWER_CAPTURE_RADIUS_PX
    state: str = "STANDING"
    archers_alive: int = 6
    occupy_timer: float = 0.0
    contested: bool = False


@dataclass
class Bunker:
    bunker_id: str
    faction_owner: str
    rect: pygame.Rect
    center: Tuple[float, float]
    wall_rects: List[pygame.Rect]
    state: str = "STANDING"
    captain_alive: bool = True


@dataclass
class MapGeometry:
    towers: List[Tower] = field(default_factory=list)
    bunkers: List[Bunker] = field(default_factory=list)
    graveyards: List[Graveyard] = field(default_factory=list)
    impassable_rects: List[pygame.Rect] = field(default_factory=list)


def build_graveyards() -> List[Graveyard]:
    graveyards = []
    for gy_id, pos in config.GRAVEYARDS_SOUTH.items():
        spawn_radius = config.GY_CENTER_SPAWN_RADIUS if gy_id == "GY_CENTER" else config.GY_SPAWN_RADIUS
        capture_radius = config.GY_CENTER_CAPTURE_RADIUS if gy_id == "GY_CENTER" else config.GY_CAPTURE_RADIUS
        graveyards.append(Graveyard(gy_id, pos, spawn_radius, capture_radius, "PLAYER" if gy_id != "GY_CENTER" else "NEUTRAL"))
    for gy_id, pos in config.GRAVEYARDS_NORTH.items():
        spawn_radius = config.GY_CENTER_SPAWN_RADIUS if gy_id == "GY_CENTER" else config.GY_SPAWN_RADIUS
        capture_radius = config.GY_CENTER_CAPTURE_RADIUS if gy_id == "GY_CENTER" else config.GY_CAPTURE_RADIUS
        graveyards.append(Graveyard(gy_id, pos, spawn_radius, capture_radius, "ENEMY" if gy_id != "GY_CENTER" else "NEUTRAL"))
    return graveyards


def build_towers() -> List[Tower]:
    towers = []
    for tower_id, center in config.TOWER_POSITIONS_SOUTH.items():
        towers.append(
            Tower(
                tower_id=tower_id,
                faction_owner="PLAYER",
                center=center,
                approach_point=config.TOWER_APPROACH_SOUTH[tower_id],
            )
        )
    for tower_id, center in config.build_north_towers().items():
        approaches = config.build_north_tower_approaches()
        towers.append(
            Tower(
                tower_id=tower_id,
                faction_owner="ENEMY",
                center=center,
                approach_point=approaches[tower_id],
            )
        )
    return towers


def build_bunkers() -> List[Bunker]:
    def build_wall_segments(rect: pygame.Rect) -> List[pygame.Rect]:
        x0, y0, w, h = rect
        x1 = x0 + w
        y1 = y0 + h
        gate_x0 = x0 + (w - config.BUNKER_GATE_WIDTH) // 2
        gate_x1 = gate_x0 + config.BUNKER_GATE_WIDTH
        walls = [
            pygame.Rect(x0, y0, config.BUNKER_WALL_THICKNESS, h),
            pygame.Rect(x1 - config.BUNKER_WALL_THICKNESS, y0, config.BUNKER_WALL_THICKNESS, h),
            pygame.Rect(x0, y0, gate_x0 - x0, config.BUNKER_WALL_THICKNESS),
            pygame.Rect(gate_x1, y0, x1 - gate_x1, config.BUNKER_WALL_THICKNESS),
            pygame.Rect(x0, y1 - config.BUNKER_WALL_THICKNESS, gate_x0 - x0, config.BUNKER_WALL_THICKNESS),
            pygame.Rect(gate_x1, y1 - config.BUNKER_WALL_THICKNESS, x1 - gate_x1, config.BUNKER_WALL_THICKNESS),
        ]
        return walls

    bunkers = [
        Bunker(
            "S_BUNKER",
            "PLAYER",
            config.S_BUNKER_RECT.copy(),
            config.S_BUNKER_CENTER,
            wall_rects=build_wall_segments(config.S_BUNKER_RECT),
        ),
    ]
    north_rect = config.S_BUNKER_RECT.copy()
    north_rect.y = config.mirror_y(config.S_BUNKER_RECT.bottom)
    bunkers.append(
        Bunker(
            "N_BUNKER",
            "ENEMY",
            north_rect,
            (config.S_BUNKER_CENTER[0], config.mirror_y(config.S_BUNKER_CENTER[1])),
            wall_rects=build_wall_segments(north_rect),
        ),
    )
    return bunkers


def build_impassables() -> List[pygame.Rect]:
    impassables = []

    # Cliff belts
    impassables.append(pygame.Rect(0, 0, config.CLIFF_BELT_WIDTH, config.MAP_H))
    impassables.append(
        pygame.Rect(config.MAP_W - config.CLIFF_BELT_WIDTH, 0, config.CLIFF_BELT_WIDTH, config.MAP_H)
    )

    # Rift band minus crossings (handled in passability checks)
    impassables.append(
        pygame.Rect(config.CLIFF_BELT_WIDTH, config.RIFT_TOP, config.MAP_W - 2 * config.CLIFF_BELT_WIDTH, config.RIFT_BOTTOM - config.RIFT_TOP)
    )

    return impassables


def is_inside_crossing(point: Tuple[float, float]) -> bool:
    px, py = point
    for x0, y0, x1, y1 in config.CROSSINGS:
        if x0 <= px <= x1 and y0 <= py <= y1:
            return True
    return False


def is_point_passable(point: Tuple[float, float], geom: MapGeometry) -> bool:
    px, py = point

    # Cliff belts
    if px < config.CLIFF_BELT_WIDTH or px > config.MAP_W - config.CLIFF_BELT_WIDTH:
        return False

    # Rift band except crossings
    if config.RIFT_TOP <= py <= config.RIFT_BOTTOM and not is_inside_crossing(point):
        return False

    # Tower cores
    for tower in geom.towers:
        dx = px - tower.center[0]
        dy = py - tower.center[1]
        if dx * dx + dy * dy <= tower.core_radius * tower.core_radius:
            return False

    # Bunker walls
    for bunker in geom.bunkers:
        for wall in bunker.wall_rects:
            if wall.collidepoint(px, py):
                return False

    return True


def build_map_geometry() -> MapGeometry:
    return MapGeometry(
        towers=build_towers(),
        bunkers=build_bunkers(),
        graveyards=build_graveyards(),
        impassable_rects=build_impassables(),
    )
