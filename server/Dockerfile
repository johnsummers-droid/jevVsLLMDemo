# Pipeline Simulator API (plan1.txt section 6). Build context: server/.
#   docker build -t pipeline-sim-server server
#   docker run -p 8000:8000 -e DATABASE_URL=... -e FACILITATOR_CODE=... -e TOKEN_SECRET=... pipeline-sim-server
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv

# Dependencies first, so code changes reuse this layer.
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install . && rm -rf app build *.egg-info

COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./
RUN pip install --no-deps . && rm -rf build *.egg-info

RUN useradd --create-home --uid 10001 appuser
USER appuser

# Railway and Render set PORT. Migrations run before the server starts; exactly one replica runs
# (in-memory run state, plan1.txt decision D8), so they never race.
ENV PORT=8000 LOG_LEVEL=info
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port \"$PORT\" --proxy-headers --forwarded-allow-ips='*' --log-level \"$LOG_LEVEL\""]
