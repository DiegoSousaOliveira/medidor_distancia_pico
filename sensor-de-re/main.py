# =============================================================================
#  Sensor de Ré — BitDogLab + VL53L0X
#  ETAPA 6: botões, joystick e modos (Modo Ré / Modo Trena).
#
#  Um sensor de estacionamento: mede a distância com laser e avisa com som,
#  luzes e display, como o sensor de ré de um carro.
#
#  CONTROLES
#    Botão A ............ liga/desliga o som
#    Botão B ............ troca entre Modo Ré e Modo Trena
#    Joystick ↕ (Ré) .... ajusta o limite da zona PARE (10 a 40 cm)
#    Botão do joystick .. (Trena) congela/descongela a medida
#
#  Como o programa funciona (laço principal NÃO BLOQUEANTE):
#
#    ┌─> 1. sensor tem medida nova? -> filtro, zona, suavização
#    │   2. botões e joystick (só olham os pinos, não esperam)
#    │   3. se algo mudou: decide o que mostrar/tocar em cada saída
#    │   4. som / matriz / LED / tela / Bluetooth fazem um pedacinho
#    │      do trabalho cada um e retornam NA HORA
#    └───────┘
#
#  Detalhes de cada parte estão nos módulos de lib/ e em config.py.
# =============================================================================

import os
import sys
import time
from machine import I2C, SoftI2C, Pin

import config

# Os drivers ficam em lib/ NA PLACA. Se a importação falhar, mostramos as
# causas mais comuns em vez de só um erro seco.
try:
    from ssd1306 import SSD1306_I2C
    from vl53l0x import VL53L0X
    from filtros import (FiltroDistancia, SuavizadorExibicao, Zonas,
                         NOMES_ZONAS, LIVRE, PARE)
    from som import Som
    from matriz import Matriz, LedRGB
    from display import Painel
    from controles import Botao, EixoJoystick
    from cores import COR_DA_ZONA
    if config.BLE_ATIVO:
        from ble_painel import PainelBLE
except ImportError as erro:
    print("\nERRO:", erro)
    print("Causas provaveis:")
    print(" 1) a pasta lib/ nao foi enviada -> MicroPico > 'Upload Project to Board';")
    print(" 2) existe uma copia ANTIGA do modulo na raiz da placa (ela tem")
    print("    prioridade sobre /lib) -> apague a copia da raiz.")
    print("Raiz da placa:", os.listdir("/"))
    print("/lib        :", os.listdir("/lib") if "lib" in os.listdir("/") else "(nao existe)")
    raise

MODO_RE = 0
MODO_TRENA = 1

INTERVALO_NOVO_SCAN_MS = 2000    # espera entre tentativas de achar o sensor
INTERVALO_ESTATISTICA_MS = 1000  # de quanto em quanto tempo mostra "leituras/s"
LARGURA_BARRA_TERMINAL = 20      # caracteres da barrinha de proximidade


# =============================================================================
#  Inicialização
# =============================================================================
def mostrar_placa():
    """Imprime a placa e o firmware, para conferir se o .uf2 é o certo."""
    maquina = os.uname().machine
    print("Placa   :", maquina)
    print("Firmware: MicroPython", sys.version)
    if "RP2350" in maquina:
        print("-> Chip RP2350: e uma Pico 2 / Pico 2 W.")
    elif "RP2040" in maquina:
        print("-> Chip RP2040: e uma Pico / Pico W.")


def listar(nome, enderecos):
    """Imprime os endereços achados num barramento I2C em hexadecimal."""
    texto = ", ".join("0x%02X" % e for e in enderecos) or "nenhum"
    print("%s: %s" % (nome, texto))


