#!/bin/bash

echo "Initializing Stratolink Git repository..."

if ! command -v git &> /dev/null; then
    echo "Error: Git is not installed. Please install Git first."
    exit 1
fi

git init
if [ $? -ne 0 ]; then
    echo "Error: Git initialization failed."
    exit 1
fi

git add .
if [ $? -ne 0 ]; then
    echo "Error: Git add failed."
    exit 1
fi

git commit -m "Initial commit: Stratolink Architecture"
if [ $? -ne 0 ]; then
    echo "Error: Git commit failed."
    exit 1
fi

echo ""
echo "Repository initialized successfully."
echo ""
echo "Next steps:"
echo "1. Create a new repository on GitHub.com"
echo "2. Run: git remote add origin <your-github-repo-url>"
echo "3. Run: git push -u origin main"
echo ""
