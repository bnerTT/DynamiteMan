from core.ports.controller import Controller
from core.vos.position import Position


class Player:
    id: int
    pos: Position
    alive: bool
    speed: int
    bomb_capacity: int
    active_bombs: int
    controller: Controller
