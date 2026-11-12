# Fila da catraca do RU: coleta e análise

Seminário de Avaliação de Desempenho (UFOPA). O projeto mede a fila da catraca do RU, compara com o modelo M/M/1 e simula cenários, como abrir uma 2ª catraca no horário de pico. Segue o checklist da Aula 10.

## Arquivos

| Arquivo | Para quê | Onde roda |
|---|---|---|
| `index.html` | Estrutura da página de coleta | Navegador do celular |
| `style.css` | Estilos da página | Carregado por `index.html` |
| `app.js` | Lógica da coleta, cronômetro e exportação CSV | Carregado por `index.html` |
| `analise_catraca.py` | Calcula λ e μ, aplica as fórmulas, simula, valida e compara cenários | Terminal (Python 3) |

A página usa `style.css` e `app.js`; mantenha os três arquivos na mesma pasta. O script de análise lê os CSVs exportados pela página.

## 1. Coleta (três observadores por rodada)

Abram a página nos três celulares. Se for usar o arquivo local, sirva a pasta na rede:

```bash
python3 -m http.server 8000
# nos celulares: http://IP-DO-COMPUTADOR:8000   (mesma rede wi-fi)
```

Outra opção é hospedar o `index.html` (GitHub Pages, por exemplo).

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
Para a análise, informe os três CSVs da mesma sessão. A fila é reconstruída pelos registros de chegada, desistência e saída do atendimento; os inícios e saídas também são pareados para calcular o tempo de atendimento.

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

No Windows, talvez seja `python` ou `py` no lugar de `python3`.

### Opções

| Opção | Padrão | Efeito |
|---|---|---|
| `--limiar X` | automático | Chegadas/min (média móvel de 5 min) a partir das quais o minuto é pico |
| `--K N` | 50 | Capacidade máxima da fila no simulador |
| `--passo S` | 5 | Passo da cadeia de Markov, em segundos (reduz sozinho se for grande demais) |
| `--reps N` | 30 | Réplicas de cada cenário |
| `--seed N` | 42 | Semente base, a mesma em todos os cenários |
| `--mu X` | | μ por minuto, se não houver atendimentos cronometrados |
| `--fila NOME LAM MU` | | Outra fila do RU (ticket, suco), para achar o gargalo. Pode repetir |
| `--saida PASTA` | `saida_catraca` | Onde salvar `relatorio.txt` e os gráficos |

Exemplo com outras filas:

```bash
python3 analise_catraca.py *.csv --fila ticket 1.8 3.0 --fila suco 1.2 2.0
```

### O que o relatório mostra

1. **Atendimento:** média, desvio e CV dos atendimentos cronometrados, e μ = 60 / média em segundos.
2. **Por sessão:**
   - λ de calma e de pico, separados pelas chegadas por minuto (e não pelas ondas da fila);
   - desistências: quantos saíram da fila sem passar, a taxa θ e o λ efetivo;
   - fórmulas M/M/1 de cada trecho (ρ, L, W, Wq). No pico, com ρ ≥ 1, as fórmulas não valem e o script avisa.
3. **Verificação:** simulador contra as fórmulas num trecho de calma (o código faz o que o modelo diz?).
4. **Simulação:** 1 catraca, 1 catraca sem desistência, 2ª catraca só no pico e 2 catracas a hora toda. Todos usam a mesma semente e trazem IC de 95% entre réplicas.
5. **Validação:** fila reconstruída a partir dos eventos contra fila simulada (L, pior momento, fração com fila ≥ 10) e se o valor reconstruído cai na faixa de 5% a 95% das réplicas.
6. **Conclusão** no formato "quando, quanto e por quê", e o **gargalo** (maior ρ).
7. **Entre sessões:** λ de calma e de pico com IC de 95%.

Se algum item da validação sair "NÃO", revejam primeiro as medições: contagens, separação calma/pico e os atendimentos cronometrados.

## Como o modelo funciona

- Estado: número de alunos no sistema (fila mais catraca).
- A cada passo de 5 s, a fila sobe com chance λ·Δt, desce com chance μ·Δt (se há alguém) e desiste com chance θ·Δt por aluno que espera.
- Com c catracas, a chance de passar vira min(n, c)·μ·Δt.
- Little: W = L / λ.

## Limitações a discutir no seminário

- O M/M/1 supõe chegadas de Poisson e atendimento exponencial. O script mostra variância/média das chegadas e o CV do atendimento, que ficam perto de 1 quando a suposição vale.
- Uma hora simulada é uma amostra, não uma medida. Por isso são 30 réplicas e IC.
- As fórmulas só valem com ρ < 1. No pico, só a simulação responde.
- A fila é reconstruída a partir das chegadas, desistências e saídas do atendimento; falhas ou toques perdidos alteram essa estimativa.
- A fronteira entre calma e pico é detectada por regra automática e pode errar em cerca de um minuto nas bordas. Ajuste com `--limiar`.

## Formato do CSV

Cada celular exporta:

```
sessao,data,refeicao,catracas,observador,tipo,instante_iso,t_seg,valor
```

`tipo` pode ser `inicio` (valor = alunos já na fila), `fim`, `chegada`, `desistencia`, `inicio_atend` ou `saida_atend`. O analisador também aceita os registros antigos `fila` (valor = alunos na fila) e `atendimento` (valor = segundos).
