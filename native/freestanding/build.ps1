# Assembles boot.asm and boots it in QEMU to verify it actually runs
# freestanding - no OS, no libc, no runtime underneath it.

$dir = Split-Path -Parent $MyInvocation.MyCommand.Path
$nasm = "$env:LOCALAPPDATA\bin\NASM\nasm.exe"
if (-not (Test-Path $nasm)) { $nasm = "nasm" }
$qemu = "C:\Program Files\qemu\qemu-system-x86_64.exe"
if (-not (Test-Path $qemu)) { $qemu = "qemu-system-x86_64" }

& $nasm -f bin "$dir\boot.asm" -o "$dir\boot.bin"
if ($LASTEXITCODE -ne 0) { Write-Error "nasm failed"; exit 1 }

Write-Host "Assembled $dir\boot.bin (512 bytes, boot-sector signature verified below)."
$bytes = [System.IO.File]::ReadAllBytes("$dir\boot.bin")
if ($bytes.Length -eq 512 -and $bytes[510] -eq 0x55 -and $bytes[511] -eq 0xAA) {
    Write-Host "OK: valid boot sector (0x55 0xAA signature present)."
} else {
    Write-Error "Not a valid boot sector."
    exit 1
}

Write-Host "Booting in QEMU (5s), capturing serial output to serial_out.txt..."
$proc = Start-Process -FilePath $qemu -ArgumentList @(
    "-fda", "$dir\boot.bin",
    "-display", "none",
    "-serial", "file:$dir\serial_out.txt",
    "-monitor", "none",
    "-no-reboot", "-no-shutdown"
) -PassThru
Start-Sleep -Seconds 5
Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue

$out = Get-Content "$dir\serial_out.txt" -Raw
Write-Host "--- serial output ---"
Write-Host $out
if ($out -match "BOLT FREESTANDING") {
    Write-Host "VERIFIED: booted freestanding, no OS involved."
} else {
    Write-Error "Expected output not found - freestanding boot did not verify."
    exit 1
}
