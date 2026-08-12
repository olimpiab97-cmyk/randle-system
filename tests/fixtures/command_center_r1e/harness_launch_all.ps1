[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
[string]$python = $env:RANDLE_PYTHON_EXE
if ([string]::IsNullOrWhiteSpace($python) -or -not [IO.Path]::IsPathRooted($python) -or -not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "r1e_governed_python_unavailable"
}
$helper = Join-Path $PSScriptRoot "tests\fixtures\command_center_r1e\harness_launch_stack.py"
& $python $helper
exit $LASTEXITCODE
