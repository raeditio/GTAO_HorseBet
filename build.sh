#!/bin/bash

echo "Building GTAO_HorseBet with PyInstaller..."
pyinstaller --name "GTAO_HorseBet" --windowed --icon="resources/icon.ico" --add-data "resources;resources" main.py
echo "Build complete! Check the 'dist' directory for the executable."