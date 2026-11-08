# =============================================================================
#  som.py — Buzzer NÃO BLOQUEANTE do Sensor de Ré.
#
#  Por que não usar time.sleep() para fazer um bipe?
#      buzzer.ligar(); time.sleep_ms(80); buzzer.desligar()
#  Durante esses 80 ms a placa fica PARADA: não lê o sensor, não atualiza o
#  display... E no modo "bipe rápido" ela passaria a maior parte do tempo
#  dormindo. Em vez disso usamos uma MÁQUINA DE ESTADOS:
#
#    * o laço principal chama som.atualizar() o tempo todo (centenas de
#      vezes por segundo);
#    * cada chamada olha o relógio (time.ticks_ms()) e decide, NAQUELE
#      instante, se o buzzer deve estar ligado ou desligado;
#    * a chamada volta na hora — nada espera.
#
#  Linha do tempo de um bipe com intervalo de 400 ms e duração de 80 ms:
#
#      ligado  ███                 ███                 ███
#      tempo   0   80             400  480            800 ...
#              ^ início           ^ início (0 + intervalo)
#
#  O buzzer da BitDogLab é PASSIVO: ele só apita se receber uma onda
#  quadrada. Quem gera a onda é o PWM. A frequência da onda define o TOM e
#  o "duty" (fração do tempo em nível alto) influencia o VOLUME: duty baixo
#  = som mais fraco.
# =============================================================================

import time
from machine import Pin, PWM

from filtros import LIVRE, PARE

# Modos de som
SILENCIO = 0
BIPES = 1
CONTINUO = 2


class Som:
    def __init__(self, pino, freq_hz, volume_pct, bipe_ms,
                 intervalo_max_ms, intervalo_min_ms):
        self._pwm = PWM(Pin(pino))
        # A frequência é ajustada UMA vez. Para ligar/desligar mexemos só no
        # duty: trocar a frequência toda hora causa estalos no buzzer.
        self._freq_hz = freq_hz
        self._pwm.freq(freq_hz)
        self._duty_ligado = int(65535 * volume_pct / 100)
        self._bipe_ms = bipe_ms
        self._intervalo_max_ms = intervalo_max_ms
        self._intervalo_min_ms = intervalo_min_ms

        self.mudo = False
        self.modo = SILENCIO
        self.intervalo_ms = intervalo_max_ms   # período entre inícios de bipes
        self._inicio_bipe = None               # ticks do último bipe iniciado
        self._ligado = None                    # estado atual do PWM
        self._avulso_ate = None                # fim de um bipe avulso (ticks)
        self._desligar_pwm()

    # ------------------------------------------------------------ PWM
    def _ligar_pwm(self):
        if self._ligado is not True:
            self._pwm.duty_u16(self._duty_ligado)
            self._ligado = True

    def _desligar_pwm(self):
        if self._ligado is not False:
            self._pwm.duty_u16(0)
            self._ligado = False

    # ------------------------------------------------------- comandos
    def definir(self, zona, proximidade):
        """Escolhe o padrão de som a partir da zona e da proximidade (0 a 1).

        O intervalo entre bipes é uma RETA entre intervalo_max (proximidade 0,
        limite da zona ATENÇÃO) e intervalo_min (proximidade 1, limite da
        zona PARE). Assim o ritmo acelera continuamente enquanto o objeto se
        aproxima, e não só quando muda de zona."""
        if zona == LIVRE:
            if self.modo != SILENCIO:
                self._inicio_bipe = None   # ao voltar, o 1º bipe é imediato
            self.modo = SILENCIO
        elif zona == PARE:
            self.modo = CONTINUO
        else:
            self.modo = BIPES
            faixa = self._intervalo_max_ms - self._intervalo_min_ms
            self.intervalo_ms = int(self._intervalo_max_ms - proximidade * faixa)

    def alternar_mudo(self):
        """Liga/desliga o modo mudo (botão A, etapa 6). Devolve o novo estado."""
        self.mudo = not self.mudo
        return self.mudo

    def bipe_avulso(self, duracao_ms, freq_hz=None, agora=None):
        """Um bipe curto de aviso (ex.: confirmar um botão), também sem
        bloquear. Tem prioridade sobre o padrão da zona enquanto dura.
        No modo mudo, não toca."""
        if self.mudo:
            return
        if agora is None:
            agora = time.ticks_ms()
        if freq_hz:
            self._pwm.freq(freq_hz)
        self._avulso_ate = time.ticks_add(agora, duracao_ms)
        self._ligado = None          # força reaplicar o duty
        self._ligar_pwm()

    def desligar(self):
        """Silencia tudo AGORA. Chame ao encerrar o programa: se o PWM ficar
        ligado, o buzzer continua apitando mesmo com o programa parado!"""
        self.modo = SILENCIO
        self._avulso_ate = None
        self._ligado = None
        self._desligar_pwm()

    # ------------------------------------------- coração não bloqueante
    def atualizar(self, agora=None):
        """Chame a cada volta do laço principal. Decide se o buzzer fica
        ligado ou desligado neste instante e retorna imediatamente."""
        if agora is None:
            agora = time.ticks_ms()

        # 1) Bipe avulso em andamento tem prioridade.
        if self._avulso_ate is not None:
            if time.ticks_diff(self._avulso_ate, agora) > 0:
                return
            self._avulso_ate = None
            self._pwm.freq(self._freq_hz)   # volta ao tom normal
            self._ligado = None
            self._desligar_pwm()

        # 2) Mudo ou zona livre: nada de som.
        if self.mudo or self.modo == SILENCIO:
            self._desligar_pwm()
            return

        # 3) Zona PARE: som contínuo.
        if self.modo == CONTINUO:
            self._ligar_pwm()
            return

        # 4) Bipes: começa um novo quando já passou "intervalo_ms" desde o
        #    início do anterior; desliga quando o bipe atual completa
        #    "bipe_ms". Como o intervalo é relido a cada chamada, uma mudança
        #    de distância vale já para o próximo bipe.
        if (self._inicio_bipe is None or
                time.ticks_diff(agora, self._inicio_bipe) >= self.intervalo_ms):
            self._inicio_bipe = agora
            self._ligar_pwm()
        elif time.ticks_diff(agora, self._inicio_bipe) >= self._bipe_ms:
            self._desligar_pwm()

    def descricao(self):
        """Texto curto do estado atual (para o terminal)."""
        if self.mudo:
            return "mudo"
        if self.modo == SILENCIO:
            return "silencio"
        if self.modo == CONTINUO:
            return "CONTINUO"
        return "bipe/%4d ms" % self.intervalo_ms
