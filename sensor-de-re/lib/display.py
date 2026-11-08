# =============================================================================
#  display.py — Telas do OLED 128x64 com visual de painel de carro.
#
#      ┌──────────────────────────────┐
#      │[R] MODO RÉ              [som]│  barra superior (ícones 16x16)
#      │──────────────────────────────│
#      │ 88 cm          carro→ |parede│  distância grande + cena
#      │            PERIGO            │  nome da zona
#      │ ■■■■■■□□□□                   │  barra de proximidade segmentada
#      └──────────────────────────────┘
#
#  ATUALIZAÇÃO NÃO BLOQUEANTE
#  Mandar a tela inteira (1024 bytes) pelo I2C a 400 kHz leva ~26 ms — medido
#  na placa. Se o laço parasse 26 ms, os bipes atrasariam. Então:
#    1) desenhamos a tela no buffer da memória (rápido);
#    2) enviamos UMA "página" (8 linhas de pixels = 128 bytes, ~3 ms) a cada
#       volta do laço. Em 8 voltas a tela inteira foi enviada.
#  A memória do SSD1306 avança sozinha de uma página para a próxima, então
#  basta dizer "comece do início" uma vez por quadro.
# =============================================================================

import time
import framebuf

from filtros import PARE

LARGURA = 128
ALTURA = 64
PAGINAS = ALTURA // 8
MARGEM = 4                      # margem lateral usada em toda a tela

# --- Layout (coordenadas em pixels) -----------------------------------------
Y_LINHA_TOPO = 18               # linha que separa a barra superior
X_ICONE_MODO = MARGEM
X_ICONE_SOM = LARGURA - MARGEM - 16
Y_DIGITOS = 21                  # dígitos grandes
DIG_LARGURA = 14
DIG_ALTURA = 22
DIG_ESPESSURA = 3
DIG_ESPACO = 3
CENA_X = 74                     # cena carro + parede
CENA_FIM = LARGURA - MARGEM     # x final da cena (parede encostada aqui)
Y_CHAO = Y_DIGITOS + DIG_ALTURA - 1
PAREDE_LARGURA = 6
Y_ZONA = 48                     # nome da zona (folga p/ acentos)
Y_BARRA = 58                    # barra segmentada
BARRA_ALTURA = 6
SEGMENTOS = 10
SEG_LARGURA = 10
SEG_ESPACO = 2

ABERTURA_QUADROS = 40           # quadros da animação de abertura

# Modo Trena: "123,4 cm" centralizado, valor em mm embaixo e uma régua
TRENA_X0 = (LARGURA - (3 * (DIG_LARGURA + DIG_ESPACO) + 6 + DIG_LARGURA + 3 + 16)) // 2
Y_MM = 46                       # linha "1234 mm"
REGUA_X0 = MARGEM               # régua de 0 a TRENA_MAX_MM
REGUA_LARGURA = LARGURA - 2 * MARGEM
Y_REGUA = 63                    # linha de base da régua
TRENA_MAX_MM = 2000

# Janela de ajuste do limite PARE (aparece por cima da tela do Modo Ré)
JANELA_X, JANELA_Y, JANELA_L, JANELA_A = 14, 20, 100, 38

# Comandos do SSD1306 usados no envio por páginas
_SET_COL_ADDR = 0x21
_SET_PAGE_ADDR = 0x22