def iniciar_painel():
    """Liga o OLED e cria o painel. Devolve None se o OLED não responder
    (o sensor de ré continua funcionando com som e luzes)."""
    i2c_oled = I2C(config.OLED_I2C_ID, sda=Pin(config.OLED_SDA),
                   scl=Pin(config.OLED_SCL), freq=config.I2C_FREQ)
    achados = i2c_oled.scan()
    listar("I2C%d (OLED)  " % config.OLED_I2C_ID, achados)
    if config.OLED_ENDERECO not in achados:
        print("Aviso: OLED nao encontrado em 0x%02X" % config.OLED_ENDERECO)
        return None
    oled = SSD1306_I2C(config.OLED_LARGURA, config.OLED_ALTURA, i2c_oled,
                       addr=config.OLED_ENDERECO)
    return Painel(oled, config.DISPLAY_QUADRO_MS, config.DISPLAY_CENA_CM)


def abrir_barramento(id_barramento, sda, scl):
    """Cria o barramento I2C de um conector externo.

    Se o conector usa o mesmo periférico do OLED, usamos SoftI2C para não
    "roubar" os pinos do OLED (veja a explicação em config.py)."""
    if id_barramento == config.OLED_I2C_ID:
        return SoftI2C(sda=Pin(sda), scl=Pin(scl), freq=config.I2C_FREQ)
    return I2C(id_barramento, sda=Pin(sda), scl=Pin(scl), freq=config.I2C_FREQ)


def esperar_sensor(painel):
    """Procura o VL53L0X em todos os conectores (i2c.scan()) até ele
    aparecer. Devolve (nome_do_conector, barramento_i2c)."""
    while True:
        for nome, id_barramento, sda, scl in config.SENSOR_CONECTORES:
            i2c = abrir_barramento(id_barramento, sda, scl)
            achados = i2c.scan()
            listar("Conector %s (GP%d/GP%d)" % (nome, sda, scl), achados)
            if config.SENSOR_ENDERECO in achados:
                print("-> VL53L0X encontrado no conector", nome)
                return nome, i2c
        print("Sensor VL53L0X (0x%02X) NAO encontrado em nenhum conector. "
              "Confira o cabo (SDA, SCL, 3V3 e GND)." % config.SENSOR_ENDERECO)
        if painel:
            painel.mensagem("SENSOR AUSENTE", ["Ligue o VL53L0X", "no conector",
                                               "I2C0 ou I2C1", "(tentando...)"])
        time.sleep_ms(INTERVALO_NOVO_SCAN_MS)


def iniciar_sensor(i2c):
    sensor = VL53L0X(i2c, address=config.SENSOR_ENDERECO)
    sensor.set_signal_rate_limit(config.SENSOR_LIMITE_SINAL_MCPS)
    sensor.set_measurement_timing_budget(config.SENSOR_TIMING_BUDGET_US)
    sensor.start_continuous(config.SENSOR_PERIODO_MS)
    return sensor


# =============================================================================
#  Funções do laço
# =============================================================================
def leitura_valida(mm):
    """True se a leitura bruta do sensor é uma distância de verdade."""
    return mm < config.SENSOR_FORA_DE_ALCANCE_MM and mm <= config.SENSOR_ALCANCE_MAX_MM


def barra_texto(fracao, largura):
    """Barrinha tipo [######------] para ver a proximidade no terminal."""
    cheios = int(fracao * largura + 0.5)
    return "[" + "#" * cheios + "-" * (largura - cheios) + "]"


def mostrar_leitura(bruto, distancia, zona, proximidade, som):
    texto_bruto = "%4d" % bruto if leitura_valida(bruto) else "----"
    texto_filtro = "sem alvo" if distancia is None else "%5.1f cm" % (distancia / 10)
    print("bruto %s mm | filtrado %-8s | %-7s | %s %3d%% | %s" % (
        texto_bruto, texto_filtro, NOMES_ZONAS[zona],
        barra_texto(proximidade, LARGURA_BARRA_TERMINAL), int(proximidade * 100),
        som.descricao()))


