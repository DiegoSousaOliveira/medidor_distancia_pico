# =============================================================================
#  config.py — TODAS as configurações do Sensor de Ré ficam aqui.
#
#  Por quê? Assim ninguém precisa caçar "números mágicos" dentro do código:
#  para mudar um pino, um limite de zona ou o brilho, basta editar este arquivo.
#  (Confira a pinagem na documentação da SUA versão da BitDogLab.)
# =============================================================================

# ----------------------------------------------------------------------------
#  Pinos da BitDogLab
# ----------------------------------------------------------------------------
# OLED SSD1306 128x64 — barramento I2C1 (fixo na placa)
OLED_I2C_ID = 1
OLED_SDA = 14
OLED_SCL = 15
OLED_LARGURA = 128
OLED_ALTURA = 64
OLED_ENDERECO = 0x3C

# Conectores I2C externos onde o VL53L0X pode estar ligado.
# A BitDogLab tem dois: "I2C0" (GP0/GP1) e "I2C1" (GP2/GP3). O programa
# procura o sensor nos dois, na ordem abaixo, e usa o primeiro que responder.
#   (nome no conector, id do barramento do RP2040, SDA, SCL)
SENSOR_CONECTORES = (
    ("I2C0", 0, 0, 1),
    ("I2C1", 1, 2, 3),
)
SENSOR_ENDERECO = 0x29
# ATENÇÃO: o conector "I2C1" usa o MESMO periférico I2C1 do OLED (GP14/GP15).
# Um periférico só pode estar ligado a um par de pinos por vez; se criássemos
# I2C(1) duas vezes, o OLED pararia de funcionar. Por isso, quando o sensor
# está nesse conector, o programa usa SoftI2C (I2C feito por software), que
# funciona em quaisquer pinos. Para o VL53L0X, que troca poucos bytes por
# medida, a diferença de velocidade não importa.

# Frequência dos barramentos I2C. 400 kHz ("fast mode") é suportado pelo
# OLED e pelo VL53L0X. Se usar fios longos e der erro, tente 100_000.
I2C_FREQ = 400_000

# Matriz de LEDs 5x5 WS2812 (NeoPixel)
MATRIZ_PINO = 7

# LED RGB (cada cor é um pino; acendemos com PWM para dosar o brilho)
LED_R = 13
LED_G = 11
LED_B = 12

# Botões (ligam o pino ao GND quando apertados -> usamos pull-up interno)
BOTAO_A = 5
BOTAO_B = 6

# Buzzer (passivo: precisa de PWM para tocar)
BUZZER = 21

# Joystick (analógico)
JOY_Y = 26      # ADC0 — eixo vertical
JOY_X = 27      # ADC1 — eixo horizontal
JOY_BOTAO = 22

# ----------------------------------------------------------------------------
#  Sensor VL53L0X
# ----------------------------------------------------------------------------
# Tempo de cada medida em microssegundos. 33 ms é o padrão da ST: bom meio
# termo entre precisão e velocidade.
SENSOR_TIMING_BUDGET_US = 33_000

# Uma medida a cada 50 ms = 20 leituras por segundo. Precisa ser maior que o
# timing budget (33 ms), senão o sensor não tem tempo de terminar a medida.
SENSOR_PERIODO_MS = 50

# Sensibilidade: força mínima do retorno do laser (em MCPS = milhões de
# fótons por segundo) para o sensor aceitar uma medida. O padrão da ST é 0,25.
# Medimos na placa: uma mão a 40 cm devolve ~0,19 a 0,26 MCPS, então com 0,25
# metade das leituras era descartada. 0,10 é o valor do modo "longo alcance"
# da Pololu. Mais baixo = alcança mais longe, porém com mais ruído.
SENSOR_LIMITE_SINAL_MCPS = 0.10

# Correção de distância (em mm), somada a toda leitura válida. Use se, ao
# comparar o Modo Trena com uma régua, o sensor errar SEMPRE para o mesmo
# lado (veja "Como calibrar" no README). Ex.: mede 8 mm a mais -> use -8.
SENSOR_CORRECAO_MM = 0

# O VL53L0X devolve 8190/8191 quando não enxerga nada. Acima de ~2 m a
# leitura também não é confiável. Tudo isso conta como "fora de alcance".
SENSOR_FORA_DE_ALCANCE_MM = 8190
SENSOR_ALCANCE_MAX_MM = 2000