# =============================================================================
#  Ícones 16x16 — desenhados em texto para ficar fácil de editar:
#  '#' = pixel aceso, '.' = apagado. Cada linha tem 16 caracteres.
# =============================================================================
_ARTE_MODO_RE = (          # "R" da alavanca de câmbio, numa moldura
    ".##############.",
    "#..............#",
    "#...######.....#",
    "#...##...##....#",
    "#...##....##...#",
    "#...##....##...#",
    "#...##...##....#",
    "#...######.....#",
    "#...##.##......#",
    "#...##..##.....#",
    "#...##...##....#",
    "#...##....##...#",
    "#...##.....##..#",
    "#...##......##.#",
    "#..............#",
    ".##############.",
)
_ARTE_SOM_LIGADO = (       # alto-falante com ondas
    "................",
    "......#.........",
    ".....##.....#...",
    "....###..#...#..",
    ".######...#...#.",
    ".######...#...#.",
    ".######....#..#.",
    ".######....#..#.",
    ".######....#..#.",
    ".######...#...#.",
    ".######...#...#.",
    "....###..#...#..",
    ".....##.....#...",
    "......#.........",
    "................",
    "................",
)
_ARTE_SOM_MUDO = (         # alto-falante com um X
    "................",
    "......#.........",
    ".....##.........",
    "....###.........",
    ".######.........",
    ".######..#...#..",
    ".######...#.#...",
    ".######....#....",
    ".######...#.#...",
    ".######..#...#..",
    ".######.........",
    "....###.........",
    ".....##.........",
    "......#.........",
    "................",
    "................",
)
_ARTE_BLE = (              # símbolo do Bluetooth (computador conectado)
    "................",
    ".......#........",
    ".......##.......",
    ".......#.#......",
    "...#...#..#.....",
    "....#..#.#......",
    ".....#.##.......",
    "......##........",
    ".....#.##.......",
    "....#..#.#......",
    "...#...#..#.....",
    ".......#.#......",
    ".......##.......",
    ".......#........",
    "................",
    "................",
)
_ARTE_MODO_TRENA = (       # régua (Modo Trena)
    "................",
    "................",
    "................",
    "################",
    "#..............#",
    "#.#.#.#.#.#.#..#",
    "#.#.#.#.#.#.#..#",
    "#.#...#...#....#",
    "#.#...#...#....#",
    "#..............#",
    "#..............#",
    "################",
    "................",
    "................",
    "................",
    "................",
)
_ARTE_CONGELADO = (        # floco de neve: medida "congelada"
    "................",
    ".......#........",
    "......###.......",
    "...#...#...#....",
    "....#..#..#.....",
    ".....#.#.#......",
    "..#...###...#...",
    ".#############..",
    "..#...###...#...",
    ".....#.#.#......",
    "....#..#..#.....",
    "...#...#...#....",
    "......###.......",
    ".......#........",
    "................",
    "................",
)
_ARTE_CARRO = (            # carro visto de lado, de ré para a direita
    "................",
    "................",
    "................",
    "................",
    "................",
    "....#######.....",
    "...#...#...#....",
    "..#....#....#...",
    ".##############.",
    "################",
    "################",
    "################",
    "..####....####..",
    "..####....####..",
    "...##......##...",
    "................",
)


