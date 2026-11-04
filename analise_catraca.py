#!/usr/bin/env python3
"""
Análise e simulação da fila da catraca do RU (seminário de Avaliação de Desempenho).

Lê os CSVs exportados pela página de coleta (um por celular; vários dias),
e faz o que o checklist da Aula 10 pede:

  1. mede  : λ por trecho (calma/pico), μ pelos atendimentos cronometrados
  2. modela: fórmulas M/M/1 (Aula 03) para cada trecho
  3. simula: cadeia de Markov com passo de 5 s (slides 9 e 10), K = 50
  4. verifica: simulador x fórmulas num trecho sem pico (slide 19)
  5. valida : fila anotada minuto a minuto x fila simulada (slide 22)
  6. compara cenários com a mesma semente: 1 catraca, 2ª só no pico, 2 a hora toda
  7. aponta o gargalo (use --fila para incluir ticket, suco etc.)

Uso:
  python3 analise_catraca.py A_dia1.csv B_dia1.csv A_dia2.csv B_dia2.csv
  python3 analise_catraca.py *.csv --limiar 3.0 --K 50 --reps 30 --seed 42
  python3 analise_catraca.py *.csv --fila ticket 1.8 3.0 --fila suco 1.2 2.0

Os arquivos dos dois observadores são juntados pelo nome da sessão.
Só precisa de Python 3. Os gráficos (PNG) saem se o matplotlib estiver instalado.
"""
import argparse
import csv
import math
import os
import random
import statistics
import sys
from collections import defaultdict
from datetime import datetime

T975 = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306,
        9: 2.262, 10: 2.228, 12: 2.179, 15: 2.131, 20: 2.086, 25: 2.060, 30: 2.042}


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
    sess = defaultdict(lambda: {'inicio': [], 'fim': [], 'chegada': [], 'desist': [], 'fila': [], 'atend': [], 'catracas': 1})
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
                try:
                    s['catracas'] = max(s['catracas'], int(r.get('catracas') or 1))
                except ValueError:
                    pass
                if tipo == 'inicio':
                    s['inicio'].append(t)
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
    return sess


