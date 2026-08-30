# Builds nboltc.exe, the native (Python-free) Bolt interpreter, with MSVC.
# Run from a plain PowerShell prompt (does not require a VS Developer prompt).

$vswhere = "${env:ProgramFiles(x86)}\Microsoft Visual Studio\Installer\vswhere.exe"
$vsPath = $null
if (Test-Path $vswhere) {
    $vsPath = & $vswhere -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath
}
if (-not $vsPath) { $vsPath = "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools" }

$vcvars = "$vsPath\VC\Auxiliary\Build\vcvars64.bat"
if (-not (Test-Path $vcvars)) {
    Write-Error "Could not find vcvars64.bat under $vsPath. Install the 'Desktop development with C++' workload."
    exit 1
}

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
cmd /c "`"$vcvars`" >nul && cd /d `"$dir`" && cl /nologo /O2 /w bolt.c /Fe:nboltc.exe user32.lib gdi32.lib winmm.lib /link /STACK:67108864"
