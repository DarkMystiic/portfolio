"""Upload a static site to Cloudflare Pages: the committed files only.

    python -I deploy.py                       # this portfolio -> jaylen-portfolio.pages.dev
    python -I deploy.py --preview             # private preview link, live site untouched
    python -I deploy.py --repo C:/path/site --project client-name   # any other site repo

Only files committed to git are uploaded (git archive HEAD), so anything in
.gitignore (call/, drafts) never goes online. Notes and scripts (*.md, *.py,
dotfiles) are dropped too. Uncommitted edits are NOT uploaded: commit first.
Keys come from the saved CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN
(roblox-asset-apis apikeys.py); the token needs Account > Cloudflare Pages > Edit.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path.home() / ".claude/skills/roblox-asset-apis/scripts"))
import apikeys  # noqa: E402

WRANGLER = "wrangler@3.114.0"
SKIP_SUFFIXES = {".md", ".py"}


def site_files(repo: Path, out: Path) -> list[str]:
    tar = subprocess.run(["git", "-C", str(repo), "archive", "HEAD"], check=True, capture_output=True).stdout
    kept = []
    with tarfile.open(fileobj=io.BytesIO(tar)) as t:
        for m in t.getmembers():
            name = Path(m.name)
            if not m.isfile() or any(p.startswith(".") for p in name.parts) or name.suffix in SKIP_SUFFIXES:
                continue
            t.extract(m, out, filter="data")
            kept.append(m.name)
    return kept


def project_exists(acct: str, tok: str, name: str) -> bool:
    req = urllib.request.Request(
        f"https://api.cloudflare.com/client/v4/accounts/{acct}/pages/projects/{name}",
        headers={"Authorization": "Bearer " + tok},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return json.load(r).get("success", False)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return False
        raise SystemExit(f"Cloudflare refused the request ({e.code}). Does the token have Cloudflare Pages > Edit?")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--repo", default=str(Path(__file__).resolve().parent))
    ap.add_argument("--project", default="jaylen-portfolio", help="Cloudflare Pages project (= <name>.pages.dev)")
    ap.add_argument("--preview", action="store_true", help="upload to a preview link instead of the live site")
    a = ap.parse_args()

    acct, tok = apikeys.get("CLOUDFLARE_ACCOUNT_ID"), apikeys.get("CLOUDFLARE_API_TOKEN")
    if not acct or not tok:
        print("Missing CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN (set them with apikeys.py).")
        return 1
    repo = Path(a.repo).resolve()
    dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain"], capture_output=True, text=True).stdout
    if dirty.strip():
        print("Note: uncommitted changes are not uploaded:\n" + dirty)

    env = {**os.environ, "CLOUDFLARE_ACCOUNT_ID": acct, "CLOUDFLARE_API_TOKEN": tok}
    npx = shutil.which("npx") or "npx"
    out = Path(tempfile.mkdtemp(prefix="pages-"))
    try:
        files = site_files(repo, out)
        print(f"Uploading {len(files)} files from {repo.name} -> {a.project}")
        if not project_exists(acct, tok, a.project):
            subprocess.run([npx, "-y", WRANGLER, "pages", "project", "create", a.project, "--production-branch", "main"],
                           check=True, env=env, cwd=tempfile.gettempdir())
        branch = "preview" if a.preview else "main"
        subprocess.run([npx, "-y", WRANGLER, "pages", "deploy", str(out), "--project-name", a.project,
                        "--branch", branch, "--commit-dirty=true"], check=True, env=env, cwd=tempfile.gettempdir())
        print(f"Live: https://{a.project}.pages.dev/" if not a.preview else f"Preview: https://preview.{a.project}.pages.dev/")
    finally:
        shutil.rmtree(out, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
