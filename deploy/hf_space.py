"""Create (or update) a Hugging Face Space that runs the Dash edition.

Usage:
    pip install huggingface_hub
    export HF_TOKEN=hf_...            # a token with "write" scope from https://huggingface.co/settings/tokens
    python deploy/hf_space.py --owner <your-hf-username-or-org> [--name ls2-facility-dashboard-dash] [--private]

The Space is a Docker Space (see the YAML front matter at the top of README.md and the Dockerfile).
The script uploads the repository snapshot (minus virtualenvs, git metadata and raw data) and prints the URL.
Re-running it pushes an update; the Space rebuilds automatically.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
IGNORE = [".venv/**", "venv/**", ".git/**", "**/__pycache__/**", "*.pyc", ".pytest_cache/**", ".DS_Store", "data/raw/**", "data/survey/*.csv", ".github/**"]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--owner", required=True, help="Hugging Face username or organisation that will own the Space")
    ap.add_argument("--name", default="ls2-facility-dashboard-dash")
    ap.add_argument("--private", action="store_true")
    ap.add_argument("--streamlit-url", default="", help="optional: sets STREAMLIT_APP_URL so the header links to the Streamlit edition")
    a = ap.parse_args()

    token = os.environ.get("HF_TOKEN")
    if not token:
        raise SystemExit("Set HF_TOKEN to a write-scoped Hugging Face token first.")
    api = HfApi(token=token)
    repo_id = f"{a.owner}/{a.name}"
    api.create_repo(repo_id, repo_type="space", space_sdk="docker", private=a.private, exist_ok=True)
    if a.streamlit_url:
        api.add_space_variable(repo_id, "STREAMLIT_APP_URL", a.streamlit_url)
    api.upload_folder(folder_path=str(ROOT), repo_id=repo_id, repo_type="space", ignore_patterns=IGNORE,
                      commit_message="Deploy Dash edition of the LS 2.0 facility dashboard")
    print(f"Space pushed: https://huggingface.co/spaces/{repo_id}  (first build takes ~3-5 minutes)")


if __name__ == "__main__":
    main()
