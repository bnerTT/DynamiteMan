import sys

import pygame

from core.entities.player import Player
from core.gateways.graphic import Graphic
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall
from core.controllers.human import Human
from core.vos.action import Action


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
    width = 9
    height = 9
    grid_walls = [
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
    flames_grid = [
        [-1 for _ in range(width)]
        for _ in range(height)
    ]
    

    return Gamestate(
        width=width,
        height=height,
        grid_walls=grid_walls,
        flames_grid=flames_grid,
        players=gen_players(),
    )


def gen_players() -> list[Player]:
    starts = [
        (1, Position(0, 0), Direction.RIGHT),
        (2, Position(8, 0), Direction.LEFT),
        (3, Position(0, 8), Direction.RIGHT),
        (4, Position(8, 8), Direction.LEFT),
    ]
    
    players = []
    
    for player_id, pos, facing in starts:
        player = Player()
        player.id = player_id
        player.pos = pos
        player.facing = facing
        player.alive = True
        player.speed = 1
        player.bomb_capacity = 1
        player.active_bombs = 0
        players.append(player)

    return players


if __name__ == "__main__":
    main()
