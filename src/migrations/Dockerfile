FROM python:3.14-slim

WORKDIR /app/src

RUN pip install --no-cache-dir psycopg2-binary==2.9.11

COPY . /app/src/migrations/
COPY entrypoint.sh /app/src/entrypoint.sh
RUN chmod +x /app/src/entrypoint.sh

ENV PYTHONPATH=/app/src
ENV MIGRATIONS_DIR=/app/src/migrations

ENTRYPOINT ["/app/src/entrypoint.sh"]
