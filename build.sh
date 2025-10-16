#!/usr/bin/env bash
# exit on error
set -o errexit

# Install backend dependencies
pip install -r requirements.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Navigate into the frontend directory
cd frontend

# Install frontend dependencies and build the static files
npm install
npm run build
