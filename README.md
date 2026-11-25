# Chat inteligente

Aplicação interna em Streamlit para consultar indicadores fictícios de produção, segurança e meio ambiente em linguagem natural. O LLM gera uma consulta, o backend valida o SQL e executa somente leitura no DuckDB; uma segunda chamada produz o resumo executivo.

Documentação da demo: [docs/chat-inteligente-cast.md](docs/chat-inteligente-cast.md).

## Requisitos

- Python 3.12
- Chave da Groq ou uma instância Ollama

## Instalação

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
Copy-Item .env.example .env
```

Preencha `GROQ_API_KEY` no `.env` ou configure `LLM_PROVIDER=ollama`.

## Execução local

```powershell
python -m chat_inteligente.synth
python -m chat_inteligente.run_daily
python -m streamlit run app/streamlit_app.py
```

Com `AUTO_BOOTSTRAP=1`, a aplicação gera automaticamente a demonstração se o banco estiver ausente ou desatualizado.

## Configuração principal

- `DB_PATH`: arquivo DuckDB; padrão `data/warehouse.duckdb`.
- `HISTORY_PATH`: histórico SQLite; padrão `data/chat_history.sqlite`.
- `MAX_ROWS`: máximo retornado por consulta, entre 1 e 10.000.
- `QUERY_TIMEOUT`: tempo máximo de uma consulta gerada, em segundos; padrão 20.
- `QUERY_MEMORY_MB`: memória máxima por conexão de consulta; padrão 1024 MB.
- `SHOW_TECHNICAL`: mostra SQL e detalhes técnicos quando igual a `1`.
- `AUTO_BOOTSTRAP`: gera e atualiza a demonstração quando igual a `1`.

Os dados gerados por `synth` são inteiramente fictícios.

## Modelos e recursos

- **Outliers** (Poisson e z-score robusto), **tendências** (30, 90 e 365 dias) e **previsão** dos próximos 14 dias
  (`chat_inteligente/ml/forecast.py`: sazonalidade semanal, nível, tendência amortecida e faixa de 80%).
  A previsão é validada por backtest nos últimos 14 dias; WAPE e acerto da faixa ficam em `v_forecasts`.
- **Resumo do dia** na abertura do chat, calculado direto das tabelas dos modelos (sem LLM).
- **Conferência de números**: números do texto que não existem no resultado são sinalizados (`chat_inteligente/verify.py`).
- **Avaliação do chat**: `python -m chat_inteligente.evaluate` roda `evals/golden.yaml` com o LLM configurado e compara
  cada resultado com o SQL de referência. Use antes de trocar de modelo ou de prompt (gasta chamadas do LLM).
- Respostas podem ser baixadas em Excel/CSV; cada resposta aceita 👍/👎, gravado no histórico.

## Testes

```powershell
python -m pytest -q
```

## Docker

```powershell
docker compose up --build
```

O compose persiste o warehouse e o histórico em volumes separados. A publicação da porta deve permanecer restrita à rede interna autorizada.
