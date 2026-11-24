# Fila da catraca do RU: coleta e análise

Seminário de Avaliação de Desempenho (UFOPA). O projeto mede a fila da catraca do RU, compara com o modelo M/M/1 e simula cenários, como abrir uma 2ª catraca no horário de pico. Segue o checklist da Aula 10.

## Arquivos

| Arquivo | Para quê | Onde roda |
|---|---|---|
| `docs/index.html` | Estrutura da página de coleta | Navegador do celular |
| `docs/style.css` | Estilos da página | Carregado por `index.html` |
| `docs/app.js` | Lógica da coleta, cronômetro e exportação CSV | Carregado por `index.html` |
| `analise_catraca.py` | Calcula λ e μ, aplica as fórmulas, simula, valida e compara cenários | Terminal (Python 3) |
| `simulador_gui.py` | Interface visual do simulador: parâmetros, cenários, gráficos e a fila animada | Janela no computador (Python 3 + PySide6) |
| `slide.pdf` | Slides da apresentação do seminário (24/11/2026): sistema, medição, modelo M/M/1, simulação, cenários "e se?", resposta à pergunta da equipe e conclusões | Qualquer leitor de PDF |

A página usa `style.css` e `app.js`; mantenha os três arquivos juntos na pasta `docs/`. O script de análise lê os CSVs exportados pela página.

A apresentação do seminário está em [`slide.pdf`](slide.pdf). Os números dos slides vêm da análise principal (`artefatos/analise_revisada/`, seção 2).

## 1. Coleta (três observadores por rodada)

Abram a página nos três celulares. Se for usar o arquivo local, sirva a pasta `docs/` na rede:

```bash
python3 -m http.server 8000 --directory docs
# nos celulares: http://IP-DO-COMPUTADOR:8000   (mesma rede wi-fi)
```

Outra opção é hospedar a pasta `docs/` (GitHub Pages, por exemplo).

**Antes de começar**, nos três celulares:
- Abram "Sessão e observador" e ponham o **mesmo nome de sessão** (padrão: `data-refeicao`). É por ele que o script junta os arquivos de A, B e C.
- Informem o mesmo número de alunos no sistema (fila + catraca) no campo **Alunos no sistema ao iniciar**.
- Cada observador escolhe seu papel: A, B ou C.
- Confirmem o número de catracas abertas.

**Durante:** os três tocam em **Iniciar coleta** juntos.

| Observador | Faz |
|---|---|
| **A** | Toca em **Chegou aluno** a cada pessoa que entra no fim da fila. Toca em **Alguém saiu da fila sem passar** quando alguém desiste. |
| **B** | Toca em **Começou a ser atendido** quando cada aluno chega à catraca. |
| **C** | Toca em **Saiu do atendimento** quando cada aluno passa pela catraca. |

Ao final, toque em **Encerrar**, abra a aba **Dados**, copie o CSV de cada celular e salve em arquivos (`A_dia1.csv`, `B_dia1.csv`, `C_dia1.csv`).

Os dados ficam salvos no navegador de cada celular. Exporte o CSV ao fim de cada coleta, porque limpar os dados do site apaga tudo.

**Horários:** a página grava tudo no fuso de Brasília (`-03:00`), mesmo que o celular esteja em outro fuso.
Para a análise, informe os três CSVs da mesma sessão. A fila é reconstruída pelos registros de chegada, desistência e saída do atendimento; os inícios e saídas também são pareados para calcular o tempo de atendimento (cada saída com o início mais recente, entre 0 e 60 s). Se início e saída forem anotados em celulares diferentes, os relógios não batem e o script descarta esses tempos: o μ sai das saídas por minuto.

### Checklist do professor

- Medir em **pelo menos dois dias**.
- Anotar chegadas e desistências, além de registrar o início e a saída de 20 a 30 atendimentos.
- Cobrir um horário de pico e um calmo.
- Quem nem entra na fila porque viu que estava grande não aparece nos dados. Se acharem que isso acontece, anotem à parte e comentem como limitação.

## 2. Análise

Só precisa de Python 3. O matplotlib é opcional e serve para gerar os gráficos; sem ele, o relatório ainda é criado normalmente. Se quiser os gráficos, instale o matplotlib no mesmo ambiente Python usado para executar o script:

```bash
python -m pip install matplotlib
```

No Windows, se você usar `py` para executar o script, use também `py -m pip install matplotlib`. No VS Code, confirme que o pacote foi instalado no interpretador selecionado para o projeto.

```bash
python3 analise_catraca.py A_dia1.csv B_dia1.csv C_dia1.csv A_dia2.csv B_dia2.csv C_dia2.csv
```

Análise principal do seminário (17/11 com fila inicial 42 e as três coletas de 16/11):

