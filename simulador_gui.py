#!/usr/bin/env python3
"""
Interface de desktop do simulador da fila da catraca do RU.

Usa as funções do analise_catraca.py (medir, simular_cenarios, validar...). Com os
mesmos parâmetros e a mesma semente, os números são os do relatorio.txt.

Instalação:  python -m pip install PySide6 matplotlib
Uso:         python simulador_gui.py                (abre com as sessões de exemplo)
             python simulador_gui.py A.csv B.csv C.csv
"""
import math
import os
import random
import statistics
import sys
from datetime import timedelta

import analise_catraca as ac

try:
    from PySide6.QtCore import QElapsedTimer, QPoint, QPointF, QRectF, Qt, QThread, QTimer, Signal
    from PySide6.QtGui import QColor, QCursor, QFont, QGuiApplication, QPainter, QPainterPath, QPen
    from PySide6.QtWidgets import (
        QApplication, QButtonGroup, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFrame,
        QGridLayout, QHBoxLayout, QHeaderView, QLabel, QMainWindow, QMessageBox, QProgressBar,
        QPushButton, QScrollArea, QSizePolicy, QSpinBox, QTableWidget, QTableWidgetItem, QTabWidget,
        QToolTip, QVBoxLayout, QWidget,
    )
    import matplotlib
    matplotlib.use('QtAgg')
    from matplotlib import font_manager
    from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
    from matplotlib.figure import Figure
    from matplotlib.ticker import FuncFormatter, MaxNLocator
except ImportError as e:
    sys.exit(f'Falta uma biblioteca ({e.name}). Instale com:  python -m pip install PySide6 matplotlib')

PASTA = os.path.dirname(os.path.abspath(__file__))

# Sessões que já vêm na pasta artefatos/dados/, agrupadas por dia (um botão por dia):
# (dia, variante, arquivo, sessão ou None, ajuste do balanço, descrição).
# μ sai das saídas por minuto nos minutos com fila (ac.estimar_mu), não de um valor fixo.
F17 = 'artefatos/dados/coleta_almoco_2026-11-17_fila42.csv'
F16 = 'artefatos/dados/coletas_2026-11-16_por_coleta.csv'
EXEMPLOS = [
    ('16/11', 'coleta 1 · 11:52–12:06', F16, '2026-11-16-coleta1', 'nenhum',
     'Começou sem fila; 14 min. O balanço fecha. Tempos cronometrados descartados (relógios de B e C '
     'dessincronizados); μ pelas contagens por minuto.'),
    ('16/11', 'coleta 2 · 12:25–12:43', F16, '2026-11-16-coleta2', 'nenhum',
     'Começou com 28 na fila; 18 min, com pico. O balanço fecha. Tempos cronometrados descartados (relógios de B e C '
     'dessincronizados); μ pelas contagens por minuto.'),
    ('16/11', 'coleta 3 · 12:51–13:02', F16, '2026-11-16-coleta3', 'nenhum',
     'Começou sem fila; 11 min, quase sem fila. O balanço fecha. Tempos cronometrados descartados; μ pelas contagens '
     'por minuto.'),
    ('17/11', 'saídas não registradas (principal)', F17, None, 'saidas',
     '11:30–13:15, fila inicial 42. Os 48 alunos que sobram no balanço são saídas que o observador B não registrou, '
     'espalhadas nos minutos com fila depois das 12:16. É a hipótese da análise principal.'),
    ('17/11', 'desistências não vistas', F17, None, 'desistencia',
     'Mesmo almoço; os 48 que sobram viram desistências não vistas, proporcionais a quem espera, depois das 12:16. '
     'μ fica menor e cai na 2ª metade.'),
    ('17/11', 'fila inicial menor', F17, None, 'n0',
     'Mesmo almoço; supõe que a fila inicial era menor que 42. Não fecha o balanço: as saídas dos primeiros minutos '
     'mostram que havia fila.'),
]
PERGUNTA = ('Abrir a 2ª catraca quando a fila chega a N alunos (e fechar quando cai à metade) poupa mais minutos '
            'de espera por minuto de catraca aberta do que abri-la no horário de pico?')

# rótulo da caixa de variantes de cada botão
VARIANTE = {'16/11': 'Coleta', '17/11': 'Hipótese para os 48 alunos que sobram no balanço', 'Arquivo': 'Sessão'}
PADRAO = ('17/11', 'saídas não registradas (principal)')

# Nome do cenário no analise_catraca.py -> chave usada para cor e seleção
CHAVES = {'1 catraca': 'base', '1 cat. sem desist.': 'semdes', '2ª só no pico': 'pico2',
          '2 a hora toda': 'toda2', 'Personalizado': 'pers', 'atend. mais rápido': 'rapido', 'aulas escalonadas': 'escal',
          '2ª pela fila': 'fila'}
NOMES_LONGOS = {'base': '1 catraca', 'semdes': '1 catraca sem desistência', 'pico2': '2ª catraca só no pico',
                'toda2': '2 catracas a hora toda', 'pers': 'Personalizado', 'rapido': 'Atendimento mais rápido',
                'escal': 'Aulas escalonadas', 'fila': '2ª catraca pela fila'}

TEMAS = {
    'claro': dict(
        bg='#eef1f4', surface='#ffffff', surface2='#f5f7f9', ink='#14212b', muted='#5c6b77', line='#dbe2e8',
        accent='#2a78d6', accent_hover='#256abf', accent_ink='#ffffff', pico='#f9e4e1',
        espera='#7b8a96', cat='#b8500a', ok='#2b7a4b', alert='#c0392b', barras='#0a6a8a',
        series={'base': '#2a78d6', 'semdes': '#8a949c', 'pico2': '#1baf7a', 'toda2': '#eb6834', 'pers': '#6250d6',
                'rapido': '#a87700', 'escal': '#b0459f', 'fila': '#0f8f9c'},
    ),
    'escuro': dict(
        bg='#0f161c', surface='#17212a', surface2='#1e2a34', ink='#e8eef2', muted='#93a3af', line='#2a3945',
        accent='#3987e5', accent_hover='#5598e7', accent_ink='#ffffff', pico='#2f2228',
        espera='#8b9aa6', cat='#f0985a', ok='#5ccf8a', alert='#ff7a6b', barras='#4cb8d9',
        series={'base': '#3987e5', 'semdes': '#8b949c', 'pico2': '#199e70', 'toda2': '#d95926', 'pers': '#9085e9',
                'rapido': '#e0b040', 'escal': '#d77cc9', 'fila': '#3fc1cc'},
    ),
}

br = ac.br


def pct(x):
    return br(x * 100, 0) + '%'


# =================================================================== cálculo (fora da interface)
class Cancelado(Exception):
    pass


def calcular(c, progresso=None):
    """Roda a simulação inteira com a configuração `c` montada pela janela.
    Mesma sequência do analisar() do analise_catraca.py: verificação, passo seguro, cenários, validação."""
    pico, mu, grupo = c['pico'], c['mu'], c.get('grupo')
    Ek = grupo['Ek'] if grupo else 1.0
    out = {'cfg': c, 'avisos': []}
    lams = ac.lams_por_minuto(pico, c['lam_cal'], c['lam_pic'], c['lam_med'])
    out['lams'] = lams
    passo = c['passo']

    if c['lam_cal'] is not None and c['lam_cal'] > 0 and ac.formulas(c['lam_cal'], mu)['estavel']:
        pv = ac.passo_seguro([c['lam_cal']], mu, 1, 0.0, c['K'], passo)
        out['verif'] = [('M/M/1, uma a uma',) + ac.verificar(c['lam_cal'], mu, c['K'], c['seed'], pv)]
        if grupo:
            pg = ac.passo_seguro([c['lam_cal']], mu, 1, 0.0, c['K'], passo, Ek)
            out['verif'].append(('M^X/M/1, em grupo',) + ac.verificar(c['lam_cal'], mu, c['K'], c['seed'], pg, grupo=grupo))

    cen = [x for x in ac.cenarios_padrao(pico, c['theta']) if CHAVES[x[0]] == 'base' or CHAVES[x[0]] in c['sel']]
    if 'pers' in c['sel']:
        cc, cp, desist = c['pers']
        cen.append(('Personalizado', [cp if p else cc for p in pico], c['theta'] if desist else 0.0))
    cen += [x for x in ac.cenarios_slide61(pico, c['theta'], lams, c['lam_cal'], mu, c.get('troca')) if CHAVES[x[0]] in c['sel']]
    T = len(pico)
    out['busca'] = None
    if 'fila' in c['sel']:
        pb = ac.passo_cenarios(cen + [ac.cenario_fila(T, c['theta'], 1, 0)], lams, mu, c['theta'], c['K'], passo, Ek)
        if c.get('gatilho'):
            N, M = c['gatilho'], c['gatilho'] // 2
        else:  # automático: o N mais eficiente entre os que esperam no máximo o mesmo que a 2ª no horário de pico
            out['busca'] = ac.buscar_gatilho(lams, mu, pico, c['n0'], c['K'], c['seed'], pb, min(c['reps'], 100),
                                             c['lam_med'], c['theta'], grupo)
            mel = out['busca']['melhor']
            N, M = (mel['N'], mel['M']) if mel else (None, None)
        if N:
            cen.append(ac.cenario_fila(T, c['theta'], N, M))
    novo = ac.passo_cenarios(cen, lams, mu, c['theta'], c['K'], passo, Ek)
    if novo != passo:
        out['avisos'].append(f'Passo reduzido de {br(passo, 1)} s para {br(novo, 1)} s: com μ = {br(mu)} /min '
                             'o passo maior daria chances somando mais de 1.')
        passo = novo
    out['passo'] = passo

    res = ac.simular_cenarios(cen, lams, mu, c['n0'], c['K'], c['seed'], passo, c['reps'], c['lam_med'], progresso, grupo)
    for nome, r in res.items():
        if r['toca_K'] > .05:
            out['avisos'].append(f'Em {pct(r["toca_K"])} das réplicas de "{NOMES_LONGOS[CHAVES[nome]]}" a fila bateu em K = {c["K"]}: '
                                 'aumente K, a fila está sendo cortada pelo limite.')
        r['chave'] = CHAVES[nome]
        cols = list(zip(*r['hs']))
        r['media'] = [sum(col) / len(col) for col in cols]
        if nome == '1 catraca':
            r['p05'] = [ac.percentil(col, .05) for col in cols]
            r['p95'] = [ac.percentil(col, .95) for col in cols]
    ac.eficiencia(res, c['lam_med'] * T)
    out['res'] = res
    # achado: quanto chegar em grupo aumenta a espera (1 catraca, com e sem grupos)
    g_ref = ac.estimar_grupos(c['d']['chegadas_seg'], 1.5) if c['d'] else None
    if g_ref:
        cq = [('1 catraca', [1] * T, c['theta'])]
        outro = None if grupo else g_ref
        pq = ac.passo_cenarios(cq, lams, mu, c['theta'], c['K'], passo, outro['Ek'] if outro else 1.0)
        w_outro = ac.simular_cenarios(cq, lams, mu, c['n0'], c['K'], c['seed'], pq, min(c['reps'], 200), c['lam_med'],
                                      grupo=outro)['1 catraca']['W']
        w_aqui = res['1 catraca']['W']
        out['q6'] = {'Ek': g_ref['Ek'], 'fator': (1 + g_ref['D']) / 2,
                     'w_um': w_aqui if not grupo else w_outro, 'w_gr': w_outro if not grupo else w_aqui}
    d = c['d']
    if d and d['fila']:
        out['valid'] = ac.validar(d['fila'], res['1 catraca']['hs'], passo)
        if c.get('med'):
            out['valid'] += ac.validar_dispersao(d, c['med'], lams, passo, grupo, min(c['reps'], 300), c['seed'])
        curva = ac.comparar_curva(d['fila'], res['1 catraca']['hs'], passo)
        if curva:
            out['valid'].append(curva['linha'])
            out['curva'] = curva
        hs_t, pt = ac.simular_base_trace(d, mu, c['n0'], c['K'], c['seed'], passo, min(c['reps'], 300), c['theta'])
        out['valid_trace'] = ac.validar(d['fila'], hs_t, pt)
    if c.get('sens') and c.get('med'):
        md = dict(c['med'], pico=pico, lam_cal=c['lam_cal'], lam_pic=c['lam_pic'], theta=c['theta'], n0=c['n0'])
        out['sens'] = ac.sensibilidade(md, c['sens'], c['K'], c['seed'], c['passo'], min(c['reps'], 60), grupo, c['lam_med'])
    return out


