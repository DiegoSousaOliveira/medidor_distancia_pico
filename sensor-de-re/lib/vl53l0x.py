# =============================================================================
#  vl53l0x.py — Driver MicroPython para o sensor de distância VL53L0X (ST)
# =============================================================================
#
#  ORIGEM E CRÉDITOS
#  -----------------
#  Este arquivo é um PORTE para MicroPython (machine.I2C) de dois drivers
#  consolidados, ambos com licença MIT:
#
#   * Pololu — "vl53l0x-arduino" (C++), (c) 2017 Pololu Corporation
#     https://github.com/pololu/vl53l0x-arduino
#     A Pololu, por sua vez, derivou o código da API oficial da ST
#     (STSW-IMG005, "VL53L0X API"), (c) STMicroelectronics.
#
#   * Adafruit — "Adafruit_CircuitPython_VL53L0X", (c) 2017 Tony DiCola for
#     Adafruit Industries. https://github.com/adafruit/Adafruit_CircuitPython_VL53L0X
#
#  O que mudou no porte:
#   - acesso ao barramento via machine.I2C (readfrom_mem / writeto_mem),
#     com buffers pré-alocados para não gerar lixo de memória a cada leitura;
#   - temporização com time.ticks_ms() (não existe time.monotonic());
#   - modo "2V8" de E/S, modo contínuo temporizado e arredondamentos das
#     conversões de tempo seguem o código da Pololu;
#   - reset por software (sequência do VL53L0X_ResetDevice da ST) antes da
#     inicialização, para o sensor voltar a um estado conhecido mesmo se a
#     Pico for reiniciada com o sensor ainda medindo em modo contínuo;
#   - leitura NÃO bloqueante: data_ready() + read_range().
#
#  A sequência de inicialização (SPADs de referência, "tuning settings" da ST,
#  calibrações VHV e de fase) foi mantida COMPLETA. Não simplifique: sem ela o
#  sensor liga, mas mede errado.
#
#  ---------------------------------------------------------------------------
#  Licença MIT
#
#  Permission is hereby granted, free of charge, to any person obtaining a copy
#  of this software and associated documentation files (the "Software"), to
#  deal in the Software without restriction, including without limitation the
#  rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
#  sell copies of the Software, and to permit persons to whom the Software is
#  furnished to do so, subject to the following conditions:
#
#  The above copyright notice and this permission notice shall be included in
#  all copies or substantial portions of the Software.
#
#  THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
#  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
#  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
#  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
#  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
#  FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
#  IN THE SOFTWARE.
# =============================================================================
#
#  USO BÁSICO
#  ----------
#      from machine import I2C, Pin
#      from vl53l0x import VL53L0X
#      i2c = I2C(0, sda=Pin(0), scl=Pin(1), freq=400_000)
#      sensor = VL53L0X(i2c)
#      sensor.set_measurement_timing_budget(33000)   # 33 ms por medida
#      sensor.start_continuous(50)                    # uma medida a cada 50 ms
#      while True:
#          if sensor.data_ready():                    # não espera!
#              print(sensor.read_range(), "mm")
# =============================================================================

from micropython import const
import time

# --- Endereço padrão de fábrica (7 bits) ------------------------------------
DEFAULT_ADDRESS = const(0x29)

