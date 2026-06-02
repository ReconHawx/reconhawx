# Self-hosted CertStream aggregator (CaliDog/certstream-server).
# Pinned commit: third-party/certstream-server/VERSION (upstream has no 1.6.0 git tag).
ARG CERTSTREAM_GIT_COMMIT=b19cba80d285ee0f63f2d8aac15e9d930433593a

# Match upstream Dockerfile base (easy_ssl compiles against OTP headers on 1.8)
FROM elixir:1.8-alpine

RUN apk add --no-cache git

WORKDIR /opt/app
ENV HOME=/opt/app
ENV MIX_HOME=/opt/mix
ENV HEX_HOME=/opt/hex
ENV MIX_ENV=prod
ENV PORT=4000

ARG CERTSTREAM_GIT_COMMIT
RUN git init . \
    && git remote add origin https://github.com/CaliDog/certstream-server.git \
    && git fetch --depth 1 origin "${CERTSTREAM_GIT_COMMIT}" \
    && git checkout FETCH_HEAD

RUN mix local.hex --force && mix local.rebar --force \
    && mix do deps.get, deps.compile \
    && mix compile

EXPOSE 4000
CMD ["mix", "run", "--no-halt"]
