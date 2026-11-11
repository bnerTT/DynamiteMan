from __future__ import annotations

from core.entities.bomb import Bomb
from core.vos.walls import Wall

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.entities.player import Player

@dataclass
class Gamestate:
    width: int
    height: int
    grid_walls: list[list[Wall]]
    flames_grid: list[list[int]]  # ticks restantes de fogo por pos
    current_tick: int = 0
    bombs: list[Bomb] = field(default_factory=list)
    players: list[Player] = field(default_factory=list)
