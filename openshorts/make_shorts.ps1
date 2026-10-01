<#
  make_shorts.ps1 - paste a YouTube link, get vertical shorts. Free and open source.

  Downloads the video on YOUR PC (home internet is not blocked by YouTube, unlike
  Colab), uploads it to your OpenShorts running on Colab, waits for the clips and
  saves them to a "shorts" folder next to this script (or -OutDir).

  Usage (PowerShell):
    powershell -ExecutionPolicy Bypass -File make_shorts.ps1 -Url "https://youtu.be/..." -Server "https://xxxx.trycloudflare.com"

  -Server : the "MCP connector URL" or the "Dashboard" link printed by the Colab
            one-cell setup (with or without /mcp at the end). It is remembered, so
            next time only -Url is needed until Colab gives you a new link.
#>
param(
    [string]$Url = "",
    [string]$VideoFile = "",    # use a video already on disk instead of downloading -Url
    [string]$Server = "",
    [int]$Clips = 0,
    [switch]$UseChromeCookies,
    [int]$MaxHeight = 1080,     # source resolution cap; 1440 gives sharper vertical crops (bigger files)
    [string]$OutDir = "",       # where the shorts go; default: a "shorts" folder next to this script
    [double]$MaxUploadMB = 95   # Cloudflare's free tunnel rejects request bodies over 100 MB
)
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"   # Invoke-WebRequest is very slow with the progress bar on

# Everything lives next to this script (e.g. F:\Openshort\openshorts-main): nothing on C:.
$ServerFile = Join-Path $PSScriptRoot ".openshorts_server"
$oldServerFile = Join-Path $HOME ".openshorts_server"
if (-not (Test-Path $ServerFile) -and (Test-Path $oldServerFile)) { Copy-Item $oldServerFile $ServerFile }

# Windows PowerShell 5.1 decodes JSON without a charset as Latin-1, turning Hindi
# into "à¤..." garbage; read the bytes as UTF-8 ourselves and print UTF-8.
try { [Console]::OutputEncoding = [Text.Encoding]::UTF8 } catch { }
function Get-Json($uri) {
    $r = Invoke-WebRequest $uri -UseBasicParsing -TimeoutSec 60
    return ([Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json)
}
# Colab answers 502 while its backend restarts; retry for ~2 minutes before giving up.
function Invoke-Retry([scriptblock]$Action, [string]$What) {
    for ($try = 1; $try -le 8; $try++) {
        try { return & $Action } catch {
            $code = 0
            if ($_.Exception.Response) { $code = [int]$_.Exception.Response.StatusCode }
            if ($code -ne 0 -and $code -lt 500) { throw }
            Write-Host "  Colab not answering ($What, attempt $try/8), retrying in 15 s..." -ForegroundColor Yellow
            Start-Sleep -Seconds 15
        }
    }
    throw "Colab did not answer. Check the Colab tab: if it disconnected, re-run cell 1 and use the new link with -Server."
}
function Step($msg) { Write-Host "`n==> $msg" -ForegroundColor Cyan }
function Have($cmd) { return [bool](Get-Command $cmd -ErrorAction SilentlyContinue) }

# --- Server address ---------------------------------------------------------
if (-not $Server -and (Test-Path $ServerFile)) { $Server = (Get-Content $ServerFile -Raw).Trim() }
if (-not $Server) { $Server = Read-Host "Paste the Colab link (Dashboard or MCP URL)" }
$Server = $Server.Trim().TrimEnd("/")
if ($Server.EndsWith("/mcp")) { $Server = $Server.Substring(0, $Server.Length - 4) }
try {
    $health = Invoke-RestMethod "$Server/health" -TimeoutSec 20
} catch {
    Write-Host "Can't reach OpenShorts at $Server. Is Colab still running? Run the one-cell setup and use the new link." -ForegroundColor Red
    exit 1
}
Set-Content -Path $ServerFile -Value $Server

# --- Rights (OpenShorts requires it) ----------------------------------------
$ok = Read-Host "Do you own this video or have permission to use it? (y/n)"
if ($ok -notmatch '^(y|yes)$') { Write-Host "Stopped: only clip videos you own or have rights to."; exit 1 }

# --- Tools: yt-dlp + ffmpeg -------------------------------------------------
$needYt = -not $VideoFile   # yt-dlp only matters when downloading from a link
if (($needYt -and -not (Have "yt-dlp")) -or -not (Have "ffmpeg")) {
    Step "Installing yt-dlp and ffmpeg (one time)"
    if ($needYt -and -not (Have "yt-dlp")) { winget install --id yt-dlp.yt-dlp -e --accept-source-agreements --accept-package-agreements | Out-Null }
    if (-not (Have "ffmpeg")) { winget install --id Gyan.FFmpeg -e --accept-source-agreements --accept-package-agreements | Out-Null }
    $env:Path = [Environment]::GetEnvironmentVariable("Path", "Machine") + ";" + [Environment]::GetEnvironmentVariable("Path", "User")
    if (($needYt -and -not (Have "yt-dlp")) -or -not (Have "ffmpeg")) {
        Write-Host "Installed. Close and reopen PowerShell, then run the same command again." -ForegroundColor Yellow
        exit 1
    }
}

# --- Download on this PC ----------------------------------------------------
# Temporary full-length download, kept next to the script (not C:\...\Temp) and
# deleted once the shorts are saved. Leftovers from failed runs go after 3 days.
$tempRoot = Join-Path $PSScriptRoot "temp"
New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
Get-ChildItem $tempRoot -Directory -Filter "openshorts_*" -ErrorAction SilentlyContinue |
    Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-3) } | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
