from core.ports.controller import Controller
from core.vos.direction import Direction
from core.vos.position import Position


class Player:
    id: int
    pos: Position
    facing: Direction
    alive: bool
    speed: int
    bomb_capacity: int
    active_bombs: int
    controller: Controller
