import os
import sys

import pygame

from core.vos.gamestate import Gamestate
from core.vos.walls import Wall


def main() -> None:
    pygame.init()
    gs = gen_gamestate()

    scale = 64

    screen_width, screen_height = gs.width * scale, gs.height * scale
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("DynamiteMan")

    clock = pygame.time.Clock()

    # hornet = pygame.image.load(os.path.join("./src/hornet.jpeg"))
    empty = pygame.image.load(os.path.join("./src/empty.png"))
    concrete = pygame.image.load(os.path.join("./src/concrete.png"))
    box = pygame.image.load(os.path.join("./src/box.png"))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill("green")

        for idy, row in enumerate(gs.grid_walls):
            for idx, pos in enumerate(row):
                if pos is Wall.CONCRETE:
                    screen.blit(concrete, [idx * scale, idy * scale])
                elif pos is Wall.BOX:
                    screen.blit(box, [idx * scale, idy * scale])
                elif pos is Wall.EMPTY:
                    screen.blit(empty, [idx * scale, idy * scale])

        pygame.display.flip()
        clock.tick(60)  # Limita o loop a 60 FPS

    pygame.quit()
    sys.exit()


def gen_gamestate() -> Gamestate:
    gs = Gamestate()
    gs.current_tick = 0
    gs.width = 9
    gs.height = 9
    gs.grid_walls = [
        [
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.BOX,
            Wall.CONCRETE,
            Wall.BOX,
            Wall.CONCRETE,
            Wall.BOX,
            Wall.CONCRETE,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.BOX,
            Wall.BOX,
            Wall.BOX,
            Wall.BOX,
            Wall.BOX,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.BOX,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.BOX,
            Wall.CONCRETE,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
            Wall.CONCRETE,
            Wall.EMPTY,
        ],
        [
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
            Wall.EMPTY,
        ],
    ]
    gs.flames_grid = [[0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0], [0, 0, 0, 0]]
    gs.bombs = []

    return gs


if __name__ == "__main__":
    main()
