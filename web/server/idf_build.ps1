param([ValidateSet('build', 'flash')][string]$Task)
$ErrorActionPreference = 'Stop'
$env:PATH = (Split-Path -Parent $env:WEB_IDF_PYTHON) + ';' + $env:PATH
$env:IDF_TOOLS_PATH = $env:WEB_IDF_TOOLS
$env:IDF_CCACHE_ENABLE = '0'
. (Join-Path $env:WEB_IDF_ROOT 'export.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& $env:WEB_IDF_PYTHON (Join-Path $env:WEB_IDF_ROOT 'tools/idf.py') -B $env:WEB_IDF_BUILD -D CCACHE_ENABLE=0 -p $env:WEB_ESP_PORT $Task
exit $LASTEXITCODE
