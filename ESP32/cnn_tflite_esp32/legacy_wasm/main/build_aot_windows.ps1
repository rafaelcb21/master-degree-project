$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$wasmFile = Join-Path $scriptDir "rust_drowsiness_trucker.wasm"
$aotFile = Join-Path $scriptDir "rust_drowsiness_trucker.aot"

if (-not (Test-Path $wasmFile)) {
    throw "Arquivo nao encontrado: $wasmFile"
}

if (-not $env:WAMRC_PATH) {
    throw "Defina a variavel de ambiente WAMRC_PATH apontando para o wamrc.exe"
}

$wamrc = $env:WAMRC_PATH

if (-not (Test-Path $wamrc)) {
    throw "wamrc.exe nao encontrado em WAMRC_PATH: $wamrc"
}

$args = @(
    "--target=xtensa",
    "--cpu=esp32",
    "--cpu-features=-fp",
    "--opt-level=3",
    "--size-level=3",
    "-o", $aotFile,
    $wasmFile
)

Write-Host "Gerando AOT com:" $wamrc $args
& $wamrc @args

if (-not (Test-Path $aotFile)) {
    throw "Falha ao gerar $aotFile"
}

Get-Item $aotFile | Format-List Name,Length,LastWriteTime
