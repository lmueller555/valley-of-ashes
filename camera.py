from dataclasses import dataclass

import pygame

import config


@dataclass
class Camera:
    x: float = config.MAP_W / 2
    y: float = config.MAP_H / 2
    zoom: float = 0.5

    def world_to_screen(self, pos):
        wx, wy = pos
        sx = (wx - self.x) * self.zoom + config.MAP_VIEW_RECT.width / 2
        sy = (wy - self.y) * self.zoom + config.MAP_VIEW_RECT.height / 2
        return sx, sy

    def screen_to_world(self, pos):
        sx, sy = pos
        wx = (sx - config.MAP_VIEW_RECT.width / 2) / self.zoom + self.x
        wy = (sy - config.MAP_VIEW_RECT.height / 2) / self.zoom + self.y
        return wx, wy

    def pan(self, dx, dy):
        self.x = max(0, min(config.MAP_W, self.x + dx))
        self.y = max(0, min(config.MAP_H, self.y + dy))

    def adjust_zoom(self, delta):
        new_zoom = max(config.ZOOM_MIN, min(config.ZOOM_MAX, self.zoom * delta))
        self.zoom = new_zoom

    def center_on(self, pos):
        px, py = pos
        self.x = max(0, min(config.MAP_W, px))
        self.y = max(0, min(config.MAP_H, py))

    def zoom_at(self, screen_pos, delta):
        """Zoom relative to the screen position inside the map view.

        Keeps the world position under the cursor stable when zooming so the
        user feels anchored. Falls back to a center zoom when invoked outside
        of the map view.
        """

        # Translate the cursor to world space before the zoom change.
        anchor_world = self.screen_to_world(screen_pos)

        # Apply zoom constraints.
        new_zoom = max(config.ZOOM_MIN, min(config.ZOOM_MAX, self.zoom * delta))
        if new_zoom == self.zoom:
            return

        self.zoom = new_zoom

        # Reposition the camera so the anchor stays under the cursor.
        if config.MAP_VIEW_RECT.collidepoint(*screen_pos):
            ax, ay = anchor_world
            sx, sy = screen_pos
            self.x = max(0, min(config.MAP_W, ax - (sx - config.MAP_VIEW_RECT.width / 2) / self.zoom))
            self.y = max(0, min(config.MAP_H, ay - (sy - config.MAP_VIEW_RECT.height / 2) / self.zoom))
