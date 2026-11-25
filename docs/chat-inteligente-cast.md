# Chat inteligente

Pacote `chat-inteligente-cast`, versão `0.1.0` (`pyproject.toml`). Aplicação Streamlit de demonstração: consulta, em português, indicadores fictícios de produção, segurança e meio ambiente de uma usina siderúrgica integrada. Um modelo de linguagem gera SQL; o backend aceita só leitura no DuckDB; uma segunda chamada resume o resultado. Em paralelo, a tela de análises mostra os mesmos dados e a saída dos modelos (outlier, tendência e previsão de 14 dias).

## Problema

A pergunta de negócio (produção de um alto-forno, taxa de acidentes, excedência ambiental, previsão da semana) está espalhada em séries diárias. Quem lê o indicador precisa de agregação correta, do contexto dos modelos e de um texto que não invente número. A demo mostra essa camada em cima de um warehouse já no formato `entities`, `metrics_catalog` e `daily_metrics`, sem depender de um sistema de origem específico.

## O que a demo entrega

- Cinco visões: Chat, Análises, Histórico, Dados e Sobre os dados.
- Chat com sugestões do catálogo, resumo do dia calculado sem LLM, gráfico automático, download Excel/CSV, 👍/👎 e registro de pergunta, resposta e SQL.
- Análises de produção, segurança, meio ambiente, outliers, tendências e previsão, mais o detalhe de uma série.
- Job `python -m chat_inteligente.run_daily` (versão de modelo `poisson+robust-z+linreg+seasonal-forecast-v4`) que grava outliers, tendências e previsões. Mantém as últimas 30 execuções.
- Avaliação opcional do chat: `python -m chat_inteligente.evaluate` compara `evals/golden.yaml` (14 perguntas) com o SQL de referência do catálogo. O repositório não guarda o resultado dessa rodada.
- Testes em `tests/` e workflow `.github/workflows/tests.yml` (Python 3.12, `pytest -q`). Não há relatório de cobertura nem de acerto do LLM versionado.

## O que fica para dados do cliente

A fonte atual é sintética. `app_meta.source` fica `sintético (fictício) — gerado por chat_inteligente.synth`. A aba Sobre diz que a fonte real só precisa preencher `entities`, `metrics_catalog` e `daily_metrics`. Não há conector, arquivo de carga nem mapeamento de sistema do cliente.

`bootstrap.ensure_data` regenera a demonstração só se o banco está ausente, vazio ou marcado como sintético. Banco classificado como `real` ou `unknown` não é apagado. Não há, no código, autenticação, papéis, retenção do histórico nem escrita de volta para a operação.

Metas internas, capacidades diárias, headcount e episódios plantados estão no gerador. Não são leitura de uma planta. Licença de uso dos relatórios citados em `docs/referencias.md` não está registrada; o próprio arquivo diz que serviram só para ordem de grandeza.

## Telas

A navegação é estado da sessão (`view`), não rota HTTP.

