#!/bin/bash
cd "$(dirname "$0")"
# Files from a downloaded zip are quarantined by macOS; once the user has allowed
# this script, clear the flag so the bundled Python and libraries can run.
xattr -dr com.apple.quarantine . 2>/dev/null
./python/bin/python3 scripts/local_start.py
