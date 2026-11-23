@echo off
title Build Quiz Cracker Standalone EXE
cd /d "%~dp0"

echo Installing PyInstaller (if needed)...
pip install pyinstaller --quiet

echo Generating app icon...
python create_assets.py

echo Building standalone QuizCracker.exe...
python -m PyInstaller ^
  --noconfirm ^
  --onefile ^
  --windowed ^
  --name "Quiz Cracker" ^
  --icon "assets\quiz_cracker.ico" ^
  --add-data "assets\quiz_cracker.ico;assets" ^
  quiz_cracker.py

echo.
echo Done! Your standalone EXE is in: dist\Quiz Cracker.exe
pause