| Visão | O que mostra |
|---|---|
| Chat | Pergunta em linguagem natural. Na abertura, até 8 sugestões de `catalog.yaml` e o botão «Mostre o resumo do dia». O resumo (até 6 itens) só aparece quando o usuário pede. A resposta traz texto, pontos de atenção, tabela, gráfico se houver de 3 a 600 linhas, Excel e CSV. Números do texto que não batem com a tabela são sinalizados. Com `SHOW_TECHNICAL=1` (padrão), o expansor mostra o SQL, tentativas, tempo e modelo. |
| Análises | Sete sub-abas. Períodos: últimos 30 dias, 90 dias, 12 meses, ano atual, todo o período. O padrão de várias sub-abas é «Últimos 12 meses». |
| Visão executiva | Gusa, bobinas a quente, galvanizados e acidentes no período, com variação contra o período anterior quando ele existe. Também acidentes por milhão de horas-homem, incidentes, medições ambientais fora do limite e outliers em 90 dias. Gráficos de produção e de acidentes por área, mais até 8 tendências de alta ou queda em 90 dias. |
| Produção | Resumo dos 5 equipamentos com `producao_t` (total, média, p10, mediana, p90, máximo, dias abaixo de 25% da mediana, disponibilidade em dias). Série por planta, ativo ou total. Produção anual e o mesmo mês em anos diferentes. Paradas: trechos contínuos abaixo de 25% da mediana, com perda estimada em toneladas contra essa mediana. Eficiência e dispersão entre dois indicadores do equipamento, com correlação de Pearson. |
| Segurança | Desvios, ocorrências, incidentes, acidentes e taxa por milhão de horas-homem, por área, sem somar a entidade consolidada. Pirâmide, evolução, taxa anual, dias sem acidente, média por dia da semana e até 25 dias recentes com acidente. |
| Meio ambiente | Medições com limite, quantas ficaram fora e o percentual. Série com limite desenhado. Sazonalidade mensal. Onde o indicador está em `REF_WORLDSTEEL`, compara a média do período com a referência. Lista de excedências (a tela pede até 100.000 e mostra 200). |
| Anomalias e tendências (ML) | Outliers em 7 dias, 90 dias e no histórico; contagem de tendências de alta e de queda em 90 dias. Filtro por área e período. Tendências nas janelas 30, 90 e 365. |
| Previsão | Séries contínuas com WAPE histórico até 25%, ordenadas pelo afastamento dos próximos 7 dias frente à média dos últimos 7 (até 10 linhas). Gráfico de uma série com faixa e os dois indicadores do backtest: WAPE e acerto da faixa de 80% nos últimos 14 dias. |
| Série em detalhe | Observado, esperado do modelo de outlier, outliers e, se existir, previsão de 14 dias. Estatísticas descritivas da série no período. |
| Histórico | Até 500 turnos, busca, CSV e o que foi executado. Dá para reabrir a conversa. A barra lateral lista 6 conversas recentes. |
| Dados | Sete tabelas somente leitura, com filtro de ativo, métrica, período e «somente outliers». Mostra o total e corta em 50.000 linhas. Download CSV do recorte exibido. |
| Sobre os dados | Texto do fluxo, dos modelos e das referências, mais o catálogo que o chat enxerga. |

A barra lateral mostra quantos ativos e séries há em `daily_metrics`, o intervalo de datas, se os modelos rodaram e se estão defasados, o provedor de LLM e o aviso de dado fictício quando a fonte começa com `sint`.

## Dados

Não há arquivo de warehouse no repositório. `.gitignore` ignora `data/*.duckdb` e `data/*.sqlite`. Contagem de linhas, valor de KPI na tela e WAPE por série não estão versionados. O que está fixo é o gerador e o que os testes exigem quando `synth.generate(end="2026-11-09")` roda (`tests/conftest.py`). Na execução local e no Docker, o fim da série é o dia da geração, não essa data.

Não há arquivo `LICENSE`. Licença do código: ausente. Licença de dataset: ausente, porque a série é fictícia. Semente do gerador: `2021`.

| Fato | Onde está |
|---|---|
| Início da série nos testes | 2021-01-01 |
| Fim da série nos testes | 2026-11-09 |
| Fim na execução normal | dia em que `synth` roda |
| Entidades no cadastro | 15 (`sim/profiles.py`) |
| Métricas no catálogo | 26 |
| Equipamentos com produção | 5 (teste: `producao_resumo` devolve 5 linhas) |
| Áreas de segurança, sem o consolidado | 10 (teste: `dias_sem_acidente`) |
| Séries definidas por `put` no gerador | 97 pares entidade–métrica (17 de produção, 55 de segurança incluindo `SEG00`, 25 de meio ambiente) |
| Valores nulos gravados em `daily_metrics` | 0 (teste). Dia sem medição não vira linha |
| Valores negativos | 0, exceto a métrica `ph_efluente`, que o teste deixa de fora dessa checagem |
| Séries na previsão | o teste exige pelo menos 90 séries e exatamente 14 linhas por série |
| Fonte registrada | texto de `synth.SOURCE` |

