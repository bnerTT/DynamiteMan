import sys

import pygame

from core.entities.player import Player
from core.gateways.graphic import Graphic
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall


def main() -> None:
    pygame.init()
    gs = gen_gamestate()
    ge = Graphic(64, gs.width, gs.height, gen_players())
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
    gs.flames_grid = [
        [-1, 0, 1, 2],
        [3, 4, 5, 6],
        [7, 8, 9, 10],
        [11, 12, 13, 14],
        [15, 16, 17, 18, 19, 20],
    ]
    gs.bombs = []

    return gs


def gen_players() -> list[Player]:
    p1 = Player()
    p1.facing = Direction.UP
    p1.pos = Position(5, 5)

    p2 = Player()
    p2.facing = Direction.LEFT
    p2.pos = Position(5, 6)

    p3 = Player()
    p3.facing = Direction.RIGHT
    p3.pos = Position(6, 5)

    p4 = Player()
    p4.facing = Direction.DOWN
    p4.pos = Position(6, 6)

    return [p1, p2, p3, p4]


if __name__ == "__main__":
    main()
