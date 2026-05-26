# Chat CAD installer for Windows.
# Sets up an isolated Miniforge environment with cadquery + flask + the rest,
# then drops a desktop shortcut. Idempotent: re-running it just upgrades.

$ErrorActionPreference = "Stop"

$AppRoot      = Split-Path -Parent $PSScriptRoot      # chat_cad/
$Miniforge    = "$env:USERPROFILE\miniforge-chatcad"
$EnvName      = "chatcad"
$EnvPython    = "$Miniforge\envs\$EnvName\python.exe"
$Installer    = "$env:TEMP\miniforge-installer.exe"
$DownloadUrl  = "https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Windows-x86_64.exe"

function Step($msg) { Write-Host "==> $msg" -ForegroundColor Cyan }
function Ok($msg)   { Write-Host "    $msg" -ForegroundColor Green }

Step "Chat CAD installer starting"
Write-Host "    App root:  $AppRoot"
Write-Host "    Miniforge: $Miniforge"
Write-Host "    Env name:  $EnvName"
Write-Host ""

# --- 1. Miniforge --- #
if (-not (Test-Path "$Miniforge\Scripts\conda.exe")) {
    Step "Downloading Miniforge (~100 MB)..."
    Invoke-WebRequest -Uri $DownloadUrl -OutFile $Installer -UseBasicParsing
    Ok "Downloaded."

    Step "Installing Miniforge silently to $Miniforge..."
    Start-Process -FilePath $Installer -Wait -ArgumentList @(
        "/InstallationType=JustMe",
        "/RegisterPython=0",
        "/AddToPath=0",
        "/S",
        "/D=$Miniforge"
    )
    Remove-Item $Installer -ErrorAction SilentlyContinue
    Ok "Miniforge installed."
} else {
    Ok "Miniforge already present, skipping download."
}

$Conda = "$Miniforge\Scripts\conda.exe"

# --- 2. Conda env --- #
$envExists = & $Conda env list | Select-String -SimpleMatch "envs\$EnvName"
if (-not $envExists) {
    Step "Creating conda env '$EnvName' with Python 3.11 + cadquery (~5 min, ~1.5 GB)..."
    & $Conda create -y -n $EnvName -c conda-forge python=3.11 cadquery=2.4
    Ok "Env created."
} else {
    Ok "Env '$EnvName' already exists."
}

# --- 3. Pip deps --- #
# numpy must be <2 because cadquery's nptyping dep references np.bool8,
# which was removed in NumPy 2.x. Removing the cap will break import.
Step "Installing/updating Python deps (flask, anthropic, numpy<2, scipy)..."
& $EnvPython -m pip install --upgrade --quiet flask "anthropic>=0.40" "numpy>=1.24,<2" "scipy>=1.11" "matplotlib>=3.7" "Pillow>=10.0"
Ok "Python deps ready."

# --- 4. Sanity check --- #
Step "Verifying cadquery imports..."
& $EnvPython -c "import cadquery; print('    cadquery', cadquery.__version__, 'OK')"

# --- 5. Desktop + Start Menu shortcut --- #
function New-Shortcut($linkPath, $target, $args, $workdir, $icon) {
    $ws = New-Object -ComObject WScript.Shell
    $sc = $ws.CreateShortcut($linkPath)
    $sc.TargetPath       = $target
    $sc.Arguments        = $args
    $sc.WorkingDirectory = $workdir
    if ($icon) { $sc.IconLocation = $icon }
    $sc.Save()
}

$Launcher = Join-Path $AppRoot "installer\Run Chat CAD.bat"
$Desktop  = [Environment]::GetFolderPath("Desktop")
$Programs = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs"

Step "Creating shortcuts..."
New-Shortcut -linkPath "$Desktop\Chat CAD.lnk"  -target $Launcher -args "" -workdir $AppRoot
New-Shortcut -linkPath "$Programs\Chat CAD.lnk" -target $Launcher -args "" -workdir $AppRoot
Ok "Shortcuts placed on Desktop and in Start Menu."

Write-Host ""
Write-Host "================================================================" -ForegroundColor Green
Write-Host " Chat CAD installed." -ForegroundColor Green
Write-Host ""
Write-Host " Launch with the 'Chat CAD' shortcut on your Desktop"
Write-Host " or double-click 'Run Chat CAD.bat' in this folder."
Write-Host "================================================================" -ForegroundColor Green
