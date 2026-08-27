# smoke-test.ps1 - E2E do @wiati/dfe-agent em scratch project (Sprint 14 Task F.2).
#
# Valida o fluxo canonico de consumo:
#   1. scratch project (sem Python, sem assets pre-instalados)
#   2. `dfe-agent install` copia agent + skill para .opencode/
#   3. `dfe-agent status` reporta versao + packageName
#
# @see PLAN_SPRINT14.md Task F.2

$ErrorActionPreference = "Continue"  # nao parar em warnings de npm (deprecation, audit)

$PKG_DIR = (Resolve-Path (Join-Path (Split-Path -Parent $MyInvocation.MyCommand.Path) "..\..\")).Path
$SCRATCH = Join-Path ([System.IO.Path]::GetTempPath()) ("dfe-agent-e2e-" + [Guid]::NewGuid().ToString("N").Substring(0,8))

Write-Host "[e2e] scratch: $SCRATCH"
Write-Host "[e2e] package root: $PKG_DIR"

New-Item -ItemType Directory -Path $SCRATCH -Force | Out-Null
Push-Location $SCRATCH

try {
    # scratch project
    Write-Host "[e2e] npm init -y"
    npm init -y 2>&1 | Out-Null

    # Empacota o pacote localmente
    Write-Host "[e2e] npm pack (local tarball)"
    Push-Location $PKG_DIR
    $TARBALL = npm pack --silent 2>&1 | Select-Object -Last 1
    Pop-Location
    $TARBALL_PATH = Join-Path $PKG_DIR $TARBALL
    if (-not (Test-Path -LiteralPath $TARBALL_PATH)) {
        throw "tarball nao foi gerado: $TARBALL_PATH"
    }

    # Instala o pacote local
    Write-Host "[e2e] npm install (local)"
    npm install $TARBALL_PATH 2>&1 | Out-Null

    # Install do agente
    Write-Host "[e2e] dfe-agent install"
    & npx --no-install dfe-agent install 2>&1 | Out-Null

    # Valida arquivos copiados
    Write-Host "[e2e] validando .opencode/"
    $agentMd = Join-Path $SCRATCH ".opencode\agent\dfe-agent.md"
    $skillMd = Join-Path $SCRATCH ".opencode\skills\dfe-fiscal\SKILL.md"
    if (-not (Test-Path -LiteralPath $agentMd)) {
        throw "FAIL: .opencode/agent/dfe-agent.md missing"
    }
    if (-not (Test-Path -LiteralPath $skillMd)) {
        throw "FAIL: .opencode/skills/dfe-fiscal/SKILL.md missing"
    }
    Write-Host "[e2e] .opencode/ OK"

    # Status
    Write-Host "[e2e] dfe-agent status"
    $STATUS_JSON = & npx --no-install dfe-agent status 2>&1 | Out-String
    $status = $STATUS_JSON | ConvertFrom-Json
    Write-Host "[e2e] status.version: $($status.version)"
    Write-Host "[e2e] status.packageName: $($status.packageName)"
    Write-Host "[e2e] status.basePath: $($status.basePath)"
    if (-not $status.version) { throw "FAIL: version ausente" }
    if ($status.packageName -ne "@wiati/dfe-agent") { throw "FAIL: packageName errado" }

    # Limpa tarball
    Remove-Item -LiteralPath $TARBALL_PATH -Force -ErrorAction SilentlyContinue

    Write-Host "[e2e] PASS"
} finally {
    Pop-Location
    Remove-Item -LiteralPath $SCRATCH -Recurse -Force -ErrorAction SilentlyContinue
}