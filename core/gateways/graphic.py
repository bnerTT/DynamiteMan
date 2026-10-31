import os
from typing import Final

import pygame

# from core.vos.gamestate import Gamestate
from core.vos.gamestate import Gamestate
from core.vos.walls import Wall

EMPTY_SPRITE_PATH: Final = os.path.join("./src/empty.png")
CONCRETE_SPRITE_PATH: Final = os.path.join("./src/concrete.png")
BOX_SPRITE_PATH: Final = os.path.join("./src/box.png")


class Graphic:
    wall_sprites: dict[Wall, pygame.Surface]

    screen: pygame.Surface
    scale: int = 64

    # Initialize the graphic engine, receives the numbers of columns and rows
    # that the current map uses.
    def __init__(self, scale: int, rows: int, colums: int):
        screen_width, screen_height = rows * scale, colums * scale
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        self.scale = scale

        self.wall_sprites = {}
        self.wall_sprites[Wall.EMPTY] = pygame.image.load(EMPTY_SPRITE_PATH)
        self.wall_sprites[Wall.CONCRETE] = pygame.image.load(CONCRETE_SPRITE_PATH)
        self.wall_sprites[Wall.BOX] = pygame.image.load(BOX_SPRITE_PATH)

    def draw(self, gs: Gamestate):
        self.screen.fill("green")
        self.draw_grid(gs.grid_walls)
        pygame.display.flip()

    def draw_grid(self, walls: list[list[Wall]]):
        for idy, row in enumerate(walls):
            for idx, wall_type in enumerate(row):
                pos = self.pos(idx, idy)
                self.screen.blit(self.wall_sprites[wall_type], pos)

    def pos(self, x, y):
        return x * self.scale, y * self.scale
