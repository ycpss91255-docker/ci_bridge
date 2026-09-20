#!/usr/bin/env bash
set -euo pipefail

[[ "${CI_BRIDGE_ACTION_ID:-}" == 'test' ]] || {
  printf 'downstream-test: expected CI_BRIDGE_ACTION_ID=test\n' >&2
  exit 1
}

printf 'downstream-test: ok\n'