def rastrear(hist, lams, mu, cs, n0, K, seed, passo, theta, grupo=None, politica=None):
    """Refaz os sorteios de uma réplica (mesmo random.Random(seed) do simular) para saber o que aconteceu em
    cada passo: 0 nada, 1 chegada (de um grupo), 2 passou na catraca, 3 desistiu, 4 chegou com a fila cheia.
    O tamanho do grupo vem de outro gerador; a animação lê quantos entraram pela diferença do histórico.
    Devolve (eventos, catracas abertas em cada passo): com a política pela fila, a 2ª catraca abre e fecha pela fila."""
    rng, n, T = random.Random(seed), n0, len(lams)
    s = mu * passo / 60
    Ek = grupo['Ek'] if grupo else 1.0
    ev = bytearray(len(hist))
    abertas = bytearray(len(hist))
    aberta = False
    for i, novo in enumerate(hist):
        m = min(int(i * passo / 60), T - 1)
        a = lams[m] / Ek * passo / 60
        c = cs[m]
        if politica:
            if not aberta and n >= politica[0]:
                aberta = True
            elif aberta and n <= politica[1]:
                aberta = False
            c += aberta
        abertas[i] = c
        d = max(n - c, 0) * theta * passo / 60
        u = rng.random()
        if u < a:
            e = 1 if n < K else 4
        elif u < a + min(n, c) * s:
            e = 2
        elif u < a + min(n, c) * s + d:
            e = 3
        else:
            e = 0
        n = novo
        ev[i] = e
    return ev, abertas


class Rodada(QThread):
    progresso = Signal(int)
    pronto = Signal(object)
    falhou = Signal(str)

    def __init__(self, cfg):
        super().__init__()
        self.cfg = cfg
        self._ultimo = -1

    def _prog(self, feitas, total):
        if self.isInterruptionRequested():
            raise Cancelado()
        p = int(100 * feitas / total)
        if p != self._ultimo:
            self._ultimo = p
            self.progresso.emit(p)

    def run(self):
        try:
            self.pronto.emit(calcular(self.cfg, self._prog))
        except Cancelado:
            pass
        except SystemExit as e:  # simular() encerra o script quando o passo é grande demais
            self.falhou.emit(str(e))
        except Exception as e:  # noqa: BLE001 — mostra qualquer erro na janela
            self.falhou.emit(f'{type(e).__name__}: {e}')


# =================================================================== estilo
def qss(t):
    return f"""
    * {{ font-family: 'Segoe UI Variable Text', 'Segoe UI', 'Inter', sans-serif; font-size: 10pt; color: {t['ink']}; }}
    QMainWindow, QWidget#raiz {{ background: {t['bg']}; }}
    QScrollArea {{ background: transparent; border: none; }}
    QWidget#miolo {{ background: transparent; }}
    QFrame#card {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 12px; }}
    QFrame#cartao {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 12px; }}
    QFrame#cartao[sel="true"] {{ border: 2px solid {t['ink']}; }}
    QFrame#cartao:hover {{ border-color: {t['muted']}; }}
    QLabel {{ background: transparent; }}
    QLabel#titulo {{ font-size: 17pt; font-weight: 700; }}
    QLabel#h2 {{ font-size: 11.5pt; font-weight: 700; }}
    QLabel#h3 {{ font-size: 10pt; font-weight: 700; color: {t['muted']}; }}
    QLabel[papel="dica"] {{ color: {t['muted']}; font-size: 9pt; }}
    QLabel[papel="medido"] {{ color: {t['muted']}; font-size: 8.5pt; }}
    QLabel[papel="rotulo"] {{ color: {t['muted']}; font-size: 8.5pt; font-weight: 600; letter-spacing: 1px; }}
    QLabel[papel="campo"] {{ color: {t['muted']}; font-size: 9pt; font-weight: 600; }}
    QLabel[papel="grande"] {{ font-size: 24pt; font-weight: 700; }}
    QLabel[papel="conclusao"] {{ font-size: 13pt; font-weight: 600; }}
    QLabel[papel="num"] {{ font-size: 17pt; font-weight: 700; }}
    QLabel[papel="erro"] {{ color: {t['alert']}; font-size: 9pt; }}
    QLabel[papel="bom"] {{ color: {t['ok']}; font-weight: 600; }}
    QLabel[papel="ruim"] {{ color: {t['alert']}; font-weight: 600; }}
    QLabel[papel="selo-pico"] {{ background: {t['pico']}; color: {t['alert']}; border-radius: 10px; padding: 3px 10px; font-weight: 700; }}
    QLabel[papel="selo-calma"] {{ background: {t['surface2']}; color: {t['muted']}; border: 1px solid {t['line']}; border-radius: 10px; padding: 3px 10px; font-weight: 700; }}
    QSpinBox, QDoubleSpinBox, QComboBox {{
        background: {t['surface2']}; border: 1px solid {t['line']}; border-radius: 8px;
        padding: 5px 8px; min-height: 22px; selection-background-color: {t['accent']}; selection-color: #fff; }}
    QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {t['accent']}; }}
    QSpinBox[editado="true"], QDoubleSpinBox[editado="true"] {{ border: 1px solid {t['cat']}; }}
    QSpinBox:disabled, QDoubleSpinBox:disabled {{ color: {t['muted']}; }}
    QComboBox::drop-down {{ border: none; width: 24px; }}
    QAbstractSpinBox::up-button, QAbstractSpinBox::down-button {{ width: 0px; border: none; }}
    QComboBox QAbstractItemView {{ background: {t['surface']}; border: 1px solid {t['line']}; padding: 4px;
        selection-background-color: {t['accent']}; selection-color: #fff; outline: none; }}
    QPushButton {{ background: {t['surface']}; border: 1px solid {t['line']}; border-radius: 8px;
        padding: 7px 14px; font-weight: 600; }}
    QPushButton:hover {{ border-color: {t['accent']}; }}
    QPushButton:disabled {{ color: {t['muted']}; border-color: {t['line']}; }}
    QPushButton[papel="primario"] {{ background: {t['accent']}; color: {t['accent_ink']}; border: none; padding: 9px 16px; }}
    QPushButton[papel="primario"]:hover {{ background: {t['accent_hover']}; }}
    QPushButton[papel="primario"]:disabled {{ background: {t['line']}; color: {t['muted']}; }}
    QPushButton[papel="seg"] {{ border-radius: 7px; padding: 5px 11px; background: {t['surface2']}; }}
    QPushButton[papel="seg"]:checked {{ background: {t['ink']}; color: {t['bg']}; border-color: {t['ink']}; }}
    QPushButton[papel="fino"] {{ background: transparent; border: none; color: {t['accent']}; padding: 4px 0; text-align: left; }}
    QPushButton[papel="fino"]:hover {{ text-decoration: underline; }}
    QCheckBox {{ spacing: 8px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 5px; border: 1px solid {t['muted']}; background: {t['surface2']}; }}
    QCheckBox::indicator:checked {{ background: {t['accent']}; border-color: {t['accent']}; }}
    QCheckBox::indicator:disabled {{ background: {t['line']}; border-color: {t['line']}; }}
    QCheckBox::indicator:checked:disabled {{ background: {t['muted']}; border-color: {t['muted']}; }}
    QTabWidget::pane {{ border: none; }}
    QTabBar::tab {{ background: transparent; color: {t['muted']}; padding: 8px 18px; margin-right: 6px;
        border-radius: 9px; font-weight: 600; border: 1px solid transparent; }}
    QTabBar::tab:selected {{ background: {t['surface']}; color: {t['ink']}; border: 1px solid {t['line']}; }}
    QTabBar::tab:hover:!selected {{ color: {t['ink']}; }}
    QProgressBar {{ background: {t['surface2']}; border: none; border-radius: 3px; max-height: 6px; min-height: 6px; }}
    QProgressBar::chunk {{ background: {t['accent']}; border-radius: 3px; }}
    QTableWidget {{ background: {t['surface']}; border: none; gridline-color: transparent;
        alternate-background-color: {t['surface2']}; selection-background-color: {t['surface2']}; selection-color: {t['ink']}; }}
    QTableWidget::item {{ padding: 4px 8px; }}
    QHeaderView::section {{ background: {t['surface']}; color: {t['muted']}; border: none;
        border-bottom: 1px solid {t['line']}; padding: 6px 8px; font-weight: 600; }}
    QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {t['line']}; border-radius: 4px; min-height: 30px; }}
    QScrollBar::handle:vertical:hover {{ background: {t['muted']}; }}
    QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    QToolTip {{ background: {t['surface']}; color: {t['ink']}; border: 1px solid {t['line']}; padding: 6px; }}
    """


def rotulo(texto, papel=None, nome=None, quebra=False):
    lb = QLabel(texto)
    if papel:
        lb.setProperty('papel', papel)
    if nome:
        lb.setObjectName(nome)
    lb.setWordWrap(quebra)
    return lb


def card():
    f = QFrame()
    f.setObjectName('card')
    lay = QVBoxLayout(f)
    lay.setContentsMargins(16, 14, 16, 16)
    lay.setSpacing(8)
    return f, lay


def repolir(w):
    w.style().unpolish(w)
    w.style().polish(w)


# =================================================================== animação da fila
class Aluno:
    __slots__ = ('x', 'y', 'tx', 'ty', 'a', 'ta', 'estado')

    def __init__(self, x, y, a=1.0):
        self.x = self.tx = x
        self.y = self.ty = y
        self.a, self.ta = a, 1.0
        self.estado = 'espera'


