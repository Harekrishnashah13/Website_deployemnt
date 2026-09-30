# OpenShorts setup

[OpenShorts](https://github.com/mutonby/openshorts) turns a long video (upload or YouTube link) into vertical 9:16 viral clips with face tracking and subtitles. There are two ways to run it from this repo.

## Option A: free Google Colab GPU (no install)

Open `notebooks/OpenShorts_Colab.ipynb` in Colab (File → Open notebook → GitHub → this repo).

1. Runtime → Change runtime type → **T4 GPU**
2. Paste your Gemini key in cell 2 (free: https://aistudio.google.com/apikey)
3. Run all cells. Cell 4 prints a `https://….trycloudflare.com` link to the dashboard.
4. When you're done, cell 6 downloads your clips as a zip. Colab deletes everything when the session ends.

## Option B: your own computer (Docker)

Requirements: [Docker Desktop](https://docs.docker.com/get-docker/) (or Docker Engine + Compose v2), git, about 15 GB of free disk, and 8 GB+ RAM.

```bash
bash openshorts/setup.sh          # CPU
bash openshorts/setup.sh --gpu    # NVIDIA GPU (needs the NVIDIA Container Toolkit)
```

The script clones OpenShorts into `openshorts/app/` (git-ignored), creates `.env` from `openshorts/env.example`, and runs `docker compose up --build -d`. The first build takes 10–20 minutes.

- Dashboard: http://localhost:5175
- Put `GEMINI_API_KEY` in `openshorts/app/.env` (then `docker compose restart backend`), or enter it in the dashboard under **Settings**
- Logs: `cd openshorts/app && docker compose logs -f backend`
- Stop: `cd openshorts/app && docker compose down`
- Update: re-run `setup.sh`

On Windows, `bash` in PowerShell only works when WSL has a Linux distro installed. You don't need the script: start Docker Desktop, then run these in PowerShell inside the OpenShorts folder:

```powershell
docker --version                # confirms Docker Desktop is installed
Copy-Item .env.example .env     # skip if .env already exists
docker compose up --build
```

## Using it

1. **Settings**: add the Gemini key. fal.ai, ElevenLabs and Upload-Post keys are only needed for AI Shorts, dubbing and auto-posting.
2. **Clip Generator**: upload a video or paste a YouTube URL, then wait for the clips.
3. Download clips from the results or the gallery.

## No Gemini key?

You can pick moments with a local model through Ollama instead. Uncomment `LLM_BASE_URL` / `LLM_MODEL` in `.env` and run Ollama with `OLLAMA_CONTEXT_LENGTH=16384`. Without Gemini, auto layout falls back to plain face-tracking crops.

## Troubleshooting

- **YouTube "sign in to confirm you're not a bot"**: upload the file directly, or set `YOUTUBE_COOKIES` in `.env`.
- **Slow on CPU**: expect 5–8 minutes per 8-minute video. Use Colab or `--gpu` if you want it faster.
- **Colab link shows "Blocked request"**: re-run cell 3, which patches `allowedHosts`, then cell 4.

## Hindi and other non-Latin captions

OpenShorts draws the hook box with a Latin-only font and burns captions without complex text shaping. Hindi (and Gujarati, Bengali, Tamil, Arabic...) then shows as empty boxes, or with vowel signs on the wrong letter. The Colab notebook fixes both: it installs `fonts-noto-core`, then runs `openshorts/patch_script_fonts.py` (cells 3b and 3c). English clips look the same as before.

For Docker, add `fonts-noto-core` to the `apt-get install` list in OpenShorts' `Dockerfile`, then run `python openshorts/patch_script_fonts.py <openshorts folder>` before `docker compose up --build`.
