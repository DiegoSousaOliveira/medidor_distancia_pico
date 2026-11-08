# =============================================================================
#  matriz.py — Luzes do Sensor de Ré: matriz 5x5 (WS2812) e LED RGB.
#
#  MATRIZ = "barra de proximidade", como um termômetro deitado de pé:
#
#      longe (LIVRE)         meio (PERIGO)          perto (PARE)
#      . . . . .             . . . . .              # # # # #  <- pisca
#      . . . . .             : : : : :  (meia)      # # # # #
#      . . . . .             # # # # #              # # # # #
#      . . . . .             # # # # #              # # # # #
#      # # # # #  verde      # # # # #  laranja     # # # # #  vermelho
#
#  A altura vai de 1 linha (proximidade 0) a 5 linhas (proximidade 1). A
#  linha do topo pode ficar PARCIALMENTE acesa (ex.: 3,4 linhas = 3 linhas
#  cheias + a 4ª com 40 % do brilho), então a barra sobe de forma contínua.
#
#  Nada aqui usa sleep: atualizar(agora) é chamado a cada volta do laço e
#  só redesenha quando chega a hora do próximo quadro.
# =============================================================================

import time
import neopixel
from machine import Pin, PWM

from cores import APAGADO, escalar, limitar_brilho, normalizar_brilho, TransicaoCor

LINHAS = 5
COLUNAS = 5
NUM_LEDS = LINHAS * COLUNAS


def indice(linha, coluna):
    """Converte (linha, coluna) na posição do LED no fio de dados.

    Linha 0 = topo, coluna 0 = esquerda (como numa tabela). Na BitDogLab os
    25 LEDs formam uma "cobra" em ZIGUE-ZAGUE que começa no canto de baixo
    à direita:

        24 23 22 21 20     <- linha 0 (topo)
        15 16 17 18 19
        14 13 12 11 10
         5  6  7  8  9
         4  3  2  1  0     <- linha 4 (base): o LED 0 é o primeiro do fio

    Contando as linhas DE BAIXO para cima, as pares (0, 2, 4) correm da
    direita para a esquerda e as ímpares (1, 3) da esquerda para a direita.
    """
    linha_de_baixo = LINHAS - 1 - linha
    if linha_de_baixo % 2 == 0:
        return linha_de_baixo * COLUNAS + (COLUNAS - 1 - coluna)
    return linha_de_baixo * COLUNAS + coluna


# Tabela pronta: índices dos 5 LEDs de cada linha, contando DE BAIXO
# (posição 0 = linha da base). Calculada uma vez só, ao importar o módulo.
_INDICES_DA_LINHA = tuple(
    tuple(indice(LINHAS - 1 - b, c) for c in range(COLUNAS)) for b in range(LINHAS))


class Matriz:
    def __init__(self, pino, brilho, transicao_ms, quadro_ms, pisca_ms):
        self._np = neopixel.NeoPixel(Pin(pino, Pin.OUT), NUM_LEDS)
        self._brilho = brilho
        self._quadro_ms = quadro_ms
        self._pisca_ms = pisca_ms
        self._cor = TransicaoCor(transicao_ms)
        self._altura = 0.0          # 0 = apagada; 1..5 = linhas acesas
        self._piscar = False
        self._inicio_pisca = 0
        self._ultimo_quadro = None
        self._desenho_anterior = None
        self.apagar()

    def definir(self, cor, proximidade, piscar, agora):
        """Escolhe o que mostrar: cor alvo, proximidade (0 a 1) e se pisca."""
        self._cor.alvo(cor, agora)
        self._altura = 1 + proximidade * (LINHAS - 1)
        if piscar and not self._piscar:
            # Começa a piscar ACESA: o alerta aparece na hora.
            self._inicio_pisca = agora
        self._piscar = piscar

    def atualizar(self, agora):
        """Redesenha no máximo a cada `quadro_ms`. Retorna na hora."""
        if (self._ultimo_quadro is not None and
                time.ticks_diff(agora, self._ultimo_quadro) < self._quadro_ms):
            return
        self._ultimo_quadro = agora

        # Normaliza DEPOIS de misturar: durante a transição de cor o brilho
        # também fica constante (não "apaga" no meio do caminho).
        cor = normalizar_brilho(self._cor.cor(agora), self._brilho)
        aceso = True
        if self._piscar:
            # Metade do ciclo acesa, metade apagada.
            fase = time.ticks_diff(agora, self._inicio_pisca) // self._pisca_ms
            aceso = (fase % 2 == 0)

        desenho = (cor, int(self._altura * 20), aceso)   # 20 degraus por linha
        if desenho == self._desenho_anterior:
            return          # nada mudou: não precisa reenviar os 25 LEDs
        self._desenho_anterior = desenho

        # Escrevemos DIRETO no buffer de bytes do NeoPixel (3 bytes por LED,
        # na ordem G, R, B que o chip WS2812 espera). Usar np[i] = cor é bem
        # mais lento, porque a biblioteca reorganiza as cores LED por LED.
        buf = self._np.buf
        for linha_de_baixo in range(LINHAS):
            # Quanto desta linha está aceso (0.0 a 1.0)?
            nivel = self._altura - linha_de_baixo
            nivel = 0.0 if nivel < 0 else (1.0 if nivel > 1 else nivel)
            # A cor é calculada UMA vez por linha (não 5 vezes) e os índices
            # vêm de uma tabela pronta.
            r, g, b = escalar(cor, nivel) if aceso else APAGADO
            for i in _INDICES_DA_LINHA[linha_de_baixo]:
                p = i * 3
                buf[p] = g
                buf[p + 1] = r
                buf[p + 2] = b
        self._np.write()

    def acender(self, pixels):
        """Acende pixels avulsos: pixels = {(linha, coluna): cor}. Para testes
        e telas especiais (nunca passa do brilho configurado)."""
        for i in range(NUM_LEDS):
            self._np[i] = APAGADO
        for (linha, coluna), cor in pixels.items():
            self._np[indice(linha, coluna)] = limitar_brilho(cor, self._brilho)
        self._np.write()
        self._desenho_anterior = None

    def apagar(self):
        for i in range(NUM_LEDS):
            self._np[i] = APAGADO
        self._np.write()
        self._desenho_anterior = None


class LedRGB:
    """LED RGB comum (3 LEDs num só), cada cor num pino com PWM.

    Atenção: no RP2040, GP12 e GP13 usam o mesmo "slice" de PWM, então
    obrigatoriamente têm a MESMA frequência — por isso usamos uma frequência
    só para as três cores."""

    def __init__(self, pino_r, pino_g, pino_b, freq_hz, ganho, transicao_ms):
        self._pwms = [PWM(Pin(p)) for p in (pino_r, pino_g, pino_b)]
        for pwm in self._pwms:
            pwm.freq(freq_hz)
        # Ganho por canal: o LED discreto e o WS2812 não têm o mesmo brilho
        # em cada cor; o ganho permite ajustar para as cores "baterem".
        self._ganho = ganho
        self._cor = TransicaoCor(transicao_ms)
        self._ultima = None
        self.desligar()

    def definir(self, cor, agora):
        self._cor.alvo(cor, agora)

    def atualizar(self, agora):
        cor = self._cor.cor(agora)
        if cor == self._ultima:
            return
        self._ultima = cor
        for pwm, valor, ganho in zip(self._pwms, cor, self._ganho):
            duty = int(valor * 257 * ganho)          # 0..255 -> 0..65535
            pwm.duty_u16(min(duty, 65535))

    def desligar(self):
        for pwm in self._pwms:
            pwm.duty_u16(0)
        self._ultima = APAGADO
