# =============================================================================
#  controles.py — Botões e joystick, lidos SEM bloquear o laço.
#
#  BOTÕES E O "REPIQUE"
#  Um botão mecânico não fecha o contato de forma limpa: por alguns
#  milissegundos ele "quica" entre aberto e fechado:
#
#      solto ‾‾‾‾‾‾|_|‾|_|‾|________________ apertado
#                  └─ repique ─┘
#
#  Se contássemos cada descida, um aperto viraria 3 ou 4. A solução
#  (antirrepique por tempo): só aceitamos um novo estado depois que ele
#  ficou ESTÁVEL por `antirrepique_ms`. Lemos o pino a cada volta do laço
#  (polling) — nada de sleep.
#
#  JOYSTICK
#  Cada eixo é um potenciômetro ligado a uma entrada analógica (ADC): parado
#  no meio ele lê ~32768 (de 0 a 65535). Ao ligar, medimos o centro real;
#  depois convertemos a leitura em uma posição de -1.0 a +1.0. Perto do
#  centro há uma ZONA MORTA (o joystick nunca volta exatamente ao meio).
# =============================================================================

import time
from machine import Pin, ADC


class Botao:
    """Botão com pull-up interno: solto = 1, apertado = 0."""

    def __init__(self, pino, antirrepique_ms):
        self._pino = Pin(pino, Pin.IN, Pin.PULL_UP)
        self._antirrepique_ms = antirrepique_ms
        self._estavel = self._pino.value()     # último estado aceito
        self._candidato = self._estavel        # estado que está "se firmando"
        self._desde = time.ticks_ms()

    def apertou(self, agora):
        """True UMA vez por aperto (no momento em que o aperto se firma)."""
        valor = self._pino.value()
        if valor != self._candidato:
            # Mudou (ou está quicando): recomeça a contar o tempo.
            self._candidato = valor
            self._desde = agora
            return False
        if (valor != self._estavel and
                time.ticks_diff(agora, self._desde) >= self._antirrepique_ms):
            self._estavel = valor
            return valor == 0          # só a DESCIDA (aperto) conta
        return False


class EixoJoystick:
    """Um eixo do joystick que gera "passos" de +1/-1 com repetição
    automática: empurrou -> 1 passo na hora; segurou -> mais passos, cada
    vez mais rápidos quanto mais longe do centro."""

    def __init__(self, pino, zona_morta, repeticao_lenta_ms,
                 repeticao_rapida_ms, invertido=False):
        self._adc = ADC(Pin(pino))
        self._zona_morta = zona_morta
        self._lenta = repeticao_lenta_ms
        self._rapida = repeticao_rapida_ms
        self._sinal = -1 if invertido else 1
        self._proximo_passo = None
        self.centro = self._medir_centro()

    def _medir_centro(self, amostras=32):
        # Ao ligar, o joystick está solto: a média das leituras é o centro.
        soma = 0
        for _ in range(amostras):
            soma += self._adc.read_u16()
        return soma // amostras

    def posicao(self):
        """-1.0 (um extremo) .. 0 (centro) .. +1.0 (outro extremo)."""
        v = self._adc.read_u16()
        if v >= self.centro:
            p = (v - self.centro) / max(1, 65535 - self.centro)
        else:
            p = (v - self.centro) / max(1, self.centro)
        return self._sinal * max(-1.0, min(1.0, p))

    def passo(self, agora):
        """Devolve +1, -1 ou 0. Chame a cada volta do laço."""
        p = self.posicao()
        if abs(p) < self._zona_morta:
            self._proximo_passo = None        # soltou: o próximo é imediato
            return 0
        if (self._proximo_passo is not None and
                time.ticks_diff(agora, self._proximo_passo) < 0):
            return 0                          # ainda não é hora de repetir
        # Quanto mais empurrado, menor o intervalo até o próximo passo.
        forca = (abs(p) - self._zona_morta) / (1 - self._zona_morta)
        intervalo = int(self._lenta - forca * (self._lenta - self._rapida))
        self._proximo_passo = time.ticks_add(agora, intervalo)
        return 1 if p > 0 else -1
