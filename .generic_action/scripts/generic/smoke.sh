#!/usr/bin/env bash
set -euo pipefail

: "${CI_BRIDGE_MESSAGE:?CI_BRIDGE_MESSAGE is required}"
: "${CI_BRIDGE_SPECIAL_SCRIPT:?CI_BRIDGE_SPECIAL_SCRIPT is required}"

printf 'generic: start (%s)\n' "${CI_BRIDGE_MESSAGE}"
"${CI_BRIDGE_SPECIAL_SCRIPT}"
printf 'generic: ok\n'
