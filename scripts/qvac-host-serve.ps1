# QVAC inference server on the Windows host (GPU via native Vulkan).
# Start after: npm install -g --prefix F:/pedro/tools/qvac-node @qvac/cli
# Logs: F:/pedro/tools/qvac-node/qvac-serve.log
# Stop:   Get-Process node | Where-Object { $_.Path -like '*qvac-node*' } | Stop-Process

$ErrorActionPreference = 'Stop'

$prefix = 'F:/pedro/tools/qvac-node'
$config = 'F:/pedro/SynapseCME/scripts/qvac.host.config.json'
$log    = "$prefix/qvac-serve.log"

$qvac = Join-Path $prefix 'qvac.cmd'
if (-not (Test-Path $qvac)) {
  # npm --prefix on Windows may drop the shim in a bin/ subdir
  $alt = Join-Path $prefix 'bin/qvac.cmd'
  if (Test-Path $alt) { $qvac = $alt } else { throw "qvac.cmd not found under $prefix" }
}

# Kill a previous host instance so the port is free
Get-Process node -ErrorAction SilentlyContinue |
  Where-Object { $_.Path -like '*qvac-node*' } |
  Stop-Process -Force -ErrorAction SilentlyContinue

# --allow-unauthenticated: the server only needs to be reachable from the
# Docker containers (host.docker.internal) and localhost, same trust domain
# as the in-Docker qvac node.
& $qvac serve --openai --no-default --allow-unauthenticated `
  -c $config --host 0.0.0.0 --port 11434 *>> $log
