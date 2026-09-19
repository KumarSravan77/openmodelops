FROM python:3.12-slim AS runtime
ARG SERVICE
ENV SERVICE=${SERVICE} PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
RUN useradd --create-home --uid 10001 openmodelops
COPY pyproject.toml .
RUN pip install --no-cache-dir .
COPY packages packages
COPY platforms platforms
COPY catalog catalog
USER 10001
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"
CMD ["sh", "-c", "uvicorn platforms.${SERVICE}.api:app --host 0.0.0.0 --port 8000"]