$work = Join-Path $tempRoot ("openshorts_" + [guid]::NewGuid().ToString("N").Substring(0, 8))
New-Item -ItemType Directory -Path $work | Out-Null
$src = Join-Path $work "source.mp4"
if (-not $Url -and -not $VideoFile) { Write-Host "Give -Url (YouTube link) or -VideoFile (a video on disk)." -ForegroundColor Red; exit 1 }
if ($VideoFile) {
    if (-not (Test-Path $VideoFile)) { Write-Host "File not found: $VideoFile" -ForegroundColor Red; exit 1 }
    $src = (Resolve-Path $VideoFile).Path
} else {
Step "Downloading the video (best quality up to ${MaxHeight}p)"
# Highest resolution in ANY codec. Requiring H.264 (avc1) used to fall back to
# 720p/480p, because YouTube often serves 1080p+ only as VP9/AV1, and the 9:16
# crop then had to stretch a ~405 px wide slice to 1080 px (blurry shorts).
$dlArgs = @("-f", "bv*[height<=$MaxHeight]+ba/b[height<=$MaxHeight]/b", "-S", "res,fps,vcodec:h264,acodec:m4a",
            "--merge-output-format", "mp4", "--no-playlist", "--no-cache-dir", "-o", $src)
if ($UseChromeCookies) { $dlArgs += @("--cookies-from-browser", "chrome") }
& yt-dlp @dlArgs $Url
if ($LASTEXITCODE -ne 0 -or -not (Test-Path $src)) {
    Write-Host "Download failed. If YouTube asks you to sign in, close Chrome fully and run again with -UseChromeCookies" -ForegroundColor Red
    exit 1
}
}
$original = $src

