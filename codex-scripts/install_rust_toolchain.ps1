$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

$rustupDir = Join-Path $env:TEMP "flowhub-rustup"
New-Item -ItemType Directory -Force -Path $rustupDir | Out-Null

$installer = Join-Path $rustupDir "rustup-init.exe"
Invoke-WebRequest `
  -Uri "https://static.rust-lang.org/rustup/dist/x86_64-pc-windows-msvc/rustup-init.exe" `
  -OutFile $installer

& $installer -y --profile minimal --default-toolchain stable-x86_64-pc-windows-msvc
if ($LASTEXITCODE -ne 0) {
  throw "rustup installation failed with exit code $LASTEXITCODE"
}

$cargoBin = Join-Path $env:USERPROFILE ".cargo\bin"
$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
if ($userPath -notlike "*$cargoBin*") {
  $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) {
    $cargoBin
  } else {
    "$userPath;$cargoBin"
  }
  [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
}

Write-Output "Installed rustup and updated user PATH."
if (Test-Path (Join-Path $cargoBin "cargo.exe")) {
  & (Join-Path $cargoBin "cargo.exe") --version
}
