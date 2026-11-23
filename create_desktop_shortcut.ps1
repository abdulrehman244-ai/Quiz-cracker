$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonW = (Get-Command pythonw.exe -ErrorAction SilentlyContinue).Source
if (-not $PythonW) {
    $Python = (Get-Command python.exe).Source
    $PythonW = Join-Path (Split-Path -Parent $Python) "pythonw.exe"
}

$Desktop = [Environment]::GetFolderPath("Desktop")
$ShortcutPath = Join-Path $Desktop "Quiz Cracker.lnk"
$IconPath = Join-Path $AppDir "assets\quiz_cracker.ico"
$ScriptPath = Join-Path $AppDir "quiz_cracker.py"

$WshShell = New-Object -ComObject WScript.Shell
$Shortcut = $WshShell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $PythonW
$Shortcut.Arguments = "`"$ScriptPath`""
$Shortcut.WorkingDirectory = $AppDir
$Shortcut.Description = "Quiz Cracker - Mouse-Move MCQ Assistant Overlay"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()

Write-Host "Desktop shortcut created: $ShortcutPath"
