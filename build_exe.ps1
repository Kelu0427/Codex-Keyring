$ErrorActionPreference = "Stop"

python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --onefile `
  --name Codex-Keyring `
  --icon img\icon.ico `
  --version-file version_info.txt `
  --add-data "web;web" `
  --add-data "img;img" `
  app.py

Write-Host "Build done: dist\\Codex-Keyring.exe"