```bash
python analise_catraca.py artefatos/dados/coleta_almoco_2026-11-17_fila42.csv artefatos/dados/coletas_2026-11-16_por_coleta.csv --ajuste saidas --reps 500 --comparar-ajustes --saida artefatos/analise_revisada
```

No Windows, talvez seja `python` ou `py` no lugar de `python3`.

### Opções

| Opção | Padrão | Efeito |
|---|---|---|
| `--limiar X` | automático | Chegadas/min (média móvel de 5 min) a partir das quais o minuto é pico |
| `--regra-pico R` | `slide59` | Limiar automático: `slide59` = 1,5 × a média de chegadas (Aula 09, slide 59); `duas-medias` = método das duas médias (versão anterior) |
| `--rapido-seg S` | metade da troca | Cenário "atendimento mais rápido": segundos a menos por aluno. Padrão: metade da troca medida (saída de um → início do próximo) |
| `--pico-min N` | 5 | Pico mais curto aceito, em minutos. Picos menores viram calma (não dá para abrir uma catraca por 2 min). 0 desliga |
| `--buraco-max N` | 3 | Calma de até N min entre dois picos vira pico. 0 desliga |
| `--K N` | 200 | Capacidade máxima da fila no simulador. O script avisa se mais de 5% das réplicas baterem em K |
| `--passo S` | 5 | Passo da cadeia de Markov, em segundos (reduz sozinho se for grande demais) |
| `--reps N` | 30 | Réplicas de cada cenário |
| `--seed N` | 42 | Semente base, a mesma em todos os cenários |
| `--mu X` | estimado | μ por minuto. Sem ele, μ = média das saídas por minuto nos minutos com fila (slide 57 da Aula 09), juntando todas as sessões |
| `--fila-min N` | 3 | Fila mínima no início e no fim do minuto para ele entrar na estimativa de μ |
| `--grupo-seg S` | 0 | 0 = M/M/1, chegadas uma a uma (modelo principal). S > 0: chegadas a até S segundos uma da outra formam um grupo e o simulador sorteia grupos com a distribuição medida |
| `--grupo-ref S` | 1,5 | Intervalo dos grupos usados na seção REFINAMENTO, que compara o M/M/1 com as chegadas em grupo. 0 = sem comparação |
| `--ajuste MODO` | `nenhum` | Como tratar alunos que sobram no balanço: `desistencia`, `saidas` (perdidas pelo observador) ou `n0` (fila inicial menor) |
| `--comparar-ajustes` | | Tabela com as quatro hipóteses do balanço: fila final, μ, θ, validação e W |
| `--sens X Y …` | IC de μ + cronometrado | Valores de μ da tabela de sensibilidade |
| `--fila NOME LAM MU` | | Outra fila do RU (ticket, suco), para achar o gargalo. Pode repetir |
| `--saida PASTA` | `saida_catraca` | Onde salvar `relatorio.txt` e os gráficos |

Exemplo com outras filas:

```bash
python3 analise_catraca.py *.csv --fila ticket 1.8 3.0 --fila suco 1.2 2.0
```

### O que o relatório mostra

1. **Atendimento:** μ de cada sessão e de todas juntas pelas saídas por minuto nos minutos com fila, com IC de 95%, e a **conferência 2 do slide 57**: os cronometrados (só a passagem, 6,9 s em 17/11) não batem com 60/μ (9,6 s); somando a troca entre alunos (2,4 s), 9,3 s, bate. Por isso μ vem das saídas.
2. **Por sessão:**
   - balanço da fila reconstruída (quantos sobram no fim) e o ajuste aplicado;
   - λ de calma e de pico, separados pelas chegadas por minuto (e não pelas ondas da fila), com a janela de pico em horário;
   - dispersão D = variância/média das chegadas e a distribuição dos grupos;
   - μ da sessão na 1ª e na 2ª metade, com aviso se cair mais de 15% (toques perdidos ou bloqueio lá dentro);
   - desistências: quantos saíram da fila sem passar, a taxa θ e o λ efetivo;
   - fórmulas M/M/1 de cada trecho (ρ, L, W, Wq) e M^X/M/1 com os grupos (L e W × (1 + D)/2), mais Pollaczek-Khinchine (M/G/1) na calma com o CV cronometrado. Com ρ ≥ 0,98 as fórmulas não valem e o script avisa.