`SEG00` é a soma das áreas em desvios, ocorrências, incidentes, acidentes e horas-homem. O chat e as análises excluem essa entidade dos totais por área.

Aciaria (`ACI01`) entra em segurança e em emissão de chaminé. Não tem `producao_t`. `AMB02` não recebe intensidade de particulados, SOx nem NOx por tonelada; `AMB01` recebe.

| Entidade | Planta | Tipo |
|---|---|---|
| AF01 Alto-Forno 1 | Norte | alto-forno |
| AF02 Alto-Forno 2 | Norte | alto-forno |
| ACI01 Aciaria | Norte | aciaria |
| LTQ01 Laminador de Tiras a Quente | Norte | laminador |
| UTL01 Utilidades e Energia | Norte | utilidades |
| MAN01 Manutenção Central Norte | Norte | manutenção |
| LOG01 Logística e Pátio Norte | Norte | logística |
| ETE01 ETE Norte | Norte | ponto ambiental |
| AMB01 Indicadores Ambientais Norte | Norte | consolidado ambiental |
| GALV01 Linha de Galvanização 1 | Sul | galvanização |
| GALV02 Linha de Galvanização 2 | Sul | galvanização |
| MAN02 Manutenção Sul | Sul | manutenção |
| ETE02 ETE Sul | Sul | ponto ambiental |
| AMB02 Indicadores Ambientais Sul | Sul | consolidado ambiental |
| SEG00 Segurança — Consolidado | Todas | consolidado de segurança |

Limites gravados no catálogo (o que a tela de meio ambiente usa). Os de CONAMA estão marcados assim no código. Os demais são meta interna fictícia.

| Métrica | Inferior | Superior | Referência no código |
|---|---|---|---|
| Particulados na chaminé | — | 50 mg/Nm³ | meta interna fictícia |
| NOx na chaminé | — | 350 mg/Nm³ | meta interna fictícia |
| pH do efluente | 5 | 9 | CONAMA 430/2011 |
| Temperatura do efluente | — | 40 °C | CONAMA 430/2011 |
| Óleos e graxas | — | 20 mg/L | CONAMA 430/2011 |
| CO₂ | — | 2,10 t/t | meta interna fictícia |
| Água nova | — | 7,0 m³/t | meta interna fictícia |
| Reaproveitamento de coprodutos | 90% | — | meta interna fictícia |
| Recirculação de água | 95% | — | meta interna fictícia |
| Particulados por t | — | 0,40 kg/t | meta interna fictícia |
| SOx por t | — | 0,90 kg/t | meta interna fictícia |
| NOx por t | — | 0,90 kg/t | meta interna fictícia |

Produção, combustível, disponibilidade, rendimento, rejeição, zinco, velocidade, contagens de segurança e horas-homem não têm limite no catálogo.

Comparação da aba Meio ambiente (`analytics.REF_WORLDSTEEL`), constante de código, não resultado medido da usina fictícia:

| Indicador | Referência usada na tela |
|---|---|
| CO₂ | 2,34 t/t (worldsteel 2024, rota alto-forno/aciaria) |
| Energia | 23,88 GJ/t (worldsteel 2024, rota alto-forno/aciaria) |
| Particulados | 0,32 kg/t (média global) |
| SOx | 0,64 kg/t |
| NOx | 0,66 kg/t |
| Água | 8,50 m³/t (captação média global) |

`docs/referencias.md` cita também Usiminas (2020), Aço Brasil e a pirâmide de Bird. Não há tabela, no repositório, com o valor lido de cada relatório além dos números acima e dos comentários em `profiles.py` (CO₂ Usiminas 2,17–2,21 em 2020; worldsteel BF-BOF 2,34; energia média global 20,95 e BF-BOF 23,88; reaproveitamento Aço Brasil ~93% em 2020; recirculação 97% em 2019–2020; acidentes com afastamento ~0,7 por milhão de horas).

