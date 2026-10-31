import os
import sys

import pygame

from core.vos.gamestate import Gamestate
from core.vos.walls import Wall


def main() -> None:

    scale = 8
    pygame.init()
    gs = gen_gamestate()

    screen_width, screen_height = gs.width * 16 * scale, gs.height * 16 * scale
    screen = pygame.display.set_mode((screen_width, screen_height))
    pygame.display.set_caption("DynamiteMan")

    clock = pygame.time.Clock()

    hornet = pygame.image.load(os.path.join("./src/hornet.jpeg"))
    empty = pygame.image.load(os.path.join("./src/empty.jpeg"))
    concrete = pygame.image.load(os.path.join("./src/concrete.png.jpeg"))
    box = pygame.image.load(os.path.join("./src/box.jpeg"))

    running = True
    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

        screen.fill("green")

        for idy, row in enumerate(gs.grid_walls):
            for idx, pos in enumerate(row):
                if pos is Wall.CONCRETE:
                    pygame.draw.rect(
                        screen,
                        "red",
                        pygame.Rect(
                            idx * 16 * scale, idy * 16 * scale, 16 * scale, 16 * scale
                        ),
                    )
                elif pos is Wall.BOX:
                    pygame.draw.rect(
                        screen,
                        "yellow",
                        pygame.Rect(
                            idx * 16 * scale, idy * 16 * scale, 16 * scale, 16 * scale
                        ),
                    )
                elif pos is Wall.EMPTY:
                    pygame.draw.rect(
                        screen,
                        "white",
                        pygame.Rect(
                            idx * 16 * scale, idy * 16 * scale, 16 * scale, 16 * scale
                        ),
                    )

                    screen.blit(hornet, [0, 0])

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
