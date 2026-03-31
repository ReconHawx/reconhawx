FROM python:3.14-slim

WORKDIR /app

RUN apt update && apt upgrade -y && \
    apt install -y --no-install-recommends ca-certificates && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN pip install --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt

COPY ./app /app
COPY ./ /app

# Create symlink for config directory
RUN ln -s /app/config /config

ARG APP_VERSION=dev
ENV APP_VERSION=${APP_VERSION}
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "app.main"]