Episódios plantados no gerador, para os modelos terem o que detectar: reforma do AF01 de 2023-05-15 a 2023-10-09; parada do AF02 de 2024-06-01 a 2024-12-31; parada anual do laminador em 12–18 de julho e um trecho em 2022-10-12 a 2022-10-14; falta de sucata na galvanização de 2021-04-01 a 2021-09-30; falha de filtro de particulados no AF01 de 2024-03-04 a 2024-03-13; deriva de particulados do AF02 desde 2026-07-01; excursões de pH, óleos e temperatura nas ETEs; queda de rendimento do laminador desde 2026-04-15 e degrau de gás desde 2025-09-01; deriva de rejeição (desde 2026-03-01) e de zinco (desde 2026-06-10) na GALV02; acidentes e incidentes da Logística multiplicados de 2026-08-01 a 2026-10-31; desvios da Manutenção Norte em queda ao longo de 2026. A lista completa das janelas está em `sim/engine.py` e o resumo em `docs/referencias.md`.

## Modelo

Três detectores em `chat_inteligente/ml/`, sem biblioteca de forecasting extra. Não há treino separado nem conjunto de teste arquivado. A validação da previsão é um backtest embutido em cada série, gravado nas colunas `wape_pct` e `coverage_pct`.

| Peça | Regra no código |
|---|---|
| Outlier contínuo | Esperado = mediana do mesmo dia da semana nas 8 semanas anteriores. Escala = MAD dos resíduos passados (janela 56, mínimo 21). |
| Outlier de contagem | λ = média móvel de 90 dias ajustada pelo dia da semana. Score = z da cauda de Poisson, limitado a ±8. |
| Corte de outlier | `\|score\| ≥ 3,5`. A view guarda todos os sinalizados e, além disso, os últimos 90 dias por completo. |
| Tendência | Regressão linear em 30, 90 e 365 dias, sem efeito de dia da semana. p-valor corrige autocorrelação. Direção alta ou queda só se p < 0,05 e o efeito na janela for ≥ 1 desvio do resíduo. Contagem com menos de 10 eventos na janela não recebe tendência. |
| Previsão | Horizonte 14 dias. Sazonalidade semanal das últimas 8 semanas, nível dos últimos 28 dias (aparado), tendência de 90 dias só se o critério acima passar, amortecida com Φ = 0,97. Faixa de 80%. Contagem usa quantis de Poisson; o restante usa MAD dos últimos 56 dias. Histórico usado: 365 dias. Série com menos de 120 dias, ou parada há mais de 3 dias, fica de fora. |
| Backtest | O modelo é ajustado sem os últimos 14 dias e comparado ao realizado. WAPE = soma do erro absoluto / soma do realizado, em %. Cobertura = percentual desses 14 dias dentro da faixa. A largura da faixa contínua é calibrada numa janela anterior a esses 14 dias (fator entre 1 e 4). |

Incerteza que o código explicita: a faixa é de 80%, não um intervalo de confiança formal publicado; a conferência de números do texto (`verify.py`) é checagem de consistência, não garantia; a correlação de Pearson na aba Produção é associação. Transferência: os limiares (3,5; p < 0,05; efeito ≥ 1; 14 dias; WAPE ≤ 25% para entrar no ranking da previsão) foram escolhidos para esta simulação. Nada no repositório mede o mesmo modelo em outra usina, outro ritmo de parada ou outro sistema de registro de acidentes.

Métricas que o repositório fixa (limites de teste no warehouse com fim em 2026-11-09, ou série artificial). Não há tabela versionada de WAPE por ativo.