# --- Registradores (nomes iguais aos da Pololu/ST, para facilitar consulta) --
_SYSRANGE_START = const(0x00)
_SYSTEM_SEQUENCE_CONFIG = const(0x01)
_SYSTEM_INTERMEASUREMENT_PERIOD = const(0x04)
_SYSTEM_INTERRUPT_CONFIG_GPIO = const(0x0A)
_SYSTEM_INTERRUPT_CLEAR = const(0x0B)
_RESULT_INTERRUPT_STATUS = const(0x13)
_RESULT_RANGE_STATUS = const(0x14)
_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT = const(0x44)
_MSRC_CONFIG_TIMEOUT_MACROP = const(0x46)
_DYNAMIC_SPAD_NUM_REQUESTED_REF_SPAD = const(0x4E)
_DYNAMIC_SPAD_REF_EN_START_OFFSET = const(0x4F)
_PRE_RANGE_CONFIG_VCSEL_PERIOD = const(0x50)
_PRE_RANGE_CONFIG_TIMEOUT_MACROP_HI = const(0x51)
_MSRC_CONFIG_CONTROL = const(0x60)
_FINAL_RANGE_CONFIG_VCSEL_PERIOD = const(0x70)
_FINAL_RANGE_CONFIG_TIMEOUT_MACROP_HI = const(0x71)
_GPIO_HV_MUX_ACTIVE_HIGH = const(0x84)
_VHV_CONFIG_PAD_SCL_SDA__EXTSUP_HV = const(0x89)
_I2C_SLAVE_DEVICE_ADDRESS = const(0x8A)
_GLOBAL_CONFIG_SPAD_ENABLES_REF_0 = const(0xB0)
_GLOBAL_CONFIG_REF_EN_START_SELECT = const(0xB6)
_SOFT_RESET_GO2_SOFT_RESET_N = const(0xBF)
_IDENTIFICATION_MODEL_ID = const(0xC0)
_OSC_CALIBRATE_VAL = const(0xF8)

# Leitura que o sensor devolve quando não há alvo (ou o alvo está longe demais)
OUT_OF_RANGE = const(8190)

# "Tuning settings" padrão da ST (DefaultTuningSettings da API). São pares
# (registrador, valor) sem documentação pública: copiados exatamente como a
# ST/Pololu os definem. NÃO altere.
_DEFAULT_TUNING = (
    (0xFF, 0x01), (0x00, 0x00), (0xFF, 0x00), (0x09, 0x00), (0x10, 0x00),
    (0x11, 0x00), (0x24, 0x01), (0x25, 0xFF), (0x75, 0x00), (0xFF, 0x01),
    (0x4E, 0x2C), (0x48, 0x00), (0x30, 0x20), (0xFF, 0x00), (0x30, 0x09),
    (0x54, 0x00), (0x31, 0x04), (0x32, 0x03), (0x40, 0x83), (0x46, 0x25),
    (0x60, 0x00), (0x27, 0x00), (0x50, 0x06), (0x51, 0x00), (0x52, 0x96),
    (0x56, 0x08), (0x57, 0x30), (0x61, 0x00), (0x62, 0x00), (0x64, 0x00),
    (0x65, 0x00), (0x66, 0xA0), (0xFF, 0x01), (0x22, 0x32), (0x47, 0x14),
    (0x49, 0xFF), (0x4A, 0x00), (0xFF, 0x00), (0x7A, 0x0A), (0x7B, 0x00),
    (0x78, 0x21), (0xFF, 0x01), (0x23, 0x34), (0x42, 0x00), (0x44, 0xFF),
    (0x45, 0x26), (0x46, 0x05), (0x40, 0x40), (0x0E, 0x06), (0x20, 0x1A),
    (0x43, 0x40), (0xFF, 0x00), (0x34, 0x03), (0x35, 0x44), (0xFF, 0x01),
    (0x31, 0x04), (0x4B, 0x09), (0x4C, 0x05), (0x4D, 0x04), (0xFF, 0x00),
    (0x44, 0x00), (0x45, 0x20), (0x47, 0x08), (0x48, 0x28), (0x67, 0x00),
    (0x70, 0x04), (0x71, 0x01), (0x72, 0xFE), (0x76, 0x00), (0x77, 0x00),
    (0xFF, 0x01), (0x0D, 0x01), (0xFF, 0x00), (0x80, 0x01), (0x01, 0xF8),
    (0xFF, 0x01), (0x8E, 0x01), (0x00, 0x01), (0xFF, 0x00), (0x80, 0x00),
)