# ----------------------------------------------------------------------------
#  Filtro
# ----------------------------------------------------------------------------
# Quantas leituras entram na mediana. 5 leituras a 20/s = 250 ms de memória:
# remove valores isolados errados sem deixar a resposta lenta. Use número
# ímpar (assim sempre existe um "valor do meio").
FILTRO_TAMANHO = 5

# Quanto tempo SEM nenhuma leitura válida até considerarmos "sem alvo".
# O sensor às vezes perde um alvo pequeno ou inclinado (uma mão a 40 cm) por
# algumas leituras; 400 ms (~8 leituras) evita que o aviso se cale nesses
# buracos, e ainda responde rápido quando o objeto sai de verdade.
FILTRO_TEMPO_SEM_ALVO_MS = 400

# ----------------------------------------------------------------------------
#  Zonas de distância (em CENTÍMETROS — veja "Como calibrar" no README)
# ----------------------------------------------------------------------------
#   LIVRE   : acima de ZONA_ATENCAO_CM            -> verde, sem som
#   ATENÇÃO : de ZONA_PERIGO_CM até ZONA_ATENCAO_CM -> amarelo, bipe lento
#   PERIGO  : de ZONA_PARE_CM até ZONA_PERIGO_CM    -> laranja, bipe rápido
#   PARE    : abaixo de ZONA_PARE_CM               -> vermelho, som contínuo
ZONA_ATENCAO_CM = 100
ZONA_PERIGO_CM = 50
ZONA_PARE_CM = 20

# Faixa em que o joystick pode ajustar o limite da zona PARE (etapa 6).
ZONA_PARE_MIN_CM = 10
ZONA_PARE_MAX_CM = 40

# Folga para SAIR de uma zona ao se afastar (evita trocar de zona sem parar
# quando o objeto está bem em cima de um limite). 2 cm é maior que o ruído
# típico do sensor depois da mediana.
ZONA_HISTERESE_CM = 2

# ----------------------------------------------------------------------------
#  Som (buzzer)
# ----------------------------------------------------------------------------
# Tom do bipe em Hz. Perto de 2 kHz o buzzer da BitDogLab soa bem e é fácil
# de ouvir num pátio.
SOM_FREQ_HZ = 2000

# Volume = duty do PWM em %. 50 % é o máximo (e é ALTO). Valores baixos
# deixam o som moderado, sem incomodar ninguém na demonstração.
SOM_VOLUME_PCT = 5

# Duração de cada bipe.
SOM_BIPE_MS = 80

# Tempo entre o início de um bipe e o do próximo. Varia em linha reta com a
# proximidade: MAX no limite da zona ATENÇÃO (bem devagar) até MIN no limite
# da zona PARE (bem rápido). Na zona PARE o som fica contínuo.
SOM_INTERVALO_MAX_MS = 1000
SOM_INTERVALO_MIN_MS = 150

# ----------------------------------------------------------------------------
#  Luzes (matriz 5x5 e LED RGB) — as CORES ficam em cores.py
# ----------------------------------------------------------------------------
# Brilho da matriz, como fração do LED todo aceso em branco (R+G+B = 765).
# TODAS as cores são ajustadas para exatamente este brilho (nunca acima),
# então as quatro zonas aparecem com a mesma intensidade.
# 0.10 = 10 %: bem visível e sem ofuscar (25 LEDs em branco total puxariam
# ~1,5 A; com 10 % fica em torno de 0,15 A).
MATRIZ_BRILHO = 0.10

# A matriz é redesenhada no máximo a cada MATRIZ_QUADRO_MS (33 quadros/s):
# suficiente para o olho ver tudo suave sem gastar tempo do laço à toa.
MATRIZ_QUADRO_MS = 30

# Na zona PARE a matriz pisca: fica MATRIZ_PISCA_MS acesa e o mesmo tempo
# apagada (200 ms = 2,5 piscadas por segundo: chama atenção sem agredir).
MATRIZ_PISCA_MS = 200

# Tempo da troca suave de cor entre zonas (matriz e LED RGB).
COR_TRANSICAO_MS = 150

