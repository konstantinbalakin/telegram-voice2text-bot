#!/bin/bash
# Update requirements.txt from poetry for Docker builds

set -e

echo "📦 Updating requirements.txt from poetry.lock..."

# Install poetry export plugin if not already installed
if ! poetry self show plugins | grep -q poetry-plugin-export; then
    echo "Installing poetry-plugin-export..."
    poetry self add poetry-plugin-export
fi

# Export with faster-whisper (production default for Docker)
echo "Exporting requirements.txt with faster-whisper..."
poetry export -f requirements.txt --output requirements.txt --without-hashes --extras "faster-whisper"

echo "✅ Requirements file updated:"
echo "  - requirements.txt (base + faster-whisper for Docker)"
