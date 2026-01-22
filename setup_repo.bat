@echo off
echo Initializing Stratolink Git repository...

git init
if %errorlevel% neq 0 (
    echo Error: Git initialization failed.
    exit /b 1
)

git add .
if %errorlevel% neq 0 (
    echo Error: Git add failed.
    exit /b 1
)

git commit -m "Initial commit: Stratolink Architecture"
if %errorlevel% neq 0 (
    echo Error: Git commit failed.
    exit /b 1
)

echo.
echo Repository initialized successfully.
echo.
echo Next steps:
echo 1. Create a new repository on GitHub.com
echo 2. Run: git remote add origin ^<your-github-repo-url^>
echo 3. Run: git push -u origin main
echo.
