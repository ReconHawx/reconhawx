# Changelog

## [0.36.0](https://github.com/ReconHawx/reconhawx/compare/v0.35.0...v0.36.0) (2026-05-16)


### Features

* **crawl_website:** fan out httpx across nodes after Katana discover ([db419c8](https://github.com/ReconHawx/reconhawx/commit/db419c8e962946d5081bc9a7f1acb073dffa61ab))

## [0.35.0](https://github.com/ReconHawx/reconhawx/compare/v0.34.0...v0.35.0) (2026-05-14)


### Features

* **crawl_website:** emit structured httpx probes and align runner parsing ([7383572](https://github.com/ReconHawx/reconhawx/commit/7383572ea5eebd4197079c3a2ed8b53ce35c3ac2))

## [0.34.0](https://github.com/ReconHawx/reconhawx/compare/v0.33.0...v0.34.0) (2026-05-12)


### ⚠ BREAKING CHANGES

* **migrations:** Upgrades after v014 must run v015 before relying on a DB that still has nuclei_findings or wpscan_findings; deploy migrations with the API.

### refactor

* **migrations:** drop legacy Nuclei and WPScan finding tables ([cf12629](https://github.com/ReconHawx/reconhawx/commit/cf1262929323d2a72bd70391079af2f4ff440927))


### Features

* **api:** publish external link events for new outbound associations ([424c340](https://github.com/ReconHawx/reconhawx/commit/424c340bbe7a78eb0b0632f82adab391740fbaf9))
* **dashboard:** add broken links to findings trend ([0c43363](https://github.com/ReconHawx/reconhawx/commit/0c43363306029a6a76601dad7cfaa2d878ddccc0))


### Bug Fixes

* **api:** serialize broken-link checked_at for JSONB details ([40a7ec4](https://github.com/ReconHawx/reconhawx/commit/40a7ec41984592e6b4c6d6c3a245baa9b47861b0))
* **migrations:** enable pgcrypto before unified findings backfill ([5a5d815](https://github.com/ReconHawx/reconhawx/commit/5a5d8156e488fb698788a9456cc50fbc2dfd6498))
* **worker:** only ingest broken social links from profile checks ([16e4df8](https://github.com/ReconHawx/reconhawx/commit/16e4df8b936ea1441b8e14df19f0b9db18553c2f))
* **worker:** pass integer katana connection timeout ([d3fbd4a](https://github.com/ReconHawx/reconhawx/commit/d3fbd4aa6f10291f0e6e9819115010fb32e3ef11))

## [0.33.0](https://github.com/ReconHawx/reconhawx/compare/v0.32.0...v0.33.0) (2026-05-11)


### ⚠ BREAKING CHANGES

* **frontend:** Deep links and bookmarks using /findings/typosquat, /findings/typosquat-urls*, and /findings/typosquat-screenshots no longer route to the typosquat UI (they fall through to the app default route).

### Features

* **frontend:** expose typosquat under Brand Protection with new URLs ([8b90260](https://github.com/ReconHawx/reconhawx/commit/8b902608fd5eacff2d210622eddd932c7b8f091a))

## [0.32.0](https://github.com/ReconHawx/reconhawx/compare/v0.31.0...v0.32.0) (2026-05-08)


### Features

* **api:** seed WordPress URL handler that triggers batched WPScan ([788ec0b](https://github.com/ReconHawx/reconhawx/commit/788ec0b3c95bebb747273b008e4e69ee300b6726))
* **dashboard:** show WPScan in trends, posture, and latest findings ([8f1e160](https://github.com/ReconHawx/reconhawx/commit/8f1e160ad8771dd26a41f9b5b489bdb95487bd7e))
* **event-handler:** add substring contains conditions for event handlers ([74c5f91](https://github.com/ReconHawx/reconhawx/commit/74c5f91fb32fb44dca7dee6f266275a16ad723df))


### Bug Fixes

* **worker:** avoid failing WPScan worker jobs on non-WordPress targets ([acd4fd6](https://github.com/ReconHawx/reconhawx/commit/acd4fd6f87ca7eed6ab643748eca47dd06c47965))

## [0.31.0](https://github.com/ReconHawx/reconhawx/compare/v0.30.0...v0.31.0) (2026-05-08)


### Features

* **frontend:** choose WPScan enumerate options with checkboxes ([3df74d2](https://github.com/ReconHawx/reconhawx/commit/3df74d2fd82c61898eb398c9ccc7fbc4b8ead5ac))
* **workflow:** configure nuclei scan options from the workflow builder ([28a3cf4](https://github.com/ReconHawx/reconhawx/commit/28a3cf4350f8972f5b1774a02700b14887a8bd3a))


### Bug Fixes

* **runner:** omit --enumerate when WPScan enumerate param is empty ([0b1ae8d](https://github.com/ReconHawx/reconhawx/commit/0b1ae8d2bdbb8f6cd32be96306e7249624eb331a))

## [0.30.0](https://github.com/ReconHawx/reconhawx/compare/v0.29.0...v0.30.0) (2026-05-06)


### Features

* **dashboard:** faster home dashboard with summary API and deep links ([d1be538](https://github.com/ReconHawx/reconhawx/commit/d1be538e982f7a9a3cab762dc1e485f67eb5563f))


### Bug Fixes

* **api:** report accurate website counts per technology ([a16af74](https://github.com/ReconHawx/reconhawx/commit/a16af7453b300d94a7aea7e2f3e61ad5b5930773))

## [0.29.0](https://github.com/ReconHawx/reconhawx/compare/v0.28.0...v0.29.0) (2026-05-03)


### Features

* **api:** store hostnames and URL hosts lowercase with DB backfill ([dddaf30](https://github.com/ReconHawx/reconhawx/commit/dddaf307eec35b46c1a808935fcfc9225832c44c))

## [0.28.0](https://github.com/ReconHawx/reconhawx/compare/v0.27.1...v0.28.0) (2026-05-03)


### Features

* **admin:** manage WAF timing and runner env from system settings ([8158623](https://github.com/ReconHawx/reconhawx/commit/8158623f05c1e50df4c3c38f43bedab1f45959e0))
* **admin:** show worker WAF block status per node in System Status ([4b73002](https://github.com/ReconHawx/reconhawx/commit/4b73002ec612095c754aba796df6fd90c8ef890c))

## [0.27.1](https://github.com/ReconHawx/reconhawx/compare/v0.27.0...v0.27.1) (2026-05-03)


### Bug Fixes

* restore default re-run delay ([72fd2fa](https://github.com/ReconHawx/reconhawx/commit/72fd2faf17872d25c42627c795793b435e60feb7))

## [0.27.0](https://github.com/ReconHawx/reconhawx/compare/v0.26.1...v0.27.0) (2026-05-03)


### Features

* **api,runner:** improve scheduled workflows and WAF rerun execution plumbing ([5d26bfd](https://github.com/ReconHawx/reconhawx/commit/5d26bfd4f418f1ccffff375c6cd931b5c049bcd4))
* **api:** add WAF auto-rerun schedules and workflow admin settings ([8f2f18f](https://github.com/ReconHawx/reconhawx/commit/8f2f18ffed637c2f760340720af641187fcc6ef3))
* **runner:** keep blocked target strings on WAF step status ([4c40f51](https://github.com/ReconHawx/reconhawx/commit/4c40f519cc543671ab859d47fd362ff879fee29b))
* **workflows:** show WAF quarantine outcomes on run detail and logs ([3a53a3f](https://github.com/ReconHawx/reconhawx/commit/3a53a3f1b1181d23323fd1fade31405ca98adcc5))


### Bug Fixes

* **api:** deduplicate queued WAF auto-rerun schedules ([ba40378](https://github.com/ReconHawx/reconhawx/commit/ba40378ce164d3726b8a9680cff7ff8c70a9c063))

## [0.26.1](https://github.com/ReconHawx/reconhawx/compare/v0.26.0...v0.26.1) (2026-05-02)


### Bug Fixes

* **runner:** avoid WAF precheck spawning Jobs for every node and target ([0908598](https://github.com/ReconHawx/reconhawx/commit/09085989110bd4b5158bbf53e29e5fec22ddc088))

## [0.26.0](https://github.com/ReconHawx/reconhawx/compare/v0.25.0...v0.26.0) (2026-05-02)


### Features

* **api:** run in-cluster upgrade jobs with target release upgrader image ([e2e5405](https://github.com/ReconHawx/reconhawx/commit/e2e5405ad29438e32c1483a957da97dc42b6c293))

## [0.25.0](https://github.com/ReconHawx/reconhawx/compare/v0.24.5...v0.25.0) (2026-05-01)


### Features

* **runner:** quarantine nodes when WAF blocks target egress ([22f159e](https://github.com/ReconHawx/reconhawx/commit/22f159e655fae9c98ca76655c33096910f98e74c))

## [0.24.5](https://github.com/ReconHawx/reconhawx/compare/v0.24.4...v0.24.5) (2026-05-01)


### Bug Fixes

* **runner:** restore typosquat ingest for scheduled gather API findings jobs ([e8bce32](https://github.com/ReconHawx/reconhawx/commit/e8bce32748f6ffe371bf63719a322197ac042bfa))

## [0.24.4](https://github.com/ReconHawx/reconhawx/compare/v0.24.3...v0.24.4) (2026-04-29)


### Bug Fixes

* **frontend:** make technologies tech filter usable while typing ([be7aa0a](https://github.com/ReconHawx/reconhawx/commit/be7aa0a8d9a35b8cdfa9a807b882e5b5d6a5cc25))
* **frontend:** show URL schemes from stored asset data ([f69aea7](https://github.com/ReconHawx/reconhawx/commit/f69aea7169cb58c184111fb695abb44d5d6acb79))
* **runner:** quote worker shell commands safely for kubectl Jobs ([174f76b](https://github.com/ReconHawx/reconhawx/commit/174f76bffa9c64247bdbe2ea4436d30da0b0118a))

## [0.24.3](https://github.com/ReconHawx/reconhawx/compare/v0.24.2...v0.24.3) (2026-04-28)


### Bug Fixes

* **upgrader:** removed observability leftover ([72dfba7](https://github.com/ReconHawx/reconhawx/commit/72dfba7612cc8b073598db77b2ffc022d3a8a27c))

## [0.24.2](https://github.com/ReconHawx/reconhawx/compare/v0.24.1...v0.24.2) (2026-04-28)


### Bug Fixes

* **k8s:** removed observability stack (make cluster unstable)
* **worker:** keep task commands from stalling when subprocesses log heavily ([d80396d](https://github.com/ReconHawx/reconhawx/commit/d80396d3c4be667f66baf9a0cc9cd89f9ca5b635))

## [0.24.1](https://github.com/ReconHawx/reconhawx/compare/v0.24.0...v0.24.1) (2026-04-25)


### Bug Fixes

* **api:** added a node_selector to upgrade jobs ([01e4fad](https://github.com/ReconHawx/reconhawx/commit/01e4fad58950bcc4ef7dc7a6b4132a118162286d))

## [0.24.0](https://github.com/ReconHawx/reconhawx/compare/v0.23.2...v0.24.0) (2026-04-25)


### Features

* **k8s:** always refresh observability on in-cluster system upgrade ([7bbc60d](https://github.com/ReconHawx/reconhawx/commit/7bbc60d12be6f780edf0e18b5690088795665d98))

## [0.23.2](https://github.com/ReconHawx/reconhawx/compare/v0.23.1...v0.23.2) (2026-04-25)


### Bug Fixes

* **k8s:** keep monitoring namespace manifest inside base-update ([cbddee1](https://github.com/ReconHawx/reconhawx/commit/cbddee12ef19e2eae3dee96edc3df091c0a5b9aa))

## [0.23.1](https://github.com/ReconHawx/reconhawx/compare/v0.23.0...v0.23.1) (2026-04-25)


### Bug Fixes

* **k8s:** allow in-cluster upgrades to apply observability RBAC ([af654fa](https://github.com/ReconHawx/reconhawx/commit/af654facc2c04803af8d01c748c9fa62336cb5bb))

## [0.23.0](https://github.com/ReconHawx/reconhawx/compare/v0.22.1...v0.23.0) (2026-04-25)


### Features

* **k8s:** add Helm observability stack and install-time wiring ([e8c9cd5](https://github.com/ReconHawx/reconhawx/commit/e8c9cd5abfe60e79ff548cbd7281985e3db7a367))
* **observability:** add Grafana log dashboards for API, frontend, and services ([c4ae485](https://github.com/ReconHawx/reconhawx/commit/c4ae485936d681429d6d0bd0a8e05fde8084e70c))
* **observability:** ship JSON logs to Loki with consistent fields across services ([a10483e](https://github.com/ReconHawx/reconhawx/commit/a10483e632edd3b9531ce0065868768a11d1d430))
* **upgrader:** refresh observability from upgrade jobs and link Grafana Explore ([3d34e4d](https://github.com/ReconHawx/reconhawx/commit/3d34e4d17b7933fbd546bb2203de2b77f8778cf0))


### Bug Fixes

* **api:** validate scheduled job program fields on the raw request model ([f1a27c7](https://github.com/ReconHawx/reconhawx/commit/f1a27c7a1bc4f6105364516be1ac467493ce72ea))
* **worker:** fixed go version for gowitness ([724105c](https://github.com/ReconHawx/reconhawx/commit/724105caa304788d7905f6b87380e96711d93721))

## [0.22.1](https://github.com/ReconHawx/reconhawx/compare/v0.22.0...v0.22.1) (2026-04-23)


### Bug Fixes

* **runner:** restore PhishLabs batch typosquat updates with program_id ([04a72e3](https://github.com/ReconHawx/reconhawx/commit/04a72e35bf71892a250bf33322e25277f6ca29ea))

## [0.22.0](https://github.com/ReconHawx/reconhawx/compare/v0.21.0...v0.22.0) (2026-04-21)


### Features

* **frontend:** bulk stop workflows and page size on status monitor ([e3dec71](https://github.com/ReconHawx/reconhawx/commit/e3dec71ab686d013722ca0c9b9b15bf46a7ba55b))

## [0.21.0](https://github.com/ReconHawx/reconhawx/compare/v0.20.0...v0.21.0) (2026-04-21)


### Features

* **event-handler:** multi-type handlers with per-type conditions ([b4964c3](https://github.com/ReconHawx/reconhawx/commit/b4964c3e7644e1c216d77ca233dd6b58e2882746))

## [0.20.0](https://github.com/ReconHawx/reconhawx/compare/v0.19.0...v0.20.0) (2026-04-20)


### Features

* **admin:** add in-cluster Kubernetes upgrade from the admin UI ([7c54fcb](https://github.com/ReconHawx/reconhawx/commit/7c54fcbfab8a9f9b94870f8d9df2d44fdc40e4b1))

## [0.19.0](https://github.com/ReconHawx/reconhawx/compare/v0.18.0...v0.19.0) (2026-04-20)


### Features

* **programs:** allow renaming an existing program ([7529584](https://github.com/ReconHawx/reconhawx/commit/7529584f0dacc0f44c25c31b607fde817ba3df77))


### Bug Fixes

* **workflows:** allow long program names in Kubernetes workflow and worker jobs ([6975c81](https://github.com/ReconHawx/reconhawx/commit/6975c81d7aa6ad4e9e0807af946db905902a7099))

## [0.18.0](https://github.com/ReconHawx/reconhawx/compare/v0.17.0...v0.18.0) (2026-04-20)


### Features

* **frontend:** add dashboard refresh and recent asset snapshots ([c42788a](https://github.com/ReconHawx/reconhawx/commit/c42788a31a6e803f7f0963a9bac53338dafc8ee0))


### Bug Fixes

* **api:** import YesWeHack programs with structured hostname scope ([ba47bf3](https://github.com/ReconHawx/reconhawx/commit/ba47bf30b6baade593b2318903c99bdb13a6f52d))
* **api:** keep HackerOne out-of-scope URL assets when not bounty-eligible ([43ad551](https://github.com/ReconHawx/reconhawx/commit/43ad5518e6af90a19a1fb213447686ba911f3f89))
* **frontend:** raise workflow sidebar overlays above the status bar ([0a96fca](https://github.com/ReconHawx/reconhawx/commit/0a96fcaa7c01272dab548db22b88c5b2cd60e8bc))

## [0.17.0](https://github.com/ReconHawx/reconhawx/compare/v0.16.1...v0.17.0) (2026-04-17)


### Features

* **frontend:** hide deprecated scheduled-job types and warn on legacy entries ([d2578f9](https://github.com/ReconHawx/reconhawx/commit/d2578f95629d8009fdfc024f7476e6fe5ec7e8cc))
* **programs:** reject invalid scope patterns on write and surface them in the editor ([16bce42](https://github.com/ReconHawx/reconhawx/commit/16bce42958a822d58973d3cd067859004010ef63))
* **runner:** drop malformed task inputs and report drops on step status ([44ccce0](https://github.com/ReconHawx/reconhawx/commit/44ccce0ca32241f56bf37ff5b6e316a354c5fee1))
* **runner:** unify recon task input and output types across stack ([ee37603](https://github.com/ReconHawx/reconhawx/commit/ee37603899e7a2ff8c05c3fe526ea8525759d3e7))


### Bug Fixes

* **frontend:** restore workflow handle colors by input and output type ([7fc96f2](https://github.com/ReconHawx/reconhawx/commit/7fc96f2f0821816f7c7409d2208b3fe91897eb91))
* **programs:** streamline program creation and continue setup in detail view ([05cae76](https://github.com/ReconHawx/reconhawx/commit/05cae76b6ee3ecd13faf6c610a20cd445b6037e4))

## [0.16.1](https://github.com/ReconHawx/reconhawx/compare/v0.16.0...v0.16.1) (2026-04-13)


### Bug Fixes

* **api:** assign whitelist auto-dismissals to the editor who added the apex ([d65aa07](https://github.com/ReconHawx/reconhawx/commit/d65aa07ef997ff3329b7c2e51bf9729bf311a0ff))

## [0.16.0](https://github.com/ReconHawx/reconhawx/compare/v0.15.0...v0.16.0) (2026-04-13)


### Features

* **programs:** structured scope domains and workflow scope targets ([760ebc6](https://github.com/ReconHawx/reconhawx/commit/760ebc62e6098d8103f05e02387e77ebbc9a4bdc))
* **typosquat:** whitelist apex domains and auto-dismiss matching findings ([e657d6c](https://github.com/ReconHawx/reconhawx/commit/e657d6c589002f2e1cc033cd7191aaa012591949))


### Bug Fixes

* **frontend:** align Bootstrap body text utilities with theme colors ([333fd4c](https://github.com/ReconHawx/reconhawx/commit/333fd4caffa69460bafbde250e4bbe27e18a61c8))

## [0.15.0](https://github.com/ReconHawx/reconhawx/compare/v0.14.0...v0.15.0) (2026-04-11)


### Features

* **k8s:** add Headlamp dashboard at /headlamp behind the frontend ([9cc807d](https://github.com/ReconHawx/reconhawx/commit/9cc807dbd712a645240c10cddeaa156e7400ecdc))


### Bug Fixes

* **api:** fix slow bulk asset ingestion with chunked PostgreSQL upserts ([a848293](https://github.com/ReconHawx/reconhawx/commit/a848293dc85dc4708c6a16e9f412fe88d8478d21))

## [0.14.0](https://github.com/ReconHawx/reconhawx/compare/v0.13.1...v0.14.0) (2026-04-11)


### Features

* **admin:** flush Kueue workloads from system maintenance ([f6989b9](https://github.com/ReconHawx/reconhawx/commit/f6989b9ad2ed54a26335f7dfea2fdbf7361ebfc7))
* **admin:** pause event-handler and flush or discard Redis batches from event queue ([ecf9fca](https://github.com/ReconHawx/reconhawx/commit/ecf9fca91a37a2da55baa983b98257bc69cdcbdd))


### Bug Fixes

* **k8s:** fixed incompatible schema on postgres:15 ([3735d39](https://github.com/ReconHawx/reconhawx/commit/3735d39d762b2ed49aa43d1af94126460d2d9299))

## [0.13.1](https://github.com/ReconHawx/reconhawx/compare/v0.13.0...v0.13.1) (2026-04-10)


### Bug Fixes

* **api:** stop unified bulk asset processing from freezing the API ([b26483c](https://github.com/ReconHawx/reconhawx/commit/b26483cdc964bbe1ea4accb9023db90b92ff0dd7))
* **runner:** stop progressive asset merges from stalling batch completion ([3d5b9bb](https://github.com/ReconHawx/reconhawx/commit/3d5b9bb76064e4b019d1c429c99d72732865a6e2))

## [0.13.0](https://github.com/ReconHawx/reconhawx/compare/v0.12.2...v0.13.0) (2026-04-09)


### ⚠ BREAKING CHANGES

* **runner:** The runner no longer falls back to offline defaults if the manifest cannot be loaded; the Data API must be reachable at workflow start.

### Features

* **admin:** YAML recon task defaults and flexible last-run cooldown ([f690b96](https://github.com/ReconHawx/reconhawx/commit/f690b96cbd0beda4ee2c69d98a9396caac03edc6))
* **frontend:** show pinned footer with version and GitHub update hint ([f2ff136](https://github.com/ReconHawx/reconhawx/commit/f2ff136be6430ff4bc0e1d21f65fe66e777d6b27))
* **migrations:** run schema changes with Alembic and stamped baselines ([3246bf9](https://github.com/ReconHawx/reconhawx/commit/3246bf9cbc020bc1b8f4e8e10e1b45951f1c8fc4))
* **runner:** bootstrap recon task parameters from API manifest ([621a870](https://github.com/ReconHawx/reconhawx/commit/621a870f96e2a11e0f067490b0cca5dc67370f5d))


### Bug Fixes

* **runner:** respect ips_per_worker and timeout for CIDR child jobs ([4e48208](https://github.com/ReconHawx/reconhawx/commit/4e4820885fe020b6033dc2d8dcb95749c307b20b))

## [0.12.2](https://github.com/ReconHawx/reconhawx/compare/v0.12.1...v0.12.2) (2026-04-08)


### Bug Fixes

* **runner:** run port scan heredoc correctly under single-quoted job commands ([3e471ae](https://github.com/ReconHawx/reconhawx/commit/3e471ae81345f21e645a4e6f763617087f054c8d))

## [0.12.1](https://github.com/ReconHawx/reconhawx/compare/v0.12.0...v0.12.1) (2026-04-08)


### Bug Fixes

* **migrations:** make V0.0.4 idempotent for schema.sql bootstrap ([bd8986d](https://github.com/ReconHawx/reconhawx/commit/bd8986dca32a09b6a26b78a414c9237516e118f6))

## [0.12.0](https://github.com/ReconHawx/reconhawx/compare/v0.11.0...v0.12.0) (2026-04-07)


### Features

* **admin:** structured runner/worker images with APP_VERSION tag mode ([77a525a](https://github.com/ReconHawx/reconhawx/commit/77a525a7a85cb1ad104fd9f49ca02510b6b7d54d))
* **auth:** harden password change and admin reset options ([ea61186](https://github.com/ReconHawx/reconhawx/commit/ea6118654dc316445b37f76fcc2c63689f1ba099))
* **frontend:** tab admin areas into status, settings, and workflow monitors ([c72749f](https://github.com/ReconHawx/reconhawx/commit/c72749f6247d0b10dbe4ab7c406513680b86036e))
* **scheduled-jobs:** multi-program workflow schedules with program_ids ([65aa322](https://github.com/ReconHawx/reconhawx/commit/65aa32249e70cdb2280ac7dd092399c5602d2755))
* **scheduled-jobs:** show workflow name with id on job detail ([ea09e52](https://github.com/ReconHawx/reconhawx/commit/ea09e5286b0c4e4a0fe2fe7a1fdcef916b10876c))


### Bug Fixes

* **scheduled-jobs:** repair scheduled job edit form loading and workflow picker ([500f321](https://github.com/ReconHawx/reconhawx/commit/500f321d2cb0db2692a8b38e1b9af156eb39250d))

## [0.11.0](https://github.com/ReconHawx/reconhawx/compare/v0.10.0...v0.11.0) (2026-04-07)


### Features

* **admin:** Ollama model dropdown and draft URL listing in AI settings ([f740bb1](https://github.com/ReconHawx/reconhawx/commit/f740bb16b3fb3680aa14370eb15fbf6cda33cbc5))

## [0.10.0](https://github.com/ReconHawx/reconhawx/compare/v0.9.0...v0.10.0) (2026-04-06)


### Features

* **admin:** store workflow runner images in system settings ([0583e59](https://github.com/ReconHawx/reconhawx/commit/0583e59f88a24aa478f9be938ea9d2c2ff426f31))
* **k8s:** run postgres as statefulset and add upgrade pre-apply hooks ([cb77b98](https://github.com/ReconHawx/reconhawx/commit/cb77b989dd7fe6cdc5c323e61985d23547f78cf8))

## [0.9.0](https://github.com/ReconHawx/reconhawx/compare/v0.8.0...v0.9.0) (2026-04-04)


### Features

* **admin:** store Ollama connection in AI system settings ([0b1d901](https://github.com/ReconHawx/reconhawx/commit/0b1d901f4b27ea87171610968fc5f8912f809beb))
* **k8s:** improve cluster and minikube installers ([0c46b89](https://github.com/ReconHawx/reconhawx/commit/0c46b898cf9cd36b644cccb25c33befde5d9d1f5))


### Bug Fixes

* **frontend:** improve dark mode borders and heading contrast ([abed02f](https://github.com/ReconHawx/reconhawx/commit/abed02f38416b6098596f3409608f29b375b9416))

## [0.8.0](https://github.com/ReconHawx/reconhawx/compare/v0.7.0...v0.8.0) (2026-04-02)


### Features

* **admin:** add system maintenance with Kueue hold and Job-based restore ([6bd3c50](https://github.com/ReconHawx/reconhawx/commit/6bd3c50b05f03453ba10fab6a69bb6b654f09bab))
* **k8s:** pin images to release semver and add in-cluster upgrade path ([e816070](https://github.com/ReconHawx/reconhawx/commit/e8160700a17c3238054b4c1d3504bb93b61e636e))
* persist closure history and last-closure discovery ([4a93e90](https://github.com/ReconHawx/reconhawx/commit/4a93e90ceab1727f8133b288285d8fbbab4ad5ae))

## [0.7.0](https://github.com/ReconHawx/reconhawx/compare/v0.6.0...v0.7.0) (2026-04-02)


### Features

* **kubernetes:** add wait-for-postgresql init container to ensure DB readiness before migrations ([29bc1ea](https://github.com/ReconHawx/reconhawx/commit/29bc1ea7782a6ff9cc1adcaa9d3ef19dbec6e485))

## [0.6.0](https://github.com/ReconHawx/reconhawx/compare/v0.5.0...v0.6.0) (2026-04-02)


### Features

* **api:** force password change on next login ([d421c7a](https://github.com/ReconHawx/reconhawx/commit/d421c7aecca105d4363f7f62162086fa1984bb77))

## [0.5.0](https://github.com/ReconHawx/reconhawx/compare/v0.4.2...v0.5.0) (2026-04-01)



## [0.4.2](https://github.com/ReconHawx/reconhawx/compare/v0.4.1...v0.4.2) (2026-04-01)


### Bug Fixes

* fixed AI analysis context handling to merge system and program AI settings for improved prompt generation ([1a8235d](https://github.com/ReconHawx/reconhawx/commit/1a8235dadf359c3551aaddd3557a95645e4d3ff0))
* fixed typosquat screenshot text extraction by adding missing dependencies ([3fb9956](https://github.com/ReconHawx/reconhawx/commit/3fb99569d75fd1d9fcb74b96e8f23ca41eac9f4b))
* implement ConfigMap owner reference patching to ensure proper garbage collection with Batch Jobs ([a8d26cf](https://github.com/ReconHawx/reconhawx/commit/a8d26cfa74aa2ff0d45f3f98343e9e850070a247))

## [0.4.1](https://github.com/ReconHawx/reconhawx/compare/v0.4.0...v0.4.1) (2026-03-31)


### Bug Fixes

* restore APP_VERSION environment variable in Dockerfile for consistency ([9fc7052](https://github.com/ReconHawx/reconhawx/commit/9fc705204a87d5163924f8fba2078b25ff6be298))

## [0.4.0](https://github.com/ReconHawx/reconhawx/compare/v0.3.2...v0.4.0) (2026-03-31)


### Features

* add admin system status page with per-service version tracking ([4c1b34d](https://github.com/ReconHawx/reconhawx/commit/4c1b34de1065121b6e8e6ce44443b2270448fdf2))
* add AI analysis batch processing for selected findings with superuser/admin requirement ([4d0e8db](https://github.com/ReconHawx/reconhawx/commit/4d0e8dbff90a0e86465fba60627be719d4c838ef))

## [0.3.2](https://github.com/ReconHawx/reconhawx/compare/v0.3.1...v0.3.2) (2026-03-31)


### Bug Fixes

* fixed npm audit findings ([366b735](https://github.com/ReconHawx/reconhawx/commit/366b735a7e4fd508032f2d28fe2094c068c779c5))

## [0.3.1](https://github.com/ReconHawx/reconhawx/compare/v0.3.0...v0.3.1) (2026-03-31)


### Bug Fixes

* **api:** Fixed node selector for workflow jobs ([0a55c43](https://github.com/ReconHawx/reconhawx/commit/0a55c43ff7a8dbacc99309a61e6c93b2825eb66c))
* Fixed node selectors in kueue flavor ([90cb08f](https://github.com/ReconHawx/reconhawx/commit/90cb08f194ddc16b48aee8e0e79fd19d0d79d270))

## [0.3.0](https://github.com/ReconHawx/reconhawx/compare/v0.2.0...v0.3.0) (2026-03-30)


### Features

* **api:** PhishLabs sync takedown, unified UI, action_taken ([0066072](https://github.com/ReconHawx/reconhawx/commit/0066072682a01c1b08fcfc7a359cdbaf415c34d6))
* **frontend:** improve Typosquat Findings filter panel layout ([df11f40](https://github.com/ReconHawx/reconhawx/commit/df11f400b87cb43ebaddf0fc7089561535c84622))


### Bug Fixes

* container images repository ([3454796](https://github.com/ReconHawx/reconhawx/commit/345479631042183e47224e93c6e1c61a18de4a6f))

## [0.2.0](https://github.com/ReconHawx/reconhawx/compare/v0.1.1...v0.2.0) (2026-03-30)


### Features

* add date range filters for created_at and updated_at in TyposquatFindings component ([9c621cf](https://github.com/ReconHawx/reconhawx/commit/9c621cfa034dcfe8692f72b7fe998e8621da3d8b))
* **api:** PhishLabs sync takedown, unified UI, action_taken ([0066072](https://github.com/ReconHawx/reconhawx/commit/0066072682a01c1b08fcfc7a359cdbaf415c34d6))
* **frontend:** improve Typosquat Findings filter panel layout ([df11f40](https://github.com/ReconHawx/reconhawx/commit/df11f400b87cb43ebaddf0fc7089561535c84622))

## [0.1.1](https://github.com/ReconHawx/reconhawx/compare/v0.1.0...v0.1.1) (2026-03-30)


### Bug Fixes

* container images repository ([3454796](https://github.com/ReconHawx/reconhawx/commit/345479631042183e47224e93c6e1c61a18de4a6f))
