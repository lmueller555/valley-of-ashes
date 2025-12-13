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
    state: str = "STANDING"
    captain_alive: bool = True


@dataclass
class MapGeometry:
    towers: List[Tower] = field(default_factory=list)
    bunkers: List[Bunker] = field(default_factory=list)
    graveyards: List[Graveyard] = field(default_factory=list)


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
    bunkers = [
        Bunker("S_BUNKER", "PLAYER", config.S_BUNKER_RECT.copy(), config.S_BUNKER_CENTER),
    ]
    north_rect = config.S_BUNKER_RECT.copy()
    north_rect.y = config.mirror_y(config.S_BUNKER_RECT.bottom)
    bunkers.append(
        Bunker("N_BUNKER", "ENEMY", north_rect, (config.S_BUNKER_CENTER[0], config.mirror_y(config.S_BUNKER_CENTER[1]))),
    )
    return bunkers


def build_map_geometry() -> MapGeometry:
    return MapGeometry(towers=build_towers(), bunkers=build_bunkers(), graveyards=build_graveyards())
