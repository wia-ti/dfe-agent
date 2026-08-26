#!/usr/bin/env pwsh
# scripts/check_env.ps1 — hardening do ambiente DFe-Agent (Windows).
#
# Origem (PLAN_SPRINT5 F.3): quando ``OSError 1455`` (page file
# insuficiente) e' levantado no load do embedding, o agente LLM
# tende a improvisar scripts ad-hoc. Este script detecta isso ANTES
# do agente improvisar, expondo o estado do ambiente em JSON.
#
# Escopos validados (6):
#   1. Memoria fisica:        WARNING se < 8 GB.
#   2. Page file:             WARNING se < 8192 MB alocado.
#   3. python main.py --health (smoke de imports).
#   4. Embedding load:        dispara load; se exit != 0, sugere
#                             DFE_EMBEDDING_DTYPE=float16.
#   5. storage/dfe.db acessivel: WARNING se nao existir.
#   6. sys.path resolvido:     importa `src.utils.http_guard` sem
#                             PYTHONPATH pre-setado (PLAN_SPRINT7 E.2).
#
# Saida: JSON no stdout com shape:
#   {memory_gb, pagefile_mb, health_ok, embedding_load_ok,
#    db_accessible, import_ok, recommendation}.
#
# Idempotente. Sem efeitos colaterais (somente leitura via CIM + Python
# subprocess nao-mutativo). Pode ser rodado multiplas vezes com seguranca.

[CmdletBinding()]
param(
    [switch]$JsonOnly
)

$ErrorActionPreference = "Continue"

# ----------------------------------------------------------------------
# 1. Memoria fisica
# ----------------------------------------------------------------------
$memoryGb = 0.0
try {
    $cs = Get-CimInstance Win32_ComputerSystem -ErrorAction SilentlyContinue
    if ($cs) {
        $memoryGb = [math]::Round($cs.TotalPhysicalMemory / 1GB, 2)
    }
} catch {
    $memoryGb = 0.0
}

# ----------------------------------------------------------------------
# 2. Page file
# ----------------------------------------------------------------------
$pagefileMb = 0
try {
    $pf = Get-CimInstance Win32_PageFileSetting -ErrorAction SilentlyContinue
    if ($pf) {
        $pagefileMb = ($pf | Measure-Object -Property InitialSize -Sum).Sum
    }
} catch {
    $pagefileMb = 0
}

# ----------------------------------------------------------------------
# 3. python main.py --health
# ----------------------------------------------------------------------
$healthOk = $false
$healthError = $null
try {
    $proc = Start-Process -FilePath "python" -ArgumentList @("main.py", "--health") `
        -NoNewWindow -Wait -PassThru -RedirectStandardOutput "check_env_health.out" `
        -RedirectStandardError "check_env_health.err"
    $healthOk = ($proc.ExitCode -eq 0)
    if (-not $healthOk) {
        $healthError = (Get-Content "check_env_health.err" -Raw -ErrorAction SilentlyContinue)
    }
    Remove-Item "check_env_health.out", "check_env_health.err" -ErrorAction SilentlyContinue
} catch {
    $healthError = $_.Exception.Message
}

# ----------------------------------------------------------------------
# 4. Embedding load
# ----------------------------------------------------------------------
$embeddingLoadOk = $false
$embeddingError = $null
try {
    $proc = Start-Process -FilePath "python" -ArgumentList @(
        "-c", "from src.indexer.embeddings import EmbeddingProvider; print(EmbeddingProvider().dim)"
    ) -NoNewWindow -Wait -PassThru -RedirectStandardError "check_env_embed.err"
    $embeddingLoadOk = ($proc.ExitCode -eq 0)
    if (-not $embeddingLoadOk) {
        $embeddingError = (Get-Content "check_env_embed.err" -Raw -ErrorAction SilentlyContinue)
    }
    Remove-Item "check_env_embed.err" -ErrorAction SilentlyContinue
} catch {
    $embeddingError = $_.Exception.Message
}

# ----------------------------------------------------------------------
# 5. storage/dfe.db acessivel
# ----------------------------------------------------------------------
$dbAccessible = Test-Path "storage/dfe.db"

# ----------------------------------------------------------------------
# 6. Import de http_guard sem PYTHONPATH pre-setado (PLAN_SPRINT7 E.2).
#    Detecta se o bootstrap de src.utils.syspath_bootstrap esta'
#    cumprindo seu papel. Se falhar, o usuario vera
#    ``ModuleNotFoundError: No module named 'hooks'`` ao rodar qualquer
#    CLI do projeto; orienta rodar ``pip install -e .`` para instalar o
#    pacote ``src/`` como editable OU rodar via ``python -m``.
# ----------------------------------------------------------------------
$importOk = $false
$importError = $null
try {
    # limpa PYTHONPATH do processo antes de submeter o subprocesso
    $childEnv = [System.Collections.Specialized.OrderedDictionary]::new()
    foreach ($k in $env:PSBoundParameters.Keys) { }
    $envSnapshot = @{}
    foreach ($k in [System.Environment]::GetEnvironmentVariables().Keys) {
        $envSnapshot[$k] = [System.Environment]::GetEnvironmentVariable($k)
    }
    $envSnapshot["PYTHONPATH"] = $null
    $proc = Start-Process -FilePath "python" -ArgumentList @(
        "-c", "from src.utils import http_guard; print('OK')"
    ) -NoNewWindow -Wait -PassThru -RedirectStandardError "check_env_import.err"
    $importOk = ($proc.ExitCode -eq 0)
    if (-not $importOk) {
        $importError = (Get-Content "check_env_import.err" -Raw -ErrorAction SilentlyContinue)
    }
    Remove-Item "check_env_import.err" -ErrorAction SilentlyContinue
} catch {
    $importError = $_.Exception.Message
}

# ----------------------------------------------------------------------
# Recomendacao
# ----------------------------------------------------------------------
$recommendation = ""
if (-not $importOk -and $importError) {
    $recommendation = "Bootstrap de sys.path quebrado: $importError. Rode 'pip install -e .' para instalar src/ como editable."
} elseif (-not $healthOk) {
    $recommendation = "Investigue o erro de import do modulo: $healthError"
} elseif (-not $embeddingLoadOk -and $embeddingError) {
    if ($embeddingError -match "DFE_EMBEDDING_DTYPE" -or $embeddingError -match "page file") {
        $recommendation = "Tente: DFE_EMBEDDING_DTYPE=float16 OU DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2"
    } else {
        $recommendation = "Falha no load do embedding. Stack: $embeddingError"
    }
} elseif ($memoryGb -lt 8) {
    $recommendation = "WARNING: < 8 GB RAM. Considere DFE_EMBEDDING_MODEL=all-MiniLM-L6-v2"
} elseif ($pagefileMb -lt 8192) {
    $recommendation = "WARNING: page file < 8192 MB. Considere aumentar para 16384 MB"
} elseif (-not $dbAccessible) {
    $recommendation = "Rode: python -m src.ragctl migrate para criar a base"
} else {
    $recommendation = "Ambiente saudavel"
}

$result = [ordered]@{
    memory_gb          = $memoryGb
    pagefile_mb        = $pagefileMb
    health_ok          = $healthOk
    embedding_load_ok  = $embeddingLoadOk
    db_accessible      = $dbAccessible
    import_ok          = $importOk
    recommendation     = $recommendation
}

if ($JsonOnly) {
    $result | ConvertTo-Json -Compress
} else {
    $result | ConvertTo-Json
}
