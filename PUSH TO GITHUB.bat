@echo off
title Push Aurentis AI to GitHub
color 0B
cd /d "%~dp0"

echo.
echo  ================================================================
echo   Aurentis AI -- Push to GitHub
echo  ================================================================
echo.
echo  This will create a new GitHub repository and push all code.
echo.
echo  You need a GitHub account. If you don't have a Personal Access
echo  Token, go to: github.com/settings/tokens/new
echo  Select scope: repo (Full control of private repositories)
echo.

set /p GITHUB_USER=  Enter your GitHub username:
set /p GITHUB_TOKEN=  Enter your Personal Access Token:
set /p REPO_NAME=  Repository name (press Enter for "aurentis-trader"):

if "%REPO_NAME%"=="" set REPO_NAME=aurentis-trader

echo.
echo  Creating repository %GITHUB_USER%/%REPO_NAME% on GitHub...

:: Create the repository via GitHub API
curl -s -X POST ^
  -H "Authorization: token %GITHUB_TOKEN%" ^
  -H "Content-Type: application/json" ^
  -d "{\"name\":\"%REPO_NAME%\",\"description\":\"Aurentis AI — Paper trading system for Hyperliquid perpetuals\",\"private\":false}" ^
  https://api.github.com/user/repos > nul

echo  Repository created (or already exists).

:: Set remote and push
git remote remove origin >nul 2>&1
git remote add origin https://%GITHUB_USER%:%GITHUB_TOKEN%@github.com/%GITHUB_USER%/%REPO_NAME%.git

git branch -M main
git push -u origin main

if %ERRORLEVEL% EQU 0 (
    echo.
    echo  ================================================================
    echo   SUCCESS! Code is now on GitHub:
    echo   https://github.com/%GITHUB_USER%/%REPO_NAME%
    echo  ================================================================
    echo.
    echo  Next step: Deploy to the cloud for 24/7 operation.
    echo  See README.md for deployment instructions.
    echo.
    start https://github.com/%GITHUB_USER%/%REPO_NAME%
) else (
    echo.
    echo  [!] Push failed. Check your username and token.
)

pause
