# certstream-server (Reconhawx image)

Container build for [CaliDog/certstream-server](https://github.com/CaliDog/certstream-server): aggregates all logs from Google’s CT log list and exposes a WebSocket feed on port 4000.

**Versioning:** Image tag `1.6.0` matches upstream `mix.exs` app version and is **not** tied to `reconhawx` `APP_VERSION`. Upstream has no git tags; the source pin is commit SHA in [`third-party/certstream-server/VERSION`](../../third-party/certstream-server/VERSION). The image uses `elixir:1.8-alpine` (same as upstream’s Dockerfile) so the `easy_ssl` dependency compiles.

## Build

```bash
./build.sh ghcr.io/<owner>/reconhawx linux/amd64 1.6.0
```

Minikube:

```bash
./build.sh minikube linux/amd64
```

## Runtime

- WebSocket (no DER): `ws://certstream:4000/`
- Health: `GET http://certstream:4000/example.json`

`ct-monitor` consumes the stream via [certstream-python](https://github.com/CaliDog/certstream-python).
