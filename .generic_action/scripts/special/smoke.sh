#!/usr/bin/env bash
set -euo pipefail

: "${CI_BRIDGE_MESSAGE:?CI_BRIDGE_MESSAGE is required}"
printf 'special: %s\n' "${CI_BRIDGE_MESSAGE}"
