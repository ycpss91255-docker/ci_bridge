# ci_bridge

A minimal proof of concept for running one CI definition on GitHub Actions and GitLab CI.

## Architecture

```text
ci.toml
   |
   v
.generic_action/ci-bridge
   |
   +-- scripts/generic/   shared pipeline behaviour
   +-- scripts/special/   repository-specific hooks
   |
   +-- .github/workflows/ci.yaml
   `-- .gitlab/pipeline.yml
```

The platform adapters only provide checkout and runner orchestration. Both call the same command:

```sh
.generic_action/ci-bridge run smoke
```

`ci-bridge` parses `ci.toml` with the pinned
`ghcr.io/ycpss91255-docker/toml-bridge:v0.1.0` image. The host contract is Docker and Bash.

## Validate locally

Run the fast contract test without Docker or network access:

```sh
.generic_action/test/smoke_test.sh
```

Run the real TOML parsing path:

```sh
.generic_action/ci-bridge validate
.generic_action/ci-bridge run smoke
```

Expected output:

```text
generic: start (ci-bridge-demo)
special: ci-bridge-demo
generic: ok
```

This demo intentionally supports one fixed `smoke` job. Pipeline generation, distribution to downstream repositories, cache, artifacts, and matrix execution are outside this first architecture check.
