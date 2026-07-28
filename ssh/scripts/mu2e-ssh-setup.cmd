@echo off
rem ---------------------------------------------------------------------------
rem mu2e-ssh-setup.cmd -- Windows wrapper around mu2e-ssh-setup.py
rem
rem Usage, from cmd.exe or PowerShell:
rem
rem     scripts\mu2e-ssh-setup.cmd --interactive
rem     scripts\mu2e-ssh-setup.cmd --fnal-user jdoe --layout monolithic --install
rem
rem Works from any directory; the templates are located relative to this script.
rem Set MU2E_SSH_PYTHON to force a particular interpreter.
rem ---------------------------------------------------------------------------
setlocal

set "SCRIPT=%~dp0mu2e-ssh-setup.py"

if not exist "%SCRIPT%" (
    echo mu2e-ssh-setup.cmd: cannot find "%SCRIPT%" 1>&2
    exit /b 1
)

if defined MU2E_SSH_PYTHON (
    "%MU2E_SSH_PYTHON%" "%SCRIPT%" %*
    exit /b %ERRORLEVEL%
)

rem The "py" launcher ships with the python.org installer and is the most
rem reliable way to reach a real Python 3 on Windows. Fall back to python.exe,
rem which on a stock Windows 11 may be the Microsoft Store stub.
where py >nul 2>&1
if %ERRORLEVEL% equ 0 (
    py -3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        py -3 "%SCRIPT%" %*
        exit /b %ERRORLEVEL%
    )
)

where python3 >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python3 -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        python3 "%SCRIPT%" %*
        exit /b %ERRORLEVEL%
    )
)

where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    python -c "import sys; sys.exit(0 if sys.version_info[:2] >= (3, 9) else 1)" >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        python "%SCRIPT%" %*
        exit /b %ERRORLEVEL%
    )
)

echo. 1>&2
echo mu2e-ssh-setup: no Python 3 found on PATH. 1>&2
echo. 1>&2
echo Install it with one of: 1>&2
echo     winget install Python.Python.3.12 1>&2
echo     https://www.python.org/downloads/windows/ 1>&2
echo. 1>&2
echo Then open a NEW terminal so the PATH change takes effect. 1>&2
exit /b 1
