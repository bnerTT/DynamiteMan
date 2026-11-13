import unittest

from core.commands.gamerules import clone, explode_bomb, plant_bomb
from core.controllers.human import IdleController
from core.entities.bomb import Bomb
from core.entities.player import Player
from core.vos.direction import Direction
from core.vos.gamestate import Gamestate
from core.vos.position import Position
from core.vos.walls import Wall


class TestCloneGamestate(unittest.TestCase):
    def setUp(self) -> None:
        """Cria um Gamestate padrão antes de cada teste."""
        p1 = Player()
        p1.id = 1
        p1.pos = Position(0.0, 0.0)
        p1.facing = Direction.RIGHT
        p1.alive = True
        p1.speed = 1
        p1.bomb_capacity = 2
        p1.active_bombs = 1
        p1.controller = IdleController()

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

        # Jogador
        self.assertEqual(len(gs_clone.players), 1)
        self.assertEqual(gs_clone.players[0].id, 1)
        self.assertEqual(gs_clone.players[0].pos, Position(0.0, 0.0))
        self.assertIs(gs_clone.players[0].controller, self.gs.players[0].controller)

        # Bomba
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

        # Diminui pavio e explode a bomba no clone (deve quebrar a caixa em (2, 0))
        gs_clone.bombs[0].fuse_ticks = 0
        explode_bomb(gs_clone, gs_clone.bombs[0])
        plant_bomb(gs_clone, gs_clone.players[0])

        # O clone mudou: caixa quebrou e fogo espalhou
        self.assertEqual(gs_clone.grid_walls[0][2], Wall.EMPTY)
        self.assertEqual(gs_clone.flames_grid[0][1], 20)

        # O original continua 100% intacto!
        self.assertEqual(self.gs.bombs[0].fuse_ticks, 60)
        self.assertEqual(self.gs.grid_walls[0][2], Wall.BOX)
        self.assertEqual(self.gs.flames_grid[0][1], -1)


if __name__ == "__main__":
    unittest.main()