| Checagem | Limite no repositório | O que não é |
|---|---|---|
| Mediana do WAPE entre séries de `v_forecasts` | < 15 | valor medido publicado; o teste só falha se a mediana passar de 15 |
| Taxa de linhas com outlier nos últimos 90 dias de `v_outliers` | maior que 0 e menor que 2% | taxa exata; ausente |
| Série artificial contínua (nível 100, tendência 0,1/dia, seno semanal, ruído σ = 1, 400 dias) | erro absoluto médio da previsão < 3 e WAPE < 3 | resultado da usina fictícia |
| Série artificial de Poisson λ = 2, horizonte 7 | previsão entre 1 e 3,5 | resultado da usina fictícia |
| Tendência de acidentes em 30 dias | nenhuma série com direção diferente de estável | contagem de acidentes |
| Histórias plantadas que o teste exige detectar | AF02 particulados em alta (90 dias); ETE02 óleos em alta (90 dias); MAN01 desvios em queda (365 dias) | lista completa do que a tela ranqueia; ausente |
| Parada do AF02 | maior trecho abaixo de 25% da mediana tem mais de 150 dias | duração exata na tela; a janela plantada é 2024-06-01 a 2024-12-31 |
| Produção de gusa em 12 meses | soma > 1.000.000 t | total exibido; ausente |
| Rendimento metálico do laminador em 12 meses | média entre 80 e 100 | média exibida; ausente |
| Excedências ambientais no período inteiro | pelo menos uma | contagem exibida; ausente |
| Acerto do chat no `golden.yaml` | ausente | o harness existe; nenhuma saída foi gravada |

O comentário em `evals/golden.yaml` avisa que o prompt escolhe exemplos parecidos com a pergunta, então a avaliação também mede vazamento do exemplo. Tolerância numérica da comparação: `rtol = 1e-6`.

## Resultados que a tela mostra

Os números grandes da visão executiva não estão no repositório: nascem da consulta ao DuckDB na hora. O que a tela mostra, de forma estável, é o seguinte.

- Produção separada em gusa (altos-fornos), bobinas (laminador) e galvanizados (duas linhas), nunca somados num único total de «aço».
- Acidentes e a taxa por milhão de horas-homem sem a linha consolidada. A taxa sobe quando o número de acidentes sobe (cor do delta invertida).
- Parada ou produção reduzida: dia abaixo de 25% da mediana histórica daquele equipamento. A perda estimada é a soma de (mediana − valor) nesses dias. É estimativa da tela, não medição de toneladas perdidas.
- Conformidade ambiental: fração de dias fora do limite do catálogo, por ponto e indicador.
- Outlier: data, ativo, observado, esperado, score e se ficou acima ou abaixo.
- Tendência: direção, variação percentual na janela, inclinação ao dia e p-valor. O rótulo estável cobre o que não passou no corte.
- Previsão: valor, faixa inferior e superior, WAPE e acerto da faixa daquela série. O ranking «o que deve mudar» só inclui contínuas com WAPE até 25%. O resumo do dia só cita previsão se a variação absoluta contra a última semana for de pelo menos 3%.
- No warehouse de teste, as três histórias acima (particulados do AF02, óleos da ETE02, desvios da MAN01) são tendência significativa na janela indicada. As demais histórias plantadas não têm asserção de detecção no teste.

## Premissas editáveis

Não há módulo de ROI, preço, custo ou payback. Premissa abaixo não é resultado medido.

| Premissa | Onde editar | Valor na demo |
|---|---|---|
| Capacidade diária de base | `sim/engine.py` | AF01 6.800 t/dia; AF02 1.700 t/dia; laminador 6.400 t/dia; GALV01 1.230 t/dia; GALV02 950 t/dia |
| Combustível de base dos altos-fornos | `sim/engine.py` | AF01 505 kg/t; AF02 530 kg/t |
| Headcount usado só para gerar horas-homem (`headcount × 6,4`, com fator de fim de semana) | `sim/engine.py` | AF01 520; AF02 280; aciaria 610; laminador 700; utilidades 240; manutenção norte 900; logística 480; GALV01 310; GALV02 260; manutenção sul 380 |
| Intensidades de partida da planta norte | `sim/engine.py` | CO₂ de 2,20 para 2,06 até 2026-11-09; energia 24 GJ/t; água 6,3 m³/t; reaproveitamento 94%; recirculação 97%; particulados 0,30; SOx 0,70; NOx 0,62 kg/t |
| Intensidades da planta sul | `sim/engine.py` | CO₂ de 0,32 para 0,28; energia 3,2 GJ/t; água 1,25 m³/t; reaproveitamento 91,5%; recirculação 96% |
| Metas e limites legais do catálogo | `sim/profiles.py` | tabela da seção Dados |
| Referência worldsteel da tela | `analytics.REF_WORLDSTEEL` | tabela da seção Dados |
| Corte para entrar no ranking de previsão | `forecast_overview` | WAPE ≤ 25 e tipo contínuo |
| Corte do resumo do dia para citar previsão | `briefing.py` | variação absoluta ≥ 3% |
| «Hoje» das perguntas | nota do `catalog.yaml` | `MAX(ref_date)` de `daily_metrics`, não a data do relógio |
| Provedor e modelo | `.env` | padrão Groq `openai/gpt-oss-120b` ou Ollama `qwen2.5-coder:7b`; temperatura 0 |
| Teto de linhas, tempo e memória da consulta gerada | `.env` | 200 linhas (teto do parâmetro 10.000), 20 s (teto 300), 1.024 MB (faixa 128–16.384) |

