"""Create a workspace (its own manuals + history) and print its access link.

    python scripts/add_workspace.py "Zhang San"
    python scripts/add_workspace.py "Illuminate" --use-existing-data   # your current manuals/data
    python scripts/add_workspace.py --list
"""
import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from technician_ai import workspaces  # noqa: E402

BASE_URL = os.environ.get("PUBLIC_URL", "https://quirk-footgear-stoppage.ngrok-free.dev").rstrip("/")

parser = argparse.ArgumentParser()
parser.add_argument("name", nargs="?")
parser.add_argument("--use-existing-data", action="store_true",
                    help="point this workspace at the existing data/tech.db and manuals/")
parser.add_argument("--list", action="store_true")
args = parser.parse_args()

if args.list:
    for code, ws in workspaces.list_all().items():
        print(f"{ws['name']:<24} {BASE_URL}/?code={code}")
elif args.name:
    code, ws = workspaces.create(args.name, use_existing_data=args.use_existing_data)
    print(f"Workspace: {ws['name']}")
    print(f"Code:      {code}")
    print(f"Link:      {BASE_URL}/?code={code}")
else:
    parser.print_help()
