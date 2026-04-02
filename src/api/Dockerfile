FROM python:3.14-slim

WORKDIR /app

# Install system dependencies.
# Pin PostgreSQL client major to 15 (matches kubernetes/base PostgreSQL). The default
# Debian postgresql-client is often newer (e.g. 17) and emits SET transaction_timeout,
# which pg_restore then applies against PG15 and fails with "unrecognized configuration parameter".
RUN set -eux; \
    apt-get update; \
    apt-get upgrade -y; \
    apt-get install -y --no-install-recommends ca-certificates curl gnupg git; \
    curl -fsSL https://www.postgresql.org/media/keys/ACCC4CF8.asc \
      | gpg --dearmor -o /usr/share/keyrings/postgresql-archive-keyring.gpg; \
    . /etc/os-release; \
    echo "deb [signed-by=/usr/share/keyrings/postgresql-archive-keyring.gpg] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends postgresql-client-15; \
    apt-get purge -y curl gnupg; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY setup_nuclei_templates.sh update_nuclei_templates.py generate_nuclei_tree.py ./
RUN chmod +x setup_nuclei_templates.sh update_nuclei_templates.py generate_nuclei_tree.py
RUN ./setup_nuclei_templates.sh

COPY ./app/ ./

# Expose port
ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"] 