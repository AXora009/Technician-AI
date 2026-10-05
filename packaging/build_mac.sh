#!/bin/bash
# Builds a self-contained macOS zip: standalone Python + dependencies + built frontend.
# Recipients unzip it and double-click start.command; no Python or Node install needed.
# Must run on a Mac of the target architecture (CI uses GitHub's macOS runners):
#
#   packaging/build_mac.sh <aarch64|x86_64> <output zip name>
set -euo pipefail
ARCH="$1"
ZIP_NAME="$2"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="$ROOT/dist"
APP="$OUT/TechnicianAI"
rm -rf "$OUT"
mkdir -p "$APP"

echo "1/5 Building frontend..."
(cd "$ROOT/frontend" && npm run build)

echo "2/5 Downloading standalone Python 3.12 ($ARCH)..."
gh release download --repo astral-sh/python-build-standalone \
  --pattern "cpython-3.12.*-$ARCH-apple-darwin-install_only.tar.gz" --dir "$OUT"
tar -xzf "$OUT"/cpython-*.tar.gz -C "$APP"
rm "$OUT"/cpython-*.tar.gz

echo "3/5 Installing dependencies..."
# Pin wheels to macOS 11+ so the package runs on older Macs than the build machine.
"$APP/python/bin/python3" -m pip install --quiet --no-cache-dir \
  --target "$APP/python/lib/python3.12/site-packages" \
  --platform "macosx_11_0_$([ "$ARCH" = aarch64 ] && echo arm64 || echo x86_64)" \
  --python-version 3.12 --implementation cp --only-binary=:all: \
  -r "$ROOT/requirements.txt"

echo "4/5 Copying app files..."
cp -R "$ROOT/technician_ai" "$ROOT/templates" "$ROOT/static" "$APP/"
mkdir -p "$APP/scripts" "$APP/data" "$APP/manuals"
cp "$ROOT/scripts/local_start.py" "$APP/scripts/"
cp "$ROOT/packaging/start.command" "$APP/"
chmod +x "$APP/start.command"
find "$APP" -name __pycache__ -type d -prune -exec rm -rf {} +

echo "5/5 Zipping..."
# ditto keeps the executable bits and symlinks that the bundled Python needs.
(cd "$OUT" && ditto -c -k --keepParent TechnicianAI "$ZIP_NAME")
echo "Done: $OUT/$ZIP_NAME"
