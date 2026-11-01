import os
from typing import Final

import pygame

# from core.vos.gamestate import Gamestate
from core.vos.gamestate import Gamestate
from core.vos.walls import Wall

EMPTY_SPRITE_PATH: Final = os.path.join("./src/empty.png")
CONCRETE_SPRITE_PATH: Final = os.path.join("./src/concrete.png")
BOX_SPRITE_PATH: Final = os.path.join("./src/box.png")

EXPLOSION_SPRITE_PATH_BASE: Final = "./src/explosion"
EXPLOSION_SPRITES_NUMBER = 10
EXPLOSION_SPRITES_PER_TICK = 2


class Graphic:
    wall_sprites: dict[Wall, pygame.Surface]
    fire_sprites: list[pygame.Surface]

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

        self.load_explosion_sprites()

    def draw(self, gs: Gamestate):
        self.screen.fill("green")
        self.draw_grid(gs.grid_walls)
        self.draw_fire(gs.flames_grid)
        pygame.display.flip()

    def draw_grid(self, walls: list[list[Wall]]):
        for idy, row in enumerate(walls):
            for idx, wall_type in enumerate(row):
                pos = self.pos(idx, idy)
                self.screen.blit(self.wall_sprites[wall_type], pos)

    def draw_fire(self, fire_ticks: list[list[int]]):
        for idy, row in enumerate(fire_ticks):
            for idx, cf in enumerate(row):
                ## -1 means that the cell does not have fire.
                if cf == -1:
                    continue

                pos = self.pos(idx, idy)
                frame_number = abs(
                    (cf // EXPLOSION_SPRITES_PER_TICK) - EXPLOSION_SPRITES_NUMBER
                )
                ## Caps the frame_number to 9, because the number of sprites available.
                frame_number = min(frame_number, 9)

                self.screen.blit(self.fire_sprites[frame_number], pos)

    def pos(self, x, y):
        return x * self.scale, y * self.scale

    def load_explosion_sprites(self):
        self.fire_sprites = []

        for n in range(1, EXPLOSION_SPRITES_NUMBER + 1):
            path = os.path.join(f"{EXPLOSION_SPRITE_PATH_BASE}{n}.png")
            self.fire_sprites.append(pygame.image.load(path))
