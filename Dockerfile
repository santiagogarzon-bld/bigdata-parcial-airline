# Production demo image (build from repository root).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/app/backend
WORKDIR /app
COPY backend/pyproject.toml backend/
COPY backend/airline_core backend/airline_core
COPY backend/alembic.ini backend/
COPY backend/alembic backend/alembic
COPY frontend /app/frontend
RUN groupadd --system airline && useradd --system --gid airline --home-dir /app --no-create-home airline \
    && pip install --no-cache-dir 'fastapi>=0.104,<1' 'uvicorn>=0.30,<1' 'SQLAlchemy>=2.0.36,<2.1' 'psycopg[binary]>=3.2,<3.3' 'alembic>=1.14,<1.15' 'pydantic>=2.10,<3' \
    && chown -R airline:airline /app
USER airline
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=3)"
CMD ["sh", "-c", "exec uvicorn airline_core.main:app --host 0.0.0.0 --port ${PORT:-8000} --workers ${WEB_CONCURRENCY:-1}"]
