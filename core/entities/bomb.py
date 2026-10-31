from core.vos.position import Position


class Bomb:
    id: int
    owner_id: int
    pos: Position
    fuse_ticks: int
    blast_radius: int