# PWM do LED RGB: 1 kHz é rápido demais para o olho perceber o pisca-pisca.
LED_PWM_FREQ = 1000

# Ganho de cada canal (R, G, B) do LED RGB, para a cor dele combinar com a
# da matriz. 1.0 = usa o valor de cores.py sem mudança.
LED_GANHO = (1.0, 1.0, 1.0)

# ----------------------------------------------------------------------------
#  Display OLED
# ----------------------------------------------------------------------------
# Intervalo mínimo entre quadros (100 ms = até 10 quadros por segundo). Cada
# quadro é desenhado na memória e enviado aos poucos, uma página por volta
# do laço, para não travar o programa (veja lib/display.py).
DISPLAY_QUADRO_MS = 100

# Distância em que o carrinho da tela aparece no começo da cena. Abaixo
# dela, ele vai chegando perto da parede.
DISPLAY_CENA_CM = ZONA_ATENCAO_CM

# Estabilidade do NÚMERO exibido (só da tela; zonas e som não mudam):
#   SUAVIZACAO: 0..1 — quanto cada leitura nova puxa a média (menor = mais liso)
#   HISTERESE : o número só muda se a média se afastar pelo menos isto (cm)
# Testado com o ruído medido no sensor: parado, o número muda menos de 1 vez
# a cada 2 s; andando a 20 cm/s, a tela fica ~4 cm "atrás" (só a tela!).
DISPLAY_SUAVIZACAO = 0.20
DISPLAY_HISTERESE_CM = 1.2

# No Modo Trena o número tem resolução de 1 mm, então a suavização é mais
# forte (testado com o ruído real: parado perto, o valor não muda; a 60 cm
# varia ~1 cm; uma mudança de 20 cm assenta em ~2 s). Para ler um valor
# fixo, use o "congelar" (botão do joystick).
TRENA_SUAVIZACAO = 0.10
TRENA_HISTERESE_MM = 4

# Imprimir cada leitura (e as estatísticas "leituras/s") no terminal. Fica
# DESLIGADO: imprimir 20 linhas por segundo custa tempo do laço. Para estudar
# ou depurar, troque para True. (As mensagens de inicialização sempre saem.)
TERMINAL_DETALHADO = False

# ----------------------------------------------------------------------------
#  Painel no computador por Bluetooth (BLE) — veja pc/painel.html
# ----------------------------------------------------------------------------
BLE_ATIVO = True
# A placa aparece como "SensorDeRe-XXXX" (XXXX = final do endereço MAC).
BLE_NOME = "SensorDeRe"
# Intervalo mínimo entre pacotes. Tem que ser MENOR que o intervalo entre
# leituras do sensor (~48 ms): com 50 ms, metade das leituras era descartada
# (medimos 5 pacotes/s). Com 40 ms sai um pacote por leitura nova — até ~20
# por segundo, cada um com só 11 bytes.
BLE_INTERVALO_MIN_MS = 40
# Mesmo sem mudança, reenvia a cada 1 s para o computador saber que a
# conexão está viva.
BLE_REENVIO_MS = 1000

# ----------------------------------------------------------------------------
#  Botões e joystick
# ----------------------------------------------------------------------------
# O estado do botão precisa ficar estável por este tempo para valer
# (filtra o "repique" mecânico do contato).
BOTAO_ANTIRREPIQUE_MS = 30

# Joystick (eixo vertical) ajusta o limite da zona PARE no Modo Ré:
#   - zona morta: fração do curso perto do centro que é ignorada;
#   - segurando, repete o passo de 1 cm: devagar (pouco empurrado) até
#     rápido (empurrado até o fim);
#   - INVERTIDO: troque para True se "para cima" estiver diminuindo o valor.
JOY_ZONA_MORTA = 0.30
JOY_REPETICAO_LENTA_MS = 350
JOY_REPETICAO_RAPIDA_MS = 90
JOY_Y_INVERTIDO = False
AJUSTE_PASSO_CM = 1
# Quanto tempo a janela "LIMITE PARE" fica na tela depois do último ajuste.
AJUSTE_MOSTRAR_MS = 1500

# "Clique" de confirmação dos botões (só toca com o som ligado).
CLIQUE_MS = 25
CLIQUE_FREQ_HZ = 2600
