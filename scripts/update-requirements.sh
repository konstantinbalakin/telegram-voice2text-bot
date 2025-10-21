#!/bin/bash
# Update requirements.txt from poetry for Docker builds

set -e

echo "📦 Updating requirements.txt from poetry.lock..."

# Install poetry export plugin if not already installed
if ! poetry self show plugins | grep -q poetry-plugin-export; then
    echo "Installing poetry-plugin-export..."
    poetry self add poetry-plugin-export
fi

# Export main dependencies
echo "Exporting main dependencies..."
poetry export -f requirements.txt --output requirements.txt --without-hashes

# Export with extras for full providers support
echo "Exporting with all providers..."
poetry export -f requirements.txt --output requirements-full.txt --without-hashes --extras "all-providers"

# Export with only faster-whisper (default for Docker)
echo "Exporting with faster-whisper only..."
poetry export -f requirements.txt --output requirements-docker.txt --without-hashes --extras "faster-whisper"

echo "✅ Requirements files updated:"
echo "  - requirements.txt (base dependencies)"
echo "  - requirements-docker.txt (base + faster-whisper)"
echo "  - requirements-full.txt (all providers)"
echo ""
echo "💡 For Docker, consider using requirements-docker.txt"
