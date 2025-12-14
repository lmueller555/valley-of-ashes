from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import math

import pygame

import config
import map_data


UnitId = int


@dataclass
class Unit:
    unit_id: UnitId
    faction: str
    unit_type: str
    pos: Tuple[float, float]
    hp: float
    max_hp: float
    damage: float
    attack_range_px: float
    aggro_range_px: float
    attack_cooldown_s: float
    attack_timer_s: float
    move_speed_px_s: float
    state: str
    lane: str
    target_id: Optional[UnitId]
    leash_anchor: Tuple[float, float]
    leash_radius_px: float
    last_hit_by_faction: Optional[str] = None
    respawn_delay_s: float = 0.0

    def is_alive(self) -> bool:
        return self.state not in {"DEAD", "RESPAWNING"}


class SpatialHash:
    def __init__(self, cell_size: float = 180):
        self.cell_size = cell_size
        self.buckets: Dict[Tuple[int, int], List[UnitId]] = {}

    def clear(self):
        self.buckets.clear()

    def _cell_coords(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        x, y = pos
        return int(x // self.cell_size), int(y // self.cell_size)

    def insert(self, unit: Unit):
        cell = self._cell_coords(unit.pos)
        self.buckets.setdefault(cell, []).append(unit.unit_id)

    def query_radius(self, pos: Tuple[float, float], radius: float) -> List[UnitId]:
        cx, cy = self._cell_coords(pos)
        cells_offset = int(math.ceil(radius / self.cell_size))
        results: List[UnitId] = []
        for dx in range(-cells_offset, cells_offset + 1):
            for dy in range(-cells_offset, cells_offset + 1):
                bucket = self.buckets.get((cx + dx, cy + dy))
                if bucket:
                    results.extend(bucket)
        return results


class Battlefield:
    def __init__(self, geom: map_data.MapGeometry):
        self.geom = geom
        self.units: Dict[UnitId, Unit] = {}
        self.respawn_queue: List[Tuple[float, UnitId]] = []
        self.next_unit_id: UnitId = 1
        self.spatial = SpatialHash()
        self.time_s = 0.0

        self.player_home = config.GRAVEYARDS_SOUTH["GY_S_HOME"]
        self.enemy_home = config.GRAVEYARDS_NORTH["GY_N_HOME"]

    def _alloc_id(self) -> UnitId:
        uid = self.next_unit_id
        self.next_unit_id += 1
        return uid

    def _lane_waypoints(self, faction: str, lane: str) -> List[Tuple[float, float]]:
        pts = config.LANE_WAYPOINTS[lane]
        if faction == "PLAYER":
            return pts
        # Mirror for enemy marching south.
        mirrored = [config.mirrored_position(p) for p in reversed(pts)]
        return mirrored

    def spawn_unit(self, faction: str, unit_type: str, lane: str, pos: Optional[Tuple[float, float]] = None) -> Unit:
        stats = config.UNIT_STATS[unit_type]
        if pos is None:
            pos = self.player_home if faction == "PLAYER" else self.enemy_home
        uid = self._alloc_id()
        unit = Unit(
            unit_id=uid,
            faction=faction,
            unit_type=unit_type,
            pos=pos,
            hp=stats["max_hp"],
            max_hp=stats["max_hp"],
            damage=stats["damage"],
            attack_range_px=stats["attack_range_px"],
            aggro_range_px=stats["aggro_range_px"],
            attack_cooldown_s=stats["attack_cooldown_s"],
            attack_timer_s=stats["attack_cooldown_s"],
            move_speed_px_s=stats["move_speed_px_s"],
            state="MARCHING",
            lane=lane,
            target_id=None,
            leash_anchor=pos,
            leash_radius_px=0.0,
            respawn_delay_s=stats["respawn_delay_s"],
        )
        self.units[uid] = unit
        return unit

    def seed_wave(self, faction: str, counts: Dict[str, int]):
        lanes = ["WEST", "CENTER", "EAST"]
        lane_index = 0
        for unit_type, count in counts.items():
            for _ in range(count):
                lane = lanes[lane_index % len(lanes)]
                lane_index += 1
                self.spawn_unit(faction, unit_type, lane)

    def _nearest_graveyard(self, faction: str, pos: Tuple[float, float]) -> Tuple[float, float]:
        owned = [gy for gy in self.geom.graveyards if gy.starting_owner == faction]
        best = owned[0]
        best_d2 = (best.pos[0] - pos[0]) ** 2 + (best.pos[1] - pos[1]) ** 2
        for gy in owned[1:]:
            d2 = (gy.pos[0] - pos[0]) ** 2 + (gy.pos[1] - pos[1]) ** 2
            if d2 < best_d2:
                best = gy
                best_d2 = d2
        return best.pos

    def _update_spatial(self):
        self.spatial.clear()
        for unit in self.units.values():
            if unit.is_alive():
                self.spatial.insert(unit)

    def _apply_separation(self, dt: float):
        for unit in self.units.values():
            if not unit.is_alive() or unit.move_speed_px_s <= 0:
                continue
            neighbors = self.spatial.query_radius(unit.pos, config.SEPARATION_RADIUS_PX)
            if not neighbors:
                continue
            repulse_x = repulse_y = 0.0
            ux, uy = unit.pos
            for nid in neighbors:
                if nid == unit.unit_id:
                    continue
                other = self.units.get(nid)
                if other is None or not other.is_alive() or other.faction != unit.faction:
                    continue
                ox, oy = other.pos
                dx = ux - ox
                dy = uy - oy
                dist2 = dx * dx + dy * dy
                if dist2 == 0:
                    continue
                if dist2 <= config.SEPARATION_RADIUS_PX * config.SEPARATION_RADIUS_PX:
                    inv_dist = 1.0 / math.sqrt(dist2)
                    repulse_x += dx * inv_dist
                    repulse_y += dy * inv_dist
            length = math.hypot(repulse_x, repulse_y)
            if length > 0:
                speed = unit.move_speed_px_s * config.SEPARATION_PUSH_LIMIT
                unit.pos = (
                    ux + repulse_x / length * speed * dt,
                    uy + repulse_y / length * speed * dt,
                )

    def _select_target(self, unit: Unit) -> Optional[UnitId]:
        candidates = self.spatial.query_radius(unit.pos, unit.aggro_range_px)
        best_id = None
        best_dist2 = None
        ux, uy = unit.pos
        for cid in candidates:
            if cid == unit.unit_id:
                continue
            enemy = self.units.get(cid)
            if enemy is None or not enemy.is_alive() or enemy.faction == unit.faction:
                continue
            dx = enemy.pos[0] - ux
            dy = enemy.pos[1] - uy
            dist2 = dx * dx + dy * dy
            if dist2 > unit.aggro_range_px * unit.aggro_range_px:
                continue
            if best_id is None or dist2 < best_dist2 or (
                dist2 == best_dist2 and enemy.hp < self.units[best_id].hp
            ):
                best_id = enemy.unit_id
                best_dist2 = dist2
        return best_id

    def _advance_waypoint(self, unit: Unit, dt: float):
        waypoints = self._lane_waypoints(unit.faction, unit.lane)
        # Determine current target waypoint index based on progress stored in leash_anchor.
        if not hasattr(unit, "_wp_index"):
            unit._wp_index = 0
        if unit._wp_index >= len(waypoints):
            return
        target = waypoints[unit._wp_index]
        ux, uy = unit.pos
        dx = target[0] - ux
        dy = target[1] - uy
        dist = math.hypot(dx, dy)
        if dist < 8:
            unit._wp_index += 1
            return
        if dist > 0:
            step = unit.move_speed_px_s * dt
            if step >= dist:
                unit.pos = target
                unit._wp_index += 1
            else:
                unit.pos = (ux + dx / dist * step, uy + dy / dist * step)

    def _update_unit(self, unit: Unit, dt: float):
        if unit.state in {"DEAD", "RESPAWNING"}:
            return

        if unit.target_id is not None:
            target = self.units.get(unit.target_id)
            if target is None or not target.is_alive():
                unit.target_id = None
            else:
                tx, ty = target.pos
                dx = tx - unit.pos[0]
                dy = ty - unit.pos[1]
                dist2 = dx * dx + dy * dy
                if dist2 > unit.aggro_range_px * unit.aggro_range_px:
                    unit.target_id = None

        if unit.target_id is None:
            unit.target_id = self._select_target(unit)

        if unit.target_id is not None:
            target = self.units[unit.target_id]
            tx, ty = target.pos
            dx = tx - unit.pos[0]
            dy = ty - unit.pos[1]
            dist = math.hypot(dx, dy)
            if dist > unit.attack_range_px:
                if dist > 0:
                    step = unit.move_speed_px_s * dt
                    unit.pos = (
                        unit.pos[0] + dx / dist * step,
                        unit.pos[1] + dy / dist * step,
                    )
            else:
                unit.attack_timer_s -= dt
                if unit.attack_timer_s <= 0:
                    target.hp -= unit.damage
                    target.last_hit_by_faction = unit.faction
                    unit.attack_timer_s = unit.attack_cooldown_s
                    if target.hp <= 0:
                        target.state = "DEAD"
                        self.respawn_queue.append((self.time_s + target.respawn_delay_s, target.unit_id))
        else:
            self._advance_waypoint(unit, dt)

    def _process_respawns(self):
        if not self.respawn_queue:
            return
        remaining = []
        for respawn_time, uid in self.respawn_queue:
            unit = self.units.get(uid)
            if unit is None:
                continue
            if self.time_s >= respawn_time:
                pos = self._nearest_graveyard(unit.faction, unit.pos)
                unit.pos = pos
                unit.hp = unit.max_hp
                unit.state = "MARCHING"
                unit.target_id = None
                unit.attack_timer_s = unit.attack_cooldown_s
            else:
                remaining.append((respawn_time, uid))
        self.respawn_queue = remaining

    def update(self, dt: float):
        self.time_s += dt
        self._update_spatial()
        for unit in self.units.values():
            self._update_unit(unit, dt)
        self._apply_separation(dt)
        self._process_respawns()

    def draw(self, surface, camera):
        for unit in self.units.values():
            if not unit.is_alive():
                continue
            sx, sy = camera.world_to_screen(unit.pos)
            color = config.COLOR_PLAYER if unit.faction == "PLAYER" else config.COLOR_ENEMY
            pygame.draw.circle(surface, color, (int(sx), int(sy)), max(2, int(5 * camera.zoom)))

