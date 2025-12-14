import math
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

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
    gold_reward: int = 0
    respawns: bool = True
    remaining_respawns: int = config.UNIT_MAX_RESPAWNS
    structure_id: Optional[str] = None  # tower/bunker association for defenders
    base_max_hp: Optional[float] = None  # used for boss scaling
    base_damage: Optional[float] = None
    out_of_combat_time_s: float = 0.0
    regen_timer_s: float = 0.0
    time_off_lane_s: float = 0.0
    heal_timer_s: float = 0.0
    heal_anim_timer_s: float = 0.0
    taunt_timer_s: float = 0.0

    def is_alive(self) -> bool:
        return self.state not in {"DEAD", "RESPAWNING"}


class SpatialHash:
    def __init__(self, cell_size: float = config.SPATIAL_HASH_CELL_SIZE):
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
        self.next_unit_id: UnitId = 1
        self.spatial = SpatialHash()
        self.time_s = 0.0

        self.boss_units: Dict[str, UnitId] = {}

        self.gold: Dict[str, int] = {
            "PLAYER": config.STARTING_GOLD_PLAYER,
            "ENEMY": config.STARTING_GOLD_ENEMY,
        }
        self.kills: Dict[str, int] = {"PLAYER": 0, "ENEMY": 0}

        self.game_over = False
        self.winner: Optional[str] = None

        self.player_home = config.GRAVEYARDS_SOUTH["GY_S_HOME"]
        self.enemy_home = config.GRAVEYARDS_NORTH["GY_N_HOME"]
        self._lane_purchase_index = 0

        self._spawn_defenders()

    def _alloc_id(self) -> UnitId:
        uid = self.next_unit_id
        self.next_unit_id += 1
        return uid

    def _enemy_faction(self, faction: str) -> str:
        return "ENEMY" if faction == "PLAYER" else "PLAYER"

    def _spawn_defenders(self):
        """Spawn archers, captains, and bosses defined in guidance."""

        # Tower archers
        archer_offsets = [(-18, -10), (18, -10), (-18, 10), (18, 10), (0, -18), (0, 18)]
        for tower in self.geom.towers:
            for dx, dy in archer_offsets:
                pos = (tower.center[0] + dx, tower.center[1] + dy)
                archer = self.spawn_unit(tower.faction_owner, "TOWER_ARCHER", lane="NONE", pos=pos)
                archer.state = "DEFENDING"
                archer.leash_anchor = tower.center
                archer.leash_radius_px = config.TOWER_CAPTURE_RADIUS_PX
                archer.respawns = False
                archer.remaining_respawns = 0
                archer.structure_id = tower.tower_id

        # Captains
        for bunker in self.geom.bunkers:
            captain = self.spawn_unit(bunker.faction_owner, "CAPTAIN", lane="NONE", pos=bunker.center)
            captain.state = "DEFENDING"
            captain.leash_anchor = bunker.center
            captain.leash_radius_px = 120
            captain.respawns = False
            captain.remaining_respawns = 0
            captain.structure_id = bunker.bunker_id

        # Bosses with scaling
        for faction, spawn in config.BOSS_SPAWN.items():
            boss = self.spawn_unit(faction, "BOSS", lane="NONE", pos=spawn)
            boss.state = "DEFENDING"
            boss.leash_anchor = spawn
            boss.leash_radius_px = config.BOSS_LEASH_RADIUS
            boss.respawns = False
            boss.remaining_respawns = 0
            boss.base_max_hp = config.BOSS_BASE_MAX_HP
            boss.base_damage = config.BOSS_BASE_DAMAGE
            self.boss_units[faction] = boss.unit_id
        self._update_boss_scaling("PLAYER")
        self._update_boss_scaling("ENEMY")

        self.ai_controller = None

    def _lane_waypoints(self, faction: str, lane: str) -> List[Tuple[float, float]]:
        pts = config.LANE_WAYPOINTS[lane]
        if faction == "PLAYER":
            return pts
        # Mirror for enemy marching south (keep waypoint order aligned to advance southward).
        mirrored = [config.mirrored_position(p) for p in pts]
        return mirrored

    def spawn_unit(self, faction: str, unit_type: str, lane: str, pos: Optional[Tuple[float, float]] = None) -> Unit:
        stats = config.UNIT_STATS[unit_type]
        if pos is None:
            if lane in config.LANE_WAYPOINTS:
                waypoints = self._lane_waypoints(faction, lane)
                pos = waypoints[0]
            else:
                pos = self.player_home if faction == "PLAYER" else self.enemy_home
        uid = self._alloc_id()
        max_respawns = config.UNIT_RESPAWNS.get(unit_type, 0)
        respawns = max_respawns > 0
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
            gold_reward=stats["gold_reward"],
            respawns=respawns,
        )
        unit.remaining_respawns = stats.get("max_respawns", max_respawns if respawns else 0)
        self.units[uid] = unit
        self._reset_waypoint_progress(unit)
        return unit

    def seed_wave(self, faction: str, counts: Dict[str, int]):
        lanes = ["WEST", "CENTER", "EAST"]
        lane_index = 0
        for unit_type, count in counts.items():
            for _ in range(count):
                lane = lanes[lane_index % len(lanes)]
                lane_index += 1
                self.spawn_unit(faction, unit_type, lane)

    def seed_lane_wave(self, faction: str, lane_counts: Dict[str, int]):
        lanes = ["WEST", "CENTER", "EAST"]
        for lane in lanes:
            for unit_type, count in lane_counts.items():
                for _ in range(count):
                    self.spawn_unit(faction, unit_type, lane)

    def _next_lane(self) -> str:
        lanes = ["WEST", "CENTER", "EAST"]
        lane = lanes[self._lane_purchase_index % len(lanes)]
        self._lane_purchase_index += 1
        return lane

    def purchase_unit(self, faction: str, unit_type: str, lane: Optional[str] = None) -> bool:
        cost = config.UNIT_STATS[unit_type]["cost"]
        if self.gold.get(faction, 0) < cost:
            return False
        chosen_lane = lane if lane is not None else self._next_lane()
        if lane is None:
            # Only advance rotation when we selected lane internally
            pass
        self.gold[faction] -= cost
        self.spawn_unit(faction, unit_type, chosen_lane)
        return True

    def _home_graveyard(self, faction: str) -> Optional[map_data.Graveyard]:
        target_id = "GY_S_HOME" if faction == "PLAYER" else "GY_N_HOME"
        for gy in self.geom.graveyards:
            if gy.gy_id == target_id:
                return gy
        return None

    def _nearest_graveyard(self, faction: str, pos: Tuple[float, float]) -> Optional[map_data.Graveyard]:
        owned = [gy for gy in self.geom.graveyards if gy.owner == faction]
        if not owned:
            return self._home_graveyard(faction)
        best = owned[0]
        best_d2 = (best.pos[0] - pos[0]) ** 2 + (best.pos[1] - pos[1]) ** 2
        for gy in owned[1:]:
            d2 = (gy.pos[0] - pos[0]) ** 2 + (gy.pos[1] - pos[1]) ** 2
            if d2 < best_d2:
                best = gy
                best_d2 = d2
        return best

    def _update_spatial(self):
        self.spatial.clear()
        for unit in self.units.values():
            if unit.is_alive():
                self.spatial.insert(unit)

    def _update_boss_scaling(self, faction: str):
        boss_id = self.boss_units.get(faction)
        if boss_id is None:
            return
        boss = self.units.get(boss_id)
        if boss is None:
            return

        standing = sum(1 for t in self.geom.towers if t.faction_owner == faction and t.state != "DESTROYED")
        mult = 1.0 + config.BOSS_HP_PER_TOWER_MULT * standing
        old_max = boss.max_hp
        ratio = boss.hp / old_max if old_max > 0 else 1.0
        boss.max_hp = boss.base_max_hp * mult if boss.base_max_hp else boss.max_hp
        boss.damage = boss.base_damage * mult if boss.base_damage else boss.damage
        boss.hp = max(1, min(boss.max_hp, ratio * boss.max_hp))

    def _is_near_lane(self, pos: Tuple[float, float]) -> bool:
        lane_centers = (config.X_W, config.X_C, config.X_E)
        return any(abs(pos[0] - cx) <= config.LANE_PROXIMITY_THRESHOLD_PX for cx in lane_centers)

    def _nearest_lane_point(self, unit: Unit) -> Optional[Tuple[str, Tuple[float, float]]]:
        best_lane: Optional[str] = None
        best_point: Optional[Tuple[float, float]] = None
        best_d2: Optional[float] = None

        for lane, _ in config.LANE_WAYPOINTS.items():
            waypoints = self._lane_waypoints(unit.faction, lane)
            for pt in waypoints:
                dx = pt[0] - unit.pos[0]
                dy = pt[1] - unit.pos[1]
                d2 = dx * dx + dy * dy
                if best_d2 is None or d2 < best_d2:
                    best_d2 = d2
                    best_lane = lane
                    best_point = pt

        if best_lane is None or best_point is None:
            return None
        return best_lane, best_point

    def _recover_stuck_unit(self, unit: Unit, dt: float):
        if unit.move_speed_px_s <= 0 or unit.lane not in config.LANE_WAYPOINTS:
            unit.time_off_lane_s = 0.0
            return

        if self._is_near_lane(unit.pos):
            unit.time_off_lane_s = 0.0
            return

        unit.time_off_lane_s += dt
        if unit.time_off_lane_s < config.STUCK_LANE_TIMEOUT_S:
            return

        nearest = self._nearest_lane_point(unit)
        if nearest is None:
            return

        new_lane, dest = nearest
        unit.pos = dest
        unit.lane = new_lane
        unit.time_off_lane_s = 0.0
        unit.target_id = None
        self._reset_waypoint_progress(unit)

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

    def _bunker_for_id(self, bunker_id: Optional[str]) -> Optional[map_data.Bunker]:
        if bunker_id is None:
            return None
        for bunker in self.geom.bunkers:
            if bunker.bunker_id == bunker_id:
                return bunker
        return None

    def _elite_aggro_zone(self, unit: Unit) -> Optional[Tuple[pygame.Rect, Tuple[float, float]]]:
        if unit.unit_type == "CAPTAIN":
            bunker = self._bunker_for_id(unit.structure_id)
            if bunker is not None:
                return bunker.rect, bunker.center
        elif unit.unit_type == "BOSS":
            keep_rect = config.S_KEEP_RECT if unit.faction == "PLAYER" else config.N_KEEP_RECT
            return keep_rect, keep_rect.center
        return None

    def _select_elite_target(self, unit: Unit, zone: pygame.Rect) -> Optional[UnitId]:
        best_id = None
        best_dist2 = None
        ux, uy = unit.pos
        for enemy in self.units.values():
            if not enemy.is_alive() or enemy.faction == unit.faction:
                continue
            ex, ey = enemy.pos
            if not zone.collidepoint(ex, ey):
                continue
            dist2 = (ex - ux) * (ex - ux) + (ey - uy) * (ey - uy)
            if best_id is None or dist2 < best_dist2:
                best_id = enemy.unit_id
                best_dist2 = dist2
        return best_id

    def _friendly_bunker_bonus(self, unit: Unit) -> bool:
        if unit.unit_type == "TOWER_ARCHER":
            return False
        for bunker in self.geom.bunkers:
            if (
                bunker.faction_owner == unit.faction
                and bunker.state != "DESTROYED"
                and bunker.captain_alive
                and bunker.rect.collidepoint(*unit.pos)
            ):
                return True
        return False

    def _effective_attack_cooldown(self, unit: Unit) -> float:
        cooldown = unit.attack_cooldown_s
        if self._friendly_bunker_bonus(unit):
            cooldown *= 0.8
        return cooldown

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
                dist2 == best_dist2
                and (enemy.hp < self.units[best_id].hp or (
                    enemy.hp == self.units[best_id].hp and enemy.unit_id < best_id
                ))
            ):
                best_id = enemy.unit_id
                best_dist2 = dist2
        return best_id

    def _on_unit_death(self, unit: Unit):
        if unit.state in {"DEAD", "RESPAWNING"}:
            return

        if unit.respawns and unit.remaining_respawns > 0:
            gy = self._nearest_graveyard(unit.faction, unit.pos)
            if gy is not None:
                unit.state = "RESPAWNING"
                if not gy.waiting_units:
                    gy.respawn_timer = 0.0
                gy.waiting_units.append(unit.unit_id)
                self._update_graveyard_respawn_progress(gy)
            else:
                unit.state = "DEAD"
        else:
            unit.state = "DEAD"
            unit.remaining_respawns = 0

        # Structure bookkeeping
        if unit.unit_type == "TOWER_ARCHER" and unit.structure_id:
            for tower in self.geom.towers:
                if tower.tower_id == unit.structure_id:
                    tower.archers_alive = max(0, tower.archers_alive - 1)
                    if tower.archers_alive == 0 and tower.state == "STANDING":
                        tower.state = "VULNERABLE"
                    break
        if unit.unit_type == "CAPTAIN" and unit.structure_id:
            for bunker in self.geom.bunkers:
                if bunker.bunker_id == unit.structure_id:
                    bunker.captain_alive = False
                    map_data.destroy_bunker(bunker)
                    break
        if unit.unit_type == "BOSS":
            self.game_over = True
            self.winner = self._enemy_faction(unit.faction)

        killer_faction = unit.last_hit_by_faction
        if killer_faction and killer_faction != unit.faction:
            self.gold[killer_faction] = self.gold.get(killer_faction, 0) + unit.gold_reward
            self.kills[killer_faction] = self.kills.get(killer_faction, 0) + 1

    def _reset_waypoint_progress(self, unit: Unit):
        if unit.lane not in config.LANE_WAYPOINTS:
            return
        waypoints = self._lane_waypoints(unit.faction, unit.lane)
        if not waypoints:
            return
        direction = 1 if unit.faction == "ENEMY" else -1  # Enemy marches south (increasing y)
        pos_x, pos_y = unit.pos

        def is_forward(idx: int) -> bool:
            wp_y = waypoints[idx][1]
            return (wp_y - pos_y) * direction >= -config.LANE_WIDTH * 0.25

        forward_indices = [idx for idx in range(len(waypoints)) if is_forward(idx)]
        candidates = forward_indices if forward_indices else range(len(waypoints))
        best = min(
            candidates,
            key=lambda idx: (waypoints[idx][0] - pos_x) ** 2 + (waypoints[idx][1] - pos_y) ** 2,
        )
        unit._wp_index = best

    def _advance_waypoint(self, unit: Unit, dt: float):
        waypoints = self._lane_waypoints(unit.faction, unit.lane)
        if not hasattr(unit, "_wp_index"):
            self._reset_waypoint_progress(unit)
        if not hasattr(unit, "_wp_index"):
            return
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
            step_ratio = min(1.0, step / dist)
            proposed = (ux + dx * step_ratio, uy + dy * step_ratio)
            if map_data.is_point_passable(proposed, self.geom):
                unit.pos = proposed
                if step_ratio >= 1.0:
                    unit._wp_index += 1
            else:
                # If blocked, try a half step to reduce tunneling into impassables.
                half_step = (ux + dx * step_ratio * 0.5, uy + dy * step_ratio * 0.5)
                if map_data.is_point_passable(half_step, self.geom):
                    unit.pos = half_step
                # If still blocked, stay in place and wait for separation or path opening.

    def _update_regeneration(self, unit: Unit, dt: float, in_combat: bool):
        if in_combat:
            unit.out_of_combat_time_s = 0.0
            unit.regen_timer_s = 0.0
            return

        unit.out_of_combat_time_s += dt

        if unit.hp >= unit.max_hp:
            return

        if unit.out_of_combat_time_s < config.REGEN_OUT_OF_COMBAT_DELAY_S:
            return

        unit.regen_timer_s += dt
        while unit.regen_timer_s >= config.REGEN_INTERVAL_S:
            unit.regen_timer_s -= config.REGEN_INTERVAL_S
            heal_amount = unit.max_hp * config.REGEN_PERCENT
            unit.hp = min(unit.max_hp, unit.hp + heal_amount)

    def _update_healer(self, unit: Unit, dt: float):
        if unit.unit_type != "HEALER":
            return

        unit.heal_timer_s += dt
        unit.heal_anim_timer_s = max(0.0, unit.heal_anim_timer_s - dt)

        if unit.heal_timer_s < config.HEALER_HEAL_COOLDOWN_S:
            return

        unit.heal_timer_s -= config.HEALER_HEAL_COOLDOWN_S

        healed_any = False
        candidates = self.spatial.query_radius(unit.pos, config.HEALER_HEAL_RADIUS_PX)
        for cid in candidates:
            ally = self.units.get(cid)
            if ally is None or not ally.is_alive() or ally.faction != unit.faction:
                continue
            if ally.hp >= ally.max_hp:
                continue
            heal_amount = ally.max_hp * config.HEALER_HEAL_PERCENT
            ally.hp = min(ally.max_hp, ally.hp + heal_amount)
            healed_any = True

        if healed_any:
            unit.heal_anim_timer_s = config.HEALER_HEAL_ANIM_DURATION_S

    def _taunt_nearest_enemies(self, unit: Unit):
        candidates = self.spatial.query_radius(unit.pos, unit.aggro_range_px)
        enemies: List[Tuple[float, Unit]] = []
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
            if dist2 <= unit.aggro_range_px * unit.aggro_range_px:
                enemies.append((dist2, enemy))

        enemies.sort(key=lambda item: (item[0], item[1].unit_id))
        for _, enemy in enemies[: config.BULWARK_TAUNT_TARGETS]:
            enemy.target_id = unit.unit_id

    def _update_bulwark(self, unit: Unit, dt: float):
        if unit.unit_type != "BULWARK":
            return

        unit.taunt_timer_s += dt
        if unit.taunt_timer_s < config.BULWARK_TAUNT_COOLDOWN_S:
            return

        unit.taunt_timer_s -= config.BULWARK_TAUNT_COOLDOWN_S
        self._taunt_nearest_enemies(unit)

    def _update_unit(self, unit: Unit, dt: float):
        if unit.state in {"DEAD", "RESPAWNING"}:
            return

        self._recover_stuck_unit(unit, dt)
        self._update_bulwark(unit, dt)
        self._update_healer(unit, dt)

        elite_zone = self._elite_aggro_zone(unit)

        if unit.target_id is not None:
            target = self.units.get(unit.target_id)
            if target is None or not target.is_alive():
                unit.target_id = None
            else:
                tx, ty = target.pos
                dx = tx - unit.pos[0]
                dy = ty - unit.pos[1]
                dist2 = dx * dx + dy * dy
                target_inside_zone = elite_zone is not None and elite_zone[0].collidepoint(tx, ty)
                if not target_inside_zone and dist2 > unit.aggro_range_px * unit.aggro_range_px:
                    unit.target_id = None

        if elite_zone is not None:
            elite_target = self._select_elite_target(unit, elite_zone[0])
            if elite_target is not None:
                unit.target_id = elite_target
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
                    unit.attack_timer_s = self._effective_attack_cooldown(unit)
                    if target.hp <= 0:
                        self._on_unit_death(target)
        elif elite_zone is not None:
            if unit.pos != elite_zone[1]:
                unit.pos = elite_zone[1]
        else:
            if unit.move_speed_px_s > 0 and unit.lane in config.LANE_WAYPOINTS:
                self._advance_waypoint(unit, dt)

        in_combat = unit.target_id is not None
        self._update_regeneration(unit, dt, in_combat)

    def _respawn_unit_at_graveyard(self, unit: Unit, gy: map_data.Graveyard):
        unit.pos = gy.pos
        unit.hp = unit.max_hp
        unit.state = "MARCHING"
        unit.target_id = None
        unit.attack_timer_s = unit.attack_cooldown_s
        unit.last_hit_by_faction = None
        unit._wp_index = 0
        unit.out_of_combat_time_s = 0.0
        unit.regen_timer_s = 0.0
        unit.heal_timer_s = 0.0
        unit.heal_anim_timer_s = 0.0
        unit.taunt_timer_s = 0.0

    def _update_graveyard_respawn_progress(self, gy: map_data.Graveyard):
        if not gy.waiting_units:
            gy.respawn_timer = 0.0
            gy.respawn_interval = 0.0
            return

        gy.respawn_interval = config.GY_RESPAWN_INTERVAL
        gy.respawn_timer = min(gy.respawn_timer, gy.respawn_interval)

    def _process_respawns(self, dt: float):
        for gy in self.geom.graveyards:
            if not gy.waiting_units:
                self._update_graveyard_respawn_progress(gy)
                continue

            gy.respawn_timer += dt
            if gy.respawn_timer < config.GY_RESPAWN_INTERVAL:
                self._update_graveyard_respawn_progress(gy)
                continue

            gy.respawn_timer -= config.GY_RESPAWN_INTERVAL
            respawn_queue = gy.waiting_units
            gy.waiting_units = []

            for unit_id in respawn_queue:
                unit = self.units.get(unit_id)
                if unit is None or not unit.respawns:
                    continue
                if unit.remaining_respawns <= 0:
                    unit.state = "DEAD"
                    unit.remaining_respawns = 0
                    continue

                target_gy = gy if gy.owner == unit.faction else self._nearest_graveyard(unit.faction, gy.pos)
                if target_gy is None:
                    unit.state = "DEAD"
                    continue

                unit.remaining_respawns -= 1
                self._respawn_unit_at_graveyard(unit, target_gy)
                self._reset_waypoint_progress(unit)

            self._update_graveyard_respawn_progress(gy)

    def _update_tower_states(self, dt: float):
        for tower in self.geom.towers:
            if tower.state == "DESTROYED":
                continue

            # Count units in capture radius
            enemy_counts = {"PLAYER": 0, "ENEMY": 0}
            for unit in self.units.values():
                if not unit.is_alive() or unit.unit_type == "TOWER_ARCHER":
                    continue
                dx = unit.pos[0] - tower.center[0]
                dy = unit.pos[1] - tower.center[1]
                dist2 = dx * dx + dy * dy
                if dist2 <= config.TOWER_CONTEST_RADIUS_PX * config.TOWER_CONTEST_RADIUS_PX:
                    enemy_counts[unit.faction] += 1

            owner = tower.faction_owner
            attacker = self._enemy_faction(owner)
            tower.contested = enemy_counts[owner] > 0 and enemy_counts[attacker] > 0

            if tower.state == "STANDING" and tower.archers_alive == 0:
                tower.state = "VULNERABLE"

            if tower.state == "VULNERABLE":
                in_capture = 0
                for unit in self.units.values():
                    if not unit.is_alive() or unit.unit_type == "TOWER_ARCHER":
                        continue
                    dx = unit.pos[0] - tower.center[0]
                    dy = unit.pos[1] - tower.center[1]
                    dist2 = dx * dx + dy * dy
                    if dist2 <= tower.capture_radius * tower.capture_radius and unit.faction == attacker:
                        in_capture += 1

                if in_capture > 0 and enemy_counts[owner] == 0:
                    tower.occupy_timer += dt
                elif tower.occupy_timer > 0 and in_capture == 0 and enemy_counts[owner] == 0:
                    tower.occupy_timer = max(0.0, tower.occupy_timer - dt * config.TOWER_CAPTURE_DECAY_RATE)

                if tower.occupy_timer >= config.TOWER_CAPTURE_DURATION_S:
                    map_data.destroy_tower(tower)
                    self._update_boss_scaling(owner)

    def _update_graveyards(self, dt: float):
        for gy in self.geom.graveyards:
            # Count units in capture radius
            counts = {"PLAYER": 0, "ENEMY": 0}
            for unit in self.units.values():
                if not unit.is_alive() or unit.unit_type == "TOWER_ARCHER":
                    continue
                dx = unit.pos[0] - gy.pos[0]
                dy = unit.pos[1] - gy.pos[1]
                dist2 = dx * dx + dy * dy
                if dist2 <= gy.capture_radius * gy.capture_radius:
                    counts[unit.faction] += 1

            occupier = None
            if counts["PLAYER"] > 0 and counts["ENEMY"] == 0:
                occupier = "PLAYER"
            elif counts["ENEMY"] > 0 and counts["PLAYER"] == 0:
                occupier = "ENEMY"

            if occupier is not None and occupier != gy.owner:
                gy.capture_timer += dt
            elif gy.capture_timer > 0 and occupier is None:
                gy.capture_timer = max(0.0, gy.capture_timer - dt * config.GY_CAPTURE_DECAY_RATE)

            if gy.capture_timer >= gy.capture_time_required:
                gy.owner = occupier if occupier else gy.owner
                gy.capture_timer = 0.0


    def update(self, dt: float):
        self.time_s += dt
        if getattr(self, "game_over", False):
            return

        self._update_spatial()
        for unit in self.units.values():
            self._update_unit(unit, dt)
        self._apply_separation(dt)
        self._process_respawns(dt)
        self._update_tower_states(dt)
        self._update_graveyards(dt)

    def draw(self, surface, camera):
        for unit in self.units.values():
            if not unit.is_alive():
                continue

            sx, sy = camera.world_to_screen(unit.pos)
            color = config.COLOR_PLAYER if unit.faction == "PLAYER" else config.COLOR_ENEMY

            # Zoom-based level of detail per ui_guidance.
            zoom = camera.zoom
            base_radius = {
                "BOSS": 9,
                "CAPTAIN": 7,
            }.get(unit.unit_type, 5)
            if zoom < 0.75:
                radius = max(2, int(3 * zoom))
            else:
                radius = max(2, int(base_radius * zoom))
            pygame.draw.circle(surface, color, (int(sx), int(sy)), radius)

            if unit.unit_type == "HEALER" and unit.heal_anim_timer_s > 0:
                t = unit.heal_anim_timer_s / config.HEALER_HEAL_ANIM_DURATION_S
                ring_radius = int((radius + 6) + (18 * (1 - t)) * zoom)
                ring_radius = max(ring_radius, radius + 4)
                ring_size = ring_radius * 2 + 2
                ring_surface = pygame.Surface((ring_size, ring_size), pygame.SRCALPHA)
                alpha = max(40, int(160 * t))
                pygame.draw.circle(
                    ring_surface,
                    (*config.COLOR_HEAL, alpha),
                    (ring_radius + 1, ring_radius + 1),
                    ring_radius,
                    width=3,
                )
                surface.blit(ring_surface, (int(sx) - ring_radius - 1, int(sy) - ring_radius - 1))

            show_health = False
            if zoom >= 1.3:
                show_health = True
            elif zoom >= 0.75 and unit.unit_type in {"BOSS", "CAPTAIN"}:
                show_health = True

            if show_health and unit.hp < unit.max_hp:
                ratio = unit.hp / unit.max_hp if unit.max_hp else 0
                bar_width = {
                    "BOSS": 30,
                    "CAPTAIN": 22,
                }.get(unit.unit_type, 16)
                bar_height = {
                    "BOSS": 5,
                    "CAPTAIN": 4,
                }.get(unit.unit_type, 3)
                bar_width = max(6, int(bar_width * zoom))
                bar_height = max(2, int(bar_height * zoom))
                bar_x = int(sx - bar_width / 2)
                bar_y = int(sy - radius - bar_height - max(2, int(3 * zoom)))

                if ratio >= 0.75:
                    bar_color = config.COLOR_HEALTH_GREEN
                elif ratio >= 0.5:
                    bar_color = config.COLOR_HEALTH_YELLOW
                elif ratio >= 0.25:
                    bar_color = config.COLOR_HEALTH_ORANGE
                else:
                    bar_color = config.COLOR_HEALTH_RED

                pygame.draw.rect(surface, config.COLOR_HEALTH_BG, (bar_x, bar_y, bar_width, bar_height))
                fill_width = max(1, int(bar_width * ratio))
                pygame.draw.rect(surface, bar_color, (bar_x, bar_y, fill_width, bar_height))


