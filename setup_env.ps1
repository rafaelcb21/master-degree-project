# Permite a execução de scripts apenas na sessão atual do terminal
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process -Force

$VENV_DIR = ".venv"

# 1. Cria o ambiente virtual se não existir
if (-not (Test-Path $VENV_DIR)) {
    Write-Host "Criando o ambiente virtual ($VENV_DIR)..." -ForegroundColor Cyan
    python -m venv $VENV_DIR
} else {
    Write-Host "O ambiente virtual ($VENV_DIR) já existe." -ForegroundColor Yellow
}

# 2. Ativa o ambiente virtual no processo atual
$ACTIVATE_PATH = ".\$VENV_DIR\Scripts\Activate.ps1"
if (Test-Path $ACTIVATE_PATH) {
    Write-Host "Ativando o ambiente virtual..." -ForegroundColor Green
    & $ACTIVATE_PATH
} else {
    Write-Host "Erro: Ficheiro de ativação não encontrado em $ACTIVATE_PATH" -ForegroundColor Red
    exit
}

# 3. Atualiza o pip e instala as bibliotecas necessárias
Write-Host "Atualizando pip e instalando dependências..." -ForegroundColor Cyan

python -m pip install --upgrade pip

# Instalação do numpy e tflite (módulos como csv, pathlib, collections, re, struct, sys e math já são nativos do Python)
python -m pip install -r requirements.txt

Write-Host "`nAmbiente configurado e ativado com sucesso!" -ForegroundColor Green