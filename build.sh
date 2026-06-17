#!/bin/bash

echo "Building AutoBet with PyInstaller..."
pyinstaller --name "AutoBet" --windowed --icon="resources/icon.ico" --add-data "resources;resources" main.py
echo "Build complete! Check the 'dist' directory for the executable."