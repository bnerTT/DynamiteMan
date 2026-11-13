import os
import sys
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

from core.commands.gamerules import (
    apply_tick,
    clone,
    explode_bomb,
    is_flame,
    is_walkable,
    plant_bomb,
    process_bombs,
    try_move,
)
from core.controllers.human import IdleController
from core.entities.bomb import Bomb
from core.entities.player import Player
from core.vos.action import Action
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall


def make_player(pid: int, x: float, y: float) -> Player:
    p = Player()
    p.id = pid
    p.pos = Position(x, y)
    p.facing = Direction.RIGHT
    p.alive = True
    p.speed = 1
    p.bomb_capacity = 1
    p.active_bombs = 0
    p.controller = IdleController()
    return p


class TestCloneGamestate(unittest.TestCase):
    def setUp(self) -> None:
        p1 = make_player(1, 0.0, 0.0)
        p1.bomb_capacity = 2
        p1.active_bombs = 1

        bomb = Bomb(id=1, owner_id=1, pos=Position(1, 0), fuse_ticks=60, blast_radius=2)

        self.gs = Gamestate(
            width=3,
            height=3,
            grid_walls=[
                [Wall.EMPTY, Wall.EMPTY, Wall.BOX],
                [Wall.EMPTY, Wall.CONCRETE, Wall.EMPTY],
                [Wall.EMPTY, Wall.EMPTY, Wall.EMPTY],
            ],
            flames_grid=[[-1, -1, -1], [-1, -1, -1], [-1, -1, -1]],
            current_tick=42,
            bombs=[bomb],
            players=[p1],
        )

    def test_valores_copiados_corretamente(self) -> None:
        """Verifica se todos os dados do clone são iguais aos do original."""
        gs_clone = clone(self.gs)

        self.assertEqual(gs_clone.width, self.gs.width)
        self.assertEqual(gs_clone.height, self.gs.height)
        self.assertEqual(gs_clone.current_tick, 42)
        self.assertEqual(gs_clone.grid_walls, self.gs.grid_walls)
        self.assertEqual(gs_clone.flames_grid, self.gs.flames_grid)
        self.assertEqual(len(gs_clone.players), 1)
        self.assertEqual(gs_clone.players[0].id, 1)
        self.assertEqual(gs_clone.players[0].pos, Position(0.0, 0.0))
        self.assertIs(gs_clone.players[0].controller, self.gs.players[0].controller)
        self.assertEqual(len(gs_clone.bombs), 1)
        self.assertEqual(gs_clone.bombs[0].fuse_ticks, 60)

    def test_isolamento_do_mapa_e_fogo(self) -> None:
        """Destruir caixa ou criar fogo no clone não pode afetar o original."""
        gs_clone = clone(self.gs)

        gs_clone.grid_walls[0][2] = Wall.EMPTY
        gs_clone.flames_grid[0][0] = 20

        self.assertEqual(self.gs.grid_walls[0][2], Wall.BOX)
        self.assertEqual(self.gs.flames_grid[0][0], -1)

    def test_isolamento_dos_jogadores(self) -> None:
        """Mover ou matar um jogador no clone não pode alterar o jogador original."""
        gs_clone = clone(self.gs)

        gs_clone.players[0].pos = Position(2.5, 2.0)
        gs_clone.players[0].alive = False
        gs_clone.players[0].active_bombs = 0

        self.assertEqual(self.gs.players[0].pos, Position(0.0, 0.0))
        self.assertTrue(self.gs.players[0].alive)
        self.assertEqual(self.gs.players[0].active_bombs, 1)

    def test_isolamento_das_bombas_e_explosao(self) -> None:
        """Plantar ou explodir bombas no clone deve manter o original intacto."""
        gs_clone = clone(self.gs)

        gs_clone.bombs[0].fuse_ticks = 0
        explode_bomb(gs_clone, gs_clone.bombs[0])
        plant_bomb(gs_clone, gs_clone.players[0])

        self.assertEqual(gs_clone.grid_walls[0][2], Wall.EMPTY)
        self.assertEqual(gs_clone.flames_grid[0][1], 20)
        self.assertEqual(self.gs.bombs[0].fuse_ticks, 60)
        self.assertEqual(self.gs.grid_walls[0][2], Wall.BOX)
        self.assertEqual(self.gs.flames_grid[0][1], -1)


