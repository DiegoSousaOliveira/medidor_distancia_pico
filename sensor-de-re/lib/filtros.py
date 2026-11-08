# =============================================================================
#  filtros.py — "Limpeza" das leituras do sensor e classificação em zonas.
#
#  1) FiltroMediana: o sensor às vezes devolve um valor absurdo isolado (um
#     reflexo, um 8191 perdido). A MÉDIA seria puxada por esse valor; a
#     MEDIANA (o valor do meio depois de ordenar) simplesmente o ignora.
#
#        leituras: 135, 141, 8191, 138, 140   -> ordenadas: 135 138 140 141 8191
#        média   = 1749 mm (errado!)          -> mediana = 140 mm (certo)
#
#  2) Zonas: transforma a distância em LIVRE / ATENÇÃO / PERIGO / PARE, com
#     HISTERESE para a cor e o som não ficarem "piscando" quando o objeto está
#     parado bem em cima de um limite (ex.: 50 cm, oscilando entre 49 e 51).
# =============================================================================

# --- Zonas (do mais longe para o mais perto) --------------------------------
LIVRE = 0
ATENCAO = 1
PERIGO = 2
PARE = 3

NOMES_ZONAS = ("LIVRE", "ATENCAO", "PERIGO", "PARE")


class FiltroMediana:
    """Mediana móvel das últimas `tamanho` leituras (use um número ímpar)."""

    def __init__(self, tamanho=5):
        self._tamanho = tamanho
        self._valores = []      # guarda no máximo `tamanho` leituras
        self._proximo = 0       # posição do buffer circular a sobrescrever

    def adicionar(self, valor):
        """Guarda uma leitura nova e devolve a mediana atual."""
        if len(self._valores) < self._tamanho:
            self._valores.append(valor)
        else:
            # Buffer circular: sobrescreve a leitura mais antiga, sem criar
            # listas novas a cada passo (economiza memória na Pico).
            self._valores[self._proximo] = valor
        self._proximo = (self._proximo + 1) % self._tamanho
        return self.mediana()

    def mediana(self):
        if not self._valores:
            return None
        ordenados = sorted(self._valores)
        return ordenados[len(ordenados) // 2]

    def limpar(self):
        self._valores = []
        self._proximo = 0


class FiltroDistancia:
    """Mediana + "retenção" do alvo.

    Problema observado na placa: com a mão a ~40 cm o sensor devolve várias
    leituras INVÁLIDAS seguidas (8190), misturadas com leituras boas. Se elas
    entrarem na mediana, basta 3 de 5 inválidas para o resultado virar
    "sem alvo" — e o alarme se cala com a mão ainda ali!

    Solução:
      * leituras inválidas NÃO entram na mediana (não são distâncias);
      * só declaramos "sem alvo" quando passamos `tempo_sem_alvo_ms` SEM
        nenhuma leitura válida. Até lá, mantemos a última distância filtrada.

    Num sensor de ré, perder o alvo por um instante não pode desligar o
    aviso: é mais seguro demorar meio segundo para dizer "livre"."""

    def __init__(self, tamanho, tempo_sem_alvo_ms):
        self._mediana = FiltroMediana(tamanho)
        self._tempo_sem_alvo_ms = tempo_sem_alvo_ms
        self._ultima_valida_ms = None   # instante da última leitura válida
        self.distancia = None           # resultado atual (mm) ou None

    def adicionar(self, mm, agora_ms):
        """mm = leitura válida em mm, ou None se a leitura foi inválida.
        agora_ms = time.ticks_ms(). Devolve a distância filtrada ou None."""
        if mm is not None:
            self._ultima_valida_ms = agora_ms
            self.distancia = self._mediana.adicionar(mm)
        elif (self._ultima_valida_ms is None or
              _ticks_diff(agora_ms, self._ultima_valida_ms) >= self._tempo_sem_alvo_ms):
            # Muito tempo sem nada válido: o alvo sumiu de verdade. Limpamos a
            # mediana para que, quando algo aparecer, ela não misture
            # distâncias antigas com a nova.
            self._mediana.limpar()
            self.distancia = None
        # Caso contrário: inválida isolada -> mantém a distância anterior.
        return self.distancia


class SuavizadorExibicao:
    """Deixa o NÚMERO MOSTRADO no display estável (não muda zonas nem som).

    Mesmo com a mediana, uma leitura parada oscila ~±1,6 cm (medimos!). Na
    tela isso vira um número pulando 61, 62, 63, 62... difícil de ler.
    Duas técnicas juntas resolvem:
      1) média móvel exponencial (EMA): cada leitura nova puxa a média só um
         pouco (fator `alfa`), alisando o ruído;
      2) histerese: o número na tela só muda quando a média se afasta dele
         pelo menos `histerese_mm`.
    O resultado responde rápido a movimentos de verdade e fica parado quando
    o objeto está parado.

    `passo_mm` é a resolução do número mostrado: 10 (Modo Ré, em cm inteiros)
    ou 1 (Modo Trena, em mm). O valor devolvido é sempre em mm."""

    def __init__(self, alfa, histerese_mm, passo_mm):
        self._alfa = alfa
        self._histerese = histerese_mm
        self._passo = passo_mm
        self._media = None
        self.valor_mm = None        # valor exibido, múltiplo de passo_mm (ou None)

    def atualizar(self, mm):
        if mm is None:
            self._media = None
            self.valor_mm = None
            return None
        if self._media is None:
            self._media = mm
        else:
            self._media += self._alfa * (mm - self._media)
        if self.valor_mm is None or abs(self._media - self.valor_mm) >= self._histerese:
            self.valor_mm = int(self._media / self._passo + 0.5) * self._passo
        return self.valor_mm


try:
    from time import ticks_diff as _ticks_diff   # MicroPython
except ImportError:                                # Python no PC (testes)
    def _ticks_diff(a, b):
        return a - b


class Zonas:
    """Classifica distâncias (mm) em zonas, com histerese.

    Limites (em mm):
        d <  limite_pare           -> PARE
        d <  limite_perigo         -> PERIGO
        d <= limite_atencao        -> ATENÇÃO
        d >  limite_atencao        -> LIVRE   (ou sem alvo: None)
    """

    def __init__(self, limite_pare_mm, limite_perigo_mm, limite_atencao_mm,
                 histerese_mm):
        self.limite_pare_mm = limite_pare_mm      # ajustável pelo joystick (etapa 6)
        self.limite_perigo_mm = limite_perigo_mm
        self.limite_atencao_mm = limite_atencao_mm
        self.histerese_mm = histerese_mm
        self.atual = LIVRE

    def _classificar(self, mm):
        """Zona "crua", sem histerese."""
        if mm < self.limite_pare_mm:
            return PARE
        if mm < self.limite_perigo_mm:
            return PERIGO
        if mm <= self.limite_atencao_mm:
            return ATENCAO
        return LIVRE

    def atualizar(self, mm):
        """Recebe a distância filtrada (ou None = sem alvo) e devolve a zona.

        Por que histerese? Para PIORAR de zona (chegar mais perto) a troca é
        imediata: segurança em primeiro lugar. Para MELHORAR (afastar), o
        objeto precisa passar o limite com uma folga de `histerese_mm`.
        Assim, um objeto parado em cima do limite não fica trocando de zona."""
        if mm is None:
            self.atual = LIVRE
            return self.atual
        crua = self._classificar(mm)
        if crua > self.atual:
            # Chegou mais perto: troca já.
            self.atual = crua
        elif crua < self.atual:
            # Afastou: só aceita se continuar afastado mesmo "descontando"
            # a folga. É como se o objeto estivesse histerese_mm mais perto.
            com_folga = self._classificar(mm - self.histerese_mm)
            if com_folga < self.atual:
                self.atual = com_folga
        return self.atual

    def proximidade(self, mm):
        """Número de 0.0 a 1.0 que cresce de forma CONTÍNUA conforme o objeto
        se aproxima: 0.0 no limite da zona ATENÇÃO (ou mais longe) e 1.0 no
        limite da zona PARE (ou mais perto).

        Ele será usado para o intervalo dos bipes (etapa 3) e para as barras
        de proximidade (etapas 4 e 5), que assim variam suavemente, e não só
        em degraus de zona."""
        if mm is None or mm >= self.limite_atencao_mm:
            return 0.0
        if mm <= self.limite_pare_mm:
            return 1.0
        faixa = self.limite_atencao_mm - self.limite_pare_mm
        return (self.limite_atencao_mm - mm) / faixa