class Palco(QWidget):
    """Desenha uma réplica da simulação: alunos esperando em serpentina e as catracas à direita."""
    mudou = Signal(int)
    terminou = Signal()
    ESP = 15         # espaço entre alunos na fila
    CAT_W, CAT_H, CAT_GAP = 92, 34, 10

    def __init__(self, tema):
        super().__init__()
        self.t = tema
        self.hist = None
        self.rodando = False
        self.vel = 30
        self.k = -1
        self.tsim = 0.0
        self.fila, self.cats, self.saindo = [], [], []
        self.aviso_k = 0.0
        self.rng = random.Random(7)
        self.relogio = QElapsedTimer()
        self.relogio.start()
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._quadro)
        self.timer.start(16)
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    # ---- dados
    def carregar(self, hist, ev, cs, n0, passo, K, abertas=None):
        self.hist, self.ev, self.cs, self.n0, self.passo, self.K = hist, ev, cs, n0, passo, K
        self.abertas = abertas  # catracas abertas em cada passo (política pela fila); None = pelo minuto
        self.N, self.T = len(hist), len(cs)
        self.cmax = max(max(cs), max(abertas) if abertas else 0)
        self.acum = {e: [] for e in (1, 2, 3, 4)}
        cont = {e: 0 for e in (1, 2, 3, 4)}
        ant = n0
        for i, e in enumerate(ev):
            if e == 1:
                cont[1] += max(1, hist[i] - ant)  # um grupo pode trazer vários alunos
            elif e:
                cont[e] += 1
            ant = hist[i]
            for x in (1, 2, 3, 4):
                self.acum[x].append(cont[x])
        self._geometria()
        self.ir_para(-1)

    def catracas_no_passo(self, k):
        if self.abertas:
            return self.abertas[min(max(k, 0), len(self.abertas) - 1)]
        return self.cs[min(int(max(k, 0) * self.passo / 60), self.T - 1)]

    def contagem(self, tipo):
        return self.acum[tipo][self.k] if self.k >= 0 else 0

    # ---- geometria
    def _geometria(self):
        if self.hist is None:
            return
        w = max(self.width(), 300)
        self.cat_x = w - self.CAT_W - 70
        self.topo = 18
        self.q_dir = self.cat_x - 26
        self.q_esq = 22
        self.cap = max(4, int((self.q_dir - self.q_esq) / self.ESP) + 1)
        maior = max(self.K, self.n0, max(self.hist))
        self.linhas = min(14, math.ceil(maior / self.cap))
        y0 = self.topo + self.CAT_H / 2
        alt_fila = y0 + (self.linhas - 1) * self.ESP + 30
        alt_cat = self.topo + self.cmax * (self.CAT_H + self.CAT_GAP) + 20
        self.setFixedHeight(int(max(alt_fila, alt_cat, 150)))

    def pos_fila(self, j):
        j = min(j, self.cap * self.linhas - 1)
        r, c = divmod(j, self.cap)
        x = self.q_dir - c * self.ESP if r % 2 == 0 else self.q_esq + c * self.ESP
        return x, self.topo + self.CAT_H / 2 + r * self.ESP

    def pos_cat(self, i):
        return self.cat_x + 16, self.topo + i * (self.CAT_H + self.CAT_GAP) + self.CAT_H / 2

    def resizeEvent(self, ev):
        self._geometria()
        self._alvos(instantaneo=True)
        super().resizeEvent(ev)

    # ---- estado
    def ir_para(self, k):
        if self.hist is None:
            return
        self.k = max(-1, min(k, self.N - 1))
        self.tsim = (self.k + 1) * self.passo
        n = self.n0 if self.k < 0 else self.hist[self.k]
        c = self.catracas_no_passo(self.k)
        self.fila, self.saindo = [], []
        self.cats = [None] * self.cmax
        for i in range(min(n, c)):
            self.cats[i] = Aluno(*self.pos_cat(i))
            self.cats[i].estado = 'catraca'
        for j in range(n - min(n, c)):
            self.fila.append(Aluno(*self.pos_fila(j)))
        self._alvos(instantaneo=True)
        self.mudou.emit(self.k)
        self.update()

    def _ocupar(self, c):
        for i in range(c):
            if self.cats[i] is None and self.fila:
                al = self.fila.pop(0)
                al.estado = 'catraca'
                self.cats[i] = al

    def _alvos(self, instantaneo=False):
        if self.hist is None:
            return
        for j, al in enumerate(self.fila):
            al.tx, al.ty = self.pos_fila(j)
        for i, al in enumerate(self.cats):
            if al:
                al.tx, al.ty = self.pos_cat(i)
        if instantaneo:
            for al in self.fila + [a for a in self.cats if a]:
                al.x, al.y = al.tx, al.ty

    def _aplicar(self, i):
        e = self.ev[i]
        c = self.catracas_no_passo(i)
        if e == 1:
            antes = self.n0 if i == 0 else self.hist[i - 1]
            for j in range(max(1, self.hist[i] - antes)):  # chegada em grupo
                x, y = self.pos_fila(len(self.fila))
                self.fila.append(Aluno(x - 20 - 10 * j, y, a=0.0))
        elif e == 4:
            self.aviso_k = 1.0
        elif e == 2:
            ocup = [j for j, al in enumerate(self.cats) if al]
            if ocup:
                j = self.rng.choice(ocup)
                al = self.cats[j]
                self.cats[j] = None
                al.estado, al.tx, al.ta = 'passou', self.width() + 30, 0.0
                self.saindo.append(al)
        elif e == 3:
            if self.fila:
                al = self.fila.pop(self.rng.randrange(len(self.fila)))
            else:  # fechou uma catraca com gente ainda nela
                ocup = [j for j, a in enumerate(self.cats) if a and j >= c] or [j for j, a in enumerate(self.cats) if a]
                if not ocup:
                    return
                j = ocup[0]
                al, self.cats[j] = self.cats[j], None
            al.estado, al.ty, al.ta = 'desistiu', al.y - 22, 0.0
            self.saindo.append(al)
        self._ocupar(c)

    # ---- reprodução
    def tocar(self, sim):
        if self.hist is None:
            return
        if sim and self.k >= self.N - 1:
            self.ir_para(-1)
        self.rodando = sim

    def _quadro(self):
        dt = min(self.relogio.restart() / 1000, 0.1)
        if self.hist is None:
            return
        if self.rodando:
            self.tsim += dt * self.vel
            alvo = min(int(self.tsim / self.passo) - 1, self.N - 1)
            if alvo - self.k > 400:
                self.ir_para(alvo)
            elif alvo > self.k:
                for i in range(self.k + 1, alvo + 1):
                    self._aplicar(i)
                self.k = alvo
                self._alvos()
                self.mudou.emit(self.k)
            if self.k >= self.N - 1:
                self.rodando = False
                self.terminou.emit()
        f = 1 - math.exp(-dt * 11)
        fa = 1 - math.exp(-dt * 5)
        vivos = []
        for al in self.fila + [a for a in self.cats if a] + self.saindo:
            al.x += (al.tx - al.x) * f
            al.y += (al.ty - al.y) * f
            al.a += (al.ta - al.a) * (fa if al.estado in ('passou', 'desistiu') else f)
        for al in self.saindo:
            if al.a > 0.03:
                vivos.append(al)
        self.saindo = vivos
        self.aviso_k = max(0.0, self.aviso_k - dt * 1.5)
        self.update()

    # ---- desenho
    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.t
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t['surface2']))
        p.drawRoundedRect(QRectF(self.rect()), 10, 10)
        if self.hist is None:
            p.setPen(QColor(t['muted']))
            p.drawText(self.rect(), Qt.AlignCenter, 'Rode a simulação para ver a fila.')
            return
        c = self.catracas_no_passo(self.k)
        fonte = QFont(self.font())
        fonte.setPointSizeF(8.5)
        p.setFont(fonte)
        # catracas
        for i in range(self.cmax):
            y = self.topo + i * (self.CAT_H + self.CAT_GAP)
            r = QRectF(self.cat_x, y, self.CAT_W, self.CAT_H)
            aberta = i < c
            pen = QPen(QColor(t['ink'] if aberta else t['line']), 1.4)
            if not aberta:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(QColor(t['surface']))
            p.drawRoundedRect(r, 7, 7)
            p.setPen(QColor(t['ink'] if aberta else t['muted']))
            p.drawText(r.adjusted(30, 0, 0, 0), Qt.AlignVCenter | Qt.AlignLeft, f'Catraca {i + 1}' if aberta else 'fechada')
        # setas de entrada e saída
        p.setPen(QColor(t['muted']))
        p.drawText(QRectF(self.cat_x + self.CAT_W + 6, self.topo, 60, self.CAT_H), Qt.AlignVCenter | Qt.AlignLeft, 'saída →')
        # alunos
        cores = {'espera': t['espera'], 'catraca': t['cat'], 'passou': t['ok'], 'desistiu': t['alert']}
        p.setPen(Qt.NoPen)
        for al in self.fila + [a for a in self.cats if a] + self.saindo:
            cor = QColor(cores[al.estado])
            cor.setAlphaF(max(0.0, min(1.0, al.a)))
            p.setBrush(cor)
            p.drawEllipse(QPointF(al.x, al.y), 5.2, 5.2)
        excesso = len(self.fila) - self.cap * self.linhas
        if excesso > 0:
            x, y = self.pos_fila(self.cap * self.linhas - 1)
            p.setPen(QColor(t['ink']))
            p.drawText(QPointF(x - 4, y + 18), f'+{excesso}')
        if self.aviso_k > 0:
            cor = QColor(t['alert'])
            cor.setAlphaF(self.aviso_k)
            p.setPen(cor)
            p.drawText(QRectF(8, self.height() - 22, 300, 18), Qt.AlignLeft, f'fila cheia (K = {self.K}): aluno não entrou')


class LinhaTempo(QWidget):
    """Mini gráfico da réplica animada; clicar ou arrastar muda o momento."""
    buscar = Signal(int)

    def __init__(self, tema):
        super().__init__()
        self.t = tema
        self.hist = None
        self.k = -1
        self.setFixedHeight(58)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)

    def carregar(self, hist, media, pico, passo):
        self.hist, self.media, self.pico, self.passo = hist, media, pico, passo
        self.ymax = max(max(hist), max(media), 1)
        self.update()

    def definir(self, k):
        self.k = k
        self.update()

    def _x(self, i):
        return 6 + (i + 1) / len(self.hist) * (self.width() - 12)

    def _k(self, x):
        return int(round((x - 6) / (self.width() - 12) * len(self.hist))) - 1

    def mousePressEvent(self, ev):
        if self.hist:
            self.buscar.emit(self._k(ev.position().x()))

    def mouseMoveEvent(self, ev):
        if self.hist and ev.buttons():
            self.buscar.emit(self._k(ev.position().x()))

    def keyPressEvent(self, ev):
        if not self.hist:
            return
        passo_min = int(60 / self.passo)
        if ev.key() == Qt.Key_Right:
            self.buscar.emit(self.k + passo_min)
        elif ev.key() == Qt.Key_Left:
            self.buscar.emit(self.k - passo_min)
        else:
            super().keyPressEvent(ev)

    def paintEvent(self, _):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        t = self.t
        if not self.hist:
            return
        h, base = self.height() - 8, self.height() - 4
        T = len(self.pico)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(t['pico']))
        for m, pk in enumerate(self.pico):
            if pk:
                x0 = 6 + m / T * (self.width() - 12)
                p.drawRect(QRectF(x0, 2, (self.width() - 12) / T + 0.5, h + 2))
        y = lambda v: base - v / self.ymax * (h - 4)
        passo = max(1, len(self.hist) // max(1, self.width()))
        for serie, cor, larg, tracejado in ((self.media, t['muted'], 1.2, True), (self.hist, t['series']['base'], 1.6, False)):
            cam = QPainterPath()
            for j, i in enumerate(range(0, len(serie), passo)):
                pt = QPointF(self._x(i), y(serie[i]))
                cam.moveTo(pt) if j == 0 else cam.lineTo(pt)
            pen = QPen(QColor(cor), larg)
            if tracejado:
                pen.setStyle(Qt.DashLine)
            p.setPen(pen)
            p.setBrush(Qt.NoBrush)
            p.drawPath(cam)
        x = self._x(max(self.k, -1))
        p.setPen(QPen(QColor(t['ink']), 2))
        p.drawLine(QPointF(x, 0), QPointF(x, self.height()))
        if self.hasFocus():
            p.setPen(QPen(QColor(t['accent']), 1.5))
            p.setBrush(Qt.NoBrush)
            p.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 6, 6)


# =================================================================== gráficos (matplotlib)
def _fonte_mpl():
    nomes = {f.name for f in font_manager.fontManager.ttflist}
    for n in ('Segoe UI', 'Inter', 'Helvetica Neue', 'Arial'):
        if n in nomes:
            return [n, 'DejaVu Sans']
    return ['DejaVu Sans']


class Grafico(FigureCanvasQTAgg):
    def __init__(self, altura=290):
        self.fig = Figure(figsize=(8, altura / 100), dpi=100, layout='constrained')
        super().__init__(self.fig)
        self.setMinimumHeight(altura)
        self.ax = self.fig.add_subplot()
        self.dica = None
        self.cursor = None
        self.mpl_connect('motion_notify_event', self._mover)
        self.mpl_connect('figure_leave_event', lambda _: self._sair())

    def limpar(self, t, t0):
        self.fig.clear()
        self.fig.set_facecolor(t['surface'])
        ax = self.ax = self.fig.add_subplot()
        ax.set_facecolor(t['surface'])
        for s in ('top', 'right'):
            ax.spines[s].set_visible(False)
        for s in ('left', 'bottom'):
            ax.spines[s].set_color(t['line'])
        ax.tick_params(colors=t['muted'], labelsize=8.5, length=0, pad=6)
        ax.grid(axis='y', color=t['line'], lw=.7)
        ax.set_axisbelow(True)
        ax.xaxis.set_major_locator(MaxNLocator(nbins=10, steps=[1, 2, 2.5, 5, 10]))
        if t0 is not None:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: (t0 + timedelta(minutes=x)).strftime('%H:%M')))
        else:
            ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f'{x:.0f} min'))
        self.cursor = ax.axvline(0, color=t['muted'], lw=.9, alpha=0)
        self.dica = None
        return ax

    def faixas_pico(self, pico, cor):
        m = 0
        while m < len(pico):
            if pico[m]:
                f = m
                while f < len(pico) and pico[f]:
                    f += 1
                self.ax.axvspan(m, f, color=cor, lw=0, zorder=0)
                m = f
            else:
                m += 1

    def _mover(self, ev):
        if ev.inaxes is not self.ax or not self.dica or ev.xdata is None:
            self._sair()
            return
        x, html = self.dica(ev.xdata)
        self.cursor.set_xdata([x, x])
        self.cursor.set_alpha(.7)
        self.draw_idle()
        QToolTip.showText(QCursor.pos() + QPoint(16, 12), html, self)

    def _sair(self):
        if self.cursor is not None and self.cursor.get_alpha():
            self.cursor.set_alpha(0)
            self.draw_idle()
        QToolTip.hideText()


