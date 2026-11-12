from __future__ import annotations

from typing import Protocol

from core.ports.controller import Controller
from core.vos.action import Action
from core.vos.gamestate import Gamestate


class AgentProtocol(Protocol):
    def choose_action(
        self, state: Gamestate, player_id: int, training: bool = False
    ) -> Action: ...


class AI(Controller):
    """
    AI Controller adapter that bridges the Controller port to an Agent implementation
    (e.g., QLearningAgent, HeuristicAgent, RandomAgent) as shown in the architecture diagram.
    """

    def __init__(self, agent: AgentProtocol, training: bool = False) -> None:
        self.agent = agent
        self.training = training
        self.last_action: Action = Action.IDLE

    def get_actions(self, state: Gamestate, player_id: int) -> list[Action]:
        action = self.agent.choose_action(state, player_id, training=self.training)
        self.last_action = action
        return [action]
