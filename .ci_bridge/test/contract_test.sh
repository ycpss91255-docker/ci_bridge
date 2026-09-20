#!/usr/bin/env bash
set -euo pipefail

TEST_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly TEST_DIR
REPO_ROOT="$(cd "${TEST_DIR}/../.." && pwd)"
readonly REPO_ROOT
readonly CLI="${REPO_ROOT}/.ci_bridge/ci-bridge"

python3 -m unittest discover -s "${TEST_DIR}" -p 'test_*.py'

fail() {
  printf 'FAIL: %s\n' "$*" >&2
  exit 1
}

assert_equal() {
  local expected="$1"
  local actual="$2"
  [[ "${actual}" == "${expected}" ]] || fail "expected '${expected}', got '${actual}'"
}

validate_output="$("${CLI}" validate)"
assert_equal 'ci-bridge: config valid' "${validate_output}"

catalog_output="$("${CLI}" catalog)"
assert_equal $'test\t.ci_action/catalog/test.toml' "${catalog_output}"

plan_output="$("${CLI}" plan ci)"
assert_equal $'test\ttest/run.sh' "${plan_output}"

run_output="$("${CLI}" pipeline ci)"
assert_equal $'ci-bridge: running test (test/run.sh)\ndownstream-test: ok' "${run_output}"

if "${CLI}" run unknown >/dev/null 2>&1; then
  fail 'unknown actions must fail'
fi

printf 'PASS: managed catalog and downstream selection contract\n'
