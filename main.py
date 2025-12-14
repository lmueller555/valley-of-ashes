import math
from dataclasses import dataclass

import pygame

import config
import map_data
from camera import Camera
from map_data import build_map_geometry
from units import Battlefield, MacroAI


@dataclass
class Button:
    rect: pygame.Rect
    label: str
    cost: int
    unit_type: str


def world_rect_to_screen(camera: Camera, rect: pygame.Rect) -> pygame.Rect:
    sx, sy = camera.world_to_screen(rect.topleft)
    return pygame.Rect(sx, sy, rect.width * camera.zoom, rect.height * camera.zoom)


def draw_bunker(surface, camera: Camera, bunker: map_data.Bunker):
    courtyard_color = (70, 70, 80)
    wall_color = (120, 90, 70)
    rubble_color = config.COLOR_DESTROYED
    rect_screen = world_rect_to_screen(camera, bunker.rect)
    pygame.draw.rect(surface, courtyard_color, rect_screen)
    if bunker.state != "DESTROYED":
        for wall in bunker.wall_rects:
            pygame.draw.rect(surface, wall_color, world_rect_to_screen(camera, wall))
    else:
        pygame.draw.rect(surface, rubble_color, rect_screen, width=2)


def draw_tower(surface, camera: Camera, tower: map_data.Tower, show_capture_meter: bool = False):
    sx, sy = camera.world_to_screen(tower.center)
    core_radius = max(2, int(config.TOWER_CORE_IMPASSABLE_RADIUS_PX * camera.zoom))
    capture_radius = max(core_radius + 4, int(config.TOWER_CAPTURE_RADIUS_PX * camera.zoom))

    if tower.state == "DESTROYED":
        pygame.draw.circle(surface, config.COLOR_DESTROYED, (sx, sy), capture_radius // 2)
        pygame.draw.circle(surface, config.COLOR_DESTROYED, (sx, sy), capture_radius, width=1)
        return

    tower_color = config.COLOR_PLAYER if tower.faction_owner == "PLAYER" else config.COLOR_ENEMY
    pygame.draw.circle(surface, config.COLOR_TOWER, (sx, sy), core_radius)
    pygame.draw.circle(surface, tower_color, (sx, sy), capture_radius, width=1)
    if tower.state == "VULNERABLE":
        pygame.draw.circle(surface, config.COLOR_NEUTRAL, (sx, sy), capture_radius + 6, width=1)
        if show_capture_meter:
            ratio = min(1.0, tower.occupy_timer / config.TOWER_CAPTURE_DURATION_S)
            bar_w = max(28, int(60 * camera.zoom))
            bar_h = max(4, int(6 * camera.zoom))
            bar_x = sx - bar_w // 2
            bar_y = sy - capture_radius - bar_h - 4
            pygame.draw.rect(surface, config.COLOR_HEALTH_BG, (bar_x, bar_y, bar_w, bar_h))
            fill = int(bar_w * ratio)
            attacker_color = config.COLOR_ENEMY if tower.faction_owner == "PLAYER" else config.COLOR_PLAYER
            pygame.draw.rect(surface, attacker_color, (bar_x, bar_y, fill, bar_h))
            pygame.draw.rect(surface, config.COLOR_WHITE, (bar_x, bar_y, bar_w, bar_h), width=1)


def draw_graveyard(surface, camera: Camera, pos, owner_color):
    sx, sy = camera.world_to_screen(pos)
    pygame.draw.circle(surface, owner_color, (sx, sy), max(3, int(6 * camera.zoom)))
    pygame.draw.circle(surface, config.COLOR_WHITE, (sx, sy), max(4, int(10 * camera.zoom)), width=1)


def draw_graveyard_status(surface, camera: Camera, font, graveyard: map_data.Graveyard):
    sx, sy = camera.world_to_screen(graveyard.pos)
    bar_width = 80
    bar_height = 8
    bar_x = sx - bar_width // 2
    bar_y = sy - 24
    ratio = 0.0
    if graveyard.respawn_interval > 0:
        ratio = min(1.0, graveyard.respawn_timer / graveyard.respawn_interval)
    base_color = (30, 30, 34)
    owner_color = (
        config.COLOR_PLAYER if graveyard.owner == "PLAYER" else config.COLOR_ENEMY if graveyard.owner == "ENEMY" else config.COLOR_NEUTRAL
    )

    pygame.draw.rect(surface, base_color, (bar_x, bar_y, bar_width, bar_height))
    fill_width = int(bar_width * ratio)
    if fill_width > 0:
        pygame.draw.rect(surface, owner_color, (bar_x, bar_y, fill_width, bar_height))
    pygame.draw.rect(surface, config.COLOR_WHITE, (bar_x, bar_y, bar_width, bar_height), width=1)

    waiting_text = font.render(f"{len(graveyard.waiting_units)} waiting", True, config.COLOR_WHITE)
    text_rect = waiting_text.get_rect(center=(sx, bar_y - 8))
    surface.blit(waiting_text, text_rect)


def draw_lane(surface, camera: Camera, points):
    if len(points) < 2:
        return
    transformed = [camera.world_to_screen(p) for p in points]
    pygame.draw.lines(surface, config.COLOR_LANE, False, transformed, width=1)


def draw_map(surface, camera: Camera, geom, show_objective_debug: bool = False):
    surface.set_clip(config.MAP_VIEW_RECT)
    pygame.draw.rect(surface, config.COLOR_TERRAIN, config.MAP_VIEW_RECT)

    # Optional overlay for impassables is drawn later through draw_debug.

    # Cliffs
    left_cliff = pygame.Rect(0, 0, config.CLIFF_BELT_WIDTH, config.MAP_H)
    right_cliff = pygame.Rect(config.MAP_W - config.CLIFF_BELT_WIDTH, 0, config.CLIFF_BELT_WIDTH, config.MAP_H)
    pygame.draw.rect(surface, (40, 40, 44), world_rect_to_screen(camera, left_cliff))
    pygame.draw.rect(surface, (40, 40, 44), world_rect_to_screen(camera, right_cliff))

    # Rift band
    rift_rect = pygame.Rect(config.CLIFF_BELT_WIDTH, config.RIFT_TOP, config.MAP_W - 2 * config.CLIFF_BELT_WIDTH, config.RIFT_BOTTOM - config.RIFT_TOP)
    pygame.draw.rect(surface, config.COLOR_RIFT, world_rect_to_screen(camera, rift_rect))

    # Crossings
    for x0, y0, x1, y1 in config.CROSSINGS:
        rect = pygame.Rect(x0, y0, x1 - x0, y1 - y0)
        pygame.draw.rect(surface, config.COLOR_CROSSING, world_rect_to_screen(camera, rect))

    # Lanes
    for pts in config.LANE_WAYPOINTS.values():
        draw_lane(surface, camera, pts)

    # Bases and keeps
    pygame.draw.rect(surface, (90, 90, 110), world_rect_to_screen(camera, config.S_BASE_RECT))
    pygame.draw.rect(surface, (90, 90, 110), world_rect_to_screen(camera, config.N_BASE_RECT))
    pygame.draw.rect(surface, (120, 120, 150), world_rect_to_screen(camera, config.S_KEEP_RECT))
    pygame.draw.rect(surface, (120, 120, 150), world_rect_to_screen(camera, config.N_KEEP_RECT))

    # Towers
    for tower in geom.towers:
        draw_tower(surface, camera, tower, show_capture_meter=show_objective_debug)

    # Bunkers
    for bunker in geom.bunkers:
        draw_bunker(surface, camera, bunker)

    # Graveyards
    for gy in geom.graveyards:
        if gy.starting_owner == "PLAYER":
            color = config.COLOR_PLAYER
        elif gy.starting_owner == "ENEMY":
            color = config.COLOR_ENEMY
        else:
            color = config.COLOR_NEUTRAL
        draw_graveyard(surface, camera, gy.pos, color)

    surface.set_clip(None)


def draw_impassable_overlay(surface, camera: Camera, geom):
    overlay = pygame.Surface(config.MAP_VIEW_RECT.size, pygame.SRCALPHA)
    shade = (200, 60, 60, 60)

    for rect in geom.impassable_rects:
        overlay.fill(shade, world_rect_to_screen(camera, rect))

    # Remove crossing gaps from the rift shading for clarity.
    for x0, y0, x1, y1 in config.CROSSINGS:
        overlay.fill((0, 0, 0, 0), world_rect_to_screen(camera, pygame.Rect(x0, y0, x1 - x0, y1 - y0)))

    for bunker in geom.bunkers:
        if bunker.state != "DESTROYED":
            for wall in bunker.wall_rects:
                overlay.fill(shade, world_rect_to_screen(camera, wall))

    for tower in geom.towers:
        if tower.state != "DESTROYED":
            sx, sy = camera.world_to_screen(tower.center)
            radius = max(1, int(tower.core_radius * camera.zoom))
            pygame.draw.circle(overlay, shade, (int(sx), int(sy)), radius)

    surface.blit(overlay, (0, 0))


def draw_spatial_grid(surface, camera: Camera, cell_size: float):
    """Render the spatial hash grid for debugging separation/aggro queries."""

    overlay = pygame.Surface(config.MAP_VIEW_RECT.size, pygame.SRCALPHA)
    view_left = camera.x - config.MAP_VIEW_RECT.width / (2 * camera.zoom)
    view_right = camera.x + config.MAP_VIEW_RECT.width / (2 * camera.zoom)
    view_top = camera.y - config.MAP_VIEW_RECT.height / (2 * camera.zoom)
    view_bottom = camera.y + config.MAP_VIEW_RECT.height / (2 * camera.zoom)

    start_x = math.floor(view_left / cell_size) * cell_size
    start_y = math.floor(view_top / cell_size) * cell_size

    grid_color = (120, 180, 120, 60)
    x = start_x
    while x <= view_right:
        sx, _ = camera.world_to_screen((x, view_top))
        pygame.draw.line(overlay, grid_color, (sx, 0), (sx, config.MAP_VIEW_RECT.height))
        x += cell_size

    y = start_y
    while y <= view_bottom:
        _, sy = camera.world_to_screen((view_left, y))
        pygame.draw.line(overlay, grid_color, (0, sy), (config.MAP_VIEW_RECT.width, sy))
        y += cell_size

    surface.blit(overlay, (0, 0))


def draw_button(surface, font, button: Button, enabled: bool, hovered: bool, pressed: bool):
    base_color = (70, 110, 80) if enabled else (60, 60, 60)
    if hovered and enabled:
        base_color = (80, 140, 95)
    if pressed and enabled:
        base_color = (65, 120, 85)
    border_color = (150, 200, 160) if enabled else (90, 90, 90)
    pygame.draw.rect(surface, base_color, button.rect)
    pygame.draw.rect(surface, border_color, button.rect, width=2)
    label = f"{button.label} ({button.cost})"
    text_color = config.COLOR_WHITE if enabled else (150, 150, 150)
    text = font.render(label, True, text_color)
    text_pos = text.get_rect(center=button.rect.center)
    surface.blit(text, text_pos)


def build_purchase_buttons(font):
    buttons = []
    padding = 12
    width = 160
    height = 36
    x = config.RIBBON_RECT.left + 20
    y = config.RIBBON_RECT.top + 110
    data = [
        ("Buy Grunt", "GRUNT"),
        ("Buy Lieutenant", "LIEUTENANT"),
        ("Buy Cavalry", "CAVALRY"),
    ]
    for label, unit_type in data:
        rect = pygame.Rect(x, y, width, height)
        buttons.append(Button(rect, label, config.UNIT_STATS[unit_type]["cost"], unit_type))
        x += width + padding
    return buttons


def draw_ribbon(surface, font, battlefield: Battlefield, buttons):
    pygame.draw.rect(surface, config.COLOR_RIBBON, config.RIBBON_RECT)
    header = font.render("Valley of Ashes — Control Ribbon (placeholder)", True, config.COLOR_WHITE)
    surface.blit(header, (config.RIBBON_RECT.left + 20, config.RIBBON_RECT.top + 20))

    gold_text = font.render(
        f"Gold — Player: {battlefield.gold['PLAYER']}  Enemy: {battlefield.gold['ENEMY']}",
        True,
        config.COLOR_WHITE,
    )
    surface.blit(gold_text, (config.RIBBON_RECT.left + 20, config.RIBBON_RECT.top + 50))

    sub = font.render(
        "Purchases, upgrades, and HUD will appear here per UI guidance.", True, (180, 180, 180)
    )
    surface.blit(sub, (config.RIBBON_RECT.left + 20, config.RIBBON_RECT.top + 80))

    mouse_pos = pygame.mouse.get_pos()
    mouse_down = pygame.mouse.get_pressed()[0]
    for button in buttons:
        enabled = battlefield.gold["PLAYER"] >= button.cost and not battlefield.game_over
        hovered = button.rect.collidepoint(mouse_pos)
        draw_button(surface, font, button, enabled, hovered, hovered and mouse_down)


def draw_debug(surface, font, camera: Camera, geom, toggle, debug_state):
    if not toggle:
        return
    mx, my = pygame.mouse.get_pos()
    cursor_world = camera.screen_to_world((mx, my))
    passable = map_data.is_point_passable(cursor_world, geom)
    tower_states = ", ".join([f"{t.tower_id}:{t.state[:3]}" for t in geom.towers])
    tower_details = []
    for t in geom.towers:
        detail = f"{t.tower_id}:{t.state[:3]} A{t.archers_alive}"
        if t.state == "VULNERABLE":
            detail += f" occ={t.occupy_timer:05.1f}s"
            if t.contested:
                detail += " (contested)"
        tower_details.append(detail)
    bunker_states = ", ".join([f"{b.bunker_id}:{b.state[:3]}" for b in geom.bunkers])
    gy_details = []
    for gy in geom.graveyards:
        gy_details.append(
            f"{gy.gy_id}:{gy.owner[0]} cap {gy.capture_timer:04.1f}/{gy.capture_time_required:.0f} "
            f"resp {gy.respawn_timer:04.1f}/{gy.respawn_interval:.0f} q={len(gy.waiting_units)}"
        )
    battlefield: Battlefield = debug_state.get("battlefield")
    unit_counts = {"PLAYER": 0, "ENEMY": 0}
    respawns = 0
    boss_lines = []
    if battlefield:
        for u in battlefield.units.values():
            if u.is_alive():
                unit_counts[u.faction] += 1
        respawns = sum(len(gy.waiting_units) for gy in geom.graveyards)
        for faction, bid in battlefield.boss_units.items():
            boss = battlefield.units.get(bid)
            if boss:
                standing = sum(1 for t in geom.towers if t.faction_owner == faction and t.state != "DESTROYED")
                mult = 1.0 + config.BOSS_HP_PER_TOWER_MULT * standing
                boss_lines.append(
                    f"Boss {faction}: {boss.hp:.0f}/{boss.max_hp:.0f} dmg {boss.damage:.1f} (mult {mult:.2f})"
                )
    lines = [
        f"Camera: ({camera.x:.1f}, {camera.y:.1f})",
        f"Zoom: {camera.zoom:.2f}",
        f"Mouse: ({mx:.0f}, {my:.0f}) -> World ({cursor_world[0]:.1f}, {cursor_world[1]:.1f})",
        f"Passable: {'YES' if passable else 'NO'}",
        "F1: toggle debug overlay",
        "F2: toggle impassable overlay",
        "F3: toggle spatial hash grid",
        "SPACE: center on home graveyard",
        f"Towers: {len(geom.towers)} (capture r={config.TOWER_CAPTURE_RADIUS_PX})",
        f"Tower states: {tower_states}",
        "  " + " | ".join(tower_details),
        f"Bunkers: {len(geom.bunkers)}",
        f"Bunker states: {bunker_states}",
        f"Graveyards: {len(geom.graveyards)}",
        "  " + " | ".join(gy_details),
        f"Impassable overlay: {'ON' if debug_state.get('show_impassable') else 'OFF'}",
        f"Spatial grid: {'ON' if debug_state.get('show_spatial_grid') else 'OFF'}",
        f"Units — Player: {unit_counts['PLAYER']}, Enemy: {unit_counts['ENEMY']}",
        f"Respawn queue: {respawns}",
        f"Gold — Player: {battlefield.gold['PLAYER'] if battlefield else 0}, Enemy: {battlefield.gold['ENEMY'] if battlefield else 0}",
        f"Kills — Player: {battlefield.kills['PLAYER'] if battlefield else 0}, Enemy: {battlefield.kills['ENEMY'] if battlefield else 0}",
    ]
    lines.extend(boss_lines)
    y = 10
    for line in lines:
        text = font.render(line, True, config.COLOR_DEBUG)
        surface.blit(text, (10, y))
        y += 18


def handle_input(camera: Camera, dt, debug_state):
    keys = pygame.key.get_pressed()
    pan_amount = config.PAN_SPEED * dt
    dx = dy = 0
    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        dx -= pan_amount
    if keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        dx += pan_amount
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        dy -= pan_amount
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        dy += pan_amount
    if dx or dy:
        camera.pan(dx, dy)

    # Mouse dragging
    if pygame.mouse.get_pressed()[1] or pygame.mouse.get_pressed()[2]:
        mx, my = pygame.mouse.get_pos()
        if config.MAP_VIEW_RECT.collidepoint(mx, my):
            if debug_state.get("last_mouse") is not None:
                lx, ly = debug_state["last_mouse"]
                camera.pan(-(mx - lx) / camera.zoom, -(my - ly) / camera.zoom)
            debug_state["last_mouse"] = (mx, my)
    else:
        debug_state["last_mouse"] = None


def handle_buttons(battlefield: Battlefield, buttons, mouse_pos):
    if battlefield.game_over:
        return
    for button in buttons:
        if button.rect.collidepoint(mouse_pos):
            battlefield.purchase_unit("PLAYER", button.unit_type)


def main():
    pygame.init()
    display_info = pygame.display.Info()
    config.apply_screen_resolution(display_info.current_w, display_info.current_h)
    screen = pygame.display.set_mode((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.FULLSCREEN)
    pygame.display.set_caption("Valley of Ashes")
    clock = pygame.time.Clock()
    font = pygame.font.Font(None, 20)

    camera = Camera()
    geom = build_map_geometry()
    battlefield = Battlefield(geom)
    ai = MacroAI(battlefield)
    battlefield.ai_controller = ai
    starting_counts = {"GRUNT": 24, "LIEUTENANT": 6, "CAVALRY": 2}
    battlefield.seed_wave("PLAYER", starting_counts)
    battlefield.seed_wave("ENEMY", starting_counts)
    buttons = build_purchase_buttons(font)
    debug_overlay = False
    state_cache = {
        "last_mouse": None,
        "show_impassable": False,
        "show_spatial_grid": False,
        "battlefield": battlefield,
    }

    running = True
    while running:
        dt = clock.tick(60) / 1000.0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_F1:
                    debug_overlay = not debug_overlay
                elif event.key == pygame.K_F2:
                    state_cache["show_impassable"] = not state_cache["show_impassable"]
                elif event.key == pygame.K_F3:
                    state_cache["show_spatial_grid"] = not state_cache["show_spatial_grid"]
                elif event.key == pygame.K_SPACE:
                    camera.center_on(config.GRAVEYARDS_SOUTH["GY_S_HOME"])
            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                if config.MAP_VIEW_RECT.collidepoint(mx, my):
                    zoom_factor = 1.1 if event.y > 0 else 0.9
                    camera.zoom_at((mx, my), zoom_factor)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                if config.RIBBON_RECT.collidepoint(*event.pos):
                    handle_buttons(battlefield, buttons, event.pos)
        handle_input(camera, dt, state_cache)

        battlefield.update(dt)
        ai.update(dt)

        screen.fill(config.COLOR_BG)
        draw_map(screen, camera, geom, show_objective_debug=debug_overlay)
        battlefield.draw(screen, camera)
        for gy in geom.graveyards:
            draw_graveyard_status(screen, camera, font, gy)
        if state_cache.get("show_impassable"):
            draw_impassable_overlay(screen, camera, geom)
        if state_cache.get("show_spatial_grid"):
            draw_spatial_grid(screen, camera, battlefield.spatial.cell_size)
        draw_ribbon(screen, font, battlefield, buttons)
        draw_debug(screen, font, camera, geom, debug_overlay, state_cache)
        if battlefield.game_over:
            overlay = pygame.Surface((config.SCREEN_WIDTH, config.SCREEN_HEIGHT), pygame.SRCALPHA)
            overlay.fill((0, 0, 0, 120))
            screen.blit(overlay, (0, 0))
            winner_text = font.render(f"GAME OVER — Winner: {battlefield.winner}", True, config.COLOR_WHITE)
            screen.blit(
                winner_text,
                winner_text.get_rect(center=(config.SCREEN_WIDTH // 2, config.SCREEN_HEIGHT // 2)),
            )
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
