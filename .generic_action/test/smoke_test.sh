#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEST_DIR
REPO_ROOT="$(cd "${TEST_DIR}/../.." && pwd)"
readonly REPO_ROOT
readonly CLI="${REPO_ROOT}/.generic_action/ci-bridge"
readonly TOML_FIXTURE="${TEST_DIR}/fixtures/toml_kv.py"

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal() {
  local expected="$1"
  local actual="$2"
  [[ "${actual}" == "${expected}" ]] || fail "expected '${expected}', got '${actual}'"
}

validate_output="$(CI_BRIDGE_TOML_COMMAND="${TOML_FIXTURE}" "${CLI}" validate)"
assert_equal 'ci-bridge: config valid' "${validate_output}"

run_output="$(CI_BRIDGE_TOML_COMMAND="${TOML_FIXTURE}" "${CLI}" run smoke)"
assert_equal $'generic: start (ci-bridge-demo)\nspecial: ci-bridge-demo\ngeneric: ok' "${run_output}"

if CI_BRIDGE_TOML_COMMAND="${TOML_FIXTURE}" "${CLI}" run unknown >/dev/null 2>&1; then
  fail 'unknown jobs must fail'
fi

printf 'PASS: ci-bridge smoke contract\n'
