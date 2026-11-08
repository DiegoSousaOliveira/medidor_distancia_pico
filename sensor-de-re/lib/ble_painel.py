# =============================================================================
#  ble_painel.py — Envia o estado do Sensor de Ré por Bluetooth Low Energy.
#
#  A Pico W tem Bluetooth embutido (chip CYW43439). Aqui ela funciona como um
#  "periférico" BLE — igual a uma pulseira fitness: anuncia o nome
#  "SensorDeRe-XXXX" e quem se conectar recebe NOTIFICAÇÕES com o estado.
#  O computador (página pc/painel.html, no Chrome ou Edge) se conecta e
#  desenha a mesma tela do OLED.
#
#  POR QUE MANDAR O "ESTADO" E NÃO A IMAGEM?
#    imagem do OLED : 1024 bytes por quadro
#    estado         :   11 bytes (distância, zona, proximidade, mudo, ...)
#  ~100x menos dados no rádio = menos atraso, menos energia e quase nenhum
#  tempo gasto no laço principal. Quem desenha é o computador, que tem
#  processamento de sobra.
#
#  FORMATO DO PACOTE (11 bytes, little-endian, struct "<BBBHBBBHB"):
#    versão(1) modo(1) zona(1) cm(2) proximidade(1) flags(1)
#    limite_pare_cm(1) mm(2) sequência(1)
#    - cm/mm = 0xFFFF quando não há alvo
#    - proximidade: 0..255 (= 0.0..1.0)
#    - flags: bit0 = mudo, bit1 = medida congelada (Modo Trena),
#             bit2 = ajustando o limite PARE (janela na tela)
#    - sequência: conta 0..255, para o computador medir pacotes/s e perdas
#
#  Tudo aqui é NÃO BLOQUEANTE: gatts_notify() só coloca o pacote na fila do
#  rádio e retorna na hora.
# =============================================================================

import struct
import time
import bluetooth
from micropython import const

# Identificadores (UUIDs) do serviço e da característica. São números
# aleatórios de 128 bits — a página do computador usa os MESMOS valores.
UUID_SERVICO = bluetooth.UUID("23b6a012-f842-4df0-bd04-a1d17ce01e5e")
UUID_ESTADO = bluetooth.UUID("3c9a3b43-00e0-4d1b-bbe9-5a45f10e791b")

VERSAO_PACOTE = 1
SEM_ALVO = 0xFFFF
FORMATO = "<BBBHBBBHB"

_IRQ_CENTRAL_CONNECT = const(1)
_IRQ_CENTRAL_DISCONNECT = const(2)
_FLAG_READ = const(0x0002)
_FLAG_NOTIFY = const(0x0010)
_ADV_FLAGS = const(0x01)
_ADV_NOME = const(0x09)
_ADV_UUID128 = const(0x07)


def _campo_anuncio(tipo, valor):
    return struct.pack("BB", len(valor) + 1, tipo) + valor


class PainelBLE:
    def __init__(self, prefixo_nome, intervalo_min_ms, reenvio_ms):
        self._ble = bluetooth.BLE()
        self._ble.active(True)
        # Nome com o final do endereço MAC: numa sala com várias placas,
        # cada uma aparece com um nome diferente.
        mac = self._ble.config("mac")[1]
        self.nome = "%s-%02X%02X" % (prefixo_nome, mac[4], mac[5])
        self._ble.config(gap_name=self.nome)
        self._ble.irq(self._irq)
        ((self._h_estado,),) = self._ble.gatts_register_services((
            (UUID_SERVICO, ((UUID_ESTADO, _FLAG_READ | _FLAG_NOTIFY),)),
        ))
        self._intervalo_min_ms = intervalo_min_ms
        self._reenvio_ms = reenvio_ms
        self._conexoes = set()
        self._ativo = True
        self._ultimo_estado = None
        self._ultimo_envio = None
        self._seq = 0
        self.pacotes_enviados = 0
        # Anúncio (até 31 bytes): flags + nome. O UUID de 128 bits não cabe
        # junto, então vai na "resposta de scan".
        self._anuncio = (_campo_anuncio(_ADV_FLAGS, b"\x06") +
                         _campo_anuncio(_ADV_NOME, self.nome.encode()))
        self._resposta = _campo_anuncio(_ADV_UUID128, bytes(UUID_SERVICO))   # já na ordem do rádio
        self._anunciar()

    # ------------------------------------------------------- conexão
    def _irq(self, evento, dados):
        # Esta função é chamada pelo sistema BLE (interrupção): faça pouco!
        if evento == _IRQ_CENTRAL_CONNECT:
            self._conexoes.add(dados[0])
            self._ultimo_estado = None        # manda o estado já na próxima volta
        elif evento == _IRQ_CENTRAL_DISCONNECT:
            self._conexoes.discard(dados[0])
            if self._ativo:                   # (ao desligar, não re-anuncia)
                self._anunciar()              # volta a ficar visível

    def _anunciar(self):
        # Anuncia a cada 100 ms: o computador acha a placa rapidinho.
        self._ble.gap_advertise(100_000, adv_data=self._anuncio, resp_data=self._resposta)

    @property
    def conectado(self):
        return bool(self._conexoes)

    # --------------------------------------------------------- envio
    def publicar(self, agora, modo, zona, cm, proximidade, mudo,
                 congelado=False, limite_pare_cm=0, mm=None, ajustando=False):
        """Envia o estado se ele mudou (no máximo a cada intervalo_min_ms)
        ou, mesmo sem mudança, a cada reenvio_ms (para o computador saber
        que a conexão continua viva). Retorna na hora."""
        if not self._conexoes:
            return
        estado = (modo, zona, SEM_ALVO if cm is None else int(cm),
                  int(proximidade * 255 + 0.5),
                  (1 if mudo else 0) | (2 if congelado else 0) | (4 if ajustando else 0),
                  int(limite_pare_cm), SEM_ALVO if mm is None else int(mm))
        if self._ultimo_envio is not None:
            passou = time.ticks_diff(agora, self._ultimo_envio)
            if passou < self._intervalo_min_ms:
                return
            if estado == self._ultimo_estado and passou < self._reenvio_ms:
                return
        self._seq = (self._seq + 1) & 0xFF
        pacote = struct.pack(FORMATO, VERSAO_PACOTE, *estado, self._seq)
        # gatts_write guarda o valor (para quem LER a característica);
        # gatts_notify avisa os conectados. Se a fila do rádio estiver cheia,
        # perdemos este pacote — o próximo traz o estado atualizado.
        self._ble.gatts_write(self._h_estado, pacote)
        for conexao in self._conexoes:
            try:
                self._ble.gatts_notify(conexao, self._h_estado)
            except OSError:
                pass
        self._ultimo_estado = estado
        self._ultimo_envio = agora
        self.pacotes_enviados += 1

    def desligar(self):
        # Marca como inativo ANTES: desligar o rádio derruba a conexão e
        # dispara o evento "desconectou", que não deve tentar re-anunciar
        # com o rádio já desligado (dava OSError ENODEV).
        self._ativo = False
        self._conexoes = set()
        self._ble.gap_advertise(None)
        self._ble.active(False)