# =============================================================================
#  Programa principal
# =============================================================================
def principal():
    print()
    print("=== Sensor de Re - Etapa 6: botoes, joystick e modos ===")
    mostrar_placa()

    painel = iniciar_painel()
    if painel:
        painel.abertura()                 # animação de ~2 s (antes do laço)

    ble = None
    if config.BLE_ATIVO:
        ble = PainelBLE(config.BLE_NOME, config.BLE_INTERVALO_MIN_MS,
                        config.BLE_REENVIO_MS)
        print("Bluetooth: anunciando como", ble.nome)

    conector, i2c_sensor = esperar_sensor(painel)
    print("Iniciando VL53L0X (calibracao leva menos de 1 s)...")
    sensor = iniciar_sensor(i2c_sensor)
    print("Controles: A = som | B = Re/Trena | joystick = limite PARE / congelar")

    # --- processamento da distância
    filtro = FiltroDistancia(config.FILTRO_TAMANHO, config.FILTRO_TEMPO_SEM_ALVO_MS)
    zonas = Zonas(limite_pare_mm=config.ZONA_PARE_CM * 10,
                  limite_perigo_mm=config.ZONA_PERIGO_CM * 10,
                  limite_atencao_mm=config.ZONA_ATENCAO_CM * 10,
                  histerese_mm=config.ZONA_HISTERESE_CM * 10)
    numero_re = SuavizadorExibicao(config.DISPLAY_SUAVIZACAO,
                                   config.DISPLAY_HISTERESE_CM * 10, 10)
    numero_trena = SuavizadorExibicao(config.TRENA_SUAVIZACAO,
                                      config.TRENA_HISTERESE_MM, 1)
    # --- saídas
    som = Som(config.BUZZER, config.SOM_FREQ_HZ, config.SOM_VOLUME_PCT,
              config.SOM_BIPE_MS, config.SOM_INTERVALO_MAX_MS,
              config.SOM_INTERVALO_MIN_MS)
    matriz = Matriz(config.MATRIZ_PINO, config.MATRIZ_BRILHO,
                    config.COR_TRANSICAO_MS, config.MATRIZ_QUADRO_MS,
                    config.MATRIZ_PISCA_MS)
    led = LedRGB(config.LED_R, config.LED_G, config.LED_B, config.LED_PWM_FREQ,
                 config.LED_GANHO, config.COR_TRANSICAO_MS)
    # --- entradas
    botao_a = Botao(config.BOTAO_A, config.BOTAO_ANTIRREPIQUE_MS)
    botao_b = Botao(config.BOTAO_B, config.BOTAO_ANTIRREPIQUE_MS)
    botao_joy = Botao(config.JOY_BOTAO, config.BOTAO_ANTIRREPIQUE_MS)
    eixo_y = EixoJoystick(config.JOY_Y, config.JOY_ZONA_MORTA,
                          config.JOY_REPETICAO_LENTA_MS,
                          config.JOY_REPETICAO_RAPIDA_MS, config.JOY_Y_INVERTIDO)

    # --- estado do programa
    modo = MODO_RE
    congelado = False
    mm_congelado = None
    ajuste_ate = None          # até quando mostrar a janela "LIMITE PARE"
    distancia = None
    zona = LIVRE
    proximidade = 0.0

    contagem = 0
    inicio_janela = time.ticks_ms()
    # Para PROVAR que o laço não trava: guardamos a volta mais demorada de
    # cada segundo (só aparece com config.TERMINAL_DETALHADO = True).
    volta_anterior = time.ticks_ms()
    volta_max_ms = 0
    try:
        while True:
            agora = time.ticks_ms()
            mudou = False

            # ---------- 1) Sensor (data_ready() não espera) ----------
            if sensor.data_ready():
                bruto = sensor.read_range()
                agora = time.ticks_ms()
                contagem += 1
                valida = None
                if leitura_valida(bruto):
                    valida = max(0, bruto + config.SENSOR_CORRECAO_MM)
                distancia = filtro.adicionar(valida, agora)
                zona = zonas.atualizar(distancia)
                proximidade = zonas.proximidade(distancia)
                numero_re.atualizar(distancia)
                numero_trena.atualizar(distancia)
                mudou = True
                if config.TERMINAL_DETALHADO:
                    mostrar_leitura(bruto, distancia, zona, proximidade, som)

            # ---------- 2) Botões e joystick ----------
            if botao_a.apertou(agora):
                som.alternar_mudo()
                som.bipe_avulso(config.CLIQUE_MS, config.CLIQUE_FREQ_HZ, agora)
                mudou = True

            if botao_b.apertou(agora):
                modo = MODO_TRENA if modo == MODO_RE else MODO_RE
                congelado = False
                ajuste_ate = None
                som.bipe_avulso(config.CLIQUE_MS, config.CLIQUE_FREQ_HZ, agora)
                print("Modo:", "TRENA" if modo == MODO_TRENA else "RE")
                mudou = True

            if botao_joy.apertou(agora) and modo == MODO_TRENA:
                congelado = not congelado
                mm_congelado = numero_trena.valor_mm
                # Tom mais agudo ao congelar, mais grave ao soltar.
                som.bipe_avulso(config.CLIQUE_MS,
                                config.CLIQUE_FREQ_HZ + (400 if congelado else -400), agora)
                mudou = True

            if modo == MODO_RE:
                passo = eixo_y.passo(agora)
                if passo:
                    limite = zonas.limite_pare_mm // 10 + passo * config.AJUSTE_PASSO_CM
                    limite = max(config.ZONA_PARE_MIN_CM, min(config.ZONA_PARE_MAX_CM, limite))
                    zonas.limite_pare_mm = limite * 10
                    zona = zonas.atualizar(distancia)
                    proximidade = zonas.proximidade(distancia)
                    ajuste_ate = time.ticks_add(agora, config.AJUSTE_MOSTRAR_MS)
                    mudou = True

            ajustando = ajuste_ate is not None and time.ticks_diff(ajuste_ate, agora) > 0
            if ajuste_ate is not None and not ajustando:
                ajuste_ate = None              # a janela some: redesenha a tela
                mudou = True

            # ---------- 3) Decide o que cada saída mostra/toca ----------
            if mudou:
                cor = COR_DA_ZONA[zona]
                if modo == MODO_RE:
                    som.definir(zona, proximidade)
                    matriz.definir(cor, proximidade, zona == PARE, agora)
                else:
                    som.definir(LIVRE, 0.0)    # trena não apita
                    matriz.definir(cor, proximidade, False, agora)
                led.definir(cor, agora)

                cm_re = None if numero_re.valor_mm is None else numero_re.valor_mm // 10
                mm_trena = mm_congelado if congelado else numero_trena.valor_mm
                limite_cm = zonas.limite_pare_mm // 10
                conectado = ble is not None and ble.conectado
                if painel:
                    if modo == MODO_RE:
                        painel.tela_re(cm_re, zona, proximidade, som.mudo, conectado,
                                       limite_cm if ajustando else None)
                    else:
                        painel.tela_trena(mm_trena, congelado, conectado)
                if conectado:
                    ble.publicar(agora, modo, zona, cm_re, proximidade, som.mudo,
                                 congelado, limite_cm,
                                 mm_trena if modo == MODO_TRENA else distancia,
                                 ajustando)

            # ---------- 4) Cada saída faz um pedacinho do trabalho ----------
            agora = time.ticks_ms()
            som.atualizar(agora)
            matriz.atualizar(agora)
            led.atualizar(agora)
            if painel:
                painel.atualizar(agora)

            volta_max_ms = max(volta_max_ms, time.ticks_diff(agora, volta_anterior))
            volta_anterior = agora
            if time.ticks_diff(agora, inicio_janela) >= INTERVALO_ESTATISTICA_MS:
                if config.TERMINAL_DETALHADO:
                    print("--- %d leituras/s | volta mais lenta do laco: %d ms ---"
                          % (contagem, volta_max_ms))
                contagem = 0
                volta_max_ms = 0
                inicio_janela = agora

            time.sleep_ms(1)   # pausa curtinha só para não ocupar 100% da CPU
    finally:
        # Sempre deixa tudo desligado ao parar (Ctrl+C ou erro).
        sensor.stop_continuous()   # laser desligado
        som.desligar()             # senão o buzzer continua apitando!
        matriz.apagar()            # e os LEDs ficariam acesos
        led.desligar()
        if ble:
            ble.desligar()
        if painel:
            painel.mensagem("SENSOR DE RÉ", ["", "Parado."])
        print("Sensor parado.")


principal()
