from __future__ import annotations

from typing import TYPE_CHECKING

from core.entities.bomb import Bomb
from core.vos.powerup import PowerUpType
from core.vos.walls import Wall

if TYPE_CHECKING:
    from core.entities.player import Player


class Gamestate:
    current_tick: int
    width: int
    height: int
    grid_walls: list[list[Wall]]
    flames_grid: list[list[int]]  # ticks restantes de fogo por pos (-1 = sem fogo)
    flame_owners: list[list[int]]  # id do dono da bomba que gerou o fogo (-1 = nenhum)
    bombs: list[Bomb]
    players: list[Player]
    powerups: dict[tuple[int, int], PowerUpType]
    sudden_death_index: int
    next_bomb_id: int
    max_ticks: int
    is_over: bool
    winner_id: int | None

    def __init__(self) -> None:
        self.current_tick = 0
        self.width = 9
        self.height = 9
        self.grid_walls = []
        self.flames_grid = []
        self.flame_owners = []
        self.bombs = []
        self.players = []
        self.powerups = {}
        self.sudden_death_index = 0
        self.next_bomb_id = 1
        self.max_ticks = 150
        self.is_over = False
        self.winner_id = None
