from abc import ABC, abstractmethod

from core.vos.action import Action
from core.vos.gamestate import Gamestate


class Controller(ABC):
    @abstractmethod
    def get_actions(self, state: Gamestate, player_id: int) -> list[Action]:
        pass