def _icone(arte):
    """Converte a arte em texto num FrameBuffer 16x16 (formato MONO_HLSB:
    cada linha = 2 bytes, bit mais significativo = pixel da esquerda)."""
    dados = bytearray(32)
    for y, linha in enumerate(arte):
        for x, ch in enumerate(linha):
            if ch == "#":
                dados[y * 2 + x // 8] |= 0x80 >> (x % 8)
    return framebuf.FrameBuffer(dados, 16, 16, framebuf.MONO_HLSB)


ICONE_MODO_RE = _icone(_ARTE_MODO_RE)
ICONE_SOM_LIGADO = _icone(_ARTE_SOM_LIGADO)
ICONE_SOM_MUDO = _icone(_ARTE_SOM_MUDO)
ICONE_CARRO = _icone(_ARTE_CARRO)
ICONE_BLE = _icone(_ARTE_BLE)
ICONE_MODO_TRENA = _icone(_ARTE_MODO_TRENA)
ICONE_CONGELADO = _icone(_ARTE_CONGELADO)
X_ICONE_BLE = X_ICONE_SOM - 18


# =============================================================================
#  Texto com acentos
#  A fonte 8x8 embutida no MicroPython só tem caracteres ASCII. Para escrever
#  "RÉ" e "ATENÇÃO", desenhamos a letra base e acrescentamos o acento à mão.
# =============================================================================
_BASE = {"É": "E", "Ê": "E", "Á": "A", "Ã": "A", "Ó": "O", "Õ": "O", "Í": "I",
         "Ú": "U", "Ç": "C"}
_AGUDO = ((3, -2), (4, -3))                       # pixels relativos à letra
_CIRCUNFLEXO = ((2, -2), (3, -3), (4, -2))
_TIL = ((1, -2), (2, -3), (3, -2), (4, -3))
_CEDILHA = ((3, 7), (4, 8))
_ACENTOS = {"É": _AGUDO, "Á": _AGUDO, "Ó": _AGUDO, "Í": _AGUDO, "Ú": _AGUDO,
            "Ê": _CIRCUNFLEXO, "Ã": _TIL, "Õ": _TIL, "Ç": _CEDILHA}


def texto(fb, s, x, y, cor=1):
    """Como fb.text(), mas aceita É Ê Á Ã Ó Õ Í Ú Ç (só maiúsculas)."""
    for ch in s:
        fb.text(_BASE.get(ch, ch), x, y, cor)
        for dx, dy in _ACENTOS.get(ch, ()):
            fb.pixel(x + dx, y + dy, cor)
        x += 8


def texto_centralizado(fb, s, y, cor=1, x0=0, largura=LARGURA):
    texto(fb, s, x0 + (largura - 8 * len(s)) // 2, y, cor)


def _texto_ampliado(s, escala):
    """Desenha o texto ampliado (cada pixel vira um quadrado escala x escala)
    num FrameBuffer próprio. Usado só na abertura, então pode ser lento."""
    pequeno_alt = 12                     # 3 linhas extras para acentos
    pequeno = framebuf.FrameBuffer(bytearray(len(s) * 8 * 2), len(s) * 8,
                                   pequeno_alt, framebuf.MONO_HLSB)
    texto(pequeno, s, 0, 3)
    larg, alt = len(s) * 8 * escala, pequeno_alt * escala
    grande = framebuf.FrameBuffer(bytearray(((larg + 7) // 8) * alt), larg, alt,
                                  framebuf.MONO_HLSB)
    for py in range(pequeno_alt):
        for px in range(len(s) * 8):
            if pequeno.pixel(px, py):
                grande.fill_rect(px * escala, py * escala, escala, escala, 1)
    return grande, larg, alt


# =============================================================================
#  Dígitos grandes estilo "display de 7 segmentos"
#
#        aaaa          Cada dígito é feito de até 7 retângulos (segmentos).
#       f    b         O '8' acende todos; o '1' só b e c, e assim por diante.
#       f    b
#        gggg
#       e    c
#       e    c
#        dddd
# =============================================================================
_SEGMENTOS_DO = {
    "0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc",
    "5": "afgcd", "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abcdfg",
    "-": "g", " ": "",
}


def digito_grande(fb, ch, x, y, cor=1):
    w, h, t = DIG_LARGURA, DIG_ALTURA, DIG_ESPESSURA
    meio = (h - t) // 2
    segs = _SEGMENTOS_DO.get(ch, "")
    if "a" in segs:
        fb.fill_rect(x, y, w, t, cor)
    if "d" in segs:
        fb.fill_rect(x, y + h - t, w, t, cor)
    if "g" in segs:
        fb.fill_rect(x, y + meio, w, t, cor)
    if "f" in segs:
        fb.fill_rect(x, y, t, meio + t, cor)
    if "b" in segs:
        fb.fill_rect(x + w - t, y, t, meio + t, cor)
    if "e" in segs:
        fb.fill_rect(x, y + meio, t, h - meio, cor)
    if "c" in segs:
        fb.fill_rect(x + w - t, y + meio, t, h - meio, cor)
    # Cantos arredondados: apaga o pixel de cada quina (fica mais suave).
    for cx, cy in ((x, y), (x + w - 1, y), (x, y + h - 1), (x + w - 1, y + h - 1)):
        fb.pixel(cx, cy, 0)


# Cache dos dígitos: cada símbolo é desenhado UMA vez numa imagem pequena;
# depois só copiamos a imagem (blit), o que é ~5x mais rápido que redesenhar
# os retângulos a cada quadro.
_GLIFOS = {}
for _ch in "0123456789-":
    _g = framebuf.FrameBuffer(bytearray(DIG_LARGURA * ((DIG_ALTURA + 7) // 8)),
                              DIG_LARGURA, DIG_ALTURA, framebuf.MONO_VLSB)
    digito_grande(_g, _ch, 0, 0)
    _GLIFOS[_ch] = _g


def numero_grande(fb, valor, x, y, casas=3):
    """Escreve um número alinhado à direita em `casas` posições.
    valor=None mostra '---' (sem alvo)."""
    s = "-" * casas if valor is None else ("%d" % valor)[-casas:]
    s = " " * (casas - len(s)) + s
    for ch in s:
        if ch != " ":
            fb.blit(_GLIFOS[ch], x, y)
        x += DIG_LARGURA + DIG_ESPACO
    return x


# =============================================================================
#  O painel
# =============================================================================
class Painel:
    def __init__(self, oled, quadro_ms, distancia_cena_cm):
        self.oled = oled                 # é também o FrameBuffer onde desenhamos
        self._mv = memoryview(oled.buffer)
        self._quadro_ms = quadro_ms
        self._distancia_cena_cm = distancia_cena_cm
        self._pagina = PAGINAS           # PAGINAS = nenhum envio em andamento
        self._ultimo_quadro = None
        self._estado = None              # o que deve aparecer na tela
        self._desenhado = None           # o que já foi desenhado
        # Fundo pronto do Modo Ré (partes que nunca mudam: barra superior,
        # parede e chão). Desenhamos uma vez para "som ligado" e outra para
        # "mudo"; a cada quadro só COPIAMOS o fundo (0,06 ms) em vez de
        # limpar e redesenhar tudo (~3 ms).
        self._fundo_re = {}
        for mudo in (False, True):
            self._desenhar_fundo_re(mudo)
            self._fundo_re[mudo] = bytes(oled.buffer)
        self._desenhar_fundo_trena()
        self._fundo_trena = bytes(oled.buffer)
        oled.fill(0)

    # ------------------------------------------------ o que mostrar
    def tela_re(self, distancia_cm, zona, proximidade, mudo, ble=False,
                ajuste_cm=None):
        """Informa o que mostrar no Modo Ré. Não desenha nada aqui: o desenho
        acontece em atualizar(), no ritmo certo.
          ble=True       -> ícone de Bluetooth (computador conectado)
          ajuste_cm=25   -> janela "LIMITE PARE 25 cm" (joystick mexendo)"""
        segmentos = int(proximidade * SEGMENTOS + 0.5)
        self._estado = ("re", distancia_cm, zona, segmentos, mudo, ble, ajuste_cm)

    def tela_trena(self, mm, congelado, ble=False):
        """Modo Trena: distância em cm (com 1 casa) e em mm, mais a régua.
        congelado=True mostra o floco de neve e destaca o valor."""
        self._estado = ("trena", mm, congelado, ble)

    # ------------------------------------------- coração não bloqueante
    def atualizar(self, agora):
        """Chame a cada volta do laço. Faz NO MÁXIMO uma destas coisas:
        envia uma página, ou redesenha o quadro. Retorna rápido."""
        if self._pagina < PAGINAS:
            p = self._pagina
            self.oled.write_data(self._mv[p * LARGURA:(p + 1) * LARGURA])
            self._pagina += 1
            return
        if self._estado is None or self._estado == self._desenhado:
            return                       # nada novo para mostrar
        if (self._ultimo_quadro is not None and
                time.ticks_diff(agora, self._ultimo_quadro) < self._quadro_ms):
            return                       # ainda cedo para o próximo quadro
        self._ultimo_quadro = agora
        self._desenhado = self._estado
        self._desenhar(self._estado)
        # Aponta a memória do OLED para o início (coluna 0, página 0); as
        # próximas 8 voltas do laço enviam as 8 páginas, uma por vez.
        o = self.oled
        for cmd in (_SET_COL_ADDR, 0, LARGURA - 1, _SET_PAGE_ADDR, 0, PAGINAS - 1):
            o.write_cmd(cmd)
        self._pagina = 0

    # ------------------------------------------------------- desenho
    def _desenhar_fundo_re(self, mudo):
        """Partes fixas da tela do Modo Ré."""
        fb = self.oled
        fb.fill(0)
        # Barra superior: modo à esquerda, som à direita.
        fb.blit(ICONE_MODO_RE, X_ICONE_MODO, 0)
        texto(fb, "MODO RÉ", X_ICONE_MODO + 20, 5)
        fb.blit(ICONE_SOM_MUDO if mudo else ICONE_SOM_LIGADO, X_ICONE_SOM, 0)
        fb.hline(0, Y_LINHA_TOPO, LARGURA, 1)
        # Parede de tijolos encostada na margem direita, e o chão.
        px = CENA_FIM - PAREDE_LARGURA
        topo = Y_DIGITOS
        fb.rect(px, topo, PAREDE_LARGURA, Y_CHAO - topo + 1, 1)
        for i, y in enumerate(range(topo + 4, Y_CHAO, 4)):
            fb.hline(px, y, PAREDE_LARGURA, 1)
            fb.vline(px + (2 if i % 2 else 4), y - 3, 3, 1)   # juntas alternadas
        fb.hline(CENA_X, Y_CHAO, CENA_FIM - CENA_X, 1)

    def _desenhar(self, estado):
        if estado[0] == "trena":
            self._desenhar_trena(estado)
        else:
            self._desenhar_re(estado)

    def _desenhar_re(self, estado):
        fb = self.oled
        _, distancia_cm, zona, segmentos, mudo, ble, ajuste_cm = estado
        self._mv[:] = self._fundo_re[mudo]      # copia o fundo pronto
        if ble:
            fb.blit(ICONE_BLE, X_ICONE_BLE, 0)

        # Distância em dígitos grandes + unidade.
        x = numero_grande(fb, distancia_cm, MARGEM, Y_DIGITOS)
        if distancia_cm is not None:            # "---" fica sem unidade
            fb.text("cm", x, Y_DIGITOS + DIG_ALTURA - 8, 1)

        # Carro de ré se aproximando da parede (a parede já está no fundo).
        self._carro(fb, distancia_cm)

        # Nome da zona (no PARE, em destaque: letras escuras num fundo claro).
        nome = _NOME_EXIBIDO[zona]
        if zona == PARE:
            larg = 8 * len(nome) + 8
            fb.fill_rect((LARGURA - larg) // 2, Y_ZONA - 2, larg, 11, 1)
            texto_centralizado(fb, nome, Y_ZONA, 0)
        else:
            texto_centralizado(fb, nome, Y_ZONA)

        # Barra de proximidade segmentada.
        total = SEGMENTOS * SEG_LARGURA + (SEGMENTOS - 1) * SEG_ESPACO
        x = (LARGURA - total) // 2
        for i in range(SEGMENTOS):
            if i < segmentos:
                fb.fill_rect(x, Y_BARRA, SEG_LARGURA, BARRA_ALTURA, 1)
            else:
                fb.rect(x, Y_BARRA, SEG_LARGURA, BARRA_ALTURA, 1)
            x += SEG_LARGURA + SEG_ESPACO

        if ajuste_cm is not None:
            self._janela_ajuste(fb, ajuste_cm)

    def _janela_ajuste(self, fb, limite_cm):
        """Janela por cima da tela: "LIMITE PARE" + valor + setas."""
        x, y, w, h = JANELA_X, JANELA_Y, JANELA_L, JANELA_A
        fb.fill_rect(x, y, w, h, 0)
        fb.rect(x, y, w, h, 1)
        texto_centralizado(fb, "LIMITE PARE", y + 3)
        largura_num = 2 * (DIG_LARGURA + DIG_ESPACO) + 16
        xn = numero_grande(fb, limite_cm, (LARGURA - largura_num) // 2, y + 13, 2)
        fb.text("cm", xn, y + 13 + DIG_ALTURA - 8, 1)
        # Setas "empurre para cima / para baixo" dos dois lados.
        for cx in (x + 12, x + w - 13):
            for i in range(4):
                fb.hline(cx - i, y + 16 + i, 2 * i + 1, 1)     # para cima
                fb.hline(cx - i, y + 29 - i, 2 * i + 1, 1)     # para baixo

    def _desenhar_fundo_trena(self):
        """Partes fixas da tela do Modo Trena: barra superior e régua."""
        fb = self.oled
        fb.fill(0)
        fb.blit(ICONE_MODO_TRENA, X_ICONE_MODO, 0)
        texto(fb, "TRENA", X_ICONE_MODO + 20, 5)
        fb.hline(0, Y_LINHA_TOPO, LARGURA, 1)
        # Régua: base + traço a cada 10 cm (maior a cada 50 cm).
        fb.hline(REGUA_X0, Y_REGUA, REGUA_LARGURA, 1)
        for cm in range(0, TRENA_MAX_MM // 10 + 1, 10):
            x = REGUA_X0 + cm * 10 * (REGUA_LARGURA - 1) // TRENA_MAX_MM
            altura = 5 if cm % 50 == 0 else 2
            fb.vline(x, Y_REGUA - altura, altura, 1)

    def _desenhar_trena(self, estado):
        fb = self.oled
        _, mm, congelado, ble = estado
        self._mv[:] = self._fundo_trena
        if ble:
            fb.blit(ICONE_BLE, X_ICONE_BLE, 0)
        if congelado:
            fb.blit(ICONE_CONGELADO, X_ICONE_SOM, 0)
        # "123,4 cm": parte inteira em 3 dígitos grandes, vírgula, décimo.
        # Sem alvo: só "---" (sem vírgula nem unidade), como no Modo Ré.
        x = numero_grande(fb, None if mm is None else mm // 10, TRENA_X0, Y_DIGITOS)
        if mm is not None:
            fb.fill_rect(x, Y_DIGITOS + DIG_ALTURA - 4, 3, 4, 1)      # vírgula
            fb.pixel(x, Y_DIGITOS + DIG_ALTURA, 1)
            x += 6
            fb.blit(_GLIFOS["%d" % (mm % 10)], x, Y_DIGITOS)
            fb.text("cm", x + DIG_LARGURA + 3, Y_DIGITOS + DIG_ALTURA - 8, 1)
        # Linha do valor em mm (destacada quando congelada).
        linha = "sem alvo" if mm is None else "%d mm" % mm
        if congelado:
            larg = 8 * len(linha) + 8
            fb.fill_rect((LARGURA - larg) // 2, Y_MM - 2, larg, 10, 1)
            texto_centralizado(fb, linha, Y_MM, 0)
        else:
            texto_centralizado(fb, linha, Y_MM)
        # Ponteiro (triângulo) em cima da régua.
        if mm is not None:
            xm = REGUA_X0 + min(mm, TRENA_MAX_MM) * (REGUA_LARGURA - 1) // TRENA_MAX_MM
            for i in range(3):
                fb.hline(xm - 2 + i, Y_REGUA - 8 + i, 5 - 2 * i, 1)

    def _carro(self, fb, distancia_cm):
        # Encostado na parede a 0 cm; no início da cena a partir de
        # distancia_cena_cm (ou sem alvo).
        px = CENA_FIM - PAREDE_LARGURA
        folga_max = px - 1 - 16 - CENA_X
        if distancia_cm is None or distancia_cm >= self._distancia_cena_cm:
            folga = folga_max
        else:
            folga = folga_max * max(distancia_cm, 0) // self._distancia_cena_cm
        # key=0: os pixels apagados do ícone ficam TRANSPARENTES (sem isso o
        # retângulo preto do ícone apagaria o chão embaixo do carro).
        fb.blit(ICONE_CARRO, px - 1 - 16 - folga, Y_CHAO - 15, 0)

    # -------------------------------------------- telas que bloqueiam
    # (usadas fora do laço principal: na abertura e nos avisos de erro)
    def mensagem(self, titulo, linhas=()):
        """Tela de aviso: título em destaque e até 4 linhas de texto."""
        fb = self.oled
        fb.fill(0)
        fb.fill_rect(0, 0, LARGURA, 13, 1)
        texto_centralizado(fb, titulo, 3, 0)
        for i, linha in enumerate(linhas[:4]):
            texto_centralizado(fb, linha, 18 + i * 11)
        fb.show()
        self._desenhado = None           # obriga a redesenhar depois

    def abertura(self):
        """Animação de abertura (~2 s): o título desce e um carro dá ré até
        a parede. Bloqueia — use só ao ligar, antes do laço principal."""
        titulos = (_texto_ampliado("SENSOR", 2), _texto_ampliado("DE RÉ", 2))
        for q in range(ABERTURA_QUADROS + 1):
            self._quadro_abertura(q, titulos)
            self.oled.show()
        time.sleep_ms(700)
        self._desenhado = None

    def _quadro_abertura(self, q, titulos):
        """Desenha o quadro q (0..ABERTURA_QUADROS) da abertura."""
        fb = self.oled
        (l1, w1, _), (l2, w2, _) = titulos
        chao = 58
        parede_x = LARGURA - MARGEM - PAREDE_LARGURA
        fb.fill(0)
        # Título descendo nos primeiros 10 quadros. O buffer ampliado tem
        # 6 linhas de folga em cima (espaço do acento de "RÉ"), por isso
        # os deslocamentos: "SENSOR" ocupa y=2..15 e "DE RÉ" y=24..37,
        # com o acento em y=18..21 — sem encostar na linha de cima.
        sobe = (10 - min(q, 10)) * 4
        fb.blit(l1, (LARGURA - w1) // 2, -4 - sobe, 0)
        fb.blit(l2, (LARGURA - w2) // 2, 18 - sobe, 0)
        # Chão e parede.
        fb.hline(0, chao, LARGURA, 1)
        fb.rect(parede_x, chao - 16, PAREDE_LARGURA, 17, 1)
        for y in range(chao - 12, chao, 4):
            fb.hline(parede_x, y, PAREDE_LARGURA, 1)
        # Carro dando ré da esquerda até perto da parede.
        fim = parede_x - 16 - 9          # para 9 px antes da parede
        x = -16 + (fim + 16) * q // ABERTURA_QUADROS
        fb.blit(ICONE_CARRO, x, chao - 15, 0)
        # Ondas do "bipe" saindo da traseira nos últimos quadros.
        if q > ABERTURA_QUADROS - 12 and q % 4 < 2:
            for r in (2, 5):             # duas "ondas" entre carro e parede
                fb.vline(x + 16 + r, chao - 11 + r // 2, 7 - r, 1)

    def apagar(self):
        self.oled.fill(0)
        self.oled.show()
        self._pagina = PAGINAS
        self._desenhado = None


# Nomes das zonas como aparecem na tela (com acento).
_NOME_EXIBIDO = ("LIVRE", "ATENÇÃO", "PERIGO", "PARE")
