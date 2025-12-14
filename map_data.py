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
    archers_alive: int = config.ARCHERS_PER_TOWER
    occupy_timer: float = 0.0
    contested: bool = False


@dataclass
class Bunker:
    bunker_id: str
    faction_owner: str
    rect: pygame.Rect
    center: Tuple[float, float]
    approach_from_south: Tuple[float, float]
    approach_from_north: Tuple[float, float]
    wall_rects: List[pygame.Rect]
    state: str = "STANDING"
    captain_alive: bool = True


@dataclass
class MapGeometry:
    towers: List[Tower] = field(default_factory=list)
    bunkers: List[Bunker] = field(default_factory=list)
    graveyards: List[Graveyard] = field(default_factory=list)
    impassable_rects: List[pygame.Rect] = field(default_factory=list)


def destroy_tower(tower: Tower):
    """Mark a tower destroyed and clear capture state."""

    tower.state = "DESTROYED"
    tower.archers_alive = 0
    tower.occupy_timer = 0.0
    tower.contested = False


def destroy_bunker(bunker: Bunker):
    """Mark a bunker destroyed and remove its blocking walls."""

    bunker.state = "DESTROYED"
    bunker.captain_alive = False
    bunker.wall_rects = []


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
    north_approaches = config.build_north_tower_approaches()
    for tower_id, center in config.build_north_towers().items():
        towers.append(
            Tower(
                tower_id=tower_id,
                faction_owner="ENEMY",
                center=center,
                approach_point=north_approaches[tower_id],
            )
        )
    return towers


def build_bunkers() -> List[Bunker]:
    def build_wall_segments(rect: pygame.Rect) -> List[pygame.Rect]:
        x0, y0, w, h = rect
        x1 = x0 + w
        y1 = y0 + h

        gate_half_width = config.BUNKER_GATE_WIDTH // 2
        gates = []
        for center_x in config.BUNKER_GATE_CENTERLINES:
            gate_start = max(x0, center_x - gate_half_width)
            gate_end = min(x1, center_x + gate_half_width)
            if gate_end > gate_start:
                gates.append((gate_start, gate_end))

        def horizontal_segments(y: float) -> List[pygame.Rect]:
            segments = []
            cursor = x0
            for gate_start, gate_end in sorted(gates):
                if gate_start > cursor:
                    segments.append(
                        pygame.Rect(cursor, y, gate_start - cursor, config.BUNKER_WALL_THICKNESS)
                    )
                cursor = max(cursor, gate_end)
            if cursor < x1:
                segments.append(pygame.Rect(cursor, y, x1 - cursor, config.BUNKER_WALL_THICKNESS))
            return segments

        walls = [
            pygame.Rect(x0, y0, config.BUNKER_WALL_THICKNESS, h),
            pygame.Rect(x1 - config.BUNKER_WALL_THICKNESS, y0, config.BUNKER_WALL_THICKNESS, h),
            *horizontal_segments(y0),
            *horizontal_segments(y1 - config.BUNKER_WALL_THICKNESS),
        ]
        return walls

    bunkers = [
        Bunker(
            "S_BUNKER",
            "PLAYER",
            config.S_BUNKER_RECT.copy(),
            config.S_BUNKER_CENTER,
            approach_from_south=config.S_BUNKER_APPROACH_SOUTH,
            approach_from_north=config.S_BUNKER_APPROACH_NORTH,
            wall_rects=build_wall_segments(config.S_BUNKER_RECT),
        ),
    ]
    north_rect = config.N_BUNKER_RECT.copy()
    north_center = config.N_BUNKER_CENTER
    north_approach_south = config.N_BUNKER_APPROACH_SOUTH
    north_approach_north = config.N_BUNKER_APPROACH_NORTH
    bunkers.append(
        Bunker(
            "N_BUNKER",
            "ENEMY",
            north_rect,
            north_center,
            approach_from_south=north_approach_south,
            approach_from_north=north_approach_north,
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

    # Rift band minus crossings. Create segmented rectangles so impassables
    # mirror the true passable gaps from map_guidance.
    band_top = config.RIFT_TOP
    band_height = config.RIFT_BOTTOM - config.RIFT_TOP
    cursor_x = config.CLIFF_BELT_WIDTH
    for x0, _, x1, _ in sorted(config.CROSSINGS, key=lambda r: r[0]):
        if x0 > cursor_x:
            impassables.append(
                pygame.Rect(cursor_x, band_top, x0 - cursor_x, band_height)
            )
        cursor_x = max(cursor_x, x1)

    # Tail of the rift band after the final crossing.
    if cursor_x < config.MAP_W - config.CLIFF_BELT_WIDTH:
        impassables.append(
            pygame.Rect(cursor_x, band_top, (config.MAP_W - config.CLIFF_BELT_WIDTH) - cursor_x, band_height)
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

    # Tower cores (standing or vulnerable only)
    for tower in geom.towers:
        if tower.state == "DESTROYED":
            continue
        dx = px - tower.center[0]
        dy = py - tower.center[1]
        if dx * dx + dy * dy <= tower.core_radius * tower.core_radius:
            return False

    # Bunker walls
    for bunker in geom.bunkers:
        if bunker.state != "DESTROYED":
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
