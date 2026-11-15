# Deploying the public URL (free)

**Deployed:** https://gigbid-fbdh.onrender.com (API + web app) and
https://gigbid-gigsim-77yp.onrender.com (GigSim), from `render.yaml` on Render's free plan.
The API uses the lite runtime (`EMBED_BACKEND=onnx`, same models through ONNX Runtime).
The Hugging Face route below remains an alternative.

Target: a Hugging Face Space, Docker SDK, "CPU basic" hardware (free: 2 vCPU, 16 GB RAM).
One container runs GigSim (localhost only), the API, the in-process MCP servers and the built
web app. LLM calls go to hosted open-weight models (`MODEL_PROFILE=open_hosted`, Groq).

## Once

1. Sign in at https://huggingface.co and create a Space: **New Space → SDK: Docker → Blank →
   Hardware: CPU basic (free) → Public**. Name it, for example, `gigbid`.
2. In the Space **Settings → Variables and secrets**, add these as **secrets**:
   * `OPEN_MODEL_API_KEY`: your Groq key
   * `JWT_SECRET_KEY`: any long random string
   * `FERNET_KEY`: output of `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
   * `REVIEWER_PASSWORD`: the reviewer password (share it only in the private Classroom comment)
3. Create a **write** token at https://huggingface.co/settings/tokens.

## Deploy (and redeploy after every final commit)

```bash
HF_TOKEN=${HF_TOKEN} python -m scripts.deploy_hf_space <your-hf-username>/gigbid
```
The script pushes only git-tracked files (never `.env`) plus the single-container Dockerfile.
The first build takes about 10–15 minutes (it downloads CPU PyTorch and the two small models).
The app is then at `https://<your-hf-username>-gigbid.hf.space`; sign in as `reviewer`. The
reviewer's inbox is seeded on first boot (`SEED_ON_START=1`).

## Keep it alive until grades are released

Free Spaces sleep after about 48 hours without visits and wake on the next visit (one to two
minutes). Before the hidden test window, open the URL once a day, or upgrade the Space's
hardware for that period. State is in the container and resets on rebuild; the reviewer
account is recreated automatically from the secrets.

## GitHub

Set `main` as the default branch: **GitHub → repo → Settings → General → Default branch → main**.
