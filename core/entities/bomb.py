from __future__ import annotations

from dataclasses import dataclass

from core.vos.position import Position


@dataclass
class Bomb:
    id: int
    owner_id: int
    pos: Position
    fuse_ticks: int = 10
    blast_radius: int = 2

    def clone(self) -> Bomb:
        return Bomb(
            id=self.id,
            owner_id=self.owner_id,
            pos=self.pos,
            fuse_ticks=self.fuse_ticks,
            blast_radius=self.blast_radius,
        )