Trocar a fonte real não passa por esses parâmetros do gerador. Passa por carregar as três tabelas base e por editar `catalog.yaml` (o comentário no topo do arquivo diz que o restante do código não muda).

## Como executar

Python 3.12. Chave Groq ou um Ollama. Dependências de execução em `requirements.txt`; de teste em `requirements-dev.txt` (inclui o primeiro e `pytest`).

Local:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
python -m chat_inteligente.synth
python -m chat_inteligente.run_daily
python -m streamlit run app/streamlit_app.py
```

Preencher `GROQ_API_KEY` ou definir `LLM_PROVIDER=ollama`. Com `AUTO_BOOTSTRAP=1` (padrão), a aplicação gera a demonstração se o banco não existe, está vazio, é sintético e está atrasado em relação ao dia, ou se os modelos não estão na versão atual. Testes: `python -m pytest -q`. Avaliação do chat (gasta chamada de LLM): `python -m chat_inteligente.evaluate`.

Docker: `docker compose up --build`. Imagem `python:3.12-slim`, usuário `appuser` (uid 10001), porta 8501, `AUTO_BOOTSTRAP=1`. Volumes `warehouse` (`/app/data`) e `historico` (`/app/history`). O healthcheck chama `GET http://127.0.0.1:8501/_stcore/health`. O README pede que a publicação da porta fique na rede interna autorizada. `.env` entra por `env_file` e está no `.dockerignore`.

## Arquitetura

Streamlit (`app/streamlit_app.py`) chama o pacote `chat_inteligente`. DuckDB guarda o warehouse. SQLite guarda o histórico. O LLM é HTTP de saída (Groq ou Ollama), temperatura 0. Não há API de negócio neste repositório.

Fluxo do chat: a pergunta passa por `prompt_guard` (recusa texto vazio, caractere invisível e tentativa de trocar instrução). O agente manda o catálogo (até 4 exemplos parecidos com a pergunta) e a lista viva de entidades e métricas. Se o SQL falha na validação ou no DuckDB, há uma segunda tentativa. Timeout não é repetido. Fora de escopo não chama o resumo. Com linhas, uma segunda chamada escreve o texto executivo só com o resultado (até 30 linhas no prompt) e o contexto dos modelos. `verify` marca números do texto que não aparecem no resultado, na diferença, na variação, na participação, na soma ou na média. Resposta sem histórico de conversa fica em cache por 600 s, invalidada se a data máxima ou o `run_id` mudam. O resumo do dia também cacheia 600 s e não chama o LLM.

O SQL executado é um único `SELECT` (ou `WITH` não recursivo) sobre as tabelas do catálogo, com `LIMIT` forçado. Junção cruzada, junção sem condição, mais de 5 junções, mais de 8 CTEs, mais de 12 subconsultas e funções de leitura de arquivo são recusadas. `ml_runs` e `app_meta` não estão no catálogo: o teste confirma que o guard as bloqueia. A conexão de consulta é somente leitura, com `memory_limit` e interrupção no tempo configurado.

