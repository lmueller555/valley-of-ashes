import pygame

import config
import map_data
from camera import Camera
from map_data import build_map_geometry


def world_rect_to_screen(camera: Camera, rect: pygame.Rect) -> pygame.Rect:
    sx, sy = camera.world_to_screen(rect.topleft)
    return pygame.Rect(sx, sy, rect.width * camera.zoom, rect.height * camera.zoom)


def draw_bunker(surface, camera: Camera, bunker: map_data.Bunker, is_north: bool):
    courtyard_color = (70, 70, 80)
    wall_color = (120, 90, 70)
    rect_screen = world_rect_to_screen(camera, bunker.rect)
    pygame.draw.rect(surface, courtyard_color, rect_screen)
    for wall in bunker.wall_rects:
        pygame.draw.rect(surface, wall_color, world_rect_to_screen(camera, wall))


def draw_tower(surface, camera: Camera, tower_center, color):
    sx, sy = camera.world_to_screen(tower_center)
    core_radius = max(2, int(config.TOWER_CORE_IMPASSABLE_RADIUS_PX * camera.zoom))
    capture_radius = max(core_radius + 4, int(config.TOWER_CAPTURE_RADIUS_PX * camera.zoom))
    pygame.draw.circle(surface, config.COLOR_TOWER, (sx, sy), core_radius)
    pygame.draw.circle(surface, color, (sx, sy), capture_radius, width=1)


def draw_graveyard(surface, camera: Camera, pos, owner_color):
    sx, sy = camera.world_to_screen(pos)
    pygame.draw.circle(surface, owner_color, (sx, sy), max(3, int(6 * camera.zoom)))
    pygame.draw.circle(surface, config.COLOR_WHITE, (sx, sy), max(4, int(10 * camera.zoom)), width=1)


def draw_lane(surface, camera: Camera, points):
    if len(points) < 2:
        return
    transformed = [camera.world_to_screen(p) for p in points]
    pygame.draw.lines(surface, config.COLOR_LANE, False, transformed, width=1)


def draw_map(surface, camera: Camera, geom):
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
        color = config.COLOR_PLAYER if tower.faction_owner == "PLAYER" else config.COLOR_ENEMY
        draw_tower(surface, camera, tower.center, color)

    # Bunkers
    for bunker in geom.bunkers:
        draw_bunker(surface, camera, bunker, bunker.faction_owner == "ENEMY")

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
        for wall in bunker.wall_rects:
            overlay.fill(shade, world_rect_to_screen(camera, wall))

    for tower in geom.towers:
        sx, sy = camera.world_to_screen(tower.center)
        radius = max(1, int(tower.core_radius * camera.zoom))
        pygame.draw.circle(overlay, shade, (int(sx), int(sy)), radius)

    surface.blit(overlay, (0, 0))


def draw_ribbon(surface, font):
    pygame.draw.rect(surface, config.COLOR_RIBBON, config.RIBBON_RECT)
    header = font.render("Valley of Ashes — Control Ribbon (placeholder)", True, config.COLOR_WHITE)
    surface.blit(header, (20, config.MAP_VIEW_HEIGHT + 20))
    sub = font.render("Purchases, upgrades, and HUD will appear here per UI guidance.", True, (180, 180, 180))
    surface.blit(sub, (20, config.MAP_VIEW_HEIGHT + 50))


def draw_debug(surface, font, camera: Camera, geom, toggle, debug_state):
    if not toggle:
        return
    mx, my = pygame.mouse.get_pos()
    cursor_world = camera.screen_to_world((mx, my))
    lines = [
        f"Camera: ({camera.x:.1f}, {camera.y:.1f})",
        f"Zoom: {camera.zoom:.2f}",
        f"Mouse: ({mx:.0f}, {my:.0f}) -> World ({cursor_world[0]:.1f}, {cursor_world[1]:.1f})",
        "F1: toggle debug overlay",
        "F2: toggle impassable overlay",
        "SPACE: center on home graveyard",
        f"Towers: {len(geom.towers)} (capture r={config.TOWER_CAPTURE_RADIUS_PX})",
        f"Bunkers: {len(geom.bunkers)}",
        f"Graveyards: {len(geom.graveyards)}",
        f"Impassable overlay: {'ON' if debug_state.get('show_impassable') else 'OFF'}",
    ]
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
    debug_overlay = False
    state_cache = {"last_mouse": None, "show_impassable": False}

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
                elif event.key == pygame.K_SPACE:
                    camera.center_on(config.GRAVEYARDS_SOUTH["GY_S_HOME"])
            elif event.type == pygame.MOUSEWHEEL:
                mx, my = pygame.mouse.get_pos()
                zoom_factor = 1.1 if event.y > 0 else 0.9
                camera.zoom_at((mx, my), zoom_factor)
        handle_input(camera, dt, state_cache)

        screen.fill(config.COLOR_BG)
        draw_map(screen, camera, geom)
        if state_cache.get("show_impassable"):
            draw_impassable_overlay(screen, camera, geom)
        draw_ribbon(screen, font)
        draw_debug(screen, font, camera, geom, debug_overlay, state_cache)
        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
