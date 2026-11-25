# Demo autocontida: app + DuckDB embutido. A cada subida do container os dados fictícios são gerados até a data de hoje.
FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 STREAMLIT_SERVER_HEADLESS=true
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /app/data /app/history \
    && chown -R appuser:appuser /app
USER appuser
EXPOSE 8501
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import requests; requests.get('http://127.0.0.1:8501/_stcore/health', timeout=3).raise_for_status()"
# AUTO_BOOTSTRAP já vem ligado: se o banco não existe (ou ficou para trás), gera dados sintéticos e roda os modelos.
CMD ["streamlit", "run", "app/streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
