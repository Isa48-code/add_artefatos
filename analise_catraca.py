#!/usr/bin/env python3
"""
Análise e simulação da fila da catraca do RU (seminário de Avaliação de Desempenho).

Lê os CSVs exportados pela página de coleta (um por celular; vários dias),
e faz o que o checklist da Aula 10 pede:

  1. mede  : λ por trecho (calma/pico), μ pelas saídas por minuto nos minutos com fila
             (slide 57 da Aula 09); o tempo cronometrado entra só como teto de referência
  2. modela: fórmulas M/M/1 (Aula 03) para cada trecho, e M/G/1 (Pollaczek-Khinchine) na calma
  3. simula: cadeia de Markov com passo de 5 s (slides 9 e 10), K = 200. Padrão: M/M/1, chegadas
             uma a uma; as chegadas em grupo (--grupo-seg 1.5) entram como refinamento comparado
  4. verifica: simulador x fórmulas num trecho sem pico (slide 19)
  5. valida : fila reconstruída x simulada, dispersão D das chegadas (slide 25 da Aula 09),
              simulação com as chegadas reais (trace) e μ estimado fora da amostra
  6. compara cenários com a mesma semente: 1 catraca, 2ª só no pico, 2 a hora toda,
     e a sensibilidade dos resultados a μ
  7. aponta o gargalo (use --fila para incluir ticket, suco etc.)

Uso:
  python3 analise_catraca.py A_dia1.csv B_dia1.csv C_dia1.csv
  python3 analise_catraca.py *.csv --ajuste saidas --comparar-ajustes --reps 500
  python3 analise_catraca.py *.csv --limiar 3.0 --K 200 --reps 30 --seed 42
  python3 analise_catraca.py *.csv --fila ticket 1.8 3.0 --fila suco 1.2 2.0

Os arquivos dos três observadores são juntados pelo nome da sessão.
Só precisa de Python 3. Os gráficos (PNG) saem se o matplotlib estiver instalado.

Para reproduzir os números da versão anterior (picos sem junção, K = 80):
  --pico-min 0 --buraco-max 0 --K 80 --mu 4.94
"""
import argparse
import bisect
import csv
import math
import os
import random
import statistics
import sys
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from itertools import accumulate

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}

MODOS_AJUSTE = ('nenhum', 'desistencia', 'saidas', 'n0')
NOMES_AJUSTE = {'nenhum': 'sem ajuste', 'desistencia': 'desistências não vistas',
                'saidas': 'saídas não registradas', 'n0': 'fila inicial menor'}


def t_crit(df):
    for k in sorted(T975):
        if df <= k:
            return T975[k]
    return 1.96


def media_ic(valores):
    """Média e meia-largura do IC de 95%."""
    n = len(valores)
    m = sum(valores) / n
    if n < 2:
        return m, float('nan')
    return m, t_crit(n - 1) * statistics.stdev(valores) / math.sqrt(n)


