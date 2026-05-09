@echo off
rem agent-inbox MCP server launcher (Windows).
rem Probes for uv first; falls back to a colocated .venv.
setlocal
set "SCRIPT_DIR=%~dp0"
set "REPO_DIR=%SCRIPT_DIR%.."
pushd "%REPO_DIR%"
where uv >nul 2>nul
if %ERRORLEVEL% equ 0 (
    uv run --quiet python -m agent_inbox %*
    set "RC=%ERRORLEVEL%"
    popd
    exit /b %RC%
)
if exist ".venv\Scripts\python.exe" (
    .venv\Scripts\python.exe -m agent_inbox %*
    set "RC=%ERRORLEVEL%"
    popd
    exit /b %RC%
)
echo agent-inbox-mcp: need 'uv' or a .venv at %REPO_DIR% 1>&2
popd
exit /b 1
