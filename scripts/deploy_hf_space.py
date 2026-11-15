"""Deploy GigBid to a Hugging Face Space (Docker SDK, free CPU, port 7860).

Prereqs (once): create a Space at https://huggingface.co/new-space (SDK: Docker, blank),
create a write token at https://huggingface.co/settings/tokens, and add these Space
secrets in the Space settings (never in the repo):
  OPEN_MODEL_API_KEY   hosted open-model key (Groq)
  JWT_SECRET_KEY       long random string
  FERNET_KEY           python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
  REVIEWER_PASSWORD    the reviewer login password you share privately on Classroom

Run: HF_TOKEN=${HF_TOKEN} python -m scripts.deploy_hf_space <hf-username>/<space-name>
It copies the tracked files (git ls-files, so no .env, raw data or caches) into a temp folder,
puts the single-container Dockerfile and the Space header at its root, and pushes.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HEADER = """---
title: GigBid
emoji: 🧭
colorFrom: blue
colorTo: indigo
sdk: docker
app_port: 7860
pinned: false
---

"""


def main(space: str) -> None:
    token = os.environ["HF_TOKEN"]
    files = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True,
                           check=True).stdout.split("\n")
    with tempfile.TemporaryDirectory() as tmp:
        dst = Path(tmp) / "space"
        for f in filter(None, files):
            src = ROOT / f
            if src.is_file():
                (dst / f).parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst / f)
        shutil.copy2(ROOT / "infra/docker/Dockerfile.deploy", dst / "Dockerfile")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        (dst / "README.md").write_text(HEADER + readme, encoding="utf-8")
        auth = f"user:{token}"
        url = f"https://{auth}@huggingface.co/spaces/{space}"
        run = lambda *a: subprocess.run(a, cwd=dst, check=True)
        run("git", "init", "-q", "-b", "main")
        run("git", "lfs", "install", "--local")
        run("git", "lfs", "track", "*.parquet", "*.npy")
        run("git", "add", "-A")
        run("git", "-c", "user.name=gigbid-deploy", "-c", "user.email=deploy@localhost",
            "commit", "-q", "-m", "Deploy GigBid")
        run("git", "push", "-f", url, "main")
    print(f"pushed; build logs at https://huggingface.co/spaces/{space}")


if __name__ == "__main__":
    main(sys.argv[1])
