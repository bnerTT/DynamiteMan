#Entidades
VAZIO = 0
PAREDE = 1       # Indestrutível
BLOCO = 2        # Destrutível (pode dropar power-up)
BOMBA = 3
FOGO = 4
JOGADOR = 5
INIMIGO = 6

#Ações
A_CIMA = 0
A_BAIXO = 1
A_ESQUERDA = 2
A_DIREITA = 3
A_BOMBA = 4
A_NADA = 5

# Configurações do Jogo
BOMB_TICKS = 45          # Tempo de explosão (ex: 3 segundos a 15 ticks/s)
FIRE_TICKS = 5           # Tempo que o fogo fica na tela
DEFAULT_BOMB_RANGE = 2