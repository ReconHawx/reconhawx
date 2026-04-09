FROM python:3.14-slim

WORKDIR /app/src

COPY requirements.txt /app/src/migrations-requirements.txt
RUN pip install --no-cache-dir -r /app/src/migrations-requirements.txt

COPY . /app/src/migrations/
COPY entrypoint.sh /app/src/entrypoint.sh
RUN chmod +x /app/src/entrypoint.sh

ENV PYTHONPATH=/app/src
ENV MIGRATIONS_DIR=/app/src/migrations

ENTRYPOINT ["/app/src/entrypoint.sh"]