# --- Conversões de tempo (ST API / Pololu) ----------------------------------
# O sensor conta tempo em "MCLKs" (macro períodos), cuja duração depende do
# período do pulso do laser (VCSEL). Estas funções convertem MCLK <-> µs.

def _decode_timeout(reg_val):
    # Formato do registrador: (LSByte * 2^MSByte) + 1
    return ((reg_val & 0xFF) << ((reg_val >> 8) & 0xFF)) + 1


def _encode_timeout(timeout_mclks):
    # Inverso de _decode_timeout.
    timeout_mclks = int(timeout_mclks)
    if timeout_mclks <= 0:
        return 0
    ls_byte = timeout_mclks - 1
    ms_byte = 0
    while ls_byte > 0xFF:
        ls_byte >>= 1
        ms_byte += 1
    return ((ms_byte << 8) | (ls_byte & 0xFF)) & 0xFFFF


def _calc_macro_period_ns(vcsel_period_pclks):
    return ((2304 * vcsel_period_pclks * 1655) + 500) // 1000


def _timeout_mclks_to_us(timeout_mclks, vcsel_period_pclks):
    macro_ns = _calc_macro_period_ns(vcsel_period_pclks)
    return ((timeout_mclks * macro_ns) + 500) // 1000


def _timeout_us_to_mclks(timeout_us, vcsel_period_pclks):
    macro_ns = _calc_macro_period_ns(vcsel_period_pclks)
    return ((timeout_us * 1000) + (macro_ns // 2)) // macro_ns


class VL53L0X:
    """Sensor de distância por tempo de voo (laser 940 nm), até ~2 m."""

    def __init__(self, i2c, address=DEFAULT_ADDRESS, io_2v8=True, io_timeout_ms=500):
        self._i2c = i2c
        self._addr = address
        self.io_timeout_ms = io_timeout_ms
        self.did_timeout = False
        self._continuous = False
        # Buffers reaproveitados: evitam alocar memória a cada acesso I2C,
        # o que reduz as pausas do coletor de lixo no laço principal.
        self._b1 = bytearray(1)
        self._b2 = bytearray(2)
        self._b4 = bytearray(4)
        self._spad_map = bytearray(6)
        self._init(io_2v8)

    # ------------------------------------------------------------------ I2C
    def _w8(self, reg, val):
        self._b1[0] = val & 0xFF
        self._i2c.writeto_mem(self._addr, reg, self._b1)

    def _w16(self, reg, val):
        self._b2[0] = (val >> 8) & 0xFF
        self._b2[1] = val & 0xFF
        self._i2c.writeto_mem(self._addr, reg, self._b2)

    def _w32(self, reg, val):
        self._b4[0] = (val >> 24) & 0xFF
        self._b4[1] = (val >> 16) & 0xFF
        self._b4[2] = (val >> 8) & 0xFF
        self._b4[3] = val & 0xFF
        self._i2c.writeto_mem(self._addr, reg, self._b4)

    def _r8(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._b1)
        return self._b1[0]

    def _r16(self, reg):
        self._i2c.readfrom_mem_into(self._addr, reg, self._b2)
        return (self._b2[0] << 8) | self._b2[1]

    def _write_pairs(self, pairs):
        for reg, val in pairs:
            self._w8(reg, val)

    # --------------------------------------------------------------- timeout
    def _start_timeout(self):
        self._t0 = time.ticks_ms()

    def _timeout_expired(self):
        return (self.io_timeout_ms > 0 and
                time.ticks_diff(time.ticks_ms(), self._t0) > self.io_timeout_ms)

    # ---------------------------------------------------------------- reset
    def _soft_reset(self):
        # Sequência do VL53L0X_ResetDevice() da ST: liga o bit de reset,
        # espera o ID sumir (0x00), solta o reset e espera o ID voltar.
        # Durante o reset o sensor pode não responder (OSError): é esperado.
        self._w8(_SOFT_RESET_GO2_SOFT_RESET_N, 0x00)
        self._start_timeout()
        while True:
            try:
                if self._r8(_IDENTIFICATION_MODEL_ID) == 0x00:
                    break
            except OSError:
                break
            if self._timeout_expired():
                break
        time.sleep_ms(2)
        self._w8(_SOFT_RESET_GO2_SOFT_RESET_N, 0x01)
        self._start_timeout()
        while True:
            try:
                if self._r8(_IDENTIFICATION_MODEL_ID) != 0x00:
                    return
            except OSError:
                pass
            if self._timeout_expired():
                raise OSError("VL53L0X nao voltou do reset")
            time.sleep_ms(1)

    # ---------------------------------------------------------------- init
    def _init(self, io_2v8):
        # Confere os registradores de identificação (datasheet, seção 3.2).
        if (self._r8(0xC0) != 0xEE or self._r8(0xC1) != 0xAA
                or self._r8(0xC2) != 0x10):
            raise OSError("ID do VL53L0X inesperado: confira a ligacao")

        self._soft_reset()

        # ===== VL53L0X_DataInit() =====
        # Ajusta os pinos de E/S do sensor para 2,8 V (padrão Pololu).
        if io_2v8:
            self._w8(_VHV_CONFIG_PAD_SCL_SDA__EXTSUP_HV,
                     self._r8(_VHV_CONFIG_PAD_SCL_SDA__EXTSUP_HV) | 0x01)

        # "Set I2C standard mode"
        self._write_pairs(((0x88, 0x00), (0x80, 0x01), (0xFF, 0x01), (0x00, 0x00)))
        # O "stop variable" é lido aqui e reescrito a cada início de medida.
        self._stop_variable = self._r8(0x91)
        self._write_pairs(((0x00, 0x01), (0xFF, 0x00), (0x80, 0x00)))

        # Desliga as checagens SIGNAL_RATE_MSRC (bit 1) e
        # SIGNAL_RATE_PRE_RANGE (bit 4).
        self._w8(_MSRC_CONFIG_CONTROL, self._r8(_MSRC_CONFIG_CONTROL) | 0x12)

        # Limite de taxa de sinal do "final range": 0,25 MCPS.
        self.set_signal_rate_limit(0.25)
        self._w8(_SYSTEM_SEQUENCE_CONFIG, 0xFF)

        # ===== VL53L0X_StaticInit() =====
        # Configura os SPADs (fotodiodos) de referência usados pelo sensor.
        spad_count, spad_is_aperture = self._get_spad_info()
        self._i2c.readfrom_mem_into(self._addr, _GLOBAL_CONFIG_SPAD_ENABLES_REF_0,
                                    self._spad_map)
        self._write_pairs((
            (0xFF, 0x01),
            (_DYNAMIC_SPAD_REF_EN_START_OFFSET, 0x00),
            (_DYNAMIC_SPAD_NUM_REQUESTED_REF_SPAD, 0x2C),
            (0xFF, 0x00),
            (_GLOBAL_CONFIG_REF_EN_START_SELECT, 0xB4),
        ))
        first_spad = 12 if spad_is_aperture else 0
        enabled = 0
        for i in range(48):
            byte_i, bit_i = i // 8, i % 8
            if i < first_spad or enabled == spad_count:
                # Abaixo do primeiro SPAD permitido, ou já habilitamos todos os
                # necessários: desliga este bit.
                self._spad_map[byte_i] &= ~(1 << bit_i)
            elif (self._spad_map[byte_i] >> bit_i) & 0x01:
                enabled += 1
        self._i2c.writeto_mem(self._addr, _GLOBAL_CONFIG_SPAD_ENABLES_REF_0,
                              self._spad_map)

        # Configurações de ajuste fino da ST.
        self._write_pairs(_DEFAULT_TUNING)

        # Interrupção "nova amostra pronta", ativa em nível baixo.
        self._w8(_SYSTEM_INTERRUPT_CONFIG_GPIO, 0x04)
        self._w8(_GPIO_HV_MUX_ACTIVE_HIGH, self._r8(_GPIO_HV_MUX_ACTIVE_HIGH) & ~0x10)
        self._w8(_SYSTEM_INTERRUPT_CLEAR, 0x01)

        # Desliga as etapas MSRC e TCC (como faz a ST) e recalcula os tempos.
        self._budget_us = self.get_measurement_timing_budget()
        self._w8(_SYSTEM_SEQUENCE_CONFIG, 0xE8)
        self.set_measurement_timing_budget(self._budget_us)

        # ===== VL53L0X_PerformRefCalibration() =====
        self._w8(_SYSTEM_SEQUENCE_CONFIG, 0x01)
        self._single_ref_calibration(0x40)   # calibração VHV
        self._w8(_SYSTEM_SEQUENCE_CONFIG, 0x02)
        self._single_ref_calibration(0x00)   # calibração de fase
        self._w8(_SYSTEM_SEQUENCE_CONFIG, 0xE8)  # restaura a sequência

    def _get_spad_info(self):
        # Lê da memória interna do sensor quantos SPADs de referência usar
        # e de que tipo (abertura ou não-abertura).
        self._write_pairs(((0x80, 0x01), (0xFF, 0x01), (0x00, 0x00), (0xFF, 0x06)))
        self._w8(0x83, self._r8(0x83) | 0x04)
        self._write_pairs(((0xFF, 0x07), (0x81, 0x01), (0x80, 0x01),
                           (0x94, 0x6B), (0x83, 0x00)))
        self._start_timeout()
        while self._r8(0x83) == 0x00:
            if self._timeout_expired():
                raise OSError("timeout lendo SPADs do VL53L0X")
        self._w8(0x83, 0x01)
        tmp = self._r8(0x92)
        count = tmp & 0x7F
        is_aperture = bool((tmp >> 7) & 0x01)
        self._write_pairs(((0x81, 0x00), (0xFF, 0x06)))
        self._w8(0x83, self._r8(0x83) & ~0x04)
        self._write_pairs(((0xFF, 0x01), (0x00, 0x01), (0xFF, 0x00), (0x80, 0x00)))
        return count, is_aperture

    def _single_ref_calibration(self, vhv_init_byte):
        self._w8(_SYSRANGE_START, 0x01 | vhv_init_byte)
        self._start_timeout()
        while (self._r8(_RESULT_INTERRUPT_STATUS) & 0x07) == 0:
            if self._timeout_expired():
                raise OSError("timeout na calibracao do VL53L0X")
        self._w8(_SYSTEM_INTERRUPT_CLEAR, 0x01)
        self._w8(_SYSRANGE_START, 0x00)

    # ------------------------------------------------------- configuração
    def set_signal_rate_limit(self, limit_mcps):
        # Valor em ponto fixo 9.7 (7 bits de fração).
        if not 0 <= limit_mcps <= 511.99:
            raise ValueError("limite fora da faixa")
        self._w16(_FINAL_RANGE_CONFIG_MIN_COUNT_RATE_RTN_LIMIT, int(limit_mcps * (1 << 7)))

    def _get_vcsel_period(self, reg):
        # Período do pulso do laser em PCLKs: (valor + 1) * 2
        return (self._r8(reg) + 1) << 1

    def _get_sequence_step_enables(self):
        cfg = self._r8(_SYSTEM_SEQUENCE_CONFIG)
        tcc = (cfg >> 4) & 1
        dss = (cfg >> 3) & 1
        msrc = (cfg >> 2) & 1
        pre_range = (cfg >> 6) & 1
        final_range = (cfg >> 7) & 1
        return tcc, dss, msrc, pre_range, final_range

    def _get_sequence_step_timeouts(self, pre_range):
        pre_vcsel = self._get_vcsel_period(_PRE_RANGE_CONFIG_VCSEL_PERIOD)
        msrc_mclks = self._r8(_MSRC_CONFIG_TIMEOUT_MACROP) + 1
        msrc_us = _timeout_mclks_to_us(msrc_mclks, pre_vcsel)
        pre_mclks = _decode_timeout(self._r16(_PRE_RANGE_CONFIG_TIMEOUT_MACROP_HI))
        pre_us = _timeout_mclks_to_us(pre_mclks, pre_vcsel)
        final_vcsel = self._get_vcsel_period(_FINAL_RANGE_CONFIG_VCSEL_PERIOD)
        final_mclks = _decode_timeout(self._r16(_FINAL_RANGE_CONFIG_TIMEOUT_MACROP_HI))
        if pre_range:
            final_mclks -= pre_mclks
        final_us = _timeout_mclks_to_us(final_mclks, final_vcsel)
        return msrc_us, pre_us, final_us, final_vcsel, pre_mclks

    def get_measurement_timing_budget(self):
        """Tempo gasto em cada medida, em microssegundos."""
        budget = 1910 + 960   # overhead de início + fim
        tcc, dss, msrc, pre_range, final_range = self._get_sequence_step_enables()
        msrc_us, pre_us, final_us, _, _ = self._get_sequence_step_timeouts(pre_range)
        if tcc:
            budget += msrc_us + 590
        if dss:
            budget += 2 * (msrc_us + 690)
        elif msrc:
            budget += msrc_us + 660
        if pre_range:
            budget += pre_us + 660
        if final_range:
            budget += final_us + 550
        self._budget_us = budget
        return budget

    def set_measurement_timing_budget(self, budget_us):
        """Define o tempo de cada medida (mín. 20000 µs).

        Mais tempo = medida mais estável e de maior alcance, porém mais lenta.
        Padrão do sensor: ~33000 µs (33 ms)."""
        if budget_us < 20000:
            raise ValueError("timing budget minimo: 20000 us")
        used = 1320 + 960     # overhead de início (diferente do get) + fim
        tcc, dss, msrc, pre_range, final_range = self._get_sequence_step_enables()
        msrc_us, pre_us, _, final_vcsel, pre_mclks = self._get_sequence_step_timeouts(pre_range)
        if tcc:
            used += msrc_us + 590
        if dss:
            used += 2 * (msrc_us + 690)
        elif msrc:
            used += msrc_us + 660
        if pre_range:
            used += pre_us + 660
        if final_range:
            used += 550
            # O tempo que sobra do orçamento vai todo para a etapa final.
            if used > budget_us:
                raise ValueError("timing budget pequeno demais")
            final_mclks = _timeout_us_to_mclks(budget_us - used, final_vcsel)
            if pre_range:
                final_mclks += pre_mclks
            self._w16(_FINAL_RANGE_CONFIG_TIMEOUT_MACROP_HI, _encode_timeout(final_mclks))
            self._budget_us = budget_us

    # ---------------------------------------------------------- medições
    def _restore_stop_variable(self):
        self._write_pairs(((0x80, 0x01), (0xFF, 0x01), (0x00, 0x00),
                           (0x91, self._stop_variable),
                           (0x00, 0x01), (0xFF, 0x00), (0x80, 0x00)))

    def start_continuous(self, period_ms=0):
        """Inicia o modo contínuo.

        period_ms = 0  -> "back-to-back": mede sem parar (uma medida por
                          timing budget).
        period_ms > 0  -> modo temporizado: uma medida a cada period_ms
                          (use um valor maior que o timing budget)."""
        self._restore_stop_variable()
        if period_ms:
            # O período é contado no oscilador interno, que tem um fator de
            # calibração de fábrica.
            osc = self._r16(_OSC_CALIBRATE_VAL)
            if osc != 0:
                period_ms *= osc
            self._w32(_SYSTEM_INTERMEASUREMENT_PERIOD, period_ms)
            self._w8(_SYSRANGE_START, 0x04)   # modo temporizado
        else:
            self._w8(_SYSRANGE_START, 0x02)   # modo back-to-back
        self._continuous = True

    def stop_continuous(self):
        """Para o modo contínuo (o laser deixa de disparar)."""
        self._write_pairs(((_SYSRANGE_START, 0x01), (0xFF, 0x01), (0x00, 0x00),
                           (0x91, 0x00), (0x00, 0x01), (0xFF, 0x00)))
        self._continuous = False

    def data_ready(self):
        """True se já existe uma medida nova. Custa só uma leitura I2C e
        NÃO espera: ideal para laços não bloqueantes."""
        return (self._r8(_RESULT_INTERRUPT_STATUS) & 0x07) != 0

    def read_range(self):
        """Devolve a distância em mm e libera o sensor para a próxima medida.

        Se ainda não houver medida pronta, espera até io_timeout_ms; em caso
        de timeout devolve 65535 e marca did_timeout = True.
        Valores >= 8190 significam "sem alvo / fora de alcance"."""
        self._start_timeout()
        while (self._r8(_RESULT_INTERRUPT_STATUS) & 0x07) == 0:
            if self._timeout_expired():
                self.did_timeout = True
                return 65535
        self.did_timeout = False
        # A distância fica 10 bytes depois de RESULT_RANGE_STATUS.
        mm = self._r16(_RESULT_RANGE_STATUS + 10)
        self._w8(_SYSTEM_INTERRUPT_CLEAR, 0x01)
        return mm

    def read_range_details(self):
        """Como read_range(), mas devolve também o DIAGNÓSTICO da medida:

            (mm, status, sinal_mcps, ambiente_mcps)

        status (código interno da ST, "DeviceRangeStatus"):
            11 = medida OK            4 = sem alvo / sinal fraco (MSRC)
             5 = relação sinal/ruído   6, 9 = falha de fase
             7 = sigma (incerteza) alta   8, 10 = alvo perto demais
        sinal_mcps: força do retorno do laser (milhões de fótons/s).
        ambiente_mcps: luz ambiente infravermelha (sol atrapalha!).

        Lê os 12 bytes de resultado de uma vez (registradores 0x14..0x1F),
        como faz a API da ST."""
        self._start_timeout()
        while (self._r8(_RESULT_INTERRUPT_STATUS) & 0x07) == 0:
            if self._timeout_expired():
                self.did_timeout = True
                return 65535, 0, 0.0, 0.0
        self.did_timeout = False
        b = self._i2c.readfrom_mem(self._addr, _RESULT_RANGE_STATUS, 12)
        self._w8(_SYSTEM_INTERRUPT_CLEAR, 0x01)
        status = (b[0] & 0x78) >> 3
        sinal = ((b[6] << 8) | b[7]) / 128      # ponto fixo 9.7
        ambiente = ((b[8] << 8) | b[9]) / 128
        mm = (b[10] << 8) | b[11]
        return mm, status, sinal, ambiente

    def read_single(self):
        """Uma medida avulsa (bloqueia ~timing budget). Fora do modo contínuo."""
        self._restore_stop_variable()
        self._w8(_SYSRANGE_START, 0x01)
        self._start_timeout()
        while self._r8(_SYSRANGE_START) & 0x01:
            if self._timeout_expired():
                self.did_timeout = True
                return 65535
        return self.read_range()

    @property
    def is_continuous(self):
        return self._continuous

    def set_address(self, new_address):
        """Muda o endereço I2C (útil com vários sensores no mesmo barramento).
        Volta a 0x29 ao desligar a energia."""
        self._w8(_I2C_SLAVE_DEVICE_ADDRESS, new_address & 0x7F)
        self._addr = new_address
