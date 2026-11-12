from dataclasses import dataclass

from core.vos.position import Position


@dataclass
class Bomb:
    id: int
    owner_id: int
    pos: Position
    fuse_ticks: int = 120 #120/60 fps = 2s
    blast_radius: int = 2
