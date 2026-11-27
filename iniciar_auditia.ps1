# ==============================================================================
# AuditIA Beta 0.2 - Script de Inicialização da Aplicação Web
# ==============================================================================
param(
    [int]$Porta = 5000
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $ScriptDir

# Localiza o executável do Python
$PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $PythonExe) {
    $Candidatos = @(
        "C:\Users\Mirella\AppData\Local\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:ProgramFiles\Python312\python.exe"
    )
    foreach ($c in $Candidatos) {
        if (Test-Path $c) {
            $PythonExe = $c
            break
        }
    }
}

if (-not $PythonExe) {
    Write-Error "Python não foi encontrado. Por favor, certifique-se de que o Python 3.12+ está instalado."
    exit 1
}

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "  AuditIA Beta 0.2 — Inicializando Servidor Web" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Diretório raiz : $ScriptDir"
Write-Host "Interpretador  : $PythonExe"
Write-Host "Porta HTTP     : $Porta"
Write-Host "Landing Page   : http://127.0.0.1:$Porta/" -ForegroundColor Green
Write-Host "Login          : http://127.0.0.1:$Porta/login (ou /entrar)" -ForegroundColor Green
Write-Host "----------------------------------------------------------"
Write-Host "Pressione Ctrl+C para encerrar o servidor a qualquer momento."
Write-Host "==========================================================" -ForegroundColor Cyan

$MvpPath = Join-Path $ScriptDir "mvp"
$AppPath = Join-Path $MvpPath "backend\app.py"

$env:AUDITIA_PORT = [string]$Porta
$env:PYTHONUTF8 = "1"
$env:PYTHONPATH = $MvpPath

& $PythonExe $AppPath $Porta
