param(
    [string]$Wamrc = $env:WAMRC_PATH,
    [string]$Wasm,
    [string]$OutputDir,
    [string]$Python,
    [string[]]$EvidenceFiles = @()
)
$ErrorActionPreference = "Stop"
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot "../../.."))
if (-not $Wamrc) {
    $compilerCommand = Get-Command wamrc.exe -ErrorAction SilentlyContinue
    if ($compilerCommand) { $Wamrc = $compilerCommand.Source }
}
if (-not $Wamrc) { throw "Informe -Wamrc ou configure WAMRC_PATH." }
if (-not $Wasm) { $Wasm = Join-Path $projectRoot "models/drowsiness/generated/model.wasm" }
if (-not $Python) {
    $Python = Join-Path $projectRoot ".venv-models/Scripts/python.exe"
    if (-not (Test-Path -LiteralPath $Python)) { $Python = "python" }
}
$compileArguments = @((Join-Path $projectRoot "build_aot_with_provenance.py"), "build",
                      "--wamrc", $Wamrc, "--wasm", $Wasm)
if ($OutputDir) { $compileArguments += @("--output-dir", $OutputDir) }
foreach ($evidence in $EvidenceFiles) { $compileArguments += @("--evidence", $evidence) }
& $Python @compileArguments
if ($LASTEXITCODE -ne 0) { throw "Compilacao AOT falhou. Consulte o manifesto e o log da tentativa." }
Write-Host "AOT e manifesto gerados em uma pasta nova. O main.aot existente foi preservado."