def preparar(nome, s):
    todos = s['inicio'] + s['fim'] + s['chegada'] + s['desist'] + [t for t, _ in s['fila']]
    if not todos:
        return None
    t0 = min(s['inicio']) if s['inicio'] else min(todos)
    t1 = max(s['fim']) if s['fim'] else max(todos)
    T = max(1, int((t1 - t0).total_seconds() // 60))
    arr = [0] * T
    for t in s['chegada']:
        m = int((t - t0).total_seconds() // 60)
        if 0 <= m < T:
            arr[m] += 1
    des = [0] * T
    for t in s['desist']:
        m = int((t - t0).total_seconds() // 60)
        if 0 <= m < T:
            des[m] += 1
    fila = sorted(((t - t0).total_seconds(), n) for t, n in s['fila'])
    fila = [(sec, n) for sec, n in fila if 0 <= sec < T * 60]
    return {'nome': nome, 'T': T, 'arr': arr, 'des': des, 'fila': fila, 'atend': s['atend'], 'catracas': s['catracas']}


# ---------------------------------------------------------------- modelo
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


def classificar(arr, limiar):
    """True = minuto de pico, pela média móvel de 5 min das chegadas por minuto."""
    return [x >= limiar for x in suavizar(arr)]


def formulas(lam, mu):
    rho = lam / mu
    if rho >= 1:
        return {'rho': rho, 'estavel': False}
    L = rho / (1 - rho)
    W = L / lam
    return {'rho': rho, 'estavel': True, 'vazia': 1 - rho, 'L': L, 'W': W, 'Wq': W - 1 / mu}


def simular(lams, mu, cs, n0, K, seed, passo=5, theta=0.0):
    """Cadeia de Markov em passos de `passo` s. lams[m] e cs[m] valem no minuto m.
    theta = taxa de desistência (por minuto, por aluno que espera e não está na catraca)."""
    T = len(lams)
    rng = random.Random(seed)
    n, hist = n0, []
    for i in range(int(round(T * 60 / passo))):
        m = min(int(i * passo / 60), T - 1)
        a = lams[m] * passo / 60
        s = mu * passo / 60
        d = max(n - cs[m], 0) * theta * passo / 60
        if a + cs[m] * s + d > 1:
            sys.exit(f'Passo de {passo:g} s grande demais para λ={lams[m]:.2f}, μ={mu:.2f}. Use --passo menor.')
        u = rng.random()
        if u < a:
            if n < K:
                n += 1
        elif u < a + min(n, cs[m]) * s:
            n -= 1
        elif u < a + min(n, cs[m]) * s + d:
            n -= 1  # desistiu da fila
        hist.append(n)
    return hist


def passo_seguro(lams, mu, cmax, theta, K, passo):
    """Maior passo (s) ≤ `passo` para o qual as chances de um passo somam no máximo 1."""
    while passo > 0.5 and (max(lams) + cmax * mu + K * theta) * passo / 60 > 1:
        passo /= 2
    return passo


def metricas(hist, lam_med):
    L = sum(hist) / len(hist)
    return {'L': L, 'pior': max(hist), 'W': L / lam_med if lam_med > 0 else float('nan'),
            'longa': sum(1 for x in hist if x >= 10) / len(hist),
            'ocupada': sum(1 for x in hist if x > 0) / len(hist)}


def percentil(v, p):
    v = sorted(v)
    return v[min(len(v) - 1, max(0, int(round(p * (len(v) - 1)))))]


# ---------------------------------------------------------------- análise
def analisar(d, mu, args, pasta):
    T, arr = d['T'], d['arr']
    total = sum(arr)
    if total == 0:
        P(f'Sessão {d["nome"]}: nenhuma chegada registrada. Pulando.')
        return None
    lam_med = total / T
    limiar = args.limiar if args.limiar is not None else limiar_auto(suavizar(arr))
    pico = classificar(arr, limiar)
    cal_m = [a for a, p in zip(arr, pico) if not p]
    pic_m = [a for a, p in zip(arr, pico) if p]
    lam_cal = sum(cal_m) / len(cal_m) if cal_m else None
    lam_pic = sum(pic_m) / len(pic_m) if pic_m else None

    P('=' * 72)
    P(f'SESSÃO {d["nome"]}  ({T} min observados, {d["catracas"]} catraca(s) aberta(s))')
    P('=' * 72)
    lim_txt = br(limiar) + ' /min' if limiar != float('inf') else 'nenhum (sem pico claro)'
    P(f'Chegadas: {total}  |  λ médio da sessão = {br(lam_med)} /min  |  limiar de pico = {lim_txt} (média móvel de 5 min)')
    P(f'  calma: {len(cal_m)} min, λ = {br(lam_cal)} /min   |   pico: {len(pic_m)} min, λ = {br(lam_pic)} /min')
    if cal_m and len(cal_m) > 2:
        mc = sum(cal_m) / len(cal_m)
        vc = statistics.pvariance(cal_m)
        P(f'  teste rápido de Poisson na calma: variância/média das chegadas por minuto = {br(vc / mc if mc else float("nan"))} (perto de 1 é Poisson)')

    # fórmulas por trecho
    D = sum(d['des'])
    c0 = d['catracas']
    esperando = sum(max(n - c0, 0) for _, n in d['fila'])
    if d['fila']:
        esperando *= T / len(d['fila'])  # cada anotação vale ~1 min de aluno esperando
    theta = D / esperando if (D and esperando) else 0.0
    P('')
    if D:
        lam_ef = lam_med - D / T
        P(f'Desistências: {D} alunos saíram da fila sem passar ({br(D / total * 100, 0)}% das chegadas). '
          f'Taxa θ = {br(theta, 3)} /min por aluno que espera. λ efetivo (quem passou) = {br(lam_ef)} /min, ρ efetivo = {br(lam_ef / mu)}')
    else:
        P('Desistências: nenhuma registrada; o simulador não usa desistência. Se houve, anotem com o botão "Alguém saiu da fila sem passar".')
    P('')
    P(f'Modelo M/M/1 (μ = {br(mu)} /min, atendimento médio {br(60 / mu, 1)} s)')
    P(f'  {"trecho":<8}{"λ":>7}{"ρ":>7}{"vazia":>8}{"L":>8}{"W (min)":>10}{"Wq (min)":>10}')
    for rot, lam in (('calma', lam_cal), ('pico', lam_pic), ('sessão', lam_med)):
        if lam is None:
            continue
        f = formulas(lam, mu)
        if f['estavel']:
            P(f'  {rot:<8}{br(lam):>7}{br(f["rho"]):>7}{br(f["vazia"] * 100, 0) + "%":>8}{br(f["L"]):>8}{br(f["W"]):>10}{br(f["Wq"]):>10}')
        else:
            P(f'  {rot:<8}{br(lam):>7}{br(f["rho"]):>7}   ρ ≥ 1: fórmulas não valem, a fila cresce. Use a simulação.')

    # verificação num trecho sem pico
    P('')
    if lam_cal is not None and formulas(lam_cal, mu)['estavel'] and lam_cal > 0:
        f = formulas(lam_cal, mu)
        horas = 200
        h = simular([lam_cal] * (horas * 60), mu, [1] * (horas * 60), 0, args.K, args.seed, args.passo)
        mt = metricas(h, lam_cal)
        P(f'VERIFICAÇÃO (slide 19): simulador com λ de calma por {horas} h simuladas contra as fórmulas')
        P(f'  {"métrica":<22}{"fórmula":>10}{"simulado":>10}')
        P(f'  {"utilização ρ":<22}{br(f["rho"] * 100, 0) + "%":>10}{br(mt["ocupada"] * 100, 0) + "%":>10}')
        P(f'  {"alunos no sistema L":<22}{br(f["L"]):>10}{br(mt["L"]):>10}')
        P(f'  {"tempo W (min)":<22}{br(f["W"]):>10}{br(mt["W"]):>10}')
        P('  Se os dois lados ficam próximos, o código faz o que o modelo diz.')
    else:
        P('VERIFICAÇÃO: sem trecho de calma estável nesta sessão. Rode com outra sessão ou ajuste --limiar.')

    # cenários
    lams = [lam_pic if p and lam_pic is not None else (lam_cal if lam_cal is not None else lam_med) for p in pico]
    cen = [('1 catraca', [1] * T, theta)]
    if theta > 0:
        cen.append(('1 cat. sem desist.', [1] * T, 0.0))
    if any(pico):
        cen.append(('2ª só no pico', [2 if p else 1 for p in pico], theta))
    cen.append(('2 a hora toda', [2] * T, theta))
    n0 = d['fila'][0][1] if d['fila'] else 0
    novo = passo_seguro(lams, mu, 2, theta, args.K, args.passo)
    if novo != args.passo:
        P(f'(passo reduzido de {br(args.passo, 1)} s para {br(novo, 1)} s: com μ = {br(mu)} /min o passo maior daria chances somando mais de 1)')
        args.passo = novo
    P('')
    P(f'SIMULAÇÃO: {args.reps} réplicas de {T} min, passo {br(args.passo, 1)} s, K = {args.K}, fila inicial = {n0}, θ = {br(theta, 3)} /min, mesma semente em todos os cenários')
    P(f'  {"cenário":<20}{"L médio":>14}{"pior momento":>14}{"W (min)":>12}{"fila ≥ 10":>12}')
    res = {}
    for nome, cs, th in cen:
        hs = [simular(lams, mu, cs, n0, args.K, args.seed + i, args.passo, th) for i in range(args.reps)]
        ms = [metricas(h, lam_med) for h in hs]
        Lm, Lic = media_ic([m['L'] for m in ms])
        Wm, Wic = media_ic([m['W'] for m in ms])
        pior = sum(m['pior'] for m in ms) / len(ms)
        lg = sum(m['longa'] for m in ms) / len(ms)
        res[nome] = {'hs': hs, 'ms': ms, 'L': Lm, 'W': Wm, 'pior': pior, 'longa': lg}
        P(f'  {nome:<20}{br(Lm, 1) + " ±" + br(Lic, 1):>14}{br(pior, 1):>14}{br(Wm, 1) + " ±" + br(Wic, 1):>12}{br(lg * 100, 0) + "%":>12}')
    P('  (± é o IC de 95% entre réplicas. Uma hora simulada é uma amostra, não uma medida.)')

    # validação
    P('')
    base = res['1 catraca']
    if d['fila']:
        anot = [n for _, n in d['fila']]
        La = sum(anot) / len(anot)
        pa = max(anot)
        ga = sum(1 for x in anot if x >= 10) / len(anot)
        idx = [min(int(sec / args.passo), len(base['hs'][0]) - 1) for sec, _ in d['fila']]
        Ls = [sum(h[i] for i in idx) / len(idx) for h in base['hs']]
        ps = [max(h[i] for i in idx) for h in base['hs']]
        gs = [sum(1 for i in idx if h[i] >= 10) / len(idx) for h in base['hs']]
        P(f'VALIDAÇÃO (slide 22): fila anotada ({len(anot)} anotações) x simulada nos mesmos instantes')
        P(f'  {"":<22}{"anotada":>10}{"simulada (média)":>18}{"faixa 5%-95%":>16}{"dentro?":>9}')
        for rot, a, sim, d1 in (('L (alunos em média)', La, Ls, 1), ('pior momento', pa, ps, 0), ('fração com fila ≥ 10', ga, gs, 2)):
            lo, hi = percentil(sim, .05), percentil(sim, .95)
            ok = 'sim' if lo <= a <= hi else 'NÃO'
            if d1 == 2:
                P(f'  {rot:<22}{br(a * 100, 0) + "%":>10}{br(sum(sim) / len(sim) * 100, 0) + "%":>18}{br(lo * 100, 0) + "%-" + br(hi * 100, 0) + "%":>16}{ok:>9}')
            else:
                P(f'  {rot:<22}{br(a, d1):>10}{br(sum(sim) / len(sim), d1):>18}{br(lo, d1) + "-" + br(hi, d1):>16}{ok:>9}')
        P('  Se algum ficar fora da faixa, revejam primeiro as medições: contagens, separação calma/pico e os atendimentos cronometrados.')
    else:
        P('VALIDAÇÃO: sem fila anotada minuto a minuto nesta sessão.')

    # conclusão
    P('')
    c1 = res['1 catraca']
    if '2ª só no pico' in res:
        c2 = res['2ª só no pico']
        P(f'CONCLUSÃO: uma 2ª catraca só no pico muda o tempo médio no sistema de {br(c1["W"], 1)} para {br(c2["W"], 1)} min '
          f'e os alunos em média de {br(c1["L"], 1)} para {br(c2["L"], 1)} (pico observado: {br(lam_pic)} chegadas/min contra μ = {br(mu)}).')
    else:
        P('CONCLUSÃO: sem pico detectado nesta sessão; compare com a 2ª catraca a hora toda.')

    grafico(d, pico, res, args, pasta)
    return {'nome': d['nome'], 'lam_cal': lam_cal, 'lam_pic': lam_pic, 'lam_med': lam_med}


def grafico(d, pico, res, args, pasta):
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
    xs = [i * args.passo / 60 for i in range(passos)]
    for a in ax:
        for m, p in enumerate(pico):
            if p:
                a.axvspan(m, m + 1, color='tab:red', alpha=.08, lw=0)
    base = res['1 catraca']['hs']
    media = [sum(h[i] for h in base) / len(base) for i in range(passos)]
    ax[0].step(xs, base[0], color='tab:blue', lw=.8, alpha=.7, label='1 réplica simulada')
    ax[0].plot(xs, media, color='navy', lw=2, label='média das réplicas (1 catraca)')
    if d['fila']:
        ax[0].scatter([s / 60 for s, _ in d['fila']], [n for _, n in d['fila']], color='black', zorder=5, s=22, label='fila anotada')
    ax[0].set_ylabel('alunos no sistema')
    ax[0].set_title(f'Validação: anotada x simulada ({d["nome"]}; faixa rosa = pico)')
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
    ap.add_argument('--K', type=int, default=50, help='capacidade máxima da fila no simulador')
    ap.add_argument('--passo', type=float, default=5, help='passo da cadeia, em segundos')
    ap.add_argument('--reps', type=int, default=30, help='réplicas por cenário')
    ap.add_argument('--seed', type=int, default=42, help='semente base (mesma em todos os cenários)')
    ap.add_argument('--mu', type=float, default=None, help='μ por minuto, se não houver atendimentos cronometrados')
    ap.add_argument('--fila', nargs=3, action='append', metavar=('NOME', 'LAMBDA', 'MU'), help='outra fila do RU (por minuto), para achar o gargalo')
    ap.add_argument('--saida', default='saida_catraca', help='pasta de saída')
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    sess = ler(args.csv)
    dados = [x for x in (preparar(n, s) for n, s in sorted(sess.items())) if x]
    if not dados:
        sys.exit('Nenhuma sessão encontrada nos arquivos.')

    atend = [a for d in dados for a in d['atend'] if a > 0]
    P('ATENDIMENTO NA CATRACA (todas as sessões juntas)')
    if atend:
        m = sum(atend) / len(atend)
        dp = statistics.stdev(atend) if len(atend) > 1 else float('nan')
        mu = 60 / m
        P(f'  {len(atend)} atendimentos cronometrados: média {br(m, 1)} s, desvio {br(dp, 1)} s, CV = {br(dp / m)} (exponencial tem CV = 1)  →  μ = {br(mu)} /min')
        if len(atend) < 20:
            P('  Atenção: o checklist pede 20 a 30 atendimentos.')
    elif args.mu:
        mu = args.mu
        P(f'  Sem cronometragem; usando μ = {br(mu)} /min informado.')
    else:
        sys.exit('Sem atendimentos cronometrados. Informe --mu ou colete-os.')
    P('')

    resumo = [analisar(d, mu, args, args.saida) for d in dados]
    resumo = [r for r in resumo if r]

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

    # gargalo
    lam_ref = max((r['lam_pic'] or r['lam_med']) for r in resumo)
    filas = [('catraca (pico)', lam_ref, mu)]
    for nome, lam, m2 in (args.fila or []):
        filas.append((nome, float(lam.replace(',', '.')), float(m2.replace(',', '.'))))
    if len(filas) > 1:
        P('')
        P('GARGALO: utilização ρ = λ/μ de cada fila (a maior é o gargalo)')
        for nome, lam, m2 in sorted(filas, key=lambda x: -x[1] / x[2]):
            P(f'  {nome:<18} ρ = {br(lam / m2)}')
        P('  Melhorar outra fila quase não muda a espera total. Calculem ρ antes de propor melhorias.')

    with open(os.path.join(args.saida, 'relatorio.txt'), 'w', encoding='utf-8') as f:
        f.write('\n'.join(SAIDA) + '\n')
    print(f'\nRelatório salvo em {os.path.join(args.saida, "relatorio.txt")}')


if __name__ == '__main__':
    main()
