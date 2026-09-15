@echo off
cd /d "%~dp0"
py -3.12 setup_review.py
if errorlevel 1 (
  echo Setup did not complete. See the message above and the user guide.
)
pause