# =================================================================== cartão de cenário
class Cartao(QFrame):
    clicado = Signal(str)

    def __init__(self, nome, r, base, t):
        super().__init__()
        self.setObjectName('cartao')
        self.nome = nome
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip('Clique para ver este cenário na animação')
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 14)
        lay.setSpacing(2)
        topo = QHBoxLayout()
        risco = QFrame()
        risco.setFixedSize(18, 4)
        risco.setStyleSheet(f'background: {t["series"][r["chave"]]}; border-radius: 2px; border: none;')
        topo.addWidget(risco, 0, Qt.AlignVCenter)
        topo.addWidget(rotulo(NOMES_LONGOS[r['chave']].upper(), 'rotulo', quebra=True), 1)
        lay.addLayout(topo)
        lay.addSpacing(4)
        lay.addWidget(rotulo(f'{br(r["W"], 1)} min', 'grande'))
        lay.addWidget(rotulo(f'tempo médio no sistema (± {br(r["Wic"], 1)})', 'dica'))
        if r is not base and base['W'] > 0:
            dif = (r['W'] - base['W']) / base['W']
            txt = f'{"−" if dif < 0 else "+"}{br(abs(dif) * 100, 0)}% de espera contra 1 catraca'
            lay.addWidget(rotulo(txt, 'bom' if dif < 0 else 'ruim', quebra=True))
        else:
            lay.addWidget(rotulo('situação atual', 'dica'))
        if r.get('custo', 0) > 0.5:
            txt = f'custo: {br(r["custo"], 0)} min de catraca extra'
            if r.get('efic') is not None:
                txt += f' · poupa {br(r["efic"], 0)} min de espera por min'
            lay.addWidget(rotulo(txt, 'dica', quebra=True))
        if r.get('nota'):
            pre = '' if r.get('politica') else 'sem catraca extra: '
            lay.addWidget(rotulo(pre + r['nota'], 'dica', quebra=True))
        lay.addSpacing(8)
        g = QGridLayout()
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(2)
        for i, (rot, val) in enumerate((('alunos em média', br(r['L'], 1)), ('pior momento', br(r['pior'], 1)),
                                         ('tempo com fila ≥ 10', pct(r['longa'])))):
            g.addWidget(rotulo(rot, 'dica'), i, 0)
            v = rotulo(val)
            v.setStyleSheet('font-weight: 600;')
            g.addWidget(v, i, 1, Qt.AlignRight)
        lay.addLayout(g)

    def selecionar(self, sim):
        self.setProperty('sel', 'true' if sim else 'false')
        repolir(self)

    def mousePressEvent(self, _):
        self.clicado.emit(self.nome)


