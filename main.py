import sys

import pygame

from core.gateways.graphic import Graphic
from core.vos.gamestate import Gamestate
from core.vos.walls import Wall


def main() -> None:
    pygame.init()
    gs = gen_gamestate()
    ge = Graphic(64, gs.width, gs.height)
    clock = pygame.time.Clock()

    while True:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            ge.draw(gs)
            clock.tick(60)


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