| Caminho | Papel |
|---|---|
| `GET /_stcore/health` em 127.0.0.1:8501 | healthcheck do container; não é API de negócio |
| Visões Chat, Análises, Histórico, Dados, Sobre | interface; não são rotas HTTP |
| `POST {OLLAMA_URL}/api/chat` | saída; padrão `http://localhost:11434`; timeout 300 s |
| `POST https://api.groq.com/openai/v1/chat/completions` | saída; timeout 120 s; até 2 novas tentativas em HTTP 429, espera máxima 25 s |

Tabelas que o chat pode consultar: `entities`, `metrics_catalog`, `daily_metrics`, `v_outliers`, `v_trends`, `v_forecasts`. As views apontam para a última linha de `ml_runs`.

## Repositório e artefatos

| Caminho | Função |
|---|---|
| `app/streamlit_app.py` | entrada da interface |
| `app/chat_view.py`, `analises.py`, `history_view.py`, `pages_extra.py`, `charts.py`, `theme.py` | telas |
| `chat_inteligente/agent.py`, `llm.py`, `sql_guard.py`, `prompt_guard.py`, `verify.py`, `context.py` | chat |
| `chat_inteligente/catalog.yaml` | o que o LLM pode ver, exemplos e sugestões |
| `chat_inteligente/sim/`, `synth.py` | gerador fictício |
| `chat_inteligente/ml/`, `run_daily.py` | modelos e job |
| `chat_inteligente/analytics.py`, `overview.py`, `briefing.py`, `labels.py` | consultas das telas |
| `chat_inteligente/bootstrap.py`, `db.py`, `history.py`, `config.py` | banco, histórico, ambiente |
| `chat_inteligente/evaluate.py`, `evals/golden.yaml` | avaliação do chat |
| `tests/` | testes; a fixture gera o warehouse até 2026-11-09 |
| `docs/referencias.md` | referências de ordem de grandeza |
| `Dockerfile`, `docker-compose.yml` | execução em container |
| `.github/workflows/tests.yml` | pytest em push e pull request |

Regenerar a demonstração:

```powershell
python -m chat_inteligente.synth
python -m chat_inteligente.run_daily
```

Isso apaga e recria o schema (`reset_schema`) e grava a fonte sintética. Não usar esse comando em cima de um banco de cliente: o bootstrap recusa banco `real`, mas `synth` chamado à mão regrava o arquivo em `DB_PATH`. Para só recalcular modelos em dado já carregado: `python -m chat_inteligente.run_daily`. Não há outro artefato (parquet, notebook, relatório de métricas) para regenerar.

## Limites numa conversa com cliente

Pode ser afirmado a partir deste repositório:

- A demo responde em português sobre produção, segurança e meio ambiente de uma usina fictícia, com SQL somente leitura e checagem dos números do texto.
- Os modelos são auditáveis no código: outlier por dia da semana, tendência linear com corte de efeito, previsão de 14 dias com faixa de 80% e WAPE de backtest na própria linha.
- No warehouse de teste (fim 2026-11-09), a mediana do WAPE fica abaixo de 15, a fração de outliers nos últimos 90 dias da view fica abaixo de 2%, e três histórias plantadas aparecem como tendência.
- Dado marcado como real não é substituído pelo bootstrap.
- Acidentes do consolidado são a soma das áreas.

Depende de calibração ou de dado do cliente, e não pode ser apresentado como medição desta demo:

- Qualquer tonelada, taxa, excedência ou WAPE visto na tela como se fosse a planta do cliente. A série é fictícia e o fim dela muda com o dia da geração.
- As metas (CO₂ 2,10 t/t, água 7,0 m³/t, recirculação 95%, reaproveitamento 90% e os tetos de chaminé e de intensidade). São fictícias, mesmo quando o número de referência do setor está citado.
- A comparação com worldsteel. É constante de tela contra a série fictícia.
- A perda estimada da parada. Usa a mediana do próprio equipamento.
- O acerto do chat com um modelo específico. `golden.yaml` tem 14 perguntas e nenhuma taxa de acerto gravada. O próprio arquivo diz que o exemplo do catálogo pode vazar para o teste.
- Que o limiar 3,5 ou a janela de 8 semanas serve para o ritmo de registro do cliente.
- Que a pirâmide desvio > ocorrência > incidente > acidente se mantém fora desta simulação. As taxas λ estão no gerador (desvios 5,0 × porte, ocorrências 0,33, incidentes 0,025, acidentes 0,006, com rampas).
- Governança de indicador de pessoa. A demo grava a pergunta e a resposta em SQLite local, sem controle de acesso.

