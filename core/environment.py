# core/environment.py
import numpy as np
from .constants import *

class BombermanEnv:
    def __init__(self, width=15, height=13):
        self.width = width
        self.height = height
        self.grid = np.zeros((self.height, self.width), dtype=np.int8)
        
        # Estado do jogador
        self.player_pos = [1, 1] # [y, x] para casar com a matriz
        self.alive = True
        self.score = 0
        self.done = False
        
        # Controle de bombas ativas
        # Formato: {'pos': (y, x), 'ticks': int, 'range': int}
        self.active_bombs = [] 
        # Controle do fogo sumindo
        self.active_fires = [] 
        
    def reset(self):
        """Prepara um novo jogo."""
        self.grid.fill(VAZIO)
        self.player_pos = [1, 1]
        self.alive = True
        self.score = 0
        self.done = False
        self.active_bombs.clear()
        self.active_fires.clear()
        
        self._generate_map()
        # Marca o jogador na matriz
        self.grid[self.player_pos[0], self.player_pos[1]] = JOGADOR
        
        return self.get_state()

    def step(self, action):
        """Avança a simulação em 1 tick."""
        if self.done:
            return self.get_state(), 0, True

        reward = 0
        
        # 1. Limpa os fogos que já expiraram
        self._process_fires()
        
        # 2. Processa movimento ou plantar bomba
        self._process_action(action)
        
        # 3. Processa a contagem regressiva e explosões das bombas
        reward += self._process_bombs()
        
        # 4. Verifica morte
        if not self.alive or self.grid[self.player_pos[0], self.player_pos[1]] == FOGO:
            self.alive = False
            self.done = True
            reward -= 100 # Punição por morrer

        # Atualiza a posição do jogador no grid (se estiver vivo)
        if self.alive:
            self.grid[self.player_pos[0], self.player_pos[1]] = JOGADOR
            
        return self.get_state(), reward, self.done

    def get_state(self):
        """Retorna uma cópia rápida da matriz para MCTS/Minimax."""
        return np.copy(self.grid)

    def _process_action(self, action):
        # Remove o jogador da posição antiga
        self.grid[self.player_pos[0], self.player_pos[1]] = VAZIO
        
        y, x = self.player_pos
        new_y, new_x = y, x

        if action == A_CIMA: new_y -= 1
        elif action == A_BAIXO: new_y += 1
        elif action == A_ESQUERDA: new_x -= 1
        elif action == A_DIREITA: new_x += 1
        elif action == A_BOMBA:
            # Planta bomba se a célula estiver vazia
            if self.grid[y, x] == VAZIO:
                self.grid[y, x] = BOMBA
                self.active_bombs.append({
                    'pos': (y, x), 
                    'ticks': BOMB_TICKS, 
                    'range': DEFAULT_BOMB_RANGE
                })

        # Verifica colisão simples
        if self._is_walkable(new_y, new_x):
            self.player_pos = [new_y, new_x]

    def _is_walkable(self, y, x):
        if not (0 <= y < self.height and 0 <= x < self.width):
            return False
        # O jogador pode andar no VAZIO ou no próprio FOGO (para morrer no step seguinte)
        return self.grid[y, x] in [VAZIO, FOGO]

    def _generate_map(self):
        """Gera as bordas e paredes internas."""
        # Paredes externas
        self.grid[0, :] = PAREDE
        self.grid[-1, :] = PAREDE
        self.grid[:, 0] = PAREDE
        self.grid[:, -1] = PAREDE
        
        # Paredes intercaladas (padrão Bomberman)
        for y in range(2, self.height - 1, 2):
            for x in range(2, self.width - 1, 2):
                self.grid[y, x] = PAREDE
                
        # (Futuro: Adicionar geração procedural de blocos destrutíveis aqui)

    def _process_bombs(self):
        # A implementar: reduzir ticks, explodir, gerar fogo cruzado
        return 0
        
    def _process_fires(self):
        # A implementar: apagar fogos que terminaram os ticks
        pass