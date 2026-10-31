from core.entities.bomb import Bomb
from core.vos.walls import Wall


class Gamestate:
    current_tick: int
    width: int
    height: int
    grid_walls: list[list[Wall]]
    flames_grid: list[list[int]]  # ticks restantes de fogo por pos
    bombs: list[Bomb]
