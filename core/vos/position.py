from dataclasses import dataclass


@dataclass(frozen=True)
class Position:
    x: float
    y: float

    def grid(self) -> tuple[int,int]:
        return round(self.x),round(self.y)
    
    def tuple(self) -> tuple[float, float]:
        return self.x, self.y
    