## Perspectiva de produto

A demo já prova o caminho de leitura: três tabelas base, job diário, três modelos com versão, chat que não executa SQL fora do catálogo, análises no mesmo warehouse e histórico da conversa. Não prova operação com dado de cliente.

| Fase | Coberto hoje | O que vem depois |
|---|---|---|
| Demonstração | Gerador, modelos, cinco visões, guard de SQL, testes no warehouse até 2026-11-09 | Parar de usar a série fictícia na frente do cliente |
| Ingestão | Contrato das tabelas `entities`, `metrics_catalog`, `daily_metrics`; bootstrap não apaga banco `real`; duplicata no mesmo dia vira média e gera aviso | Carga a partir do sistema do cliente. Não existe conector |
| Calibração | Limites e referências no código e em `docs/referencias.md` | Trocar meta, capacidade e referência worldsteel pelos valores do cliente, fora do gerador |
| Uso da tela | Consulta, gráfico, download, feedback e histórico | Nada grava decisão, alerta nem volta para o sistema de origem |
| Governança | Métricas de pessoas (acidentes, horas-homem, áreas); histórico com pergunta, SQL e prévia de 50 linhas | Acesso, papel, retenção e base legal. Ausentes |
| Shadow | A consulta gerada é só `SELECT` | Não há fila do que seria recomendado sem afetar a operação, nem comparação com a decisão real |
| Escala | Duas plantas fictícias, um DuckDB, um SQLite, um provedor de LLM, 30 execuções de modelo | Várias unidades, vários fabricantes e as premissas do cliente no lugar dos valores de `engine.py` |

O que construir, na ordem em que o código já deixa o gancho:

1. Ingestão. Implementar a carga das três tabelas que `pages_extra.sobre` e `bootstrap.py` já tratam como contrato. Incluir o que a simulação não tem: aço líquido da aciaria (`ACI01` não tem `producao_t`), intensidades da planta sul equivalentes às da norte (`AMB02` não tem particulados, SOx nem NOx por tonelada) e a regra real de hora-homem no lugar do `headcount × 6,4`.
2. Calibração. Tirar de `profiles.py`, `engine.py` e `REF_WORLDSTEEL` as metas, as bases diárias e as referências, e passar a lê-las do catálogo do cliente. O ranking de previsão (WAPE ≤ 25) e o resumo (variação ≥ 3%) também são corte fixo.
3. Fechar a tela de ponta a ponta. O chat para no texto e no arquivo. Não há dono do indicador, prazo, nem registro de que a pergunta mudou uma decisão. A avaliação `evaluate` precisa de uma meta de acerto gravada; hoje a saída só vai para o console e o golden reaproveita os 14 exemplos do catálogo.
4. Governança, porque a demo mede pessoas. Acidentes, incidentes e horas-homem são por área, com headcount no gerador. O histórico guarda a pergunta inteira, o SQL e uma prévia dos dados, em arquivo local, sem login. Antes de apontar para dado real falta controle de quem pergunta, o que pode ver e por quanto tempo o turno fica gravado.
5. Shadow. Manter o que já existe (somente leitura, sem `INSERT` na consulta do chat) e acrescentar o que não existe: lista do que o modelo teria sinalizado, sem disparar a rotina da planta, e a comparação posterior com o que a operação fez. O banner de dado fictício não substitui esse modo.
6. Escala. Um arquivo DuckDB e um SQLite não separam unidades. O cadastro tem duas plantas e um consolidado de segurança. Fabricante de LLM é uma chave no `.env`. As premissas de demonstração (capacidades, headcount, metas, episódios de 2023–2026) teriam de sair do gerador e entrar como parâmetro do cliente, editável sem novo deploy do código da simulação.
