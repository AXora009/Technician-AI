# Builds a self-contained Windows zip: embedded Python + dependencies + built frontend.
# Recipients unzip it and double-click start.bat; no Python or Node install needed.
#
#   powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 [-GeminiKey <key>]
#
# With -GeminiKey the key ships inside the zip and recipients are never asked for one.
# Anyone with the zip can read it, so use a dedicated key you can revoke.
param(
    [string]$OutDir = "$env:TEMP\TechnicianAI-package",
    [string]$PythonVersion = "3.12.10",
    [string]$GeminiKey = ""
)
$ErrorActionPreference = "Stop"
$Root = Split-Path $PSScriptRoot -Parent
$App = Join-Path $OutDir "TechnicianAI"
$PyTag = ($PythonVersion -split '\.')[0..1] -join ''   # e.g. 312

if (Test-Path $OutDir) { Remove-Item $OutDir -Recurse -Force }
New-Item -ItemType Directory -Force $App | Out-Null

Write-Host "1/5 Building frontend..."
Push-Location (Join-Path $Root "frontend")
npm run build
if ($LASTEXITCODE -ne 0) { throw "frontend build failed" }
Pop-Location

Write-Host "2/5 Downloading embedded Python $PythonVersion..."
$PyZip = Join-Path $OutDir "python-embed.zip"
Invoke-WebRequest "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -OutFile $PyZip
Expand-Archive $PyZip (Join-Path $App "python")
Remove-Item $PyZip
# Let the embedded interpreter find the app code and the bundled packages.
Add-Content (Join-Path $App "python\python$PyTag._pth") "..`r`n..\packages"

Write-Host "3/5 Installing dependencies for Windows / Python $PythonVersion..."
& (Join-Path $Root ".venv\Scripts\python.exe") -m pip install --quiet `
    --target (Join-Path $App "packages") `
    --platform win_amd64 --python-version $PythonVersion --implementation cp --only-binary=:all: `
    -r (Join-Path $Root "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install failed" }

Write-Host "4/5 Copying app files..."
Copy-Item (Join-Path $Root "technician_ai") $App -Recurse
Copy-Item (Join-Path $Root "templates") $App -Recurse
Copy-Item (Join-Path $Root "static") $App -Recurse
New-Item -ItemType Directory -Force (Join-Path $App "scripts"), (Join-Path $App "data"), (Join-Path $App "manuals") | Out-Null
Copy-Item (Join-Path $Root "scripts\local_start.py") (Join-Path $App "scripts")
Copy-Item (Join-Path $PSScriptRoot "start.bat") $App
if ($GeminiKey) {
    [IO.File]::WriteAllText((Join-Path $App "gemini_key.txt"), $GeminiKey.Trim())
}
Get-ChildItem $App -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force

Write-Host "5/5 Zipping..."
$Zip = Join-Path $OutDir "TechnicianAI-windows.zip"
# Windows' built-in bsdtar writes a standard zip (forward-slash paths) and is much faster than Compress-Archive.
tar.exe -a -c -f $Zip -C $OutDir TechnicianAI
if ($LASTEXITCODE -ne 0) { throw "zip failed" }
Write-Host "Done: $Zip ($([math]::Round((Get-Item $Zip).Length / 1MB)) MB)"