# =================================================================== janela
class Janela(QMainWindow):
    def __init__(self, arquivos_iniciais):
        super().__init__()
        self.setWindowTitle('Simulador da fila da catraca · RU UFOPA')
        self.resize(1400, 900)
        hints = QGuiApplication.styleHints()
        escuro = hasattr(hints, 'colorScheme') and hints.colorScheme() == Qt.ColorScheme.Dark
        self.nome_tema = 'escuro' if escuro else 'claro'
        self.t = dict(TEMAS[self.nome_tema])
        self.fontes = []
        self.med = None
        self.medido = {}
        self.editado = set()
        self._prog = False
        self.saida = None
        self.rodada = None
        self.anim_nome = '1 catraca'
        self.anim_rep = 0
        self.cartoes = {}
        self._montar()
        self.aplicar_tema()
        self._carregar_exemplos()
        if arquivos_iniciais:
            self.abrir_csvs(arquivos_iniciais)
        elif self.fontes:
            self._selecionar(self._indice_padrao())
            self.trocar_fonte()

    # ------------------------------------------------------------ montagem
    def _montar(self):
        raiz = QWidget()
        raiz.setObjectName('raiz')
        self.setCentralWidget(raiz)
        geral = QVBoxLayout(raiz)
        geral.setContentsMargins(20, 16, 20, 16)
        geral.setSpacing(14)

        cab = QHBoxLayout()
        tit = QVBoxLayout()
        tit.setSpacing(2)
        tit.addWidget(rotulo('Simulador da fila da catraca', nome='titulo'))
        tit.addWidget(rotulo('RU da UFOPA · Avaliação de Desempenho · cadeia de Markov do analise_catraca.py', 'dica'))
        cab.addLayout(tit, 1)
        self.btn_tema = QPushButton()
        self.btn_tema.clicked.connect(self.trocar_tema)
        cab.addWidget(self.btn_tema, 0, Qt.AlignVCenter)
        geral.addLayout(cab)

        corpo = QHBoxLayout()
        corpo.setSpacing(16)
        geral.addLayout(corpo, 1)

        # ---- barra lateral
        lateral = QScrollArea()
        lateral.setWidgetResizable(True)
        lateral.setFixedWidth(350)
        lateral.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        miolo = QWidget()
        miolo.setObjectName('miolo')
        lat = QVBoxLayout(miolo)
        lat.setContentsMargins(0, 0, 8, 0)
        lat.setSpacing(12)
        lateral.setWidget(miolo)
        corpo.addWidget(lateral)

        # dados
        f, l = card()
        l.addWidget(rotulo('Dados', nome='h2'))
        self.linha_dias = QHBoxLayout()
        self.linha_dias.setSpacing(6)
        l.addLayout(self.linha_dias)
        self.grupo_dias = QButtonGroup(self)
        self.grupo_dias.setExclusive(True)
        self.botoes_dia = {}
        self.dia = None
        self.variante_lb = rotulo('', 'campo', quebra=True)
        l.addWidget(self.variante_lb)
        self.variante = QComboBox()
        self.variante.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.variante.setMinimumContentsLength(12)
        self.variante.currentIndexChanged.connect(lambda _: self.trocar_fonte())
        l.addWidget(self.variante)
        self.fonte_desc = rotulo('', 'dica', quebra=True)
        l.addWidget(self.fonte_desc)
        b = QPushButton('Abrir CSVs da coleta…')
        b.clicked.connect(lambda: self.abrir_csvs())
        l.addWidget(b)
        self.msg_arquivos = rotulo('', 'erro', quebra=True)
        self.msg_arquivos.hide()
        l.addWidget(self.msg_arquivos)
        lat.addWidget(f)

        # parâmetros
        f, l = card()
        l.addWidget(rotulo('Chegadas e Atendimento', nome='h2'))
        self.caixa_manual = QWidget()
        gm = QGridLayout(self.caixa_manual)
        gm.setContentsMargins(0, 0, 0, 0)
        gm.setHorizontalSpacing(10)
        self.m_T = self._spin(QSpinBox, 5, 600, 105)
        self.m_pi = self._spin(QSpinBox, 0, 600, 20)
        self.m_pf = self._spin(QSpinBox, 0, 600, 60)
        for col, (rot, w) in enumerate((('Duração (min)', self.m_T), ('Pico do min', self.m_pi), ('até o min', self.m_pf))):
            gm.addWidget(rotulo(rot, 'campo'), 0, col)
            gm.addWidget(w, 1, col)
        l.addWidget(self.caixa_manual)

        self.campos = {}
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(2)
        defs = [
            ('lam_cal', 'λ calma', 'chegadas/min', QDoubleSpinBox, 0, 60, 2),
            ('lam_pic', 'λ pico', 'chegadas/min', QDoubleSpinBox, 0, 60, 2),
            ('mu', 'μ por catraca', 'atendimentos/min', QDoubleSpinBox, 0.1, 60, 2),
            ('theta', 'θ desistência', '/min por aluno', QDoubleSpinBox, 0, 5, 3),
            ('n0', 'Fila inicial', 'alunos no sistema', QSpinBox, 0, 999, 0),
            ('limiar', 'Limiar de pico', 'chegadas/min', QDoubleSpinBox, 0, 60, 2),
        ]
        for i, (k, nome, unid, cls, lo, hi, dec) in enumerate(defs):
            r, c = divmod(i, 2)
            caixa = QVBoxLayout()
            caixa.setSpacing(3)
            caixa.addWidget(rotulo(f'{nome}<br><span style="font-weight:400">{unid}</span>', 'campo'))
            w = self._spin(cls, lo, hi, 0, dec)
            if k == 'limiar':
                w.setSpecialValueText('automático')
                w.valueChanged.connect(self._limiar_mudou)
            else:
                w.valueChanged.connect(lambda _v, k=k: self._editou(k))
            caixa.addWidget(w)
            med = rotulo('', 'medido', quebra=True)
            caixa.addWidget(med)
            self.campos[k] = (w, med)
            g.addLayout(caixa, r, c)
        l.addLayout(g)
        for w in (self.m_T, self.m_pi, self.m_pf):
            w.valueChanged.connect(lambda _v: self._pendente())
        linha_regra = QHBoxLayout()
        linha_regra.addWidget(rotulo('Regra do pico', 'campo'))
        self.regra = QComboBox()
        self.regra.addItem('1,5 × a média (slide 59)', 'slide59')
        self.regra.addItem('duas médias (versão anterior)', 'duas-medias')
        self.regra.setToolTip('Como o limiar automático separa calma e pico (sempre pelas chegadas por minuto, '
                              'na média móvel de 5 min).')
        self.regra.currentIndexChanged.connect(lambda _i: self._limiar_mudou())
        linha_regra.addWidget(self.regra, 1)
        l.addLayout(linha_regra)
        self.btn_medidos = QPushButton('↺ Voltar aos valores medidos')
        self.btn_medidos.setProperty('papel', 'fino')
        self.btn_medidos.clicked.connect(self.restaurar_medidos)
        l.addWidget(self.btn_medidos)
        lat.addWidget(f)

        # cenários
        f, l = card()
        l.addWidget(rotulo('Cenários', nome='h2'))
        self.checks = {}
        for k in ('base', 'semdes', 'pico2', 'fila', 'toda2', 'rapido', 'escal', 'pers'):
            cb = QCheckBox(NOMES_LONGOS[k])
            cb.setChecked(k != 'pers')
            if k == 'base':
                cb.setEnabled(False)
                cb.setToolTip('Sempre simulado: é a base da validação.')
            cb.toggled.connect(lambda _v: self._pendente())
            self.checks[k] = cb
            l.addWidget(cb)
        linha_g = QHBoxLayout()
        linha_g.setContentsMargins(24, 0, 0, 0)
        linha_g.addWidget(rotulo('Pela fila: abre com N alunos (fecha com N/2)', 'campo', quebra=True), 1)
        self.p_gatilho = self._spin(QSpinBox, 0, 200, 0)
        self.p_gatilho.setSpecialValueText('automático')
        self.p_gatilho.setToolTip('Automático: testa N = 3 a 30 e usa o que poupa mais espera por minuto de catraca aberta, '
                                  'entre os que esperam no máximo o mesmo que a 2ª catraca no horário de pico.')
        self.p_gatilho.valueChanged.connect(lambda _v: self._pendente())
        linha_g.addWidget(self.p_gatilho)
        self.caixa_gatilho = QWidget()
        self.caixa_gatilho.setLayout(linha_g)
        l.addWidget(self.caixa_gatilho)
        self.checks['fila'].toggled.connect(self.caixa_gatilho.setVisible)
        self.caixa_pers = QWidget()
        gp = QGridLayout(self.caixa_pers)
        gp.setContentsMargins(24, 2, 0, 0)
        gp.setHorizontalSpacing(10)
        self.pers_calma = self._spin(QSpinBox, 1, 6, 1)
        self.pers_pico = self._spin(QSpinBox, 1, 6, 3)
        self.pers_desist = QCheckBox('com desistência')
        self.pers_desist.setChecked(True)
        gp.addWidget(rotulo('Catracas na calma', 'campo'), 0, 0)
        gp.addWidget(rotulo('Catracas no pico', 'campo'), 0, 1)
        gp.addWidget(self.pers_calma, 1, 0)
        gp.addWidget(self.pers_pico, 1, 1)
        gp.addWidget(self.pers_desist, 2, 0, 1, 2)
        for w in (self.pers_calma, self.pers_pico):
            w.valueChanged.connect(lambda _v: self._pendente())
        self.pers_desist.toggled.connect(lambda _v: self._pendente())
        self.checks['pers'].toggled.connect(self.caixa_pers.setVisible)
        self.caixa_pers.setVisible(False)
        l.addWidget(self.caixa_pers)
        lat.addWidget(f)

        # simulação
        f, l = card()
        l.addWidget(rotulo('Simulação', nome='h2'))
        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(3)
        self.p_K = self._spin(QSpinBox, 5, 2000, 200)
        self.p_reps = self._spin(QSpinBox, 2, 5000, 500)
        self.p_seed = self._spin(QSpinBox, 0, 2_000_000_000, 42)
        self.p_passo = self._spin(QDoubleSpinBox, 0.5, 60, 5, 1)
        for i, (rot, w) in enumerate((('Capacidade K', self.p_K), ('Réplicas', self.p_reps),
                                      ('Semente', self.p_seed), ('Passo (s)', self.p_passo))):
            r, c = divmod(i, 2)
            g.addWidget(rotulo(rot, 'campo'), r * 2, c)
            g.addWidget(w, r * 2 + 1, c)
            w.valueChanged.connect(lambda _v: self._pendente())
        l.addLayout(g)
        self.p_grupo = QCheckBox('Refinamento: chegadas em grupo')
        self.p_grupo.setChecked(False)
        self.p_grupo.setToolTip('Desligado = M/M/1, chegadas uma a uma (modelo dos slides). Ligado: chegadas a até 1,5 s uma da '
                                'outra formam um grupo, o que reproduz as rajadas (D > 1) que o M/M/1 não imita. Sem dados, fica desligado.')
        self.p_grupo.toggled.connect(lambda _v: self._pendente())
        l.addWidget(self.p_grupo)
        l.addSpacing(4)
        self.btn_sim = QPushButton('Simular')
        self.btn_sim.setProperty('papel', 'primario')
        self.btn_sim.clicked.connect(self.simular)
        l.addWidget(self.btn_sim)
        self.barra = QProgressBar()
        self.barra.setTextVisible(False)
        self.barra.hide()
        l.addWidget(self.barra)
        self.msg_sim = rotulo('', 'dica', quebra=True)
        l.addWidget(self.msg_sim)
        lat.addWidget(f)
        lat.addStretch(1)

        # ---- resultados em abas
        self.abas = QTabWidget()
        self.abas.setDocumentMode(True)
        corpo.addWidget(self.abas, 1)
        self.abas.addTab(self._aba_geral(), 'Visão geral')
        self.abas.addTab(self._aba_graficos(), 'Gráficos')
        self.abas.addTab(self._aba_tabelas(), 'Modelo e Validação')

    def _rolagem(self):
        sa = QScrollArea()
        sa.setWidgetResizable(True)
        sa.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        w = QWidget()
        w.setObjectName('miolo')
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 12, 8, 12)
        lay.setSpacing(14)
        sa.setWidget(w)
        return sa, lay

    def _aba_geral(self):
        sa, lay = self._rolagem()
        linha_pr = QHBoxLayout()
        linha_pr.setSpacing(12)
        f, l = card()
        l.addWidget(rotulo('PERGUNTA DA EQUIPE', 'rotulo'))
        self.pergunta_lb = rotulo(PERGUNTA, 'conclusao', quebra=True)
        l.addWidget(self.pergunta_lb)
        l.addStretch(1)
        linha_pr.addWidget(f, 1)
        f, l = card()
        l.addWidget(rotulo('RESPOSTA', 'rotulo'))
        self.resposta_lb = rotulo('Simulando…', 'grande', quebra=True)
        l.addWidget(self.resposta_lb)
        self.resposta_det = rotulo('', 'dica', quebra=True)
        l.addWidget(self.resposta_det)
        l.addStretch(1)
        linha_pr.addWidget(f, 1)
        lay.addLayout(linha_pr)

        f, l = card()
        l.addWidget(rotulo('CONCLUSÃO', 'rotulo'))
        self.conclusao = rotulo('Simulando…', 'conclusao', quebra=True)
        l.addWidget(self.conclusao)
        self.achado_lb = rotulo('', 'dica', quebra=True)
        l.addWidget(self.achado_lb)
        self.selo_valid = rotulo('', 'dica', quebra=True)
        l.addWidget(self.selo_valid)
        lay.addWidget(f)

        self.grade_cartoes = QGridLayout()
        self.grade_cartoes.setSpacing(12)
        lay.addLayout(self.grade_cartoes)

        f, l = card()
        topo = QHBoxLayout()
        tx = QVBoxLayout()
        tx.setSpacing(2)
        tx.addWidget(rotulo('A fila andando', nome='h2'))
        tx.addWidget(rotulo('Uma réplica da simulação, passo a passo. Clique num cartão acima para trocar o cenário.', 'dica', quebra=True))
        topo.addLayout(tx, 1)
        self.anim_nome_lb = rotulo('', 'rotulo')
        topo.addWidget(self.anim_nome_lb, 0, Qt.AlignTop)
        l.addLayout(topo)

        placar = QHBoxLayout()
        placar.setSpacing(22)
        caixa = QVBoxLayout()
        caixa.setSpacing(0)
        caixa.addWidget(rotulo('HORÁRIO', 'rotulo'))
        self.a_hora = rotulo('--:--', 'num')
        caixa.addWidget(self.a_hora)
        placar.addLayout(caixa)
        self.a_fase = rotulo('calma', 'selo-calma')
        placar.addWidget(self.a_fase, 0, Qt.AlignVCenter)
        self.a_nums = {}
        for k, rot in (('esp', 'esperando'), ('cat', 'na catraca'), ('cheg', 'chegaram'),
                       ('pass', 'passaram'), ('des', 'desistiram'), ('abertas', 'catracas abertas')):
            cx = QVBoxLayout()
            cx.setSpacing(0)
            n = rotulo('0', 'num')
            cx.addWidget(n)
            cx.addWidget(rotulo(rot, 'dica'))
            self.a_nums[k] = n
            placar.addLayout(cx)
        placar.addStretch(1)
        l.addLayout(placar)

        self.palco = Palco(self.t)
        self.palco.mudou.connect(self._anim_mudou)
        self.palco.terminou.connect(lambda: self.btn_play.setText('▶  Reproduzir'))
        l.addWidget(self.palco)
        self.linha = LinhaTempo(self.t)
        self.linha.buscar.connect(self.palco.ir_para)
        l.addWidget(self.linha)
        leg = rotulo('', 'dica', quebra=True)
        self.leg_anim = leg
        l.addWidget(leg)

        ctl = QHBoxLayout()
        ctl.setSpacing(8)
        self.btn_play = QPushButton('▶  Reproduzir')
        self.btn_play.setProperty('papel', 'primario')
        self.btn_play.clicked.connect(self._play)
        ctl.addWidget(self.btn_play)
        ctl.addSpacing(8)
        ctl.addWidget(rotulo('Velocidade', 'campo'))
        self.grupo_vel = QButtonGroup(self)
        for v in (5, 15, 30, 60, 120):
            b = QPushButton(f'{v}×')
            b.setProperty('papel', 'seg')
            b.setCheckable(True)
            b.setChecked(v == 30)
            self.grupo_vel.addButton(b, v)
            ctl.addWidget(b)
        self.grupo_vel.idClicked.connect(lambda v: setattr(self.palco, 'vel', v))
        ctl.addSpacing(8)
        b = QPushButton('↻  Outra réplica')
        b.clicked.connect(self._outra_replica)
        ctl.addWidget(b)
        ctl.addStretch(1)
        l.addLayout(ctl)
        lay.addWidget(f)
        lay.addStretch(1)
        return sa

    def _aba_graficos(self):
        sa, lay = self._rolagem()
        self.g_cheg = Grafico(270)
        self.g_valid = Grafico(320)
        self.g_cen = Grafico(320)
        self.card_valid = None
        for tit, dica, g in (
            ('Chegadas por minuto', 'Faixa rosada = minutos de pico. As linhas tracejadas são a capacidade com 1 e 2 catracas: '
             'quando as chegadas passam da capacidade, a fila cresce. Passe o mouse para ver os valores.', self.g_cheg),
            ('Validação: fila reconstruída × simulada', 'Pontos = alunos no sistema reconstruídos a partir dos eventos da coleta. '
             'Linha = média das réplicas com 1 catraca; faixa = 5% a 95% das réplicas.', self.g_valid),
            ('Cenários ao longo do tempo', 'Alunos no sistema, média das réplicas. Mesma semente em todos os cenários.', self.g_cen),
        ):
            f, l = card()
            l.addWidget(rotulo(tit, nome='h2'))
            l.addWidget(rotulo(dica, 'dica', quebra=True))
            l.addWidget(g)
            lay.addWidget(f)
            if g is self.g_valid:
                self.card_valid = f
        lay.addStretch(1)
        return sa

    def _aba_tabelas(self):
        sa, lay = self._rolagem()
        self.tabs = {}
        self.dica_valid = ''
        for k, tit, dica in (
            ('cen', 'Cenários', '± é o IC de 95% entre réplicas. Uma hora simulada é uma amostra, não uma medida. '
             'Custo = minutos de catraca extra aberta; eficiência = minutos de espera poupados, somando os alunos, por minuto de catraca extra.'),
            ('busca', 'Pergunta da equipe: gatilho da 2ª catraca pela fila', 'A 2ª catraca abre quando a fila chega a N e fecha '
             'quando cai a N/2. O melhor N é o mais eficiente entre os que esperam no máximo o mesmo que a 2ª catraca no '
             'horário de pico. Com o gatilho em "automático"; menos réplicas por linha.'),
            ('valid', 'Validação', 'Fila reconstruída × simulada nos mesmos instantes. Se algum item ficar fora da faixa, '
             'revejam primeiro as medições: contagens, separação calma/pico e os atendimentos cronometrados. '
             'No M/M/1 (chegadas uma a uma) o D fica perto de 1 e falha contra os dados; ligue "Refinamento: chegadas em grupo" '
             'para comparar.'),
            ('sens', 'Sensibilidade a μ', 'μ é a medida mais incerta do estudo: o mesmo cálculo com o IC de μ e com o '
             'tempo cronometrado (otimista: mede só a passagem, sem a troca entre alunos). Menos réplicas por linha.'),
            ('mm1', 'Modelo M/M/1 por trecho', ''),
            ('verif', 'Verificação', 'Simulador com λ de calma e 1 catraca por 200 h simuladas contra as fórmulas: '
             'M/M/1 com chegadas uma a uma e M^X/M/1 com os grupos, L = ρ(1 + D)/(2(1 − ρ)), D = E[k²]/E[k]. '
             'Se os dois lados ficam próximos, o código faz o que o modelo diz.'),
        ):
            f, l = card()
            l.addWidget(rotulo(tit, nome='h2'))
            tb = QTableWidget()
            tb.setEditTriggers(QTableWidget.NoEditTriggers)
            tb.setSelectionMode(QTableWidget.NoSelection)
            tb.setFocusPolicy(Qt.NoFocus)
            tb.verticalHeader().hide()
            tb.setAlternatingRowColors(True)
            tb.setShowGrid(False)
            tb.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            tb.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            l.addWidget(tb)
            info = rotulo(dica, 'dica', quebra=True)
            if k == 'valid':
                self.dica_valid = dica
            l.addWidget(info)
            self.tabs[k] = (tb, info, f)
            lay.addWidget(f)
        lay.addStretch(1)
        return sa

    def _spin(self, cls, lo, hi, val, dec=2):
        w = cls()
        w.setRange(lo, hi)
        if cls is QDoubleSpinBox:
            w.setDecimals(dec)
            w.setSingleStep(10 ** -min(dec, 2) if dec else 1)
        w.setValue(val)
        w.setKeyboardTracking(False)
        return w

    # ------------------------------------------------------------ tema
    def trocar_tema(self):
        self.nome_tema = 'claro' if self.nome_tema == 'escuro' else 'escuro'
        self.aplicar_tema()

    def aplicar_tema(self):
        self.t.clear()
        self.t.update(TEMAS[self.nome_tema])  # o mesmo dicionário é usado pelo palco e pela linha do tempo
        QApplication.instance().setStyleSheet(qss(self.t))
        self.btn_tema.setText('☀  Tema claro' if self.nome_tema == 'escuro' else '☾  Tema escuro')
        if self.saida:
            self.mostrar(self.saida, manter_anim=True)
        self.palco.update()
        self.linha.update()

    # ------------------------------------------------------------ fontes de dados
    def _fonte_de(self, rot, desc, dados):
        """Monta uma fonte a partir de [(d, s)]: μ pelas saídas com fila; o cronometrado fica como referência."""
        vals = [v for d, _ in dados for v in ac.vals_mu(d)]
        est = ac.resumo_mu(vals)
        atend = [a for d, _ in dados for a in d['atend'] if a > 0]
        mu_cron = 60 / (sum(atend) / len(atend)) if atend else None
        if est:
            mu = est['mu']
            mu_txt = f'saídas/min com fila, {est["n"]} min, ± {br(est["ic"])}'
        elif mu_cron:
            mu, mu_txt = mu_cron, 'cronometrado, otimista'
        else:
            mu, mu_txt = None, None
        if mu_cron and est:
            mu_txt += f'; cronometrado (só a passagem) {br(mu_cron)}'
        return {'rotulo': rot, 'desc': desc, 'mu': mu, 'mu_txt': mu_txt, 'mu_est': est, 'mu_cron': mu_cron, 'K': 200}

    def _carregar_exemplos(self):
        for dia, var, rel, sessao, ajuste, desc in EXEMPLOS:
            caminho = os.path.join(PASTA, rel)
            if not os.path.exists(caminho):
                continue
            sess = ac.ler([caminho])
            # todas as sessões do arquivo (o dia inteiro), com o mesmo ajuste: μ sai do dia, não só da sessão
            dia_todo = {}
            for nome, s in sorted(sess.items()):
                s2, txt = ac.ajustar(s, ajuste)
                d = ac.preparar(nome, s2)
                if d:
                    dia_todo[nome] = (d, s2, txt)
            for nome, (d, s2, txt) in dia_todo.items():
                if sessao and nome != sessao:
                    continue
                f = self._fonte_de(f'{dia} · {var}', desc + (f' Ajuste: {txt.rstrip(".")}.' if txt and ajuste != 'nenhum' else ''),
                                   [(x[0], x[1]) for x in dia_todo.values()])
                if len(dia_todo) > 1 and f['mu_txt']:
                    f['mu_txt'] += f'; juntando as {len(dia_todo)} coletas do dia'
                f.update({'d': d, 't0': d['t0'], 'grupo': dia, 'variante': var})
                self.fontes.append(f)
        self.fontes.append({'rotulo': 'Sem dados (modelo manual)', 'grupo': 'Sem dados', 'variante': '',
                            'd': None, 'mu': 6.2, 'K': 200, 't0': None, 'mu_est': None, 'mu_cron': None,
                            'desc': 'Escolha a duração, o trecho de pico e as taxas. Sem dados não há validação.'})
        self._encher_combo()

    def _encher_combo(self, atual=None):
        """Refaz um botão por dia (na ordem em que aparecem em self.fontes) e seleciona a fonte `atual` (índice)."""
        for b in self.botoes_dia.values():
            self.grupo_dias.removeButton(b)
            b.setParent(None)
            b.deleteLater()
        self.botoes_dia = {}
        for f in self.fontes:
            g = f['grupo']
            if g in self.botoes_dia:
                continue
            b = QPushButton(g)
            b.setProperty('papel', 'seg')
            b.setCheckable(True)
            b.clicked.connect(lambda _c=False, g=g: self._escolher_dia(g))
            self.grupo_dias.addButton(b)
            self.linha_dias.addWidget(b)
            self.botoes_dia[g] = b
        if atual is not None:
            self._selecionar(atual)

    def _do_dia(self, dia):
        return [f for f in self.fontes if f['grupo'] == dia]

    def _selecionar(self, i):
        """Marca o botão do dia da fonte i e põe a variante dela na caixa (sem simular)."""
        f = self.fontes[i]
        self.dia = f['grupo']
        self.botoes_dia[self.dia].setChecked(True)
        do_dia = self._do_dia(self.dia)
        self._prog = True
        self.variante.clear()
        for x in do_dia:
            self.variante.addItem(x['variante'])
        self.variante.setCurrentIndex(do_dia.index(f))
        self._prog = False
        varias = len(do_dia) > 1
        self.variante.setVisible(varias)
        self.variante_lb.setVisible(varias)
        self.variante_lb.setText(VARIANTE.get(self.dia, 'Opção'))

    def _escolher_dia(self, dia):
        if dia == self.dia:
            return
        self._selecionar(self.fontes.index(self._do_dia(dia)[0]))
        self.trocar_fonte()

    def _indice_padrao(self):
        for i, f in enumerate(self.fontes):
            if (f['grupo'], f['variante']) == PADRAO:
                return i
        return 0

    def abrir_csvs(self, caminhos=None):
        if caminhos is None:
            caminhos, _ = QFileDialog.getOpenFileNames(self, 'CSVs da coleta (observadores A, B e C)', PASTA, 'CSV (*.csv);;Todos (*)')
            if not caminhos:
                return
        self.msg_arquivos.hide()
        try:
            sess = ac.ler(caminhos)
        except Exception as e:  # noqa: BLE001
            self.msg_arquivos.setText(f'Não consegui ler os arquivos: {e}')
            self.msg_arquivos.show()
            return
        dados = [(ac.preparar(n, s), s) for n, s in sorted(sess.items())]
        dados = [(d, s) for d, s in dados if d]
        if not dados:
            self.msg_arquivos.setText('Nenhuma sessão encontrada. Os arquivos precisam ser os CSVs exportados pela página de coleta.')
            self.msg_arquivos.show()
            return
        base = self._fonte_de('', '', dados)  # μ conjunto de todas as sessões abertas
        primeiro = len(self.fontes) - 1  # antes do "Modelo manual"
        for d, s in dados:
            desc = f'{len(caminhos)} arquivo(s) · {d["T"]} min · {sum(d["arr"])} chegadas · {sum(d["des"])} desistências.'
            if d['reconstruida'] and d['fila_final']:
                desc += f' A fila reconstruída termina com {d["fila_final"]}: faltou anotar algo (veja --comparar-ajustes).'
            if d['atend_aviso']:
                desc += ' Tempos cronometrados descartados (relógios de celulares diferentes).'
            if base['mu'] is None:
                desc += ' Sem minutos com fila nem cronometragem: informe μ.'
            f = dict(base, rotulo=f'{d["nome"]} (arquivo)', desc=desc, d=d, K=None, t0=d['t0'],
                     grupo='Arquivo', variante=d['nome'])
            self.fontes.insert(len(self.fontes) - 1, f)
        self._encher_combo(primeiro)
        self.trocar_fonte()

    def fonte_atual(self):
        do_dia = self._do_dia(self.dia)
        i = self.variante.currentIndex()
        return do_dia[i] if 0 <= i < len(do_dia) else (do_dia[0] if do_dia else None)

    def trocar_fonte(self):
        if self._prog:
            return
        f = self.fonte_atual()
        if not f:
            return
        self.fonte_desc.setText(f['desc'])
        manual = f['d'] is None
        self.caixa_manual.setVisible(manual)
        self.campos['limiar'][0].setEnabled(not manual)
        self.btn_medidos.setVisible(not manual)
        if self.card_valid is not None:
            self.card_valid.setVisible(not manual)
        self._prog = True
        if f['K']:
            self.p_K.setValue(f['K'])
        self.campos['limiar'][0].setValue(0)
        self._prog = False
        if not manual and sum(f['d']['arr']) == 0:
            self.msg_arquivos.setText('Esta sessão não tem chegadas registradas (o CSV do observador A está junto?).')
            self.msg_arquivos.show()
        self.restaurar_medidos()
        self.simular()

    # ------------------------------------------------------------ campos
    def _limiar_mudou(self):
        if self._prog:
            return
        self.restaurar_medidos(manter_mu=True)

    def restaurar_medidos(self, manter_mu=False):
        """Preenche os campos com o que foi medido na sessão. manter_mu=True (troca de limiar) preserva um μ digitado."""
        f = self.fonte_atual()
        mu_digitado = manter_mu and 'mu' in self.editado
        self.editado.clear()
        self.medido = {}
        self._prog = True
        if f['d'] is None:
            self.med = None
            for k, v in (('lam_cal', 3.5), ('lam_pic', 8.0), ('theta', 0.05), ('n0', 0), ('mu', f['mu'])):
                self.campos[k][0].setValue(v)
            for k in self.campos:
                self.campos[k][1].setText('')
        else:
            lim = self.campos['limiar'][0].value() or None
            self.med = md = ac.medir(f['d'], lim, regra=self.regra.currentData())
            self.medido = {'lam_cal': md['lam_cal'], 'lam_pic': md['lam_pic'], 'theta': md['theta'], 'n0': md['n0']}
            if mu_digitado:
                self.editado.add('mu')
            elif f['mu'] is not None:
                self.medido['mu'] = f['mu']
            for k, v in self.medido.items():
                self.campos[k][0].setValue(v if v is not None else 0)
            self.campos['lam_cal'][1].setText(f'medido: {br(md["lam_cal"])} em {len(md["cal_m"])} min')
            self.campos['lam_pic'][1].setText(f'medido: {br(md["lam_pic"])} em {len(md["pic_m"])} min' if md['lam_pic'] is not None else 'sem pico detectado')
            self.campos['theta'][1].setText(f'medido: {br(md["theta"], 3)} ({md["D"]} desistências)')
            self.campos['n0'][1].setText(f'medido: {md["n0"]}')
            self.campos['mu'][1].setText(f'medido: {br(f["mu"])} ({f.get("mu_txt") or "informado"})' if f['mu'] is not None else 'sem minutos com fila: informe μ')
            limtxt = br(md['limiar']) if md['limiar'] != float('inf') else 'sem pico claro'
            self.campos['limiar'][1].setText(('automático: ' if not lim else 'usado: ') + limtxt)
        self._prog = False
        for k in self.campos:
            self._marcar(k)
        self._pendente()

    def _editou(self, k):
        if self._prog:
            return
        self.editado.add(k)
        self._marcar(k)
        self._pendente()

    def _marcar(self, k):
        w = self.campos[k][0]
        w.setProperty('editado', 'true' if (k in self.editado and k in self.medido) else 'false')
        repolir(w)

    def _pendente(self):
        if self._prog or self.saida is None:
            return
        self.msg_sim.setText('Parâmetros alterados: clique em Simular para atualizar os resultados.')
        self.btn_sim.setText('Simular de novo')

    def valor(self, k):
        if k in self.medido and k not in self.editado:
            return self.medido[k]
        return self.campos[k][0].value()

    def configuracao(self):
        f = self.fonte_atual()
        sel = {k for k, cb in self.checks.items() if cb.isChecked()}
        c = {'d': f['d'], 't0': f['t0'], 'mu': self.valor('mu'), 'theta': self.valor('theta'), 'n0': int(self.valor('n0')),
             'K': self.p_K.value(), 'reps': self.p_reps.value(), 'seed': self.p_seed.value(), 'passo': self.p_passo.value(),
             'sel': sel, 'pers': (self.pers_calma.value(), self.pers_pico.value(), self.pers_desist.isChecked())}
        if f['d'] is None:
            T = self.m_T.value()
            pi, pf = self.m_pi.value(), self.m_pf.value()
            c['pico'] = [pi <= m < pf for m in range(T)]
            c['lam_cal'] = self.valor('lam_cal') if not all(c['pico']) else None
            c['lam_pic'] = self.valor('lam_pic') if any(c['pico']) else None
        else:
            c['pico'] = self.med['pico']
            c['lam_cal'] = self.valor('lam_cal') if self.med['lam_cal'] is not None else None
            c['lam_pic'] = self.valor('lam_pic') if self.med['lam_pic'] is not None else None
        c['T'] = len(c['pico'])
        c['med'] = self.med if f['d'] is not None else None
        tr = f['d'].get('trocas') if f['d'] is not None else None
        c['troca'] = sum(tr) / len(tr) if tr else None
        c['gatilho'] = self.p_gatilho.value()
        c['grupo'] = ac.estimar_grupos(f['d']['chegadas_seg']) if (f['d'] is not None and self.p_grupo.isChecked()) else None
        c['sens'] = ac.opcoes_sens(f.get('mu_est'), c['mu'], f.get('mu_cron')) if f['d'] is not None else []
        lams = ac.lams_por_minuto(c['pico'], c['lam_cal'], c['lam_pic'], 0)
        if f['d'] is not None and not ({'lam_cal', 'lam_pic'} & self.editado):
            c['lam_med'] = self.med['lam_med']  # o mesmo λ médio do relatório (W = L / λ)
        else:
            c['lam_med'] = sum(lams) / len(lams)
        return c

    # ------------------------------------------------------------ simulação
    def simular(self):
        if self.rodada and self.rodada.isRunning():
            return
        f = self.fonte_atual()
        if f is None:
            return
        if f['d'] is not None and sum(f['d']['arr']) == 0:
            return
        if f['d'] is None and self.m_pf.value() <= self.m_pi.value():
            self.msg_sim.setText('O fim do pico precisa vir depois do começo.')
            return
        cfg = self.configuracao()
        if cfg['lam_med'] <= 0:
            self.msg_sim.setText('Informe λ maior que zero.')
            return
        self.btn_sim.setEnabled(False)
        self.btn_sim.setText('Simulando…')
        self.barra.setValue(0)
        self.barra.show()
        self.msg_sim.setText(f'{cfg["reps"]} réplicas por cenário…')
        self.palco.tocar(False)
        self.rodada = Rodada(cfg)
        self.rodada.progresso.connect(self.barra.setValue)
        self.rodada.pronto.connect(self._pronto)
        self.rodada.falhou.connect(self._falhou)
        self.rodada.start()

    def _fim_rodada(self):
        self.btn_sim.setEnabled(True)
        self.btn_sim.setText('Simular')
        self.barra.hide()

    def _falhou(self, msg):
        self._fim_rodada()
        self.msg_sim.setText('')
        QMessageBox.warning(self, 'Simulação', msg)

    def _pronto(self, saida):
        self._fim_rodada()
        self.saida = saida
        c = saida['cfg']
        txt = f'{c["reps"]} réplicas · passo {br(saida["passo"], 1)} s · K = {c["K"]} · semente {c["seed"]}.'
        self.msg_sim.setText(' '.join(saida['avisos'] + [txt]))
        if self.anim_nome not in saida['res']:
            self.anim_nome = '1 catraca'
        self.anim_rep = 0
        self.mostrar(saida)

    # ------------------------------------------------------------ resultados
    def mostrar(self, s, manter_anim=False):
        c, res, t = s['cfg'], s['res'], self.t
        base = res['1 catraca']

        # conclusão
        if '2ª só no pico' in res:
            c2 = res['2ª só no pico']
            quando = ac.texto_janelas(ac.janelas_pico(c['pico']), c['t0'])
            quando = quando[0].upper() + quando[1:]
            txt = ''
            if c['lam_pic'] is not None:
                txt = (f'{quando} chegam {br(c["lam_pic"])} alunos/min para μ = {br(c["mu"])} de uma catraca '
                       f'(ρ = {br(c["lam_pic"] / c["mu"])}). ')
            txt += (f'Uma 2ª catraca só nesse intervalo muda o tempo médio no sistema de {br(base["W"], 1)} para '
                    f'{br(c2["W"], 1)} min, e os alunos em média de {br(base["L"], 1)} para {br(c2["L"], 1)}.')
            sens = s.get('sens') or []
            w2 = [x['res']['2ª só no pico']['W'] for x in sens if '2ª só no pico' in x['res']]
            if len(w2) > 1:
                txt += (f' Com μ entre {br(sens[0]["mu"])} e {br(sens[-1]["mu"])}, W com a 2ª catraca fica entre '
                        f'{br(min(w2), 1)} e {br(max(w2), 1)} min.')
            txt += f' Custo: {br(c2["custo"], 0)} min de 2ª catraca aberta.'
            alt = [r for n, r in res.items() if CHAVES[n] in ('rapido', 'escal')]
            if alt:
                txt += ' Sem catraca extra: ' + '; '.join(f'{NOMES_LONGOS[r["chave"]].lower()}, W = {br(r["W"], 1)} min' for r in alt) + '.'
            rf = res.get('2ª pela fila')
            if rf and rf['efic'] is not None and c2['efic'] is not None:
                N, M = rf['politica']
                resposta = 'Sim.' if rf['efic'] > c2['efic'] else 'Não.'
                detalhe = (f'Abrindo com {N} alunos na fila e fechando com {M}, cada minuto de 2ª catraca poupa '
                           f'<b>{br(rf["efic"], 0)} min</b> de espera, contra <b>{br(c2["efic"], 0)}</b> no horário de pico.<br>'
                           f'2ª catraca aberta: {br(rf["custo"], 0)} min pela fila × {br(c2["custo"], 0)} min pelo horário · '
                           f'W: {br(rf["W"], 1)} × {br(c2["W"], 1)} min (1 catraca: {br(base["W"], 1)} min).')
            else:
                resposta, detalhe = '—', 'Marque "2ª catraca pela fila" e "2ª catraca só no pico" nos cenários para responder.'
        elif '2 a hora toda' in res:
            c2 = res['2 a hora toda']
            resposta, detalhe = '—', 'Sem pico detectado nesta sessão: não há horário de pico para comparar.'
            txt = (f'Sem pico detectado. Com 2 catracas a hora toda, o tempo médio no sistema vai de {br(base["W"], 1)} '
                   f'para {br(c2["W"], 1)} min.')
        else:
            resposta, detalhe = '—', 'Marque os cenários com 2ª catraca para responder.'
            txt = f'Com 1 catraca, o tempo médio no sistema é {br(base["W"], 1)} min e há {br(base["L"], 1)} alunos em média.'
        self.resposta_lb.setText(resposta)
        self.resposta_det.setText(detalhe)
        q6 = s.get('q6')
        self.achado_lb.setText(
            f'<b>Achado:</b> chegar em grupo ({br(q6["Ek"])} alunos por grupo) aumenta a espera: ×{br(q6["fator"], 1)} '
            f'na calma pela fórmula; no almoço simulado, W com 1 catraca vai de {br(q6["w_um"], 1)} (um a um) para '
            f'{br(q6["w_gr"], 1)} min (em grupo).' if q6 else '')
        self.achado_lb.setVisible(bool(q6))
        self.conclusao.setText(txt)
        if s.get('valid'):
            todos = s['valid'] + (s.get('valid_trace') or [])
            ok = sum(v['ok'] for v in todos)
            self.selo_valid.setText(f'{"✓" if ok == len(todos) else "⚠"}  Validação: {ok} de {len(todos)} itens dentro da faixa '
                                    '5%–95% das réplicas (fila reconstruída, dispersão D e chegadas reais; aba Modelo e validação).')
            self.selo_valid.setProperty('papel', 'bom' if ok == len(todos) else 'ruim')
        else:
            self.selo_valid.setText('Sem fila reconstruída: não há validação para este caso.')
            self.selo_valid.setProperty('papel', 'dica')
        repolir(self.selo_valid)

        # cartões
        while self.grade_cartoes.count():
            w = self.grade_cartoes.takeAt(0).widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.cartoes = {}
        cols = min(4, max(1, len(res)))
        for col in range(8):
            self.grade_cartoes.setColumnStretch(col, 1 if col < cols else 0)
        for i, (nome, r) in enumerate(res.items()):
            ct = Cartao(nome, r, base, t)
            ct.clicado.connect(self._escolher_anim)
            self.cartoes[nome] = ct
            self.grade_cartoes.addWidget(ct, i // cols, i % cols)
        self._graficos(s)
        self._tabelas(s)
        if manter_anim:
            self._destacar()
        else:
            self._preparar_anim()

    def _graficos(self, s):
        c, res, t = s['cfg'], s['res'], self.t
        t0, passo, pico, T = c['t0'], s['passo'], c['pico'], c['T']
        hora = (lambda m: (t0 + timedelta(minutes=m)).strftime('%H:%M')) if t0 else (lambda m: f'min {m:.0f}')

        def linha_html(cor, valor, nome):
            return f'<span style="color:{cor}">━━</span>&nbsp;<b>{valor}</b>&nbsp;<span style="color:{t["muted"]}">{nome}</span>'

        def cab(m):
            fase = 'pico' if pico[min(int(m), T - 1)] else 'calma'
            return f'<b>{hora(m)}</b> <span style="color:{t["muted"]}">· minuto {int(m)} · {fase}</span>'

        # chegadas
        g = self.g_cheg
        ax = g.limpar(t, t0)
        g.faixas_pico(pico, t['pico'])
        d = c['d']
        if d:
            ax.bar([m + .5 for m in range(T)], d['arr'], width=.78, color=t['barras'], label='chegadas no minuto', zorder=2)
        ax.step(range(T + 1), s['lams'] + [s['lams'][-1]], where='post', color=t['ink'], lw=1.6, label='λ usado na simulação', zorder=3)
        for mult, estilo, nome in ((1, (0, (5, 3)), '1 catraca'), (2, (0, (1.5, 2.5)), '2 catracas')):
            ax.axhline(c['mu'] * mult, color=t['muted'], lw=1.2, ls=estilo, zorder=3)
            ax.text(T, c['mu'] * mult, f'  capacidade, {nome} ({br(c["mu"] * mult)}/min)', color=t['muted'], fontsize=8,
                    va='bottom', ha='right', bbox=dict(boxstyle='round,pad=0.15', fc=t['surface'], ec='none', alpha=.85))
        ax.set_xlim(0, T)
        ax.set_ylim(0, max(max(d['arr']) if d else 0, max(s['lams']), c['mu'] * 2) * 1.15)
        ax.set_ylabel('alunos por minuto', color=t['muted'], fontsize=9)
        lg = ax.legend(loc='upper left', fontsize=8.5, frameon=False, labelcolor=t['ink'])

        def dica_cheg(x):
            m = max(0, min(int(x), T - 1))
            rows = [cab(m)]
            if d:
                rows.append(linha_html(t['barras'], d['arr'][m], 'chegadas no minuto'))
                if d['des'][m]:
                    rows.append(linha_html(t['alert'], d['des'][m], 'desistências'))
            rows.append(linha_html(t['ink'], br(s['lams'][m]), 'λ usado'))
            return m + .5, '<br>'.join(rows)
        g.dica = dica_cheg
        g.draw_idle()

        # índices de passo -> minutos
        N = len(res["1 catraca"]["hs"][0])
        xs = [(i + 1) * passo / 60 for i in range(N)]

        def idx(x):
            return max(0, min(N - 1, int(round(x * 60 / passo)) - 1))

        # validação
        g = self.g_valid
        ax = g.limpar(t, t0)
        g.faixas_pico(pico, t['pico'])
        b = res['1 catraca']
        cor = t['series']['base']
        ax.fill_between(xs, b['p05'], b['p95'], color=cor, alpha=.16, lw=0, label='5%–95% das réplicas', step='pre')
        ax.step(xs, b['hs'][0], color=cor, lw=.8, alpha=.55, label='1 réplica simulada', where='pre')
        ax.plot(xs, b['media'], color=cor, lw=2.2, label='média das réplicas (1 catraca)')
        fila = d['fila'] if d else []
        if fila:
            ax.scatter([sec / 60 for sec, _ in fila], [n for _, n in fila], s=26, color=t['ink'], zorder=5,
                       edgecolors=t['surface'], linewidths=1.2, label='fila reconstruída')
        ax.set_xlim(0, T)
        ax.set_ylim(bottom=0)
        ax.set_ylabel('alunos no sistema', color=t['muted'], fontsize=9)
        ax.legend(loc='upper right', fontsize=8.5, frameon=False, labelcolor=t['ink'], ncols=2)
        obs = {int(round(sec / 60)): n for sec, n in fila}

        def dica_valid(x):
            m = max(0, min(int(round(x)), T))
            i = idx(m)
            rows = [cab(min(m, T - 1))]
            if m in obs:
                rows.append(linha_html(t['ink'], obs[m], 'fila reconstruída'))
            rows.append(linha_html(cor, br(b['media'][i], 1), 'média das réplicas'))
            rows.append(linha_html(cor, f'{b["p05"][i]:g}–{b["p95"][i]:g}', 'faixa 5%–95%'))
            return m, '<br>'.join(rows)
        g.dica = dica_valid
        g.draw_idle()

        # cenários
        g = self.g_cen
        ax = g.limpar(t, t0)
        g.faixas_pico(pico, t['pico'])
        for nome, r in res.items():
            ax.plot(xs, r['media'], color=t['series'][r['chave']], lw=2, label=f'{NOMES_LONGOS[r["chave"]]} (W = {br(r["W"], 1)} min)',
                    ls=(0, (4, 2)) if r['chave'] == 'semdes' else '-')
        ax.set_xlim(0, T)
        ax.set_ylim(bottom=0)
        ax.set_ylabel('alunos no sistema (média)', color=t['muted'], fontsize=9)
        ax.legend(loc='upper right', fontsize=8.5, frameon=False, labelcolor=t['ink'])

        def dica_cen(x):
            m = max(0, min(int(round(x)), T))
            i = idx(m)
            rows = [cab(min(m, T - 1))]
            for nome, r in sorted(res.items(), key=lambda kv: -kv[1]['media'][i]):
                rows.append(linha_html(t['series'][r['chave']], br(r['media'][i], 1), NOMES_LONGOS[r['chave']]))
            return m, '<br>'.join(rows)
        g.dica = dica_cen
        g.draw_idle()

    def _tabela(self, k, cab, linhas, cores=None):
        tb, _info, _f = self.tabs[k]
        tb.clear()
        tb.setColumnCount(len(cab))
        tb.setRowCount(len(linhas))
        tb.setHorizontalHeaderLabels(cab)
        tb.clearSpans()
        for i, lin in enumerate(linhas):
            for j, val in enumerate(lin):
                if val is None:
                    continue
                it = QTableWidgetItem(str(val))
                it.setTextAlignment((Qt.AlignLeft if j == 0 else Qt.AlignRight) | Qt.AlignVCenter)
                if cores and (i, j) in cores:
                    it.setForeground(QColor(cores[(i, j)]))
                tb.setItem(i, j, it)
            if len(lin) < len(cab):
                tb.setSpan(i, len(lin) - 1, 1, len(cab) - len(lin) + 1)
                tb.item(i, len(lin) - 1).setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        tb.resizeRowsToContents()
        h = tb.horizontalHeader().height() + sum(tb.rowHeight(i) for i in range(tb.rowCount())) + 4
        tb.setFixedHeight(h)

    def _tabelas(self, s):
        c, res, t = s['cfg'], s['res'], self.t
        self._tabela('cen', ['cenário', 'L médio', 'pior momento', 'W (min)', 'tempo com fila ≥ 10', 'custo', 'eficiência'],
                     [[NOMES_LONGOS[r['chave']], f'{br(r["L"], 1)} ± {br(r["Lic"], 1)}', br(r['pior'], 1),
                       f'{br(r["W"], 1)} ± {br(r["Wic"], 1)}', pct(r['longa']),
                       f'{br(r["custo"], 0)} catraca-min' if r.get('custo', 0) > 0.5 else '—',
                       br(r['efic'], 0) if r.get('efic') is not None else '—'] for r in res.values()])
        tb_b, _ib, card_b = self.tabs['busca']
        b = s.get('busca')
        if b:
            card_b.show()
            rr = b['ref']
            linhas = [[f'{NOMES_LONGOS[CHAVES[b["ref_nome"]]]} (referência)', br(rr['custo'], 0), br(rr['W'], 1),
                       br(rr['efic'], 0) if rr['efic'] is not None else '—']]
            for x in b['linhas']:
                marca = '  ← melhor' if b['melhor'] and x['N'] == b['melhor']['N'] else ''
                linhas.append([f'abre com {x["N"]}, fecha com {x["M"]}{marca}', br(x['custo'], 0), br(x['W'], 1),
                               br(x['efic'], 0) if x['efic'] is not None else '—'])
            self._tabela('busca', ['política', 'catraca-min', 'W (min)', 'eficiência'], linhas)
        else:
            card_b.hide()

        tb_v, info_v, card_v = self.tabs['valid']
        if s.get('valid'):
            card_v.show()
            linhas, cores = [], {}
            itens = [(v, '') for v in s['valid']] + [(v, 'chegadas reais · ') for v in (s.get('valid_trace') or [])]
            for i, (v, pre) in enumerate(itens):
                fm = pct if v['casas'] == 2 else (lambda x, d=v['casas']: br(x, d))
                linhas.append([pre + v['rot'], fm(v['obs']), fm(v['sim']), f'{fm(v["lo"])} – {fm(v["hi"])}', '✓ sim' if v['ok'] else '✗ NÃO'])
                cores[(i, 4)] = t['ok'] if v['ok'] else t['alert']
            self._tabela('valid', ['', 'observada', 'simulada (média)', 'faixa 5%–95%', 'dentro?'], linhas, cores)
            cv = s.get('curva')
            extra = ''
            if cv:
                extra = (f' Curva: a fila observada fica dentro da faixa em {pct(cv["frac"])} dos minutos '
                         f'(as próprias réplicas ficam em {pct(cv["linha"]["sim"])}; mínimo aceito {pct(cv["linha"]["lo"])}).')
                if cv['fora']:
                    extra += f' Trechos fora: {ac.texto_fora(cv["fora"], c["t0"])}.'
            info_v.setText(self.dica_valid + extra)
        else:
            card_v.hide()

        tb_s, _i, card_s = self.tabs['sens']
        if s.get('sens'):
            card_s.show()
            seg = '2ª só no pico' if '2ª só no pico' in s['sens'][0]['res'] else '2 a hora toda'
            self._tabela('sens', ['μ (/min)', 'origem', 'ρ no pico', 'W 1 catraca', f'W {NOMES_LONGOS[CHAVES[seg]]}'],
                         [[br(x['mu']), x['origem'], br(x['rho_pico']), f'{br(x["res"]["1 catraca"]["W"], 1)} min',
                           f'{br(x["res"][seg]["W"], 1)} min'] for x in s['sens']])
        else:
            card_s.hide()

        mu, linhas = c['mu'], []
        g = c.get('grupo')
        trechos = [('calma', c['lam_cal']), ('pico', c['lam_pic']), ('sessão', c['lam_med'])]
        for rot, lam in trechos:
            if lam is None:
                continue
            f = ac.formulas(lam, mu)
            if f['estavel']:
                lin = [rot, br(lam), br(f['rho']), pct(f['vazia']), br(f['L']), br(f['W']), br(f['Wq'])]
                if g:
                    fg = ac.formulas_grupo(lam, mu, g['D'])
                    lin += [br(fg['L']), br(fg['W'])]
                linhas.append(lin)
            else:
                linhas.append([rot, br(lam), br(f['rho']), 'ρ ≥ 1 (ou perto): as fórmulas não valem, a fila cresce. Use a simulação.'])
        cab = ['trecho', 'λ (/min)', 'ρ', 'vazia', 'L', 'W (min)', 'Wq (min)'] + (['L em grupo', 'W em grupo'] if g else [])
        self._tabela('mm1', cab, linhas)
        md = self.med if c['d'] else None
        partes = [f'μ = {br(mu)} /min (atendimento médio {br(60 / mu, 1)} s) · θ = {br(c["theta"], 3)} /min por aluno que espera.']
        if g:
            partes.append(f'Chegadas em grupo: E[k] = {br(g["Ek"])}, D = E[k²]/E[k] = {br(g["D"])}; '
                          f'"em grupo" é o M^X/M/1, L e W multiplicados por (1 + D)/2 = {br((1 + g["D"]) / 2)}.')
        if md:
            partes.append(f'{md["total"]} chegadas em {md["T"]} min (λ médio {br(md["lam_med"])} /min). '
                          f'Calma: {len(md["cal_m"])} min · pico: {len(md["pic_m"])} min.')
            cal = md['cal_m']
            if len(cal) > 2:
                mc = sum(cal) / len(cal)
                vm = statistics.pvariance(cal) / mc if mc else float('nan')
                partes.append(f'Dispersão na calma: variância/média = {br(vm)} (perto de 1 é Poisson).')
            if md['janelas']:
                partes.append(f'Pico {ac.texto_janelas(md["janelas"], c["t0"])}.')
            if md['D']:
                partes.append(f'Desistências: {md["D"]} ({br(md["D"] / md["total"] * 100, 0)}% das chegadas).')
        self.tabs['mm1'][1].setText(' '.join(partes))

        if s.get('verif'):
            vs = s['verif']
            self.tabs['verif'][2].show()
            cab = ['métrica'] + [x for nome, _f, _m in vs for x in (f'{nome}: fórmula', 'simulado')]
            self._tabela('verif', cab,
                         [['utilização ρ'] + [x for _n, f, mt in vs for x in (pct(f['rho']), pct(mt['ocupada']))],
                          ['catraca vazia 1 − ρ'] + [x for _n, f, mt in vs for x in (pct(f['vazia']), pct(1 - mt['ocupada']))],
                          ['alunos no sistema L'] + [x for _n, f, mt in vs for x in (br(f['L']), br(mt['L']))],
                          ['tempo W (min)'] + [x for _n, f, mt in vs for x in (br(f['W']), br(mt['W']))],
                          ['espera na fila Wq (min)'] + [x for _n, f, mt in vs for x in (br(f['Wq']), br(mt['Lq'] / c['lam_cal']))]])
        else:
            self.tabs['verif'][2].hide()

    # ------------------------------------------------------------ animação
    def _escolher_anim(self, nome):
        self.anim_nome = nome
        self.anim_rep = 0
        self._preparar_anim()

    def _outra_replica(self):
        if not self.saida:
            return
        self.anim_rep = (self.anim_rep + 1) % self.saida['cfg']['reps']
        self._preparar_anim()

    def _destacar(self):
        for nome, ct in self.cartoes.items():
            ct.selecionar(nome == self.anim_nome)

    def _preparar_anim(self):
        s = self.saida
        if not s:
            return
        if self.anim_nome not in s['res']:
            self.anim_nome, self.anim_rep = '1 catraca', 0
        c, r = s['cfg'], s['res'][self.anim_nome]
        tocando = self.palco.rodando
        hist = r['hs'][self.anim_rep]
        ev, abertas = rastrear(hist, r['lams'], r['mu'], r['cs'], c['n0'], c['K'], c['seed'] + self.anim_rep, s['passo'],
                               r['theta'], c.get('grupo'), r.get('politica'))
        self.palco.carregar(hist, ev, r['cs'], c['n0'], s['passo'], c['K'], abertas if r.get('politica') else None)
        self.linha.carregar(list(hist), r['media'], c['pico'], s['passo'])
        self.anim_nome_lb.setText(f'{NOMES_LONGOS[r["chave"]].upper()} · RÉPLICA {self.anim_rep + 1} DE {c["reps"]} · SEMENTE {c["seed"] + self.anim_rep}')
        self.leg_anim.setText(
            f'<span style="color:{self.t["espera"]}">●</span> esperando &nbsp;&nbsp; '
            f'<span style="color:{self.t["cat"]}">●</span> na catraca &nbsp;&nbsp; '
            f'<span style="color:{self.t["ok"]}">●</span> passou &nbsp;&nbsp; '
            f'<span style="color:{self.t["alert"]}">●</span> desistiu &nbsp;&nbsp;·&nbsp;&nbsp; '
            'linha do tempo: azul = esta réplica, tracejado = média das réplicas, faixa rosada = pico. Clique ou arraste para ir a outro momento.')
        self._destacar()
        self.palco.tocar(tocando)

    def _play(self):
        sim = not self.palco.rodando
        self.palco.tocar(sim)
        self.btn_play.setText('❚❚  Pausar' if sim else '▶  Reproduzir')

    def _anim_mudou(self, k):
        s = self.saida
        if not s:
            return
        c = s['cfg']
        self.linha.definir(k)
        seg = (k + 1) * s['passo']
        if c['t0'] is not None:
            self.a_hora.setText((c['t0'] + timedelta(seconds=seg)).strftime('%H:%M:%S'))
        else:
            self.a_hora.setText(f'{int(seg // 60)}:{int(seg % 60):02d}')
        m = min(int(max(k, 0) * s['passo'] / 60), c['T'] - 1)
        pk = c['pico'][m]
        self.a_fase.setText(f'pico · λ {br(s["lams"][m])}/min' if pk else f'calma · λ {br(s["lams"][m])}/min')
        self.a_fase.setProperty('papel', 'selo-pico' if pk else 'selo-calma')
        repolir(self.a_fase)
        p = self.palco
        self.a_nums['esp'].setText(str(len(p.fila)))
        self.a_nums['cat'].setText(str(sum(1 for a in p.cats if a)))
        self.a_nums['cheg'].setText(str(p.contagem(1)))
        self.a_nums['pass'].setText(str(p.contagem(2)))
        self.a_nums['des'].setText(str(p.contagem(3)))
        self.a_nums['abertas'].setText(str(p.catracas_no_passo(k)))

    def closeEvent(self, ev):
        if self.rodada and self.rodada.isRunning():
            self.rodada.requestInterruption()
            self.rodada.wait(5000)
        super().closeEvent(ev)


def main():
    ac.configurar_utf8()
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    app.setApplicationName('Simulador da fila da catraca')
    from PySide6.QtCore import QLocale
    QLocale.setDefault(QLocale(QLocale.Portuguese, QLocale.Brazil))  # vírgula decimal nos campos
    matplotlib.rcParams['font.family'] = _fonte_mpl()
    matplotlib.rcParams['axes.unicode_minus'] = False
    arquivos = [a for a in sys.argv[1:] if not a.startswith('-')]
    jan = Janela(arquivos)
    jan.show()
    sys.exit(app.exec())


if __name__ == '__main__':
    main()
