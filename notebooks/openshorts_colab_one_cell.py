#@title OpenShorts on Colab: complete setup in ONE cell (paste into an empty Colab cell)
# Runtime -> Change runtime type -> T4 GPU, then paste your Gemini key below and run.
# Safe to re-run: it skips what is already installed and restarts the servers.
GEMINI_API_KEY = ""  #@param {type:"string"}
WHISPER_MODEL = "large-v3-turbo"  #@param ["small", "medium", "large-v3-turbo"]

import os, re, subprocess, time

PATCHES = "https://raw.githubusercontent.com/Harekrishnashah13/Website_deployemnt/claude/trusting-franklin-jtrzg6/openshorts"
APP = "/content/openshorts"
VENV = "/content/venv"

def sh(cmd):
    """Run a shell command, stop with its output if it fails."""
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\n{r.stdout[-2000:]}\n{r.stderr[-2000:]}")
    return r.stdout

def step(msg):
    print(f"\n==> {msg}", flush=True)

gpu = subprocess.run("nvidia-smi", shell=True, capture_output=True).returncode == 0
print("GPU:", "yes" if gpu else "NO (Runtime > Change runtime type > T4 GPU for faster clips)")

# 1. System packages: ffmpeg, fonts (incl. Hindi/Indic), Node 20, cloudflared
step("Installing system packages (~1 min)")
sh("apt-get -qq update && apt-get -qq install -y ffmpeg fontconfig fonts-liberation "
   "fonts-noto-color-emoji fonts-noto-core > /dev/null")
if "v20" not in subprocess.run("node -v", shell=True, capture_output=True, text=True).stdout:
    sh("curl -fsSL https://deb.nodesource.com/setup_20.x | bash - > /dev/null && apt-get -qq install -y nodejs > /dev/null")
if not os.path.exists("/usr/local/bin/cloudflared"):
    sh("wget -q https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 "
       "-O /usr/local/bin/cloudflared && chmod +x /usr/local/bin/cloudflared")

# 2. OpenShorts code + settings
step("Getting OpenShorts")
if not os.path.isdir(APP):
    sh(f"git clone --depth 1 https://github.com/mutonby/openshorts.git {APP}")
os.chdir(APP)
settings = {
    "GEMINI_API_KEY": GEMINI_API_KEY,
    "WHISPER_MODEL": WHISPER_MODEL if gpu else "small",
    "WHISPER_DEVICE": "cuda" if gpu else "cpu",
    "WHISPER_COMPUTE": "float16" if gpu else "int8",
    "FFMPEG_ENCODER": "auto",
    "GEMINI_RETRY_ATTEMPTS": "6",
}
with open(".env", "w") as f:
    f.writelines(f"{k}={v}\n" for k, v in settings.items())
if not GEMINI_API_KEY:
    print("No Gemini key set here: add it later in the dashboard under Settings.")

# 3. Python 3.11 environment (OpenShorts' pinned packages don't exist for Colab's newer Python)
step("Installing Python packages (~5-8 min the first time)")
sh("pip install -q uv")
sh(f"uv venv -q --allow-existing --python 3.11 {VENV}")
sh(f'UV_HTTP_TIMEOUT=300 uv pip install -q --python {VENV}/bin/python -r requirements.txt '
   f'"nvidia-cublas-cu12<13" "nvidia-cudnn-cu12>=9,<10" "yt-dlp[default]"')
os.environ["MPLBACKEND"] = "Agg"  # Colab's inline plot backend crashes mediapipe in the 3.11 env
print(sh(f'{VENV}/bin/python -c "import torch, mediapipe, faster_whisper; print(\'Python env OK, torch\', torch.__version__)"').strip())

# 4. Fonts + fixes: Hindi/Indic hooks and captions, retry Gemini when Google is busy
step("Applying fonts and fixes")
sh("mkdir -p /usr/local/share/fonts/openshorts && cp fonts/*.ttf /usr/local/share/fonts/openshorts/ "
   "&& cp fonts/openshorts-fontmap.conf /etc/fonts/conf.d/60-openshorts.conf && fc-cache -f")
for patch in ("patch_script_fonts.py", "patch_gemini_retry.py"):
    sh(f"curl -fsSL {PATCHES}/{patch} -o /content/{patch}")
    print(sh(f"python /content/{patch} {APP}").strip())

# 5. Dashboard: allow the tunnel hostname, pre-build (the dev server shows a black page through tunnels)
step("Building the dashboard (~1 min)")
sh("grep -q trycloudflare dashboard/vite.config.js || "
   "sed -i \"s/allowedHosts: \\[/allowedHosts: ['.trycloudflare.com', /\" dashboard/vite.config.js")
sh("cd dashboard && npm install --no-audit --no-fund --loglevel=error > /dev/null && npx vite build --logLevel error")

# 6. (Re)start backend, dashboard and the two public links
step("Starting OpenShorts")
subprocess.run('pkill -f "[u]vicorn app:app"; pkill -f "[n]ode.*vite"; pkill -f "[c]loudflared"', shell=True)
time.sleep(3)
nv = f"{VENV}/lib/python3.11/site-packages/nvidia"
os.environ["LD_LIBRARY_PATH"] = ":".join(f"{nv}/{d}/lib" for d in ("cublas", "cudnn", "cuda_runtime", "cu13")) \
    + ":" + os.environ.get("LD_LIBRARY_PATH", "")
subprocess.Popen(f"{VENV}/bin/uvicorn app:app --host 0.0.0.0 --port 8000 > /content/backend.log 2>&1", shell=True)
subprocess.Popen("cd dashboard && VITE_PROXY_TARGET=http://localhost:8000 npx vite preview --host 0.0.0.0 "
                 "--port 5173 --strictPort > /content/frontend.log 2>&1", shell=True)
subprocess.Popen("cloudflared tunnel --url http://localhost:5173 --no-autoupdate > /content/tunnel.log 2>&1", shell=True)
subprocess.Popen("cloudflared tunnel --url http://localhost:8000 --no-autoupdate > /content/tunnel_mcp.log 2>&1", shell=True)

def tunnel_url(log):
    for _ in range(60):
        time.sleep(2)
        m = re.search(r"https://[a-z0-9-]+\.trycloudflare\.com", open(log).read())
        if m:
            return m.group(0)
    return None

dashboard, mcp = tunnel_url("/content/tunnel.log"), tunnel_url("/content/tunnel_mcp.log")
health = ""
for _ in range(30):
    health = subprocess.run("curl -s localhost:8000/health", shell=True, capture_output=True, text=True).stdout
    if "ok" in health:
        break
    time.sleep(2)

print("\n" + "=" * 70)
print("Backend:", "running" if "ok" in health else "NOT running, see: !tail -n 40 /content/backend.log")
print("Dashboard (open in browser):", dashboard)
print("MCP connector URL:", f"{mcp}/mcp" if mcp else None)
print("  -> claude.ai/customize/connectors (update the URL there), or on your PC:")
print(f"     claude mcp add --transport http openshorts {mcp}/mcp")
print("=" * 70)
print("Keep this tab open. Logs: !tail -n 40 /content/backend.log")
print("Download all clips: !cd /content/openshorts && zip -qr /content/clips.zip output")