3. **Verificação (slide 19):** simulador contra as fórmulas num trecho de calma: utilização, catraca vazia, L, W e Wq, com chegadas uma a uma (M/M/1) e, com grupos ligados, M^X/M/1.
4. **Simulação:** 1 catraca, 1 catraca sem desistência, 2ª catraca só no pico, 2 catracas a hora toda e os outros "e se?" do slide 61, sem catraca extra: atendimento mais rápido (metade da troca a menos) e aulas escalonadas (o excesso do pico espalhado no dobro do tempo). Cada cenário traz o custo em minutos de catraca extra. Todos usam a mesma semente e trazem IC de 95% entre réplicas. W usa só o λ de quem entrou (sem os barrados por K).
5. **Validação:**
   - fila reconstruída contra fila simulada (L, pior momento, fração com fila ≥ 10) e D das chegadas (calma e total), contra a faixa de 5% a 95% das réplicas;
   - a curva minuto a minuto (slide 16): em quantos minutos a fila observada cai na faixa das réplicas, o mínimo que o próprio modelo produz e os trechos de 3+ minutos fora;
   - com as chegadas reais (trace): só atendimento e desistências sorteados, isola o μ;
   - fora da amostra: μ da 1ª metade validado na 2ª, e μ das outras sessões validado na sessão.
6. **Refinamentos:** como dar λ ao simulador (regra do slide 59, regra anterior das duas médias e média móvel de 5 min) e M/M/1 × chegadas em grupo, com curva, validação e W de cada um.
7. **Sensibilidade a μ:** W de 1 catraca e da 2ª catraca para o IC de μ e o μ cronometrado.
8. **Pergunta da equipe** (slide 55): *abrir a 2ª catraca quando a fila chega a N alunos (e fechar quando cai a N/2) poupa mais minutos de espera por minuto de catraca aberta do que abri-la no horário de pico?* A busca testa N = 3 a 30 e escolhe o mais eficiente entre os que esperam no máximo o mesmo que a 2ª catraca no horário de pico; a resposta compara as duas pela **eficiência** (minutos de espera poupados, somando os alunos, por minuto de catraca extra aberta).
   **Achado (chegadas em grupo):** quanto chegar em grupo aumenta a espera (fórmula M^X/M/1 na calma e simulação do almoço) e se a resposta da pergunta se mantém com grupos.
   **Conclusão** no formato "quando, quanto, por quê e a que custo", com a faixa da sensibilidade, a política pela fila e as alternativas sem catraca extra, e o **gargalo** (maior ρ).
9. **Entre sessões:** λ de calma e de pico com IC de 95% e o λ de pico juntando os minutos de pico dos dias (slide 59).
10. **Hipóteses do balanço** (com `--comparar-ajustes`).

Se algum item da validação sair "NÃO", revejam primeiro as medições: contagens, separação calma/pico e os atendimentos cronometrados.

## 3. Simulador com interface visual

O `simulador_gui.py` abre uma janela com o mesmo simulador do `analise_catraca.py`. Ele chama as funções do script, então, com os mesmos parâmetros e a mesma semente, dá os mesmos números do `relatorio.txt`.

```bash
python -m pip install PySide6 matplotlib
python simulador_gui.py                      # abre com as sessões de 16/11 e 17/11 que estão em artefatos/dados/
python simulador_gui.py A_dia1.csv B_dia1.csv C_dia1.csv
```

- **Dados:** um botão por dia. **16/11** usa `coletas_2026-11-16_por_coleta.csv`, com a escolha da coleta (1, 2 ou 3) e μ do dia (as três coletas juntas). **17/11** usa `coleta_almoco_2026-11-17_fila42.csv`, com a escolha da hipótese para os 48 alunos que sobram no balanço (saídas não registradas, a principal; desistências não vistas; fila inicial menor): é o mesmo arquivo com o ajuste trocado. **Sem dados** é o modelo manual (duração, trecho de pico e taxas). "Abrir CSVs da coleta…" acrescenta o botão **Arquivo**. O μ vem das saídas por minuto com fila; o cronometrado aparece como referência.
- **Parâmetros:** λ de calma e de pico, μ, θ, fila inicial e limiar de pico já vêm medidos da sessão. Dá para mudar qualquer um para testar "e se…"; o campo alterado fica destacado e "Voltar aos valores medidos" desfaz.
- **Cenários:** os do relatório (incluindo atendimento mais rápido e aulas escalonadas, do slide 61), a **2ª catraca pela fila** (abre com N alunos, fecha com N/2; N "automático" usa o melhor da busca, ou digite um N para a demonstração) e um personalizado, com quantas catracas abrir na calma e no pico. A conclusão começa pela pergunta da equipe e sua resposta, traz o custo e o achado das chegadas em grupo; a aba "Modelo e validação" mostra a tabela da busca do gatilho.
- **Regra do pico:** 1,5 × a média (slide 59, padrão) ou duas médias (versão anterior).
- **Visão geral:** conclusão, um cartão por cenário (W, L, pior momento, tempo com fila ≥ 10) e a fila andando: uma réplica animada, com catracas abrindo no pico, desistências e linha do tempo para ir a qualquer momento.
- **Gráficos:** chegadas por minuto contra a capacidade de 1 e 2 catracas, validação (fila reconstruída × simulada) e cenários ao longo do tempo. Passe o mouse para ver os valores.
- **Simulação:** K (padrão 200), réplicas, semente, passo e "Refinamento: chegadas em grupo" (desligado por padrão = M/M/1; ligado, usa os grupos medidos na sessão).
- **Modelo e validação:** as tabelas do relatório (cenários com IC, validação com D e com as chegadas reais, sensibilidade a μ, M/M/1 e M^X/M/1 por trecho e verificação).

