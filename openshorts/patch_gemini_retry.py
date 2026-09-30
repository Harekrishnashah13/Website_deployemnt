"""Make OpenShorts retry Gemini when Google is overloaded.

Google's Gemini API sometimes answers "503 UNAVAILABLE: This model is currently
experiencing high demand". OpenShorts makes each call once, so one busy moment
fails the whole job ("Gemini vision error ... Process failed with exit code 1").
This adds gemini_retry.py, which gives every Gemini client exponential-backoff
retries on 429/5xx (6 attempts, 5-60 s apart), and imports it in app.py (the
server) and main.py (the clip worker). Tune with GEMINI_RETRY_ATTEMPTS in .env.

Usage (idempotent):  python patch_gemini_retry.py /path/to/openshorts
"""
import pathlib
import sys

MODULE = '"""Retry Gemini calls on overload (429/5xx) instead of failing the whole job.\n\nImported once at startup by app.py and main.py; every genai.Client created\nafterwards without its own http_options gets exponential-backoff retries.\nTune with GEMINI_RETRY_ATTEMPTS (default 6)."""\nimport os\n\nfrom google import genai\nfrom google.genai import types\n\n_ATTEMPTS = int(os.environ.get("GEMINI_RETRY_ATTEMPTS", "6"))\n_orig_init = genai.Client.__init__\n\n\ndef _init_with_retry(self, *args, **kwargs):\n    if kwargs.get("http_options") is None and _ATTEMPTS > 1:\n        kwargs["http_options"] = types.HttpOptions(retry_options=types.HttpRetryOptions(\n            attempts=_ATTEMPTS, initial_delay=5, max_delay=60,\n            http_status_codes=[429, 500, 502, 503, 504]))\n    _orig_init(self, *args, **kwargs)\n\n\nif not getattr(genai.Client, "_openshorts_retry", False):\n    genai.Client.__init__ = _init_with_retry\n    genai.Client._openshorts_retry = True\n'

IMPORT = "import gemini_retry  # noqa: F401  (retry Gemini on 503 overload)\n"
ANCHOR = "\nload_dotenv()\n"


def patch(repo):
    repo = pathlib.Path(repo)
    (repo / "gemini_retry.py").write_text(MODULE, encoding="utf-8")
    for name in ("app.py", "main.py"):
        path = repo / name
        src = path.read_text(encoding="utf-8")
        if IMPORT in src:
            print(f"{name} already patched")
            continue
        if ANCHOR not in src:
            sys.exit(f"{name} changed upstream; patch anchor not found")
        path.write_text(src.replace(ANCHOR, ANCHOR + IMPORT, 1), encoding="utf-8")
        print(f"{name} patched: Gemini calls retry when Google is busy")


if __name__ == "__main__":
    patch(sys.argv[1] if len(sys.argv) > 1 else ".")
