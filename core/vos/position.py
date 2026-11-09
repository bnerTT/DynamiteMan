from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def tuple(self) -> tuple[int, int]:
        return self.x, self.y
