from __future__ import annotations

from typing import TYPE_CHECKING

from core.vos.direction import Direction
from core.vos.position import Position

if TYPE_CHECKING:
    from core.ports.controller import Controller


class Player:
    id: int
    pos: Position
    prev_pos: Position
    facing: Direction
    alive: bool
    speed: int
    bomb_capacity: int
    active_bombs: int
    blast_radius: int
    kills: int
    boxes_destroyed: int
    controller: Controller | None

    def __init__(
        self,
        player_id: int = 0,
        pos: Position = Position(0, 0),
        facing: Direction = Direction.DOWN,
        alive: bool = True,
        speed: int = 1,
        bomb_capacity: int = 1,
        active_bombs: int = 0,
        blast_radius: int = 2,
        controller: Controller | None = None,
    ) -> None:
        self.id = player_id
        self.pos = pos
        self.prev_pos = pos
        self.facing = facing
        self.alive = alive
        self.speed = speed
        self.bomb_capacity = bomb_capacity
        self.active_bombs = active_bombs
        self.blast_radius = blast_radius
        self.kills = 0
        self.boxes_destroyed = 0
        self.controller = controller

    def clone(self) -> Player:
        cloned = Player(
            player_id=self.id,
            pos=self.pos,
            facing=self.facing,
            alive=self.alive,
            speed=self.speed,
            bomb_capacity=self.bomb_capacity,
            active_bombs=self.active_bombs,
            blast_radius=self.blast_radius,
            controller=self.controller,
        )
        cloned.prev_pos = self.prev_pos
        cloned.kills = self.kills
        cloned.boxes_destroyed = self.boxes_destroyed
        return cloned