Com 500 réplicas a simulação leva alguns segundos; a barra de progresso mostra o andamento.

## Como o modelo funciona

- Estado: número de alunos no sistema (fila mais catraca).
- A cada passo de 5 s (ou menor, se as chances somarem mais de 1), chega um aluno com chance λ·Δt (M/M/1, padrão). No refinamento com grupos, chega um grupo com chance λ/E[k]·Δt, que traz k alunos sorteados da distribuição medida; a fila desce com chance μ·Δt (se há alguém) e desiste com chance θ·Δt por aluno que espera.
- Calma e pico seguem a agenda do dia observado (os minutos de pico medidos), não um modelo de troca de fases (Gilbert, slide 59 da Aula 09). É uma escolha declarada: reproduz o almoço observado, mas não sorteia almoços com picos em outros horários.
- Com c catracas, a chance de passar vira min(n, c)·μ·Δt.
- Little: W = L / λ.

## Limitações a discutir no seminário

- O M/M/1 supõe chegadas de Poisson e atendimento exponencial. As chegadas não são: D = variância/média fica entre 1,8 e 3,1 em 17/11, porque os alunos chegam em grupos (E[k] ≈ 1,8). O modelo principal continua M/M/1, como pedem os slides, e por isso falha no teste de D; a seção REFINAMENTO do relatório mostra que, com grupos, o D passa e a conclusão quase não muda (W 1,9 → 1,1 min no M/M/1; 2,2 → 1,4 min com grupos). O CV do atendimento cronometrado (1,2) é compatível com o exponencial, mas mede só a passagem na catraca.
- Em 17/11 a fila não foi contada (sem observador C). A "fila observada" da validação é reconstruída das mesmas contagens que dão λ e μ, então a validação é parcialmente circular. A validação com as chegadas reais, a fora da amostra e o D reduzem esse problema, mas só uma contagem direta da fila o resolve.
- O balanço de 17/11 não fecha: sobram 48 alunos. O app gravou fila inicial 0; a equipe usou 42 (`coleta_almoco_2026-11-17_fila42.csv`). As hipóteses (`--comparar-ajustes`) mudam μ e W; a análise principal usa "saídas não registradas" porque é a única que deixa μ estável no dia e mais perto do de 16/11.
- μ é a medida mais incerta: 5,9 /min em 17/11 (com o ajuste) e 7,2 a 7,5 em 16/11. O relatório traz a sensibilidade de W a μ.
- Só a catraca foi medida. Se a fila de dentro (servir, mesas) frear a catraca, o gargalo é outro e a 2ª catraca só leva a fila para dentro. O aviso de queda de μ na 2ª metade aponta esse risco.
- Uma hora simulada é uma amostra, não uma medida. Por isso são 30 réplicas e IC.
- As fórmulas só valem com ρ < 1. No pico, só a simulação responde.
- A fila é reconstruída a partir das chegadas, desistências e saídas do atendimento; falhas ou toques perdidos alteram essa estimativa.
- A fronteira entre calma e pico é detectada por regra automática e pode errar em cerca de um minuto nas bordas. Ajuste com `--limiar`.
- A regra do slide 59 (1,5 × a média) deixa só 13 min de pico em 17/11 (11:55–12:03 e 12:25–12:30) e joga o trecho "morno" de 11:37–11:52 (~6 chegadas/min, quase igual a μ) na calma. Com ela, a fração do tempo com fila ≥ 10 fica no limite da faixa (59% contra 22%–58%). A regra anterior (duas médias) dá 44 min de pico e passa nos 3 itens. O relatório mostra as duas na seção REFINAMENTO.

## Formato do CSV

Cada celular exporta:

```
sessao,data,refeicao,catracas,observador,tipo,instante_iso,t_seg,valor
```

`tipo` pode ser `inicio` (valor = alunos já na fila), `fim`, `chegada`, `desistencia`, `inicio_atend` ou `saida_atend`. O analisador também aceita os registros antigos `fila` (valor = alunos na fila) e `atendimento` (valor = segundos).