def br(x, d=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return '-'
    return f'{x:.{d}f}'.replace('.', ',')


SAIDA = []


def configurar_utf8():
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        try:
            stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass


def P(texto=''):
    print(texto)
    SAIDA.append(texto)


# ---------------------------------------------------------------- leitura
def ler(arquivos):
    sess = defaultdict(lambda: {
        'inicio': [], 'fim': [], 'chegada': [], 'desist': [], 'fila': [],
        'atend': [], 'inicio_atend': [], 'saida_atend': [], 'n0': None,
        'catracas': 1, 'obs': {},
    })
    for caminho in arquivos:
        with open(caminho, newline='', encoding='utf-8-sig') as f:
            for r in csv.DictReader(f):
                nome = (r.get('sessao') or '').strip()
                if not nome or nome == 'sessao':  # cabeçalho repetido ao colar dois CSVs
                    continue
                s = sess[nome]
                try:
                    # a página grava em horário de Brasília (-03:00); só interessam as diferenças
                    t = datetime.fromisoformat(r['instante_iso']).replace(tzinfo=None)
                except (KeyError, ValueError):
                    continue
                tipo = r['tipo']
                s['obs'].setdefault(tipo, set()).add((r.get('observador') or '').strip())
                try:
                    s['catracas'] = max(s['catracas'], int(r.get('catracas') or 1))
                except ValueError:
                    pass
                if tipo == 'inicio':
                    s['inicio'].append(t)
                    if r.get('valor', '').strip():
                        try:
                            s['n0'] = int(float(r['valor']))
                        except ValueError:
                            pass
                elif tipo == 'fim':
                    s['fim'].append(t)
                elif tipo == 'chegada':
                    s['chegada'].append(t)
                elif tipo == 'desistencia':
                    s['desist'].append(t)
                elif tipo == 'fila':
                    s['fila'].append((t, int(float(r['valor']))))
                elif tipo == 'atendimento':
                    s['atend'].append(float(r['valor']))
                elif tipo == 'inicio_atend':
                    s['inicio_atend'].append(t)
                elif tipo == 'saida_atend':
                    s['saida_atend'].append(t)
    return sess


def parear(inicios, saidas, maximo=60, pares=False):
    """Cada saída pareia com o início mais recente ainda não usado, se a diferença ficar entre 0 e `maximo` s.
    Um toque perdido descarta só aquele par, em vez de desalinhar todos os seguintes.
    Devolve as durações (s) ou, com pares=True, os pares (início, saída)."""
    ev = sorted([(t, 0) for t in inicios] + [(t, 1) for t in saidas])
    pend, out = None, []
    for t, k in ev:
        if k == 0:
            pend = t
        elif pend is not None:
            x = (t - pend).total_seconds()
            if 0 <= x <= maximo:
                out.append((pend, t) if pares else x)
            pend = None
    return out


def preparar(nome, s):
    saidas = s['saida_atend'] + s.get('saida_extra', [])
    todos = (
        s['inicio'] + s['fim'] + s['chegada'] + s['desist']
        + s['inicio_atend'] + saidas
        + [t for t, _ in s['fila']]
    )
    if not todos:
        return None
    t0 = min(s['inicio']) if s['inicio'] else min(todos)
    t1 = max(s['fim']) if s['fim'] else max(todos)
    T = max(1, int((t1 - t0).total_seconds() // 60))

    def por_minuto(lista):
        v = [0] * T
        for t in lista:
            m = int((t - t0).total_seconds() // 60)
            if 0 <= m < T:
                v[m] += 1
        return v

    arr, des, sai = por_minuto(s['chegada']), por_minuto(s['desist']), por_minuto(saidas)
    fila = sorted(((t - t0).total_seconds(), n) for t, n in s['fila'])
    fila = [(sec, n) for sec, n in fila if 0 <= sec < T * 60]
    reconstruida = False
    fila_final = None
    if not fila and (s['n0'] is not None or s['inicio_atend'] or saidas):
        reconstruida = True
        n = max(0, s['n0'] or 0)
        eventos = sorted(
            [(t, 1) for t in s['chegada']]
            + [(t, -1) for t in s['desist']]
            + [(t, -1) for t in saidas]
        )
        pos = 0
        fila = []
        for minuto in range(T):
            limite = t0 + timedelta(minutes=minuto)
            while pos < len(eventos) and eventos[pos][0] <= limite:
                n = max(0, n + eventos[pos][1])
                pos += 1
            fila.append((minuto * 60, n))
        while pos < len(eventos):
            n = max(0, n + eventos[pos][1])
            pos += 1
        fila_final = n

    # atendimentos cronometrados: só valem se início e saída foram anotados no mesmo celular
    atend = list(s['atend'])
    aviso = None
    descartados = 0
    trocas = []
    ini_obs = s['obs'].get('inicio_atend', set())
    sai_obs = s['obs'].get('saida_atend', set())
    if s['inicio_atend'] and s['saida_atend']:
        if ini_obs and sai_obs and ini_obs != sai_obs:
            pares = list(zip(sorted(s['inicio_atend']), sorted(s['saida_atend'])))
            neg = sum(1 for a, b in pares if b < a) / len(pares)
            descartados = len(s['saida_atend'])
            aviso = (f'início ({"/".join(sorted(ini_obs))}) e saída ({"/".join(sorted(sai_obs))}) anotados em celulares '
                     f'diferentes; pareando por ordem, {br(neg * 100, 0)}% dos tempos dariam negativos: relógios '
                     f'dessincronizados, os {descartados} atendimentos foram descartados (use as contagens por minuto).')
        else:
            pr = parear(s['inicio_atend'], s['saida_atend'], pares=True)
            dur = [(b - a).total_seconds() for a, b in pr]
            descartados = len(s['saida_atend']) - len(dur)
            atend.extend(dur)
            # troca: da saída de um aluno ao início do próximo, só quando o próximo já estava esperando (< 30 s)
            trocas = [x for x in ((pr[i + 1][0] - pr[i][1]).total_seconds() for i in range(len(pr) - 1)) if 0 <= x < 30]
    return {
        'nome': nome, 'T': T, 'arr': arr, 'des': des, 'sai': sai, 'fila': fila,
        'atend': atend, 'atend_descartados': descartados, 'atend_aviso': aviso, 'trocas': trocas,
        'catracas': s['catracas'], 't0': t0,
        'chegadas_seg': sorted((t - t0).total_seconds() for t in s['chegada']),
        'reconstruida': reconstruida, 'fila_final': fila_final,
        # alunos que sobram no fim: pela fila reconstruída (que não deixa a fila ficar negativa) ou pela conta direta
        'excesso': fila_final if reconstruida else (s['n0'] or 0) + len(s['chegada']) - len(s['desist']) - len(saidas),
    }


# ---------------------------------------------------------------- ajuste do balanço
def copiar_sessao(s):
    s2 = {k: (list(v) if isinstance(v, list) else v) for k, v in s.items()}
    s2['obs'] = {k: set(v) for k, v in s['obs'].items()}
    return s2


def repartir(total, pesos):
    """Divide `total` eventos inteiros proporcionalmente aos pesos (maiores restos)."""
    soma = sum(pesos)
    if soma <= 0 or total <= 0:
        return [0] * len(pesos)
    bruto = [total * p / soma for p in pesos]
    base = [int(x) for x in bruto]
    ordem = sorted(range(len(pesos)), key=lambda i: -(bruto[i] - base[i]))
    for i in ordem[:total - sum(base)]:
        base[i] += 1
    return base


def limitar_por_fila(cont, fm, final):
    """Remoções extras não podem deixar a fila negativa: até o minuto m, o total acrescentado não passa da menor
    fila reconstruída dali em diante. O que não cabe é empurrado para depois (o último mínimo da fila)."""
    T = len(cont)
    cap = [0] * T
    menor = final
    for m in range(T - 1, -1, -1):
        cap[m] = menor            # menor fila nos inícios de minuto depois de m (e no fim)
        menor = min(menor, fm[m])
    acum, R = 0, []
    for m in range(T):
        acum += cont[m]
        R.append(min(acum, cap[m]))
    R[-1] = min(sum(cont), final)
    return [R[0]] + [R[m] - R[m - 1] for m in range(1, T)]


def ajustar(s, modo, fila_min=3):
    """Trata o excesso do balanço (fila inicial + chegadas − desistências − saídas que sobra no fim).
    modo: 'nenhum', 'desistencia' (desistências não vistas, proporcionais a quem espera),
    'saidas' (saídas que o observador não registrou, espalhadas nos minutos com fila) ou
    'n0' (a fila inicial era menor). Devolve (sessão ajustada, texto)."""
    s2 = copiar_sessao(s)
    if modo == 'nenhum':
        return s2, ''
    if s['fila']:
        return s2, 'a fila foi anotada pelo observador C: o balanço não é ajustado.'
    d = preparar('ajuste', s2)
    if d is None:
        return s2, ''
    exc = d['excesso']
    if exc <= 0:
        return s2, f'o balanço fecha (sobra {exc}); nada a ajustar.'
    T, fm = d['T'], [n for _, n in d['fila']]
    if modo == 'n0':
        n0 = s2['n0'] or 0
        tira = min(exc, n0)
        s2['n0'] = n0 - tira
        txt = f'fila inicial reduzida de {n0} para {n0 - tira}'
        if exc > tira:
            txt += f'; {exc - tira} continuam sem explicação'
        return s2, txt
    if modo == 'desistencia':
        pesos = [max(n - d['catracas'], 0) for n in fm]
    else:
        pesos = [1 if fm[m] >= fila_min and (m + 1 >= T or fm[m + 1] >= fila_min) else 0 for m in range(T)]
    # até a última vez em que a fila reconstruída ficou abaixo de fila_min, a conta fechava: o excesso veio depois
    baixos = [m for m in range(T) if fm[m] < fila_min]
    desde = baixos[-1] + 1 if baixos else 0
    if sum(pesos[desde:]) > 0:
        pesos = [0] * desde + pesos[desde:]
    else:
        desde = 0
    cont = limitar_por_fila(repartir(exc, pesos), fm, d['fila_final'])
    novos = []
    for m, k in enumerate(cont):
        for j in range(k):
            novos.append(d['t0'] + timedelta(seconds=(m + (j + .5) / k) * 60))
    if modo == 'desistencia':
        s2['desist'] = s2['desist'] + novos
    else:
        s2['saida_extra'] = s2.get('saida_extra', []) + novos
    h = (d['t0'] + timedelta(minutes=desde)).strftime('%H:%M')
    return s2, (f'{exc} {NOMES_AJUSTE[modo]} distribuídas em {sum(1 for k in cont if k)} minutos a partir de {h} '
                f'(depois da última vez em que a fila reconstruída ficou abaixo de {fila_min}, quando a conta ainda fechava)')


# ---------------------------------------------------------------- calma e pico
def suavizar(arr, meia=2):
    """Média móvel centrada de 2*meia+1 minutos."""
    T = len(arr)
    out = []
    for m in range(T):
        jan = arr[max(0, m - meia):min(T, m + meia + 1)]
        out.append(sum(jan) / len(jan))
    return out


def limiar_auto(suave):
    """Divide os minutos em dois grupos (baixo e alto) pelo método das duas médias.
    Só aceita se o grupo alto tiver pelo menos 1,5 x a taxa do baixo; senão não há pico."""
    lo, hi = min(suave), max(suave)
    for _ in range(20):
        lim = (lo + hi) / 2
        a = [x for x in suave if x < lim]
        b = [x for x in suave if x >= lim]
        if not a or not b:
            break
        lo, hi = sum(a) / len(a), sum(b) / len(b)
    if lo <= 0 or hi / lo < 1.5:
        return float('inf')
    return (lo + hi) / 2


REGRAS_PICO = ('slide59', 'duas-medias')
NOMES_REGRA = {'slide59': '1,5 × a média (slide 59)', 'duas-medias': 'duas médias (versão anterior)'}


def limiar_slide59(arr):
    """Aula 09, slide 59: pico = chegadas acima de cerca de 1,5 vez a média da sessão."""
    m = sum(arr) / len(arr) if arr else 0
    return 1.5 * m if m > 0 else float('inf')


def limiar_regra(arr, regra='slide59'):
    """Limiar de pico (chegadas/min na média móvel de 5 min) pela regra escolhida."""
    return limiar_slide59(arr) if regra == 'slide59' else limiar_auto(suavizar(arr))


def janelas_pico(pico):
    """Trechos de pico como [(início, fim)], em minutos, com o fim exclusivo."""
    out, ini = [], None
    for m, p in enumerate(list(pico) + [False]):
        if p and ini is None:
            ini = m
        elif not p and ini is not None:
            out.append((ini, m))
            ini = None
    return out


def classificar(arr, limiar, min_pico=5, max_buraco=3):
    """True = minuto de pico, pela média móvel de 5 min das chegadas por minuto.
    Depois junta picos separados por até `max_buraco` min de calma e descarta picos com menos de
    `min_pico` min: um pico de 2 min não dá para operar (abrir e fechar a 2ª catraca)."""
    p = [x >= limiar for x in suavizar(arr)]
    jan = janelas_pico(p)
    for (_, f1), (i2, _) in zip(jan, jan[1:]):
        if i2 - f1 <= max_buraco:
            for m in range(f1, i2):
                p[m] = True
    for i, f in janelas_pico(p):
        if f - i < min_pico:
            for m in range(i, f):
                p[m] = False
    return p


# ---------------------------------------------------------------- modelo
def formulas(lam, mu):
    rho = lam / mu
    if rho >= .98:  # perto de 1 as fórmulas explodem (L = ρ/(1−ρ)); na prática a fila não se estabiliza
        return {'rho': rho, 'estavel': False}
    L = rho / (1 - rho)
    W = L / lam
    return {'rho': rho, 'estavel': True, 'vazia': 1 - rho, 'L': L, 'W': W, 'Wq': W - 1 / mu}


def formulas_grupo(lam, mu, D):
    """M^X/M/1 (chegadas em grupo de Poisson, atendimento exponencial): L = ρ(1 + D) / (2(1 − ρ)),
    com D = E[k²]/E[k] e λ em alunos/min. Com D = 1 (grupos de 1) volta ao M/M/1."""
    f = formulas(lam, mu)
    if not f['estavel']:
        return f
    rho = f['rho']
    L = rho * (1 + D) / (2 * (1 - rho))
    W = L / lam
    return {'rho': rho, 'estavel': True, 'vazia': 1 - rho, 'L': L, 'W': W, 'Wq': W - 1 / mu}


def estimar_grupos(chegadas_seg, gap=1.5):
    """Chegadas a menos de `gap` s uma da outra formam um grupo. Devolve a distribuição dos tamanhos."""
    if not gap or gap <= 0 or len(chegadas_seg) < 2:
        return None
    tam, k = [], 1
    for a, b in zip(chegadas_seg, chegadas_seg[1:]):
        if b - a <= gap:
            k += 1
        else:
            tam.append(k)
            k = 1
    tam.append(k)
    cont = Counter(tam)
    ks = sorted(cont)
    ps = [cont[k] / len(tam) for k in ks]
    Ek = sum(k * p for k, p in zip(ks, ps))
    Ek2 = sum(k * k * p for k, p in zip(ks, ps))
    return {'ks': ks, 'ps': ps, 'acum': list(accumulate(ps)), 'Ek': Ek, 'D': Ek2 / Ek, 'gap': gap, 'n': len(tam)}


def sortear_grupo(rng, g):
    i = bisect.bisect_right(g['acum'], rng.random())
    return g['ks'][min(i, len(g['ks']) - 1)]


def simular(lams, mu, cs, n0, K, seed, passo=5, theta=0.0, grupo=None, info=None, politica=None):
    """Cadeia de Markov em passos de `passo` s. lams[m] e cs[m] valem no minuto m.
    theta = taxa de desistência (por minuto, por aluno que espera e não está na catraca).
    grupo = distribuição do tamanho dos grupos (estimar_grupos): cada chegada traz k alunos e a taxa de
    chegadas vira λ/E[k]. O tamanho vem de outro gerador, então o sorteio principal não muda.
    info (dict, opcional) recebe as chegadas tentadas e as bloqueadas por K.
    politica = (N, M): uma catraca extra abre quando há N ou mais alunos no sistema e fecha quando cai a M ou menos
    (dois gatilhos, para não abrir e fechar a cada aluno). info['extra_passos'] conta os passos com ela aberta."""
    T = len(lams)
    rng = random.Random(seed)
    aberta, extra = False, 0
    rg = random.Random(seed * 7919 + 1) if grupo else None
    Ek = grupo['Ek'] if grupo else 1.0
    s = mu * passo / 60
    n, hist = n0, []
    tent = bloq = 0
    for i in range(int(round(T * 60 / passo))):
        m = min(int(i * passo / 60), T - 1)
        a = lams[m] / Ek * passo / 60
        c = cs[m]
        if politica:
            if not aberta and n >= politica[0]:
                aberta = True
            elif aberta and n <= politica[1]:
                aberta = False
            if aberta:
                c += 1
                extra += 1
        d = max(n - c, 0) * theta * passo / 60
        if a + c * s + d > 1:
            sys.exit(f'Passo de {passo:g} s grande demais para λ={lams[m]:.2f}, μ={mu:.2f}. Use --passo menor.')
        u = rng.random()
        if u < a:
            k = sortear_grupo(rg, grupo) if grupo else 1
            entra = min(k, K - n) if n < K else 0
            tent += k
            bloq += k - entra
            n += entra
        elif u < a + min(n, c) * s:
            n -= 1
        elif u < a + min(n, c) * s + d:
            n -= 1  # desistiu da fila
        hist.append(n)
    if info is not None:
        info['tentadas'], info['bloqueadas'], info['extra_passos'] = tent, bloq, extra
    return hist


def simular_trace(chegadas_seg, mu, cs, n0, K, seed, passo, theta=0.0, info=None):
    """Mesma cadeia, mas as chegadas são as reais (injetadas no passo em que aconteceram).
    Só o atendimento e as desistências são sorteados: testa o modelo de atendimento isolado."""
    T = len(cs)
    N = int(round(T * 60 / passo))
    por_passo = [0] * N
    for sec in chegadas_seg:
        i = int(sec / passo)
        if 0 <= i < N:
            por_passo[i] += 1
    rng = random.Random(seed)
    s = mu * passo / 60
    n, hist, tent, bloq = n0, [], 0, 0
    for i in range(N):
        m = min(int(i * passo / 60), T - 1)
        k = por_passo[i]
        if k:
            entra = min(k, max(K - n, 0))
            tent += k
            bloq += k - entra
            n += entra
        c = min(n, cs[m])
        d = max(n - cs[m], 0) * theta * passo / 60
        if c * s + d > 1:
            sys.exit(f'Passo de {passo:g} s grande demais para μ={mu:.2f}. Use --passo menor.')
        u = rng.random()
        if u < c * s + d:
            n -= 1
        hist.append(n)
    if info is not None:
        info['tentadas'], info['bloqueadas'] = tent, bloq
    return hist


def passo_seguro(lams, mu, cmax, theta, K, passo, Ek=1.0):
    """Maior passo (s) ≤ `passo` para o qual as chances de um passo somam no máximo 1."""
    while passo > 0.5 and (max(lams) / Ek + cmax * mu + K * theta) * passo / 60 > 1:
        passo /= 2
    return passo


def metricas(hist, lam_med, bloq=0.0):
    """bloq = fração das chegadas barradas por K: W usa só o λ de quem entrou (Little)."""
    L = sum(hist) / len(hist)
    lam = lam_med * (1 - bloq)
    return {'L': L, 'pior': max(hist), 'W': L / lam if lam > 0 else float('nan'),
            'longa': sum(1 for x in hist if x >= 10) / len(hist),
            'ocupada': sum(1 for x in hist if x > 0) / len(hist),
            'Lq': sum(x - 1 for x in hist if x > 1) / len(hist)}


def percentil(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


def dispersao(v):
    """D = variância ÷ média (≈ 1 para chegadas de Poisson)."""
    if len(v) < 2:
        return float('nan')
    m = sum(v) / len(v)
    return statistics.pvariance(v) / m if m > 0 else float('nan')


# ---------------------------------------------------------------- cálculos (usados pelo relatório e pelo simulador_gui.py)
def medir(d, limiar=None, min_pico=5, max_buraco=3, regra='slide59'):
    """λ de calma e de pico, desistências (θ) e fila inicial de uma sessão, sem imprimir nada."""
    T, arr = d['T'], d['arr']
    total = sum(arr)
    lam_med = total / T
    if limiar is None:
        limiar = limiar_regra(arr, regra)
    pico = classificar(arr, limiar, min_pico, max_buraco)
    cal_m = [a for a, p in zip(arr, pico) if not p]
    pic_m = [a for a, p in zip(arr, pico) if p]
    D = sum(d['des'])
    c0 = d['catracas']
    esperando = sum(max(n - c0, 0) for _, n in d['fila'])
    if d['fila']:
        esperando *= T / len(d['fila'])  # cada anotação vale ~1 min de aluno esperando
    return {
        'T': T, 'total': total, 'lam_med': lam_med, 'limiar': limiar, 'pico': pico, 'regra': regra,
        'janelas': janelas_pico(pico), 'cal_m': cal_m, 'pic_m': pic_m,
        'lam_cal': sum(cal_m) / len(cal_m) if cal_m else None,
        'lam_pic': sum(pic_m) / len(pic_m) if pic_m else None,
        'D': D, 'theta': D / esperando if (D and esperando) else 0.0,
        'n0': d['fila'][0][1] if d['fila'] else 0,
    }


def vals_mu(d, fila_min=3, de=0, ate=None):
    """Saídas por minuto (÷ catracas) nos minutos em que havia fila (≥ fila_min) no início e no fim do minuto."""
    T = d['T']
    ate = T if ate is None else min(ate, T)
    fm = {int(sec // 60): n for sec, n in d['fila']}
    c = max(1, d['catracas'])
    return [d['sai'][m] / c for m in range(max(0, de), ate)
            if fm.get(m, -1) >= fila_min and fm.get(m + 1, -1) >= fila_min]


def resumo_mu(vals):
    if len(vals) < 2:
        return None
    m, ic = media_ic(vals)
    return {'mu': m, 'ic': ic, 'n': len(vals), 'vals': vals}


def estimar_mu(d, fila_min=3, de=0, ate=None):
    """μ pelo slide 57 da Aula 09: média das saídas por minuto nos minutos com fila, com IC de 95%.
    Com fila, a catraca nunca fica parada esperando alguém chegar: o ritmo de saída é a capacidade."""
    return resumo_mu(vals_mu(d, fila_min, de, ate))


def lams_por_minuto(pico, lam_cal, lam_pic, lam_med):
    """λ de cada minuto: o de pico nos minutos de pico, o de calma nos demais."""
    return [lam_pic if p and lam_pic is not None else (lam_cal if lam_cal is not None else lam_med) for p in pico]


def cenarios_padrao(pico, theta):
    """(nome, catracas por minuto, θ) dos cenários comparados no relatório."""
    T = len(pico)
    cen = [('1 catraca', [1] * T, theta)]
    if theta > 0:
        cen.append(('1 cat. sem desist.', [1] * T, 0.0))
    if any(pico):
        cen.append(('2ª só no pico', [2 if p else 1 for p in pico], theta))
    cen.append(('2 a hora toda', [2] * T, theta))
    return cen


def escalonar(lams, pico, lam_cal, fator=2):
    """Saídas de aula escalonadas (slide 61): o excesso de chegadas de cada pico sobre a calma é espalhado num
    trecho `fator` vezes mais longo, a partir do mesmo minuto. O total de alunos não muda (salvo se passar do fim)."""
    T = len(lams)
    out = list(lams)
    if lam_cal is None:
        return out
    for a, b in janelas_pico(pico):
        exc = sum(lams[m] - lam_cal for m in range(a, b))
        for m in range(a, b):
            out[m] -= lams[m] - lam_cal
        fim = min(T, a + fator * (b - a))
        for m in range(a, fim):
            out[m] += exc / (fim - a)
    return out


def mu_mais_rapido(mu, troca_seg=None, corte=None):
    """Atendimento mais rápido (slide 61): cada aluno leva `corte` s a menos na catraca. Padrão: metade da troca
    medida (saída de um → início do próximo, ex.: cartão já na mão); sem cronômetro, 10% do tempo por aluno."""
    ciclo = 60 / mu
    if corte is None:
        corte = troca_seg / 2 if troca_seg else ciclo * 0.10
    corte = max(0.0, min(corte, ciclo * 0.5))
    return 60 / (ciclo - corte), corte


def cenarios_slide61(pico, theta, lams, lam_cal, mu, troca_seg=None, corte=None):
    """Os outros dois "e se?" do slide 61, sem catraca extra: atendimento mais rápido e aulas escalonadas."""
    T = len(pico)
    mu_r, c = mu_mais_rapido(mu, troca_seg, corte)
    cen = [('atend. mais rápido', [1] * T, theta,
            {'mu': mu_r, 'nota': f'μ de {br(mu)} para {br(mu_r)} /min: {br(c, 1)} s a menos por aluno'
             + (' (metade da troca medida)' if troca_seg and corte is None else '')})]
    if any(pico) and lam_cal is not None:
        cen.append(('aulas escalonadas', [1] * T, theta,
                    {'lams': escalonar(lams, pico, lam_cal),
                     'nota': 'o excesso de chegadas de cada pico espalhado no dobro do tempo (mesmo total de alunos)'}))
    return cen


def passo_cenarios(cen, lams, mu, theta, K, passo, Ek=1.0):
    """Passo seguro para todos os cenários (cada um pode ter seu λ e seu μ)."""
    for item in cen:
        ex = item[3] if len(item) > 3 else {}
        cmax = max(item[1]) + (1 if ex.get('politica') else 0)
        passo = min(passo, passo_seguro(ex.get('lams', lams), ex.get('mu', mu), cmax, theta, K, passo, Ek))
    return passo


def verificar(lam, mu, K, seed, passo, horas=200, grupo=None):
    """Simulador com λ constante e 1 catraca por `horas` h, para comparar com as fórmulas:
    M/M/1 com chegadas uma a uma (grupo=None) ou M^X/M/1 com chegadas em grupo."""
    h = simular([lam] * (horas * 60), mu, [1] * (horas * 60), 0, K, seed, passo, grupo=grupo)
    f = formulas_grupo(lam, mu, grupo['D']) if grupo else formulas(lam, mu)
    return f, metricas(h, lam)


def simular_cenarios(cen, lams, mu, n0, K, seed, passo, reps, lam_med, progresso=None, grupo=None):
    """Roda `reps` réplicas de cada cenário com as mesmas sementes. progresso(feitas, total) é opcional."""
    res = {}
    total, feitas = len(cen) * reps, 0
    for item in cen:
        nome, cs, th = item[:3]
        ex = item[3] if len(item) > 3 else {}
        mu_c, lams_c, pol = ex.get('mu', mu), ex.get('lams', lams), ex.get('politica')
        hs, ms, fr, topo, ext = [], [], [], 0, []
        for i in range(reps):
            info = {}
            h = simular(lams_c, mu_c, cs, n0, K, seed + i, passo, th, grupo, info, pol)
            ext.append(info['extra_passos'] * passo / 60)
            b = info['bloqueadas'] / info['tentadas'] if info['tentadas'] else 0.0
            hs.append(h)
            fr.append(b)
            ms.append(metricas(h, lam_med, b))
            topo += max(h) >= K
            feitas += 1
            if progresso:
                progresso(feitas, total)
        Lm, Lic = media_ic([m['L'] for m in ms])
        Wm, Wic = media_ic([m['W'] for m in ms])
        res[nome] = {
            'hs': hs, 'ms': ms, 'cs': cs, 'theta': th, 'L': Lm, 'Lic': Lic, 'W': Wm, 'Wic': Wic,
            'pior': sum(m['pior'] for m in ms) / len(ms),
            'longa': sum(m['longa'] for m in ms) / len(ms),
            'bloq': sum(fr) / len(fr), 'toca_K': topo / reps,
            'mu': mu_c, 'lams': lams_c, 'politica': pol, 'nota': ex.get('nota', ''),
            'custo': sum(c - 1 for c in cs) + sum(ext) / len(ext),  # minutos de catraca extra aberta
        }
    return res


def eficiencia(res, n_alunos, base='1 catraca'):
    """Minutos de espera poupados (somando todos os alunos) por minuto de catraca extra aberta."""
    w0 = res[base]['W']
    for r in res.values():
        r['poupado'] = (w0 - r['W']) * n_alunos
        r['efic'] = r['poupado'] / r['custo'] if r['custo'] > 0.5 else None
    return res


GATILHOS = (3, 5, 8, 10, 12, 15, 20, 25, 30)


def buscar_gatilho(lams, mu, pico, n0, K, seed, passo, reps, lam_med, theta, grupo=None, Ns=GATILHOS, progresso=None):
    """Pergunta da equipe: testa a 2ª catraca pela fila (abre com N, fecha com M = N/2) para vários N e compara
    com a 2ª catraca no horário de pico (ou a hora toda, sem pico). O melhor N é o de maior eficiência entre os
    que esperam no máximo o mesmo que a referência."""
    T = len(lams)
    ref_nome = '2ª só no pico' if any(pico) else '2 a hora toda'
    cen = [('1 catraca', [1] * T, theta),
           (ref_nome, [2 if p else 1 for p in pico] if any(pico) else [2] * T, theta)]
    cen += [(f'N{N}', [1] * T, theta, {'politica': (N, N // 2)}) for N in Ns]
    res = simular_cenarios(cen, lams, mu, n0, K, seed, passo, reps, lam_med, progresso, grupo)
    eficiencia(res, lam_med * T)
    ref = res[ref_nome]
    linhas = [{'N': N, 'M': N // 2, 'W': res[f'N{N}']['W'], 'custo': res[f'N{N}']['custo'], 'efic': res[f'N{N}']['efic']}
              for N in Ns]
    ok = [x for x in linhas if x['efic'] is not None and x['W'] <= ref['W'] + 1e-9]
    cand = ok or [x for x in linhas if x['efic'] is not None]
    melhor = max(cand, key=lambda x: x['efic']) if cand else None
    return {'linhas': linhas, 'melhor': melhor, 'mesma_espera': bool(ok), 'ref_nome': ref_nome, 'ref': ref,
            'W0': res['1 catraca']['W']}


def cenario_fila(T, theta, N, M):
    return ('2ª pela fila', [1] * T, theta, {'politica': (N, M), 'nota': f'abre quando a fila chega a {N} e fecha quando cai a {M}'})


def validar(fila, hs, passo, de=None, ate=None):
    """Fila reconstruída x réplicas simuladas nos mesmos instantes (L, pior momento, fração com fila ≥ 10).
    de/ate (minutos) restringem a comparação a um trecho, para validar fora da amostra."""
    amostras = [(sec, n) for sec, n in fila
                if (de is None or sec / 60 >= de) and (ate is None or sec / 60 < ate)]
    if len(amostras) < 2:
        return []
    anot = [n for _, n in amostras]
    idx = [min(int(sec / passo), len(hs[0]) - 1) for sec, _ in amostras]
    Ls = [sum(h[i] for i in idx) / len(idx) for h in hs]
    ps = [max(h[i] for i in idx) for h in hs]
    gs = [sum(1 for i in idx if h[i] >= 10) / len(idx) for h in hs]
    linhas = []
    for rot, a, sim, casas in (
        ('L (alunos em média)', sum(anot) / len(anot), Ls, 1),
        ('pior momento', max(anot), ps, 0),
        ('fração com fila ≥ 10', sum(1 for x in anot if x >= 10) / len(anot), gs, 2),
    ):
        linhas.append(linha_validacao(rot, a, sim, casas))
    return linhas


def comparar_curva(fila, hs, passo, minimo=3):
    """Slide 16: "comparem a curva com a fila anotada". Em cada minuto, a faixa 5%–95% das réplicas naquele
    instante; conta em quantos minutos a fila observada cai dentro. A mesma conta feita para cada réplica dá
    o que o próprio modelo produz: abaixo do percentil 5% dela, a curva não acompanha."""
    if len(fila) < 2:
        return None
    idx = [min(int(sec / passo), len(hs[0]) - 1) for sec, _ in fila]
    obs = [n for _, n in fila]
    cols = [[h[i] for h in hs] for i in idx]
    lo = [percentil(c, .05) for c in cols]
    hi = [percentil(c, .95) for c in cols]
    med = [sum(c) / len(c) for c in cols]
    dentro = [lo[j] <= obs[j] <= hi[j] for j in range(len(obs))]
    frac = sum(dentro) / len(dentro)
    fr_rep = [sum(1 for j, i in enumerate(idx) if lo[j] <= h[i] <= hi[j]) / len(idx) for h in hs]
    rmse = math.sqrt(sum((m - o) ** 2 for m, o in zip(med, obs)) / len(obs))
    fora, j = [], 0
    while j < len(obs):
        if dentro[j]:
            j += 1
            continue
        k = j
        while k < len(obs) and not dentro[k]:
            k += 1
        if k - j >= minimo:
            acima = sum(med[x] - obs[x] for x in range(j, k)) > 0
            fora.append((int(fila[j][0] // 60), int(fila[k - 1][0] // 60) + 1, 'simulada acima' if acima else 'simulada abaixo'))
        j = k
    p5 = percentil(fr_rep, .05)
    linha = {'rot': 'curva: minutos na faixa', 'obs': frac, 'sim': sum(fr_rep) / len(fr_rep), 'lo': p5, 'hi': 1.0,
             'ok': frac >= p5, 'casas': 2}
    return {'frac': frac, 'rmse': rmse, 'fora': fora, 'linha': linha, 'media': med}


def texto_fora(fora, t0):
    h = hora_de(t0)
    return '; '.join(f'{h(a)}–{h(b)} ({lado})' for a, b, lado in fora)


def linha_validacao(rot, obs, sim, casas):
    lo, hi = percentil(sim, .05), percentil(sim, .95)
    return {'rot': rot, 'obs': obs, 'sim': sum(sim) / len(sim), 'lo': lo, 'hi': hi,
            'ok': lo <= obs <= hi, 'casas': casas}


def dispersao_modelo(lams, passo, grupo, reps, seed, mascara=None):
    """D das chegadas por minuto geradas pelo modelo (só as chegadas, com os mesmos λ e grupos)."""
    Ek = grupo['Ek'] if grupo else 1.0
    npm = max(1, int(round(60 / passo)))
    Dc, Dt = [], []
    for r in range(reps):
        rng = random.Random(seed + 100_000 + r)
        rg = random.Random((seed + 100_000 + r) * 7919 + 1)
        cont = []
        for lam in lams:
            a = lam / Ek * passo / 60
            c = 0
            for _ in range(npm):
                if rng.random() < a:
                    c += sortear_grupo(rg, grupo) if grupo else 1
            cont.append(c)
        Dt.append(dispersao(cont))
        if mascara is not None:
            Dc.append(dispersao([c for c, p in zip(cont, mascara) if p]))
    return Dc, Dt


def validar_dispersao(d, md, lams, passo, grupo, reps, seed):
    """D observado (calma e total) x faixa 5%–95% do modelo. O modelo errado não imita esta medida."""
    calma = [not p for p in md['pico']]
    Dc, Dt = dispersao_modelo(lams, passo, grupo, reps, seed, calma)
    linhas = []
    obs_c = dispersao(md['cal_m'])
    if len(md['cal_m']) > 2 and not math.isnan(obs_c):
        Dc = [x for x in Dc if not math.isnan(x)]
        if Dc:
            linhas.append(linha_validacao('D das chegadas, calma', obs_c, Dc, 1))
    obs_t = dispersao(d['arr'])
    Dt = [x for x in Dt if not math.isnan(x)]
    if Dt and not math.isnan(obs_t):
        linhas.append(linha_validacao('D das chegadas, total', obs_t, Dt, 1))
    return linhas


def simular_base_trace(d, mu, n0, K, seed, passo, reps, theta):
    T = d['T']
    pt = passo_seguro([0.0], mu, 1, theta, K, passo)
    hs = [simular_trace(d['chegadas_seg'], mu, [1] * T, n0, K, seed + i, pt, theta) for i in range(reps)]
    return hs, pt


def sensibilidade(md, mus, K, seed, passo, reps, grupo, lam_med):
    """W e L de 1 catraca e da 2ª catraca (só no pico, ou a hora toda se não houver pico) para cada μ."""
    pico, theta = md['pico'], md['theta']
    lams = lams_por_minuto(pico, md['lam_cal'], md['lam_pic'], lam_med)
    T = len(pico)
    cen = [('1 catraca', [1] * T, theta)]
    cen.append(('2ª só no pico', [2 if p else 1 for p in pico], theta) if any(pico) else ('2 a hora toda', [2] * T, theta))
    Ek = grupo['Ek'] if grupo else 1.0
    out = []
    for mu, origem in mus:
        ps = passo_seguro(lams, mu, 2, theta, K, passo, Ek)
        r = simular_cenarios(cen, lams, mu, md['n0'], K, seed, ps, reps, lam_med, grupo=grupo)
        out.append({'mu': mu, 'origem': origem, 'res': r,
                    'rho_pico': (md['lam_pic'] / mu) if md['lam_pic'] else None})
    return out


def opcoes_sens(est, mu, mu_cron, extra=None):
    """Valores de μ para a tabela de sensibilidade: IC da estimativa, o μ usado e o cronometrado."""
    v = []
    if extra:
        v += [(x, 'informado') for x in extra]
    else:
        if est and not math.isnan(est['ic']):
            v += [(est['mu'] - est['ic'], 'IC baixo'), (est['mu'], 'estimado'), (est['mu'] + est['ic'], 'IC alto')]
        v.append((mu, 'usado'))
        if mu_cron:
            v.append((mu_cron, 'cronometrado (otimista)'))
    vistos, out = set(), []
    for x, o in sorted(v, key=lambda t: t[0]):
        k = round(x, 2)
        if x > 0 and k not in vistos:
            vistos.add(k)
            out.append((x, o))
    return out


def hora_de(t0):
    return (lambda m: (t0 + timedelta(minutes=m)).strftime('%H:%M')) if t0 else (lambda m: f'min {m}')


def texto_janelas(janelas, t0):
    if not t0:
        return ' e '.join(f'do minuto {a} ao {b}' for a, b in janelas)
    h = hora_de(t0)
    return ' e '.join(f'das {h(a)} às {h(b)}' for a, b in janelas)


# ---------------------------------------------------------------- análise
def imprimir_validacao(linhas):
    P(f'  {"":<26}{"observada":>10}{"simulada (média)":>18}{"faixa 5%-95%":>16}{"dentro?":>9}')
    for v in linhas:
        rot, a, sm, lo, hi, d1 = v['rot'], v['obs'], v['sim'], v['lo'], v['hi'], v['casas']
        ok = 'sim' if v['ok'] else 'NÃO'
        if d1 == 2:
            P(f'  {rot:<26}{br(a * 100, 0) + "%":>10}{br(sm * 100, 0) + "%":>18}{br(lo * 100, 0) + "%-" + br(hi * 100, 0) + "%":>16}{ok:>9}')
        else:
            P(f'  {rot:<26}{br(a, d1):>10}{br(sm, d1):>18}{br(lo, d1) + "-" + br(hi, d1):>16}{ok:>9}')


def analisar(d, mu, args, pasta, ctx=None):
    ctx = ctx or {}
    T, arr = d['T'], d['arr']
    total = sum(arr)
    if total == 0:
        P(f'Sessão {d["nome"]}: nenhuma chegada registrada. Pulando.')
        return None
    md = medir(d, args.limiar, args.pico_min, args.buraco_max, args.regra_pico)
    lam_med, limiar, pico = md['lam_med'], md['limiar'], md['pico']
    cal_m, pic_m = md['cal_m'], md['pic_m']
    lam_cal, lam_pic = md['lam_cal'], md['lam_pic']
    hora = hora_de(d['t0'])

    P('=' * 72)
    P(f'SESSÃO {d["nome"]}  ({T} min observados, {d["catracas"]} catraca(s) aberta(s))')
    P('=' * 72)
    if ctx.get('ajuste_txt'):
        P(f'Ajuste do balanço ({NOMES_AJUSTE[args.ajuste]}): {ctx["ajuste_txt"].rstrip(".")}.')
    if d['reconstruida']:
        P(f'Balanço: a fila reconstruída (fila inicial + chegadas − desistências − saídas) termina com {d["fila_final"]} alunos. '
          'Se não for perto de 0, faltou anotar algo: veja --comparar-ajustes.')
    lim_txt = br(limiar) + ' /min' if limiar != float('inf') else 'nenhum (sem pico claro)'
    regra_txt = 'informado (--limiar)' if args.limiar else NOMES_REGRA[args.regra_pico]
    P(f'Chegadas: {total}  |  λ médio da sessão = {br(lam_med)} /min  |  limiar de pico = {lim_txt} '
      f'(regra: {regra_txt}; aplicado à média móvel de 5 min)')
    P(f'  calma: {len(cal_m)} min, λ = {br(lam_cal)} /min   |   pico: {len(pic_m)} min, λ = {br(lam_pic)} /min')
    if md['janelas']:
        P(f'  pico {texto_janelas(md["janelas"], d["t0"])} (picos com menos de {args.pico_min} min descartados; '
          f'buracos de até {args.buraco_max} min de calma no meio do pico, juntados)')
    if cal_m and len(cal_m) > 2:
        P(f'  dispersão D = variância/média das chegadas por minuto: calma {br(dispersao(cal_m))}, '
          f'sessão inteira {br(dispersao(arr))} (perto de 1 é Poisson)')
    grupo = estimar_grupos(d['chegadas_seg'], args.grupo_seg)
    if grupo:
        dist = ', '.join(f'{k}: {br(p * 100, 0)}%' for k, p in zip(grupo['ks'], grupo['ps']) if p >= .01)
        P(f'  chegadas em grupo (intervalo ≤ {br(grupo["gap"], 1)} s): {grupo["n"]} grupos, tamanho médio E[k] = {br(grupo["Ek"])}; '
          f'D esperado do Poisson composto = E[k²]/E[k] = {br(grupo["D"])}')
        P(f'    tamanhos: {dist}')
    gref = None if grupo else estimar_grupos(d['chegadas_seg'], getattr(args, 'grupo_ref', 0))
    if gref:
        P(f'  modelo principal: M/M/1, chegadas uma a uma. Grupos medidos (intervalo ≤ {br(gref["gap"], 1)} s), só para comparação: '
          f'E[k] = {br(gref["Ek"])}, D esperado = {br(gref["D"])}')
    Ek = grupo['Ek'] if grupo else 1.0

    # μ desta sessão e tendência
    P('')
    e = estimar_mu(d, args.fila_min)
    if e:
        P(f'μ desta sessão (saídas/min com fila ≥ {args.fila_min}): {br(e["mu"])} ± {br(e["ic"])} /min em {e["n"]} min')
        h = T // 2
        e1, e2 = estimar_mu(d, args.fila_min, 0, h), estimar_mu(d, args.fila_min, h, T)
        if e1 and e2:
            P(f'  1ª metade: {br(e1["mu"])} ± {br(e1["ic"])} ({e1["n"]} min)   |   2ª metade: {br(e2["mu"])} ± {br(e2["ic"])} ({e2["n"]} min)')
            if e2['mu'] < 0.85 * e1['mu']:
                P(f'  ATENÇÃO: com fila, as saídas caem {br((1 - e2["mu"] / e1["mu"]) * 100, 0)}% da 1ª para a 2ª metade. Ou o observador '
                  'perdeu saídas, ou a catraca está sendo freada por outra fila lá dentro (servir, mesas): nesse caso o '
                  'gargalo não é a catraca e a 2ª catraca só leva a fila para dentro. Meçam a fila de dentro (--fila).')
    else:
        P('μ desta sessão: poucos minutos com fila para estimar.')

    # desistências e fórmulas
    D, theta = md['D'], md['theta']
    P('')
    if D:
        lam_ef = lam_med - D / T
        P(f'Desistências: {D} alunos saíram da fila sem passar ({br(D / total * 100, 0)}% das chegadas). '
          f'Taxa θ = {br(theta, 3)} /min por aluno que espera. λ efetivo (quem passou) = {br(lam_ef)} /min, ρ efetivo = {br(lam_ef / mu)}')
    else:
        P('Desistências: nenhuma registrada; o simulador não usa desistência. Se houve, anotem com o botão "Alguém saiu da fila sem passar".')
    P('')
    P(f'Modelo M/M/1 (μ = {br(mu)} /min, atendimento médio {br(60 / mu, 1)} s)'
      + (f' e M^X/M/1 com os grupos medidos (D = E[k²]/E[k] = {br(grupo["D"])}: L e W multiplicados por (1 + D)/2 = {br((1 + grupo["D"]) / 2)})' if grupo else ''))
    cab_g = f'{"L grupos":>10}{"W grupos":>10}' if grupo else ''
    P(f'  {"trecho":<8}{"λ":>7}{"ρ":>7}{"vazia":>8}{"L":>8}{"W (min)":>10}{"Wq (min)":>10}{cab_g}')
    for rot, lam in (('calma', lam_cal), ('pico', lam_pic), ('sessão', lam_med)):
        if lam is None:
            continue
        f = formulas(lam, mu)
        if f['estavel']:
            gx = ''
            if grupo:
                fg = formulas_grupo(lam, mu, grupo['D'])
                gx = f'{br(fg["L"]):>10}{br(fg["W"]):>10}'
            P(f'  {rot:<8}{br(lam):>7}{br(f["rho"]):>7}{br(f["vazia"] * 100, 0) + "%":>8}{br(f["L"]):>8}{br(f["W"]):>10}{br(f["Wq"]):>10}{gx}')
        else:
            P(f'  {rot:<8}{br(lam):>7}{br(f["rho"]):>7}   ρ ≥ 1 (ou perto): fórmulas não valem, a fila cresce. Use a simulação.')
    cv = ctx.get('cv_cron')
    if lam_cal and cv is not None and formulas(lam_cal, mu)['estavel']:
        rho = lam_cal / mu
        wq_mm1 = rho / (1 - rho) / mu
        wq_mg1 = wq_mm1 * (1 + cv * cv) / 2
        P(f'  M/G/1 na calma (Pollaczek-Khinchine) com o CV cronometrado = {br(cv)}: Wq = {br(wq_mg1)} min, contra {br(wq_mm1)} do M/M/1 '
          f'(CV = 1). Com CV = 0 (catraca determinística) seria {br(wq_mm1 / 2)}. O CV cronometrado mede só a passagem na catraca.')

    # verificação num trecho sem pico
    P('')
    if lam_cal is not None and formulas(lam_cal, mu)['estavel'] and lam_cal > 0:
        horas = 200
        pv = passo_seguro([lam_cal], mu, 1, 0.0, args.K, args.passo)
        f, mt = verificar(lam_cal, mu, args.K, args.seed, pv, horas)
        P(f'VERIFICAÇÃO (slide 19): simulador com λ de calma por {horas} h simuladas contra as fórmulas')
        cols = [('M/M/1 (uma a uma)', f, mt)]
        if grupo:
            pg = passo_seguro([lam_cal], mu, 1, 0.0, args.K, args.passo, Ek)
            fg, mg = verificar(lam_cal, mu, args.K, args.seed, pg, horas, grupo)
            cols.append(('M^X/M/1 (grupos)', fg, mg))
        P(f'  {"métrica":<22}' + ''.join(f'{nome:>22}' for nome, _, _ in cols))
        P(f'  {"":<22}' + ''.join(f'{"fórmula":>11}{"simulado":>11}' for _ in cols))
        P(f'  {"utilização ρ":<22}' + ''.join(f'{br(a["rho"] * 100, 0) + "%":>11}{br(b["ocupada"] * 100, 0) + "%":>11}' for _, a, b in cols))
        P(f'  {"catraca vazia 1 − ρ":<22}' + ''.join(f'{br(a["vazia"] * 100, 0) + "%":>11}{br((1 - b["ocupada"]) * 100, 0) + "%":>11}' for _, a, b in cols))
        P(f'  {"alunos no sistema L":<22}' + ''.join(f'{br(a["L"]):>11}{br(b["L"]):>11}' for _, a, b in cols))
        P(f'  {"tempo W (min)":<22}' + ''.join(f'{br(a["W"]):>11}{br(b["W"]):>11}' for _, a, b in cols))
        P(f'  {"espera na fila Wq":<22}' + ''.join(f'{br(a["Wq"]):>11}{br(b["Lq"] / lam_cal):>11}' for _, a, b in cols))
        P('  Se os dois lados ficam próximos, o código faz o que o modelo diz. M^X/M/1: L = ρ(1 + D)/(2(1 − ρ)), D = E[k²]/E[k].')
    else:
        P('VERIFICAÇÃO: sem trecho de calma estável nesta sessão. Rode com outra sessão ou ajuste --limiar.')

    # cenários
    lams = lams_por_minuto(pico, lam_cal, lam_pic, lam_med)
    cen = cenarios_padrao(pico, theta)
    cen += cenarios_slide61(pico, theta, lams, lam_cal, mu, ctx.get('troca'), args.rapido_seg)
    n0 = md['n0']
    passo = passo_cenarios(cen + [cenario_fila(T, theta, 1, 0)], lams, mu, theta, args.K, args.passo, Ek)
    busca = buscar_gatilho(lams, mu, pico, n0, args.K, args.seed, passo, min(args.reps, 200), lam_med, theta, grupo)
    if busca['melhor']:
        cen.append(cenario_fila(T, theta, busca['melhor']['N'], busca['melhor']['M']))
    if passo != args.passo:
        P(f'(passo reduzido de {br(args.passo, 1)} s para {br(passo, 2)} s: com o passo maior as chances somariam mais de 1)')
    P('')
    gtxt = f'chegadas em grupos de {br(Ek)} em média' if grupo else 'chegadas uma a uma'
    P(f'SIMULAÇÃO: {args.reps} réplicas de {T} min, passo {br(passo, 2)} s, K = {args.K}, fila inicial = {n0}, θ = {br(theta, 3)} /min, '
      f'{gtxt}, mesma semente em todos os cenários')
    P(f'  {"cenário":<20}{"L médio":>14}{"pior momento":>14}{"W (min)":>12}{"fila ≥ 10":>12}{"custo":>16}{"eficiência":>12}')
    res = simular_cenarios(cen, lams, mu, n0, args.K, args.seed, passo, args.reps, lam_med, grupo=grupo)
    eficiencia(res, lam_med * T)
    for nome, r in res.items():
        custo = f'{br(r["custo"], 0)} catraca-min' if r['custo'] > 0.5 else '-'
        ef = br(r['efic'], 0) if r['efic'] is not None else '-'
        P(f'  {nome:<20}{br(r["L"], 1) + " ±" + br(r["Lic"], 1):>14}{br(r["pior"], 1):>14}{br(r["W"], 1) + " ±" + br(r["Wic"], 1):>12}'
          f'{br(r["longa"] * 100, 0) + "%":>12}{custo:>16}{ef:>12}')
    P('  (± é o IC de 95% entre réplicas. Uma hora simulada é uma amostra, não uma medida.)')
    P('  Custo = minutos de catraca extra aberta (slide 61: "um parâmetro por vez, com ganho e custo").')
    P('  Eficiência = minutos de espera poupados, somando todos os alunos, por minuto de catraca extra aberta.')
    for nome, r in res.items():
        if r['nota'] and not r['politica']:
            P(f'  {nome}: {r["nota"]}. Sem catraca extra; o custo é mudar o procedimento ou os horários.')
        elif r['politica']:
            P(f'  {nome}: {r["nota"]} (o melhor gatilho da busca, na seção PERGUNTA DA EQUIPE).')
    for nome, r in res.items():
        if r['toca_K'] > .05:
            P(f'  ATENÇÃO: em {br(r["toca_K"] * 100, 0)}% das réplicas de "{nome}" a fila bateu em K = {args.K} '
              f'({br(r["bloq"] * 100, 1)}% das chegadas barradas). Aumentem --K: a fila está sendo cortada pelo limite.')

    # validação
    P('')
    base = res['1 catraca']
    if d['fila']:
        rot = 'reconstruída' if d['reconstruida'] else 'anotada'
        P(f'VALIDAÇÃO (slide 22): fila {rot} ({len(d["fila"])} amostras) x simulada nos mesmos instantes')
        if d['reconstruida']:
            P('  Atenção: a fila não foi contada (sem observador C); foi reconstruída das mesmas contagens que dão λ e μ.')
        linhas = validar(d['fila'], base['hs'], passo)
        linhas += validar_dispersao(d, md, lams, passo, grupo, args.reps, args.seed)
        curva = comparar_curva(d['fila'], base['hs'], passo)
        if curva:
            linhas.append(curva['linha'])
        imprimir_validacao(linhas)
        if curva:
            P(f'  Curva (slide 16): a fila observada cai na faixa 5%-95% das réplicas em {br(curva["frac"] * 100, 0)}% dos minutos '
              f'(as próprias réplicas: {br(curva["linha"]["sim"] * 100, 0)}% em média, mínimo aceito {br(curva["linha"]["lo"] * 100, 0)}%). '
              f'Erro médio da curva média: {br(curva["rmse"], 1)} alunos.')
            if curva['fora']:
                P(f'  Trechos de 3+ minutos fora da faixa: {texto_fora(curva["fora"], d["t0"])}.')
        P('  D (Aula 09, slide 25) é uma medida que um modelo errado não imita: chegadas uma a uma dão D ≈ 1.')
        P('  Se algum ficar fora da faixa, revejam primeiro as medições: contagens, separação calma/pico e o μ.')

        # trace-driven
        P('')
        hs_t, pt = simular_base_trace(d, mu, n0, args.K, args.seed, passo, args.reps, theta)
        P(f'VALIDAÇÃO COM AS CHEGADAS REAIS (trace): só atendimento e desistências sorteados, {args.reps} réplicas, passo {br(pt, 2)} s')
        imprimir_validacao(validar(d['fila'], hs_t, pt))
        P('  Isola o atendimento: se falhar aqui, o problema está em μ (ou nas saídas anotadas), não nas chegadas.')

        # fora da amostra
        h = T // 2
        e1 = estimar_mu(d, args.fila_min, 0, h)
        P('')
        P('VALIDAÇÃO FORA DA AMOSTRA: μ estimado num trecho, fila comparada em outro')
        if e1:
            p1 = passo_seguro(lams, e1['mu'], 1, theta, args.K, args.passo, Ek)
            hs1 = [simular(lams, e1['mu'], [1] * T, n0, args.K, args.seed + i, p1, theta, grupo) for i in range(args.reps)]
            v = validar(d['fila'], hs1, p1, de=h, ate=T)
            P(f'  μ da 1ª metade ({hora(0)}–{hora(h)}) = {br(e1["mu"])} /min ({e1["n"]} min), validação na 2ª metade ({hora(h)}–{hora(T)}):')
            if v:
                imprimir_validacao(v)
        else:
            P('  1ª metade sem minutos com fila suficientes para estimar μ.')
        eo = ctx.get('mu_outras')
        if eo:
            po = passo_seguro(lams, eo['mu'], 1, theta, args.K, args.passo, Ek)
            hso = [simular(lams, eo['mu'], [1] * T, n0, args.K, args.seed + i, po, theta, grupo) for i in range(args.reps)]
            P(f'  μ das outras sessões = {br(eo["mu"])} ± {br(eo["ic"])} /min ({eo["n"]} min), validação nesta sessão inteira:')
            imprimir_validacao(validar(d['fila'], hso, po))
    else:
        P('VALIDAÇÃO: sem dados suficientes para reconstruir a fila nesta sessão.')

    # refinamento: como dar λ ao simulador (regra de pico e média móvel)
    if d['fila'] and any(pico):
        rr = min(args.reps, 200)
        outra = 'duas-medias' if args.regra_pico == 'slide59' else 'slide59'
        md2 = medir(d, None, args.pico_min, args.buraco_max, outra)
        alts = [(f'2 níveis, {NOMES_REGRA[args.regra_pico]}', pico, lams, 'principal'),
                (f'2 níveis, {NOMES_REGRA[outra]}', md2['pico'], lams_por_minuto(md2['pico'], md2['lam_cal'], md2['lam_pic'], lam_med), ''),
                ('média móvel de 5 min', pico, suavizar(arr), 'refinamento')]
        P('')
        P(f'REFINAMENTO: como dar λ ao simulador ({rr} réplicas, μ = {br(mu)}; a 2ª catraca abre nos minutos de pico de cada linha)')
        P(f'  {"λ usado":<52}{"2ª catraca":>11}{"curva":>8}{"fila (3)":>10}{"W 1 cat.":>10}{"W 2ª pico":>11}')
        for rot, pk, lm, tag in alts:
            cc = [('1 catraca', [1] * T, theta)]
            if any(pk):
                cc.append(('2ª só no pico', [2 if p else 1 for p in pk], theta))
            pp = passo_seguro(lm, mu, 2, theta, args.K, args.passo, Ek)
            rx = simular_cenarios(cc, lm, mu, n0, args.K, args.seed, pp, rr, lam_med, grupo=grupo)
            vf = validar(d['fila'], rx['1 catraca']['hs'], pp)
            cx = comparar_curva(d['fila'], rx['1 catraca']['hs'], pp)
            w2 = rx.get('2ª só no pico')
            nome_l = rot + (f' ({tag})' if tag else '')
            P(f'  {nome_l:<52}{str(sum(pk)) + " min":>11}{br(cx["frac"] * 100, 0) + "%":>8}'
              f'{str(sum(v["ok"] for v in vf)) + "/" + str(len(vf)):>10}{br(rx["1 catraca"]["W"], 1) + " min":>10}'
              f'{(br(w2["W"], 1) + " min") if w2 else "-":>11}')
        P('  "curva" = minutos com a fila observada dentro da faixa 5%-95%. Os slides pedem 2 níveis (calma e pico);')
        P('  a média móvel copia a curva das chegadas minuto a minuto, por isso encaixa melhor quase por construção.')

    # refinamento: chegadas em grupo, comparado ao M/M/1
    if gref and d['fila']:
        P('')
        P(f'REFINAMENTO: M/M/1 (chegadas uma a uma) x chegadas em grupo (E[k] = {br(gref["Ek"])}, D = {br(gref["D"])}), '
          f'mesmo μ, θ e semente, {args.reps} réplicas')
        pg = passo_cenarios(cen, lams, mu, theta, args.K, args.passo, gref['Ek'])
        res_g = simular_cenarios(cen, lams, mu, n0, args.K, args.seed, pg, args.reps, lam_med, grupo=gref)
        eficiencia(res_g, lam_med * T)
        ctx['res_grupo'] = res_g
        modelos = (('M/M/1 (principal)', res, passo, None), ('em grupo', res_g, pg, gref))
        seg = '2ª só no pico' if '2ª só no pico' in res else '2 a hora toda'
        P(f'  {"modelo":<20}{"W 1 catraca":>13}{"W " + seg:>18}{"fila (3 itens)":>16}{"D calma":>10}{"D total":>10}')
        for rot, rr, pp, gg in modelos:
            vf = validar(d['fila'], rr['1 catraca']['hs'], pp)
            vd = {v['rot']: v for v in validar_dispersao(d, md, lams, pp, gg, args.reps, args.seed)}

            def dtxt(k):
                v = vd.get(k)
                return '-' if v is None else f'{br(v["lo"], 1)}-{br(v["hi"], 1)} {"✓" if v["ok"] else "✗"}'
            P(f'  {rot:<20}{br(rr["1 catraca"]["W"], 1) + " min":>13}{br(rr[seg]["W"], 1) + " min":>18}'
              f'{str(sum(v["ok"] for v in vf)) + "/" + str(len(vf)):>16}'
              f'{dtxt("D das chegadas, calma"):>10}{dtxt("D das chegadas, total"):>10}')
        P(f'  D observado: calma {br(dispersao(cal_m))}, total {br(dispersao(arr))}. As colunas de D mostram a faixa 5%-95% do modelo.')
        P('  O M/M/1 é o modelo pedido nos slides; os grupos mostram o que muda quando o modelo também imita as rajadas.')

    # sensibilidade
    sens = []
    mus = opcoes_sens(ctx.get('mu_est'), mu, ctx.get('mu_cron'), args.sens)
    if mus:
        rs = min(args.reps, 100)
        P('')
        P(f'SENSIBILIDADE A μ ({rs} réplicas por linha, mesma semente): o μ é a medida mais incerta do estudo')
        sens = sensibilidade(md, mus, args.K, args.seed, args.passo, rs, grupo, lam_med)
        seg = '2ª só no pico' if any(pico) else '2 a hora toda'
        P(f'  {"μ (/min)":>9}  {"origem":<25}{"ρ pico":>8}{"W 1 catraca":>13}{"W " + seg:>18}')
        for x in sens:
            r1, r2 = x['res']['1 catraca'], x['res'][seg]
            P(f'  {br(x["mu"]):>9}  {x["origem"]:<25}{br(x["rho_pico"]):>8}{br(r1["W"], 1) + " min":>13}{br(r2["W"], 1) + " min":>18}')

    # pergunta da equipe (slide 55) e achado dos grupos
    P('')
    P('PERGUNTA DA EQUIPE: abrir a 2ª catraca quando a fila chega a N alunos (e fechar quando cai à metade) poupa mais')
    P('minutos de espera por minuto de catraca aberta do que abri-la no horário de pico?')
    ref_nome = busca['ref_nome']
    P(f'  busca do gatilho ({min(args.reps, 200)} réplicas por linha; eficiência = minutos de espera poupados por catraca-min):')
    P(f'  {"política":<34}{"catraca-min":>12}{"W (min)":>10}{"eficiência":>12}')
    rr = busca['ref']
    P(f'  {ref_nome + " (referência)":<34}{br(rr["custo"], 0):>12}{br(rr["W"], 1):>10}{br(rr["efic"], 0) if rr["efic"] else "-":>12}')
    for x in busca['linhas']:
        marca = '  ← melhor' if busca['melhor'] and x['N'] == busca['melhor']['N'] else ''
        P(f'  {"abre com " + str(x["N"]) + ", fecha com " + str(x["M"]):<34}{br(x["custo"], 0):>12}{br(x["W"], 1):>10}'
          f'{br(x["efic"], 0) if x["efic"] is not None else "-":>12}{marca}')
    if busca['melhor'] and '2ª pela fila' in res and ref_nome in res:
        rf, rp = res['2ª pela fila'], res[ref_nome]
        b = busca['melhor']
        sim = rf['efic'] is not None and rp['efic'] is not None and rf['efic'] > rp['efic']
        P(f'RESPOSTA ({args.reps} réplicas): {"SIM" if sim else "NÃO"}. Abrindo com {b["N"]} e fechando com {b["M"]}, a 2ª catraca fica '
          f'{br(rf["custo"], 0)} min aberta e poupa {br(rf["efic"], 0)} minutos de espera por minuto aberta, contra '
          f'{br(rp["efic"], 0)} no horário de pico ({br(rp["custo"], 0)} min aberta). W: {br(rf["W"], 1)} min pela fila, '
          f'{br(rp["W"], 1)} no horário, {br(res["1 catraca"]["W"], 1)} com 1 catraca.')
        if not busca['mesma_espera']:
            P('  Nenhum gatilho testado espera tão pouco quanto a referência; o melhor N foi escolhido só pela eficiência.')
    else:
        P('RESPOSTA: sem dados para comparar nesta sessão.')

    rg = ctx.get('res_grupo')
    if rg and gref:
        r1, g1 = res['1 catraca'], rg['1 catraca']
        fator = (1 + gref['D']) / 2
        txt = (f'ACHADO (chegadas em grupo): {br(gref["Ek"])} alunos por grupo. Na calma, a fórmula M^X/M/1 multiplica a espera por '
               f'(1 + D)/2 = {br(fator, 1)}. No almoço simulado, W com 1 catraca vai de {br(r1["W"], 1)} (um a um) para '
               f'{br(g1["W"], 1)} min (em grupo), {br(g1["W"] / r1["W"], 1)}×.')
        if '2ª pela fila' in rg and ref_nome in rg and rg['2ª pela fila']['efic'] and rg[ref_nome]['efic']:
            mantem = (rg['2ª pela fila']['efic'] > rg[ref_nome]['efic']) == (res['2ª pela fila']['efic'] > res[ref_nome]['efic'])
            txt += (f' Com grupos, a eficiência fica {br(rg["2ª pela fila"]["efic"], 0)} pela fila contra {br(rg[ref_nome]["efic"], 0)} '
                    f'no horário: a resposta {"se mantém" if mantem else "muda"}.')
        P(txt)

    # conclusão
    P('')
    c1 = res['1 catraca']
    if '2ª só no pico' in res:
        c2 = res['2ª só no pico']
        quando = texto_janelas(md['janelas'], d['t0'])
        txt = (f'CONCLUSÃO: {quando[0].upper() + quando[1:]} chegam {br(lam_pic)} alunos/min para μ = {br(mu)} /min de uma catraca '
               f'(ρ = {br(lam_pic / mu)}{": a fila cresce" if lam_pic >= mu else ""}). Uma 2ª catraca só nesse intervalo muda o tempo médio no '
               f'sistema de {br(c1["W"], 1)} ± {br(c1["Wic"], 1)} para {br(c2["W"], 1)} ± {br(c2["Wic"], 1)} min '
               f'e os alunos em média de {br(c1["L"], 1)} para {br(c2["L"], 1)}.')
        if len(sens) > 1:
            w1 = [x['res']['1 catraca']['W'] for x in sens]
            w2 = [x['res']['2ª só no pico']['W'] for x in sens]
            txt += (f' Com μ entre {br(sens[0]["mu"])} e {br(sens[-1]["mu"])}, W vai de {br(min(w1), 1)}–{br(max(w1), 1)} min '
                    f'para {br(min(w2), 1)}–{br(max(w2), 1)} min: a direção se mantém, o tamanho do ganho depende de μ.')
        txt += f' Custo: {br(c2["custo"], 0)} minutos de 2ª catraca aberta.'
        if '2ª pela fila' in res:
            rf = res['2ª pela fila']
            txt += (f' Pela fila ({rf["nota"]}): W = {br(rf["W"], 1)} min com {br(rf["custo"], 0)} min de 2ª catraca.')
        alt = [(n, res[n]) for n in ('atend. mais rápido', 'aulas escalonadas') if n in res]
        if alt:
            txt += ' Sem catraca extra: ' + '; '.join(f'{n} → W = {br(r["W"], 1)} min' for n, r in alt) + '.'
        P(txt)
    else:
        P('CONCLUSÃO: sem pico detectado nesta sessão; compare com a 2ª catraca a hora toda.')

    grafico(d, pico, res, args, pasta, passo)
    return {'nome': d['nome'], 'lam_cal': lam_cal, 'lam_pic': lam_pic, 'lam_med': lam_med, 'pic_m': pic_m, 'cal_m': cal_m}


def rodar_rapido(d, mu, args, reps):
    """Cenários 1 catraca e 2ª no pico + validação, sem imprimir (usado na comparação de ajustes)."""
    md = medir(d, args.limiar, args.pico_min, args.buraco_max, args.regra_pico)
    grupo = estimar_grupos(d['chegadas_seg'], args.grupo_seg)
    Ek = grupo['Ek'] if grupo else 1.0
    lams = lams_por_minuto(md['pico'], md['lam_cal'], md['lam_pic'], md['lam_med'])
    cen = [x for x in cenarios_padrao(md['pico'], md['theta']) if x[0] in ('1 catraca', '2ª só no pico')]
    passo = passo_seguro(lams, mu, 2, md['theta'], args.K, args.passo, Ek)
    res = simular_cenarios(cen, lams, mu, md['n0'], args.K, args.seed, passo, reps, md['lam_med'], grupo=grupo)
    val = validar(d['fila'], res['1 catraca']['hs'], passo) if d['fila'] else []
    return md, res, val


def comparar_ajustes(sess, mu_fixo, args):
    reps = min(args.reps, 200)
    for nome, s in sorted(sess.items()):
        d = preparar(nome, s)
        if not d or not d['reconstruida'] or d['excesso'] <= 0:
            continue
        P('')
        P('=' * 72)
        P(f'HIPÓTESES PARA O BALANÇO DE {nome}: sobram {d["excesso"]} alunos no fim ({reps} réplicas por linha)')
        P('=' * 72)
        P('  Cada hipótese muda a fila reconstruída, e com ela o μ estimado, o θ e a validação.')
        P(f'  {"hipótese":<26}{"fila final":>11}{"μ (/min)":>16}{"θ":>7}{"validação":>11}{"W 1 cat.":>10}{"W 2ª pico":>11}')
        for modo in MODOS_AJUSTE:
            s2, txt = ajustar(s, modo, args.fila_min)
            d2 = preparar(nome, s2)
            e = estimar_mu(d2, args.fila_min)
            mu = mu_fixo or (e['mu'] if e else None)
            if mu is None:
                continue
            md, res, val = rodar_rapido(d2, mu, args, reps)
            w2 = res.get('2ª só no pico')
            mtxt = f'{br(e["mu"])} ± {br(e["ic"])}' if e else '-'
            P(f'  {NOMES_AJUSTE[modo]:<26}{d2["fila_final"]:>11}{mtxt:>16}{br(md["theta"], 3):>7}'
              f'{str(sum(v["ok"] for v in val)) + " de " + str(len(val)):>11}{br(res["1 catraca"]["W"], 1):>10}'
              f'{(br(w2["W"], 1) if w2 else "-"):>11}')
        if mu_fixo:
            P(f'  (todas as linhas com μ = {br(mu_fixo)} informado; a coluna μ mostra o que cada hipótese estimaria)')
        else:
            P('  (cada linha simula com o μ que ela mesma estima)')


def grafico(d, pico, res, args, pasta, passo):
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
    except ImportError:
        P('(matplotlib não instalado: gráficos não gerados. pip install matplotlib)')
        return
    T = d['T']
    fig, ax = plt.subplots(2, 1, figsize=(9, 7), sharex=True)
    passos = len(res['1 catraca']['hs'][0])
    xs = [i * passo / 60 for i in range(passos)]
    for a in ax:
        for m, p in enumerate(pico):
            if p:
                a.axvspan(m, m + 1, color='tab:red', alpha=.08, lw=0)
    base = res['1 catraca']['hs']
    media = [sum(h[i] for h in base) / len(base) for i in range(passos)]
    ax[0].step(xs, base[0], color='tab:blue', lw=.8, alpha=.7, label='1 réplica simulada')
    ax[0].plot(xs, media, color='navy', lw=2, label='média das réplicas (1 catraca)')
    if d['fila']:
        ax[0].scatter([s / 60 for s, _ in d['fila']], [n for _, n in d['fila']], color='black', zorder=5, s=22, label='fila reconstruída')
    ax[0].set_ylabel('alunos no sistema')
    ax[0].set_title(f'Validação: reconstruída x simulada ({d["nome"]}; faixa rosa = pico)')
    ax[0].legend(loc='upper left', fontsize=8)
    cores = {'1 catraca': 'tab:blue', '2ª só no pico': 'tab:green', '2 a hora toda': 'tab:orange', '1 cat. sem desist.': 'tab:gray'}
    for nome, r in res.items():
        mm = [sum(h[i] for h in r['hs']) / len(r['hs']) for i in range(passos)]
        ax[1].plot(xs, mm, label=f'{nome} (W = {br(r["W"], 1)} min)', color=cores.get(nome))
    ax[1].set_ylabel('alunos (média das réplicas)')
    ax[1].set_xlabel('minutos de observação')
    ax[1].set_title('Cenários, mesma semente')
    ax[1].legend(loc='upper left', fontsize=8)
    ax[1].set_xlim(0, T)
    fig.tight_layout()
    seguro = ''.join(c if c.isalnum() or c in '-_' else '_' for c in d['nome'])
    caminho = os.path.join(pasta, f'fila_{seguro}.png')
    fig.savefig(caminho, dpi=130)
    plt.close(fig)
    P(f'Gráfico salvo em {caminho}')


def main():
    configurar_utf8()
    ap = argparse.ArgumentParser(description='Análise e simulação da fila da catraca do RU')
    ap.add_argument('csv', nargs='+', help='CSVs exportados pela página de coleta')
    ap.add_argument('--limiar', type=float, default=None, help='chegadas/min (média móvel de 5 min) a partir das quais o minuto é pico (padrão: automático)')
    ap.add_argument('--regra-pico', choices=REGRAS_PICO, default='slide59',
                    help='limiar automático de pico: slide59 = 1,5 × a média de chegadas (Aula 09, slide 59); '
                    'duas-medias = método das duas médias (versão anterior)')
    ap.add_argument('--rapido-seg', type=float, default=None,
                    help='cenário "atendimento mais rápido": segundos a menos por aluno (padrão: metade da troca medida)')
    ap.add_argument('--pico-min', type=int, default=5, help='pico mais curto aceito, em minutos (0 = aceita todos)')
    ap.add_argument('--buraco-max', type=int, default=3, help='calma de até N min entre dois picos vira pico (0 = não junta)')
    ap.add_argument('--K', type=int, default=200, help='capacidade máxima da fila no simulador')
    ap.add_argument('--passo', type=float, default=5, help='passo da cadeia, em segundos')
    ap.add_argument('--reps', type=int, default=30, help='réplicas por cenário')
    ap.add_argument('--seed', type=int, default=42, help='semente base (mesma em todos os cenários)')
    ap.add_argument('--mu', type=float, default=None, help='μ por minuto; sem ele, μ sai das saídas por minuto nos minutos com fila')
    ap.add_argument('--fila-min', type=int, default=3, help='fila mínima (início e fim do minuto) para o minuto entrar na estimativa de μ')
    ap.add_argument('--grupo-seg', type=float, default=0, help='modelo principal: chegadas a até N s uma da outra formam um grupo '
                    '(padrão 0 = M/M/1, chegadas uma a uma)')
    ap.add_argument('--grupo-ref', type=float, default=1.5, help='intervalo (s) dos grupos na comparação M/M/1 x chegadas em grupo '
                    '(0 = não compara)')
    ap.add_argument('--ajuste', choices=MODOS_AJUSTE, default='nenhum',
                    help='como tratar alunos que sobram no balanço: desistencia, saidas (perdidas pelo observador) ou n0 (fila inicial menor)')
    ap.add_argument('--comparar-ajustes', action='store_true', help='compara as hipóteses de ajuste do balanço')
    ap.add_argument('--sens', type=float, nargs='+', default=None, help='valores de μ para a tabela de sensibilidade')
    ap.add_argument('--fila', nargs=3, action='append', metavar=('NOME', 'LAMBDA', 'MU'), help='outra fila do RU (por minuto), para achar o gargalo')
    ap.add_argument('--saida', default='saida_catraca', help='pasta de saída')
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    brutas = ler(args.csv)
    sess, ajuste_txt = {}, {}
    for n, s in sorted(brutas.items()):
        sess[n], ajuste_txt[n] = ajustar(s, args.ajuste, args.fila_min)
    dados = [x for x in (preparar(n, s) for n, s in sorted(sess.items())) if x]
    if not dados:
        sys.exit('Nenhuma sessão encontrada nos arquivos.')

    P('ATENDIMENTO NA CATRACA (todas as sessões juntas)')
    vals = {d['nome']: vals_mu(d, args.fila_min) for d in dados}
    est = resumo_mu([v for vs in vals.values() for v in vs])
    P(f'  μ pelas saídas por minuto nos minutos com fila ≥ {args.fila_min} no início e no fim (slide 57 da Aula 09):')
    for d in dados:
        e = resumo_mu(vals[d['nome']])
        P(f'    {d["nome"]:<26}' + (f'{br(e["mu"])} ± {br(e["ic"])} /min em {e["n"]} min' if e else 'poucos minutos com fila'))
    if est:
        P(f'    {"todas juntas":<26}{br(est["mu"])} ± {br(est["ic"])} /min em {est["n"]} min (IC de 95%)')

    atend = [a for d in dados for a in d['atend'] if a > 0]
    for d in dados:
        if d['atend_aviso']:
            P(f'  {d["nome"]}: {d["atend_aviso"]}')
        elif d['atend_descartados']:
            P(f'  {d["nome"]}: {d["atend_descartados"]} saídas sem início pareável (0–60 s) descartadas do cronômetro.')
    mu_cron = cv_cron = None
    if atend:
        m = sum(atend) / len(atend)
        dp = statistics.stdev(atend) if len(atend) > 1 else float('nan')
        mu_cron, cv_cron = 60 / m, (dp / m if len(atend) > 1 else None)
        P(f'  {len(atend)} atendimentos cronometrados: média {br(m, 1)} s, mediana {br(statistics.median(atend), 1)} s, '
          f'CV = {br(cv_cron)} → {br(mu_cron)} /min se fosse o tempo todo de cada aluno.')
        if len(atend) < 20:
            P('  Atenção: o checklist pede 20 a 30 atendimentos.')

    if args.mu:
        mu = args.mu
        P(f'  Usando μ = {br(mu)} /min informado (--mu).')
    elif est:
        mu = est['mu']
        P(f'  Usando μ = {br(mu)} /min (estimativa pelas saídas com fila).')
    elif mu_cron:
        mu = mu_cron
        P(f'  Sem minutos com fila suficientes; usando o μ cronometrado = {br(mu)} /min (otimista).')
    else:
        sys.exit('Sem minutos com fila nem atendimentos cronometrados. Informe --mu.')

    trocas = [x for d in dados for x in d.get('trocas', [])]
    troca = statistics.mean(trocas) if trocas else None
    if atend:
        m = sum(atend) / len(atend)
        alvo = 60 / mu
        P('')
        P(f'CONFERÊNCIA 2 (Aula 09, slide 57): os atendimentos cronometrados devem dar perto de 60/μ = {br(alvo, 1)} s por aluno')
        dif = m / alvo - 1
        P(f'  só a passagem (cronômetro): {br(m, 1)} s, {br(dif * 100, 0)}% de diferença: '
          + ('bate.' if abs(dif) <= .15 else 'NÃO bate.'))
        if troca is not None:
            ciclo = m + troca
            dif2 = ciclo / alvo - 1
            P(f'  passagem {br(m, 1)} s + troca {br(troca, 1)} s (saída de um aluno → início do próximo, {len(trocas)} trocas) '
              f'= {br(ciclo, 1)} s, {br(dif2 * 100, 0)}% de diferença: ' + ('bate.' if abs(dif2) <= .15 else 'NÃO bate.'))
            P('  O cronômetro não pega a troca entre alunos, que também ocupa a catraca. Por isso μ vem das saídas por minuto,')
            P('  e o μ cronometrado entra na sensibilidade só como limite otimista.')
    P('')

    resumo = []
    for d in dados:
        outras = [v for n, vs in vals.items() if n != d['nome'] for v in vs]
        ctx = {'mu_est': est, 'mu_cron': mu_cron, 'cv_cron': cv_cron, 'mu_outras': resumo_mu(outras), 'troca': troca,
               'ajuste_txt': ajuste_txt.get(d['nome'])}
        r = analisar(d, mu, args, args.saida, ctx)
        if r:
            resumo.append(r)

    if len(resumo) > 1:
        P('')
        P('=' * 72)
        P('ENTRE SESSÕES')
        P('=' * 72)
        P(f'  {"sessão":<28}{"λ calma":>9}{"λ pico":>9}{"λ médio":>9}')
        for r in resumo:
            P(f'  {r["nome"]:<28}{br(r["lam_cal"]):>9}{br(r["lam_pic"]):>9}{br(r["lam_med"]):>9}')
        for rot, k in (('λ de calma', 'lam_cal'), ('λ de pico', 'lam_pic')):
            v = [r[k] for r in resumo if r[k] is not None]
            if len(v) > 1:
                m, ic = media_ic(v)
                P(f'  {rot}: média {br(m)} ± {br(ic)} /min (IC 95% entre {len(v)} sessões)')
        pic_all = [x for r in resumo for x in r['pic_m']]
        com_pico = [r['nome'] for r in resumo if r['pic_m']]
        if len(com_pico) > 1 and len(pic_all) > 1:
            m, ic = media_ic(pic_all)
            P(f'  Juntando os {len(pic_all)} minutos de pico de {len(com_pico)} sessões (slide 59: "uma hora tem poucos picos; juntem dias'
              f' diferentes"): λ de pico = {br(m)} ± {br(ic)} /min, ρ = {br(m / mu)} com μ = {br(mu)}.')
            P('  Ressalva: cada sessão tem poucos minutos de pico; o λ de pico de uma sessão sozinha é incerto.')

    if args.comparar_ajustes:
        comparar_ajustes(brutas, args.mu, args)

    # gargalo
    lam_ref = max((r['lam_pic'] or r['lam_med']) for r in resumo)
    filas = [('catraca (pico)', lam_ref, mu)]
    for nome, lam, m2 in (args.fila or []):
        filas.append((nome, float(lam.replace(',', '.')), float(m2.replace(',', '.'))))
    P('')
    if len(filas) > 1:
        P('GARGALO: utilização ρ = λ/μ de cada fila (a maior é o gargalo)')
        for nome, lam, m2 in sorted(filas, key=lambda x: -x[1] / x[2]):
            P(f'  {nome:<18} ρ = {br(lam / m2)}')
        P('  Melhorar outra fila quase não muda a espera total. Calculem ρ antes de propor melhorias.')
    else:
        P('GARGALO: só a catraca foi medida. Sem λ e μ das filas de dentro (--fila), não dá para afirmar que ela é o gargalo.')

    with open(os.path.join(args.saida, 'relatorio.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(SAIDA) + '\n')
    print(f'\nRelatório salvo em {os.path.join(args.saida, "relatorio.txt")}')


if __name__ == '__main__':
    main()
