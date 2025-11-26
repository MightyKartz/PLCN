#!/bin/bash
# Get the directory where the script is located
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

# Ensure the binary is executable
chmod +x PLCN-macOS

# Run the application with the UI subcommand
./PLCN-macOS ui
