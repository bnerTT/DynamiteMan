import os
from typing import Final

import pygame

# from core.vos.gamestate import Gamestate
from core.entities.player import Player
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.walls import Wall
from core.entities.bomb import Bomb

EMPTY_SPRITE_PATH: Final = os.path.join("./src/empty.png")
CONCRETE_SPRITE_PATH: Final = os.path.join("./src/concrete.png")
BOX_SPRITE_PATH: Final = os.path.join("./src/box.png")
BOMB_SPRITE_PATH: Final = os.path.join("./src/bomb.breno.png")

EXPLOSION_SPRITE_PATH_BASE: Final = "./src/explosion"
EXPLOSION_SPRITES_NUMBER = 10
EXPLOSION_SPRITES_PER_TICK = 2

PLAYER_SPRITE_PATH_BASE: Final = "./src/p1"


class Graphic:
    wall_sprites: dict[Wall, pygame.Surface]
    fire_sprites: list[pygame.Surface]
    player_sprites: dict[Direction, pygame.Surface]

    temp_players: list[Player]

    screen: pygame.Surface
    scale: int = 64

    def __init__(self, scale: int, rows: int, colums: int):
        screen_width, screen_height = rows * scale, colums * scale
        self.screen = pygame.display.set_mode((screen_width, screen_height))
        self.scale = scale

        self.wall_sprites = {}
        self.wall_sprites[Wall.EMPTY] = pygame.image.load(EMPTY_SPRITE_PATH)
        self.wall_sprites[Wall.CONCRETE] = pygame.image.load(CONCRETE_SPRITE_PATH)
        self.wall_sprites[Wall.BOX] = pygame.image.load(BOX_SPRITE_PATH)
        self.font = pygame.font.SysFont("Arial", 32, bold=True)
        
        raw_bomb = pygame.image.load(BOMB_SPRITE_PATH)
        self.bomb_sprite = pygame.transform.scale(raw_bomb, (self.scale, self.scale))
        
        self.load_explosion_sprites()
        self.load_player_sprites()

    def draw(self, gs: Gamestate):
        self.screen.fill("green")
        self.draw_grid(gs.grid_walls)
        self.draw_bombs(gs.bombs)
        self.draw_fire(gs.flames_grid)
        self.draw_players(gs.players)
        
        if gs.game_over:
            msg = f"Player {gs.winner_id} Venceu! (R = Reset)" if gs.winner_id else "Empate! (R = Reset)"
            text_surface = self.font.render(msg, True, "white", "black")
            rect = text_surface.get_rect(center=(self.screen.get_width() // 2, self.screen.get_height() // 2))
            self.screen.blit(text_surface, rect)
        
        pygame.display.flip()
        
    def draw_bombs(self, bombs: list[Bomb]):
        for b in bombs:
            pos = self.pos(b.pos.x, b.pos.y)
            self.screen.blit(self.bomb_sprite, pos)

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
                frame_number = min(frame_number, 9)

                self.screen.blit(self.fire_sprites[frame_number], pos)

    def draw_players(self, players: list[Player]):
        for p in players:
            if not p.alive:
                continue
            pos = self.pos(p.pos.x, p.pos.y)
            sprite = self.player_sprites[p.facing]
            self.screen.blit(sprite, pos)

    def pos(self, x, y):
        return x * self.scale, y * self.scale

    def load_explosion_sprites(self):
        self.fire_sprites = []

        for n in range(1, EXPLOSION_SPRITES_NUMBER + 1):
            path = os.path.join(f"{EXPLOSION_SPRITE_PATH_BASE}{n}.png")
            self.fire_sprites.append(pygame.image.load(path))

    def load_player_sprites(self):
        self.player_sprites = {}

        for d in [Direction.UP, Direction.DOWN, Direction.LEFT, Direction.RIGHT]:
            path = os.path.join(f"{PLAYER_SPRITE_PATH_BASE}{d}.png")
            self.player_sprites[d] = pygame.image.load(path)
