# Changelog

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
