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
