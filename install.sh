#!/bin/sh
# Install hermes-agent from the dxianping fork (feat/sep-2640).
#
#   curl -fsSL https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.sh | bash
#
# Extra arguments are forwarded to the official installer, e.g.
#   curl -fsSL .../install.sh | bash -s -- --skip-setup
set -eu

HERMES_REPO_URL='https://github.com/dxianping/hermes-agent.git'
export HERMES_REPO_URL

echo 'Hermes Agent - installing from github.com/dxianping/hermes-agent @ feat/sep-2640'

curl -fsSL https://hermes-agent.nousresearch.com/install.sh \
  | bash -s -- --branch feat/sep-2640 "$@"
