# Changelog

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