# --- Fit under the tunnel's upload limit: split, don't shrink ---------------
# Cloudflare's free tunnel takes ~100 MB per upload. Long videos are cut into
# parts with stream copy (no re-encode, full quality) and each part becomes its
# own OpenShorts job; all shorts land in one folder.
$parts = @($src)
$sizeMB = (Get-Item $src).Length / 1MB
if ($sizeMB -gt $MaxUploadMB) {
    $duration = [double](& ffprobe -v error -show_entries format=duration -of csv=p=0 $src)
    $n = [math]::Ceiling($sizeMB / ($MaxUploadMB * 0.8))
    for ($attempt = 0; $attempt -lt 5; $attempt++) {
        $segSeconds = [math]::Ceiling($duration / $n)
        Step ("Video is {0:N0} MB: splitting into {1} parts of ~{2} min (no quality loss)" -f $sizeMB, $n, [math]::Round($segSeconds / 60, 1))
        Get-ChildItem $work -Filter "part_*.mp4" -ErrorAction SilentlyContinue | Remove-Item -Force
        & ffmpeg -hide_banner -loglevel error -y -i $src -map 0:v:0 -map 0:a:0? -c copy -f segment `
            -segment_time $segSeconds -reset_timestamps 1 (Join-Path $work "part_%02d.mp4")
        if ($LASTEXITCODE -ne 0) { Write-Host "Splitting failed." -ForegroundColor Red; exit 1 }
        $files = @(Get-ChildItem $work -Filter "part_*.mp4" | Sort-Object Name)
        if (-not ($files | Where-Object { $_.Length / 1MB -gt $MaxUploadMB })) { break }
        $n++   # a cut landed late on a keyframe and a part is still too big: cut finer
    }
    # OpenShorts needs at least ~45 s of material per job; drop a tiny tail part.
    $parts = @($files | Where-Object {
        [double](& ffprobe -v error -show_entries format=duration -of csv=p=0 $_.FullName) -ge 50
    } | ForEach-Object { $_.FullName })
    if (-not $parts) { Write-Host "Could not split the video into usable parts." -ForegroundColor Red; exit 1 }
}

if (-not $OutDir) { $OutDir = Join-Path $PSScriptRoot "shorts" }
New-Item -ItemType Directory -Path $OutDir -Force | Out-Null
$dest = Join-Path $OutDir ("shorts_" + (Get-Date -Format "yyyyMMdd_HHmmss"))

# Gemini already writes post text for every clip; save it next to the videos,
# in the same order as the zip (clip_01, clip_02, ...), ready to copy-paste.
function Save-Captions($status, [string]$folder) {
    $clips = @()
    if ($status.result -and $status.result.clips) { $clips = @($status.result.clips) }
    if (-not $clips) { return }
    $sb = New-Object System.Text.StringBuilder
    for ($c = 0; $c -lt $clips.Count; $c++) {
        $x = $clips[$c]
        [void]$sb.AppendLine(("===== clip_{0:D2} =====" -f ($c + 1)))
        if ($x.viral_hook_text) { [void]$sb.AppendLine("HOOK (first 3 seconds): $($x.viral_hook_text)") }
        if ($x.video_title_for_youtube_short) { [void]$sb.AppendLine("YOUTUBE SHORTS TITLE: $($x.video_title_for_youtube_short)") }
        if ($x.video_description_for_instagram) { [void]$sb.AppendLine("INSTAGRAM CAPTION:"); [void]$sb.AppendLine([string]$x.video_description_for_instagram) }
        if ($x.video_description_for_tiktok) { [void]$sb.AppendLine("TIKTOK / YOUTUBE DESCRIPTION:"); [void]$sb.AppendLine([string]$x.video_description_for_tiktok) }
        [void]$sb.AppendLine("")
    }
    $file = Join-Path $folder "captions.txt"
    [IO.File]::WriteAllText($file, $sb.ToString(), (New-Object System.Text.UTF8Encoding($true)))
    Write-Host "  Titles, captions and hooks saved to $file"
}

function Invoke-Part([string]$file, [int]$index, [int]$total) {
    $label = ""
    if ($total -gt 1) { $label = " (part $index of $total)" }

    Step ("Uploading {0:N0} MB to OpenShorts{1}" -f ((Get-Item $file).Length / 1MB), $label)
    try {
        $slot = Invoke-Retry { Invoke-RestMethod -Method Post "$Server/api/uploads" -ContentType "application/json" -Body '{"filename":"source.mp4"}' } "reserve upload"
        Invoke-Retry { Invoke-WebRequest -Method Put "$Server/api/uploads/$($slot.upload_id)" -InFile $file -ContentType "video/mp4" -TimeoutSec 3600 -UseBasicParsing | Out-Null } "upload" | Out-Null
    } catch {
        Write-Host "`n$_" -ForegroundColor Red
        return $false
    }

    $job = @{ upload_id = $slot.upload_id; acknowledged = $true; auto_hook = $true; captions = $true }
    if ($Clips -gt 0) { $job.target_clips = $Clips }
    try {
        $started = Invoke-RestMethod -Method Post "$Server/api/process" -ContentType "application/json" -Body ($job | ConvertTo-Json)
    } catch {
        Write-Host "OpenShorts refused the job: $($_.ErrorDetails.Message)" -ForegroundColor Red
        return $false
    }
    $jobId = $started.job_id
    Step "Making shorts$label (job $jobId). Usually a few minutes on the Colab GPU..."

    $seen = 0
    while ($true) {
        Start-Sleep -Seconds 15
        try { $st = Get-Json "$Server/api/status/$jobId" } catch { Write-Host "  (can't reach Colab, retrying...)"; continue }
        $logs = @($st.logs)
        for ($i = $seen; $i -lt $logs.Count; $i++) {
            $line = ([string]$logs[$i]).Trim()
            if ($line -and $line -notmatch '^(\[debug\]|\[\d+\.\d+s ->|W0000|INFO:|WARNING: All log|Warning: You are sending|\^|File "|Creating new Ultralytics|View Ultralytics|Update Settings|Analyzing Scenes)') {
                if ($line.Length -gt 140) { $line = $line.Substring(0, 140) + "..." }
                Write-Host "  $line"
            }
        }
        $seen = $logs.Count
        if ($st.status -eq "completed") { break }
        if ($st.status -eq "failed") {
            Write-Host "`nThe job failed. Last log lines:" -ForegroundColor Red
            $logs | Select-Object -Last 8 | ForEach-Object { Write-Host "  $_" }
            return $false
        }
    }

    $target = $dest
    if ($total -gt 1) { $target = Join-Path $dest "part$index" }
    $zip = Join-Path $work "shorts_$index.zip"
    Step "Downloading your shorts$label"
    Invoke-Retry { Invoke-WebRequest "$Server/api/jobs/$jobId/download-all" -OutFile $zip -TimeoutSec 3600 -UseBasicParsing } "download" | Out-Null
    Expand-Archive -Path $zip -DestinationPath $target -Force
    Remove-Item $zip -Force -ErrorAction SilentlyContinue
    Save-Captions $st $target
    return $true
}

$ok = 0
for ($k = 0; $k -lt $parts.Count; $k++) {
    if (Invoke-Part $parts[$k] ($k + 1) $parts.Count) { $ok++ }
}

if ($ok -eq 0) {
    Write-Host "`nNo shorts were made. Your video is saved, no need to download again. After fixing Colab, run:" -ForegroundColor Yellow
    Write-Host "  powershell -ExecutionPolicy Bypass -File .\make_shorts.ps1 -VideoFile `"$original`" -Server `"NEW-COLAB-LINK`""
    exit 1
}
if ($ok -lt $parts.Count) {
    Write-Host ("`n{0} of {1} parts worked; the video is kept at {2} so you can retry with -VideoFile." -f $ok, $parts.Count, $original) -ForegroundColor Yellow
} else {
    Remove-Item $work -Recurse -Force -ErrorAction SilentlyContinue
}
Write-Host "`nDone! Your shorts are in: $dest" -ForegroundColor Green
Write-Host "Post them: YouTube app -> + -> Upload a video (vertical and under 3 min = a Short)."
try { Start-Process explorer.exe $dest } catch { }
