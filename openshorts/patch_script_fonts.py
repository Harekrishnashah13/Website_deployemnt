"""Make OpenShorts hooks and captions readable in non-Latin languages (Hindi,
Gujarati, Bengali, Tamil, Arabic, ...). Needs the fonts installed first:
apt-get install fonts-noto-core

hooks.py: the hook box is drawn with one fixed Latin font (Montserrat, Anton or
Noto Serif), so Devanagari and other scripts come out as empty boxes. When the
hook text has characters that font lacks, use an installed font that covers
them (preferring Noto Sans Bold), found through fontconfig.

subtitles.py: captions are burned with ffmpeg's `subtitles` filter, which runs
libass with simple shaping, so Indic vowel signs land on the wrong letter
("दिल" renders as "दलि"). Burn them with the `ass` filter and shaping=complex
instead; plain SRT captions are converted to ASS with the same style first.

Usage (idempotent):  python patch_script_fonts.py /path/to/openshorts
"""
import pathlib
import sys

MARKER = "# openshorts-script-font-fallback"

HELPER = '''
''' + MARKER + '''
import functools as _ft
import unicodedata as _ud


@_ft.lru_cache(maxsize=16)
def _font_cmap(path):
    try:
        from fontTools.ttLib import TTFont
        return set(TTFont(path, fontNumber=0, lazy=True).getBestCmap())
    except Exception:
        return None


@_ft.lru_cache(maxsize=64)
def _font_covering(chars):
    charset = " ".join(f"{ord(c):x}" for c in chars)
    try:
        out = subprocess.run(["fc-list", f":charset={charset}", "file", "family", "style"],
                             capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return None
    best, best_score = None, -1
    for line in out.splitlines():
        path, _, meta = line.partition(":")
        meta = meta.lower()
        score = (4 if "noto sans" in meta else 1 if "noto" in meta else 0) \\
            + (2 if "bold" in meta else 0) - (1 if " ui" in meta else 0)
        if score > best_score:
            best, best_score = path.strip(), score
    return best


def _script_font_for(text, font_path):
    """Return font_path, or an installed font covering the characters it lacks."""
    cmap = _font_cmap(font_path)
    if cmap is None:
        return font_path
    missing = sorted({c for c in text
                      if not c.isspace() and ord(c) not in cmap
                      and _ud.category(c) != "Cf" and not _EMOJI_RE.match(c)})
    if not missing:
        return font_path
    fallback = _font_covering("".join(missing))
    if fallback:
        print(f"🔤 Hook text needs another script, using {fallback}")
    return fallback or font_path
'''

ANCHOR = "    font_path, size_factor = HOOK_FONTS.get(font or default_font, HOOK_FONTS[default_font])\n"
CALL = "    font_path = _script_font_for(text, font_path)\n"


SUB_MARKER = "# openshorts-complex-shaping"

SUB_HELPER = '''
''' + SUB_MARKER + '''
def _srt_to_styled_ass(srt_path, style_string):
    """SRT -> ASS with force_style's fields baked into the Default style, so it
    can go through the `ass` filter (the only one that takes shaping=complex).
    ffmpeg writes the same 384x288 script header the subtitles filter uses for
    SRT, so sizes and margins are unchanged. Returns None on any failure."""
    out = str(srt_path) + ".shaped.ass"
    try:
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-sub_charenc", "UTF-8",
                        "-i", str(srt_path), out], check=True, capture_output=True)
        overrides = dict(kv.split("=", 1) for kv in style_string.split(",") if "=" in kv)
        with open(out, encoding="utf-8") as f:
            lines = f.read().splitlines()
        fields = None
        for i, line in enumerate(lines):
            if line.startswith("Format:") and fields is None and "Fontname" in line:
                fields = [x.strip() for x in line[7:].split(",")]
            elif line.startswith("Style:") and fields:
                values = [x.strip() for x in line[6:].split(",")]
                for k, v in overrides.items():
                    if k in fields:
                        values[fields.index(k)] = v
                lines[i] = "Style: " + ",".join(values)
        with open(out, "w", encoding="utf-8") as f:
            f.write("\\n".join(lines) + "\\n")
        return out
    except Exception as e:
        _log(f"⚠️ Complex-shaping caption conversion failed, using plain filter: {e}")
        return None
'''

SUB_ASS_OLD = """        vf = f"ass=filename='{safe_srt_path}':fontsdir='{safe_fonts_dir}'"
"""
SUB_ASS_NEW = """        vf = f"ass=filename='{safe_srt_path}':fontsdir='{safe_fonts_dir}':shaping=complex"
"""
SUB_SRT_OLD = """    else:
        vf = (f"subtitles=filename='{safe_srt_path}':fontsdir='{safe_fonts_dir}'"
              f":charenc=UTF-8:force_style='{style_string}'")
"""
SUB_SRT_NEW = """    elif (shaped := _srt_to_styled_ass(srt_path, style_string)):
        vf = (f"ass=filename='{_escape_ffmpeg_filter_value(shaped)}'"
              f":fontsdir='{safe_fonts_dir}':shaping=complex")
    else:
        vf = (f"subtitles=filename='{safe_srt_path}':fontsdir='{safe_fonts_dir}'"
              f":charenc=UTF-8:force_style='{style_string}'")
"""


def patch_subtitles(repo):
    subs = pathlib.Path(repo) / "subtitles.py"
    src = subs.read_text(encoding="utf-8")
    if SUB_MARKER in src:
        print("subtitles.py already patched")
        return
    if SUB_ASS_OLD not in src or SUB_SRT_OLD not in src:
        sys.exit("subtitles.py changed upstream; patch anchor not found, nothing modified")
    src = src.replace(SUB_ASS_OLD, SUB_ASS_NEW, 1).replace(SUB_SRT_OLD, SUB_SRT_NEW, 1)
    src = src.replace("\n\ndef subtitles_filter(", "\n" + SUB_HELPER + "\n\ndef subtitles_filter(", 1)
    subs.write_text(src, encoding="utf-8")
    print("subtitles.py patched: captions burn with complex text shaping")


def patch(repo):
    hooks = pathlib.Path(repo) / "hooks.py"
    src = hooks.read_text(encoding="utf-8")
    if MARKER in src:
        print("hooks.py already patched")
        return
    if ANCHOR not in src:
        sys.exit("hooks.py changed upstream; patch anchor not found, nothing modified")
    src = src.replace(ANCHOR, ANCHOR + CALL, 1)
    src = src.replace("\n\ndef create_hook_image(", "\n" + HELPER + "\n\ndef create_hook_image(", 1)
    hooks.write_text(src, encoding="utf-8")
    print("hooks.py patched: non-Latin hook text now uses a matching font")


if __name__ == "__main__":
    target = sys.argv[1] if len(sys.argv) > 1 else "."
    patch(target)
    patch_subtitles(target)
