# =============================================================================
#  cores.py — TODAS as cores do projeto ficam aqui (matriz 5x5 e LED RGB).
#
#  Cada cor é (vermelho, verde, azul), de 0 a 255. Os valores já vêm com
#  BRILHO REDUZIDO: 255 num WS2812 ofusca e esquenta; perto de 40 já é bem
#  visível. Como a mesma tabela alimenta a matriz e o LED RGB, as duas luzes
#  mostram sempre a mesma cor — ficam "harmonizadas".
#
#  Brilho de cada cor em relação ao LED todo aceso em branco (255+255+255):
#      verde  (0, 40, 12)  ->  52/765 = 6,8 %
#      amarelo(40, 32, 0)  ->  72/765 = 9,4 %
#      laranja(45, 15, 0)  ->  60/765 = 7,8 %
#      vermelho(50, 0, 4)  ->  54/765 = 7,1 %
#  Na MATRIZ, essas cores definem só o TOM: o brilho é igualado em
#  config.MATRIZ_BRILHO (10 %) por normalizar_brilho(), para as quatro zonas
#  ficarem igualmente visíveis. O LED RGB usa os valores daqui como estão.
# =============================================================================

try:
    from time import ticks_diff
except ImportError:                 # Python no PC (testes)
    def ticks_diff(a, b):
        return a - b

VERDE = (0, 40, 12)
AMARELO = (40, 32, 0)
LARANJA = (45, 15, 0)
VERMELHO = (50, 0, 4)
APAGADO = (0, 0, 0)

# Cor de cada zona, NA ORDEM das zonas de filtros.py:
#                 LIVRE  ATENÇÃO  PERIGO   PARE
COR_DA_ZONA = (VERDE, AMARELO, LARANJA, VERMELHO)


def escalar(cor, fator):
    """Multiplica o brilho da cor por `fator` (0.0 a 1.0)."""
    return (int(cor[0] * fator + 0.5), int(cor[1] * fator + 0.5), int(cor[2] * fator + 0.5))


def misturar(cor_a, cor_b, fracao):
    """Cor intermediária: fracao=0 -> cor_a, fracao=1 -> cor_b."""
    return (int(cor_a[0] + (cor_b[0] - cor_a[0]) * fracao + 0.5),
            int(cor_a[1] + (cor_b[1] - cor_a[1]) * fracao + 0.5),
            int(cor_a[2] + (cor_b[2] - cor_a[2]) * fracao + 0.5))


def normalizar_brilho(cor, brilho):
    """Ajusta a cor para que R+G+B seja exatamente `brilho` (0 a 1) do
    branco total, mantendo o TOM. Ex.: com brilho=0.10, verde, amarelo,
    laranja e vermelho ficam todos com 10 % — o mesmo brilho aparente de
    potência, só mudando a cor.

    Como os canais são inteiros, arredondamos e, se a soma passar do alvo,
    tiramos 1 do canal mais forte: o resultado nunca ultrapassa o limite."""
    soma = cor[0] + cor[1] + cor[2]
    if soma == 0:
        return cor                      # apagado continua apagado
    alvo = int(brilho * 765)
    fator = alvo / soma
    canais = [int(c * fator + 0.5) for c in cor]
    while canais[0] + canais[1] + canais[2] > alvo:
        maior = canais.index(max(canais))
        canais[maior] -= 1
    return (canais[0], canais[1], canais[2])


def limitar_brilho(cor, maximo):
    """Garante que a soma R+G+B não passe de `maximo` (0 a 1) do branco
    total. Mantém o TOM da cor: reduz os três canais na mesma proporção."""
    soma = cor[0] + cor[1] + cor[2]
    teto = maximo * 765
    if soma <= teto:
        return cor
    return escalar(cor, teto / soma)


class TransicaoCor:
    """Troca de cor SUAVE e não bloqueante.

    Em vez de pular de verde para amarelo, a cor "viaja" de uma para a outra
    em `duracao_ms`. Quem chama cor(agora) recebe a cor certa para aquele
    instante. Se o alvo mudar no meio do caminho, a nova viagem começa da
    cor que está na tela naquele momento (sem saltos)."""

    def __init__(self, duracao_ms, inicial=APAGADO):
        self._duracao = duracao_ms
        self._de = inicial
        self._para = inicial
        self._inicio = 0

    def alvo(self, cor, agora):
        if cor == self._para:
            return
        self._de = self.cor(agora)
        self._para = cor
        self._inicio = agora

    def cor(self, agora):
        passado = ticks_diff(agora, self._inicio)
        if passado >= self._duracao:
            return self._para
        return misturar(self._de, self._para, passado / self._duracao)