class MacroAI:
    def __init__(self, battlefield: Battlefield):
        self.battlefield = battlefield
        self.sense_timer = 0.0
        self.decision_timer = 0.0
        self.cached_counts = {"PLAYER": 0, "ENEMY": 0}
        self.purchase_cooldowns: Dict[str, float] = {key: -999.0 for key in config.AI_PURCHASE_COOLDOWNS}
        self.lane_index = 0

    def _count_active_units(self):
        counts = {"PLAYER": 0, "ENEMY": 0}
        for unit in self.battlefield.units.values():
            if unit.is_alive() and unit.unit_type not in {"TOWER_ARCHER", "CAPTAIN", "BOSS"}:
                counts[unit.faction] += 1
        self.cached_counts = counts

    def _pick_lane(self) -> str:
        lanes = ["WEST", "CENTER", "EAST"]
        lane = lanes[self.lane_index % len(lanes)]
        self.lane_index += 1
        return lane

    def _can_purchase(self, unit_type: str) -> bool:
        now = self.battlefield.time_s
        cooldown = config.AI_PURCHASE_COOLDOWNS.get(unit_type, 0.0)
        return now - self.purchase_cooldowns.get(unit_type, -999.0) >= cooldown

    def _attempt_purchase(self, unit_type: str) -> bool:
        if not self._can_purchase(unit_type):
            return False
        lane_override = self._pick_lane()
        cost = config.UNIT_STATS[unit_type]["cost"]
        if self.battlefield.gold["ENEMY"] < cost:
            return False
        success = self.battlefield.purchase_unit("ENEMY", unit_type, lane_override)
        if not success:
            return False
        self.purchase_cooldowns[unit_type] = self.battlefield.time_s
        return True

    def _decision_tick(self):
        if self.battlefield.game_over:
            return
        purchases = 0
        gold_spent = 0
        max_spend = self.battlefield.gold["ENEMY"] * config.AI_SPEND_FRACTION_PER_TICK
        target_order: List[str]
        if self.cached_counts["ENEMY"] < self.cached_counts["PLAYER"]:
            target_order = ["GRUNT", "LIEUTENANT", "CAVALRY"]
        else:
            target_order = ["LIEUTENANT", "CAVALRY", "GRUNT"]

        while purchases < config.AI_MAX_PURCHASES_PER_TICK and gold_spent <= max_spend:
            bought = False
            for unit_type in target_order:
                if self._attempt_purchase(unit_type):
                    purchases += 1
                    gold_spent += config.UNIT_STATS[unit_type]["cost"]
                    bought = True
                    break
            if not bought:
                break

    def update(self, dt: float):
        if self.battlefield.game_over:
            return
        self.sense_timer += dt
        self.decision_timer += dt
        if self.sense_timer >= config.AI_SENSE_INTERVAL:
            self._count_active_units()
            self.sense_timer = 0.0
        if self.decision_timer >= config.AI_DECISION_INTERVAL:
            self._decision_tick()
            self.decision_timer = 0.0

