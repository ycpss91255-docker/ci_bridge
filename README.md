# ci_bridge

A minimal proof of concept for running one validated task plan locally, in
GitHub Actions, and in GitLab CI.

## Architecture

```text
.ci_bridge/                    managed resolver and executor
.ci_action/catalog/*.toml      managed approved action catalog
.github/                       managed GitHub adapter
.gitlab/                       managed GitLab adapter
ci-project.toml                downstream task selection and script bindings
test/, scripts/, src/          downstream-owned, locally runnable content
```

The action catalog is auto-discovered. File order has no task semantics; action
IDs must be unique. `ci-project.toml` selects approved actions, and the bridge
validates the complete resolved plan before executing its first task.

Both platform adapters call the same command:

```sh
.ci_bridge/ci-bridge pipeline ci
```

The bridge uses the pinned
`ghcr.io/ycpss91255-docker/toml-bridge:v0.1.0` image as its Python/TOML runtime.
The host contract is Docker and Bash. The GitLab adapter provisions Docker CLI
and Docker-in-Docker; its runner must allow privileged services.

## Commands

```sh
.ci_bridge/ci-bridge validate
.ci_bridge/ci-bridge catalog
.ci_bridge/ci-bridge plan ci
.ci_bridge/ci-bridge run test
.ci_bridge/ci-bridge pipeline ci
```

Expected pipeline output:

```text
ci-bridge: running test (test/run.sh)
downstream-test: ok
```

Run the fast contract test with Python 3.11+ and no Docker/network access:

```sh
.ci_bridge/test/contract_test.sh
```

This demo intentionally supports one sequential `ci` pipeline. Parallel DAG
execution, matrix expansion, distribution to downstream repositories, cache,
artifacts, and result normalization remain outside this first architecture
check.