class TestDynamiteManEngine(unittest.TestCase):
    def setUp(self) -> None:
        p1 = make_player(1, 0.0, 0.0)
        p2 = make_player(2, 2.0, 2.0)

        self.gs = Gamestate(
            width=3,
            height=3,
            grid_walls=[
                [Wall.EMPTY, Wall.EMPTY, Wall.BOX],
                [Wall.EMPTY, Wall.CONCRETE, Wall.EMPTY],
                [Wall.EMPTY, Wall.EMPTY, Wall.EMPTY],
            ],
            flames_grid=[[-1, -1, -1], [-1, -1, -1], [-1, -1, -1]],
            current_tick=0,
            bombs=[],
            players=[p1, p2],
        )

    def test_movimento_continuo_e_parada_sub_bloco(self) -> None:
        """Jogador deve avançar 0.1 por tick e poder parar em 0.5 (entre dois blocos)."""
        for _ in range(5):
            apply_tick(self.gs, {1: [Action.RIGHT]})

        self.assertEqual(self.gs.players[0].pos, Position(0.5, 0.0))

    def test_colisao_com_parede_e_caixa(self) -> None:
        """Jogador não deve atravessar Wall.CONCRETE em (1,1) nem Wall.BOX em (2,0)."""
        self.gs.players[0].pos = Position(1.0, 0.0)
        self.assertFalse(try_move(self.gs, self.gs.players[0], 0, 1))
        self.assertFalse(try_move(self.gs, self.gs.players[0], 1, 0))
        self.assertEqual(self.gs.players[0].pos, Position(1.0, 0.0))

    def test_corner_sliding_nas_quinas(self) -> None:
        """Se o jogador estiver em (0.0, 0.3) e apertar DIREITA, deve deslizar para y=0.0."""
        self.gs.players[0].pos = Position(0.0, 0.3)
        self.assertTrue(try_move(self.gs, self.gs.players[0], 1, 0))
        self.assertLess(self.gs.players[0].pos.y, 0.3)

    def test_colisao_entre_jogadores(self) -> None:
        """Jogador vivo bloqueia outro jogador; se morrer, deixa passar."""
        self.gs.players[1].pos = Position(1.0, 0.0)
        self.assertFalse(is_walkable(self.gs, 1, 0, self.gs.players[0]))

        self.gs.players[1].alive = False
        self.assertTrue(is_walkable(self.gs, 1, 0, self.gs.players[0]))

    def test_plantar_bomba_e_sair_de_cima(self) -> None:
        """Jogador planta bomba, respeita capacidade, consegue sair de cima e depois é bloqueado."""
        p1 = self.gs.players[0]
        plant_bomb(self.gs, p1)
        self.assertEqual(len(self.gs.bombs), 1)
        self.assertEqual(p1.active_bombs, 1)

        # Capacidade = 1: tentar plantar de novo não adiciona outra bomba
        plant_bomb(self.gs, p1)
        self.assertEqual(len(self.gs.bombs), 1)

        # Consegue sair de cima da bomba recém-plantada em (0, 0)
        for _ in range(10):
            apply_tick(self.gs, {1: [Action.RIGHT]})
        self.assertEqual(p1.pos, Position(1.0, 0.0))

        # Depois que saiu, a bomba em (0, 0) bloqueia o retorno
        self.assertFalse(is_walkable(self.gs, 0, 0, p1))

    def test_explosao_quebra_caixa_e_reacao_em_cadeia(self) -> None:
        """Bomba explode em cadeia, destrói caixa em (2,0), para no concreto em (1,1) e devolve munição."""
        b1 = Bomb(id=1, owner_id=1, pos=Position(0, 0), fuse_ticks=1, blast_radius=2)
        b2 = Bomb(id=2, owner_id=2, pos=Position(1, 0), fuse_ticks=99, blast_radius=2)
        self.gs.bombs = [b1, b2]
        self.gs.players[0].active_bombs = 1

        process_bombs(self.gs)

        self.assertEqual(len(self.gs.bombs), 0)
        self.assertEqual(self.gs.players[0].active_bombs, 0)
        self.assertEqual(self.gs.grid_walls[0][2], Wall.EMPTY)
        self.assertFalse(is_flame(self.gs, 1, 1))

    def test_morte_vitoria_e_empate(self) -> None:
        """Quando P2 morre no fogo, game_over vira True e winner_id vira 1."""
        self.gs.flames_grid[2][2] = 5
        apply_tick(self.gs, {})

        self.assertFalse(self.gs.players[1].alive)
        self.assertTrue(self.gs.game_over)
        self.assertEqual(self.gs.winner_id, 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)