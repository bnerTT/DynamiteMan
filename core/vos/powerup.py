from enum import Enum, auto


class PowerUpType(Enum):
    BOMB_UP = auto()   # +1 bomb_capacity
    FIRE_UP = auto()   # +1 blast_radius
    SPEED_UP = auto()  # +1 speed
