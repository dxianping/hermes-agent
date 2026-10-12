# Install hermes-agent from the dxianping fork (feat/sep-2640).
#
#   irm https://raw.githubusercontent.com/dxianping/hermes-agent/installer/install.ps1 | iex
#
# Extra arguments are forwarded to the official installer, e.g.
#   irm .../install.ps1 | iex   (then)   ... -SkipSetup
$ErrorActionPreference = 'Stop'

$env:HERMES_REPO_URL = 'https://github.com/dxianping/hermes-agent.git'

Write-Host 'Hermes Agent - installing from github.com/dxianping/hermes-agent @ feat/sep-2640'

$installer = [scriptblock]::Create((Invoke-RestMethod 'https://hermes-agent.nousresearch.com/install.ps1'))
& $installer -Branch 'feat/sep-2640' @args
