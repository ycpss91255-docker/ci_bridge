#!/usr/bin/env bash
set -euo pipefail

config_file="${1:?config path is required}"
[[ -f "${config_file}" ]]

cat <<'EOF'
bridge	schema_version	1
smoke	generic_script	.generic_action/scripts/generic/smoke.sh
smoke	special_script	.generic_action/scripts/special/smoke.sh
smoke	message	ci-bridge-demo
EOF
