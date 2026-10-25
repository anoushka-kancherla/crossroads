#!/bin/sh
# Copies the one brand token source into both apps (each app builds from its own folder in Docker).
set -e
cd "$(dirname "$0")/.."
for app in customer-app internal-app; do
  mkdir -p "$app/src/styles"
  cp branding/tokens.css "$app/src/styles/tokens.css"
done
echo "Copied branding/tokens.css into customer-app and internal-app."
