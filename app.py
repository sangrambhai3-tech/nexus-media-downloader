from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, HttpUrl
from urllib.parse import urlparse
import ipaddress, socket, requests, os, uuid, mimetypes
from pathlib import Path

ROOT = Path(__file__).parent
DOWNLOADS = ROOT / "downloads"
DOWNLOADS.mkdir(exist_ok=True)

app = FastAPI(title="Nexus Media Downloader")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")

class DownloadRequest(BaseModel):
    url: HttpUrl

def validate_public_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(400, "Please enter a valid public HTTP or HTTPS media URL.")
    host = parsed.hostname.lower()
    if host in ("localhost",) or host.endswith((".local", ".internal")):
        raise HTTPException(400, "Private/local addresses are not allowed.")
    try:
        infos = socket.getaddrinfo(host, None)
        for info in infos:
            addr = ipaddress.ip_address(info[4][0])
            if not addr.is_global:
                raise HTTPException(400, "Private/local addresses are not allowed.")
    except socket.gaierror:
        raise HTTPException(400, "The URL host could not be resolved.")
    return parsed

@app.get("/", response_class=HTMLResponse)
def home():
    return (ROOT / "static" / "index.html").read_text(encoding="utf-8")

@app.post("/api/download")
def download_media(data: DownloadRequest):
    url = str(data.url)
    validate_public_url(url)
    try:
        with requests.get(url, stream=True, timeout=(10, 45), allow_redirects=False,
                          headers={"User-Agent": "NexusMediaDownloader/1.0"}) as r:
            if 300 <= r.status_code < 400:
                raise HTTPException(400, "This link redirects. Please use a direct media-file URL.")
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "").split(";")[0].lower()
            if not (content_type.startswith("video/") or content_type.startswith("audio/")):
                raise HTTPException(415, "This is not a direct audio/video file URL. Use an authorized direct media link.")
            length = int(r.headers.get("Content-Length", "0") or 0)
            if length > 1024 * 1024 * 1024:
                raise HTTPException(413, "Files larger than 1 GB are not supported.")
            ext = mimetypes.guess_extension(content_type) or (".mp4" if content_type.startswith("video/") else ".mp3")
            name = f"nexus_{uuid.uuid4().hex[:12]}{ext}"
            target = DOWNLOADS / name
            total = 0
            with target.open("wb") as f:
                for chunk in r.iter_content(1024 * 256):
                    if chunk:
                        total += len(chunk)
                        if total > 1024 * 1024 * 1024:
                            f.close()
                            target.unlink(missing_ok=True)
                            raise HTTPException(413, "Files larger than 1 GB are not supported.")
                        f.write(chunk)
    except HTTPException:
        raise
    except requests.RequestException:
        raise HTTPException(400, "Could not fetch this media file. Check the link and try again.")
    return FileResponse(target, filename=f"nexus_download{ext}", media_type=content_type,
                        background=None)

@app.get("/health")
def health():
    return {"status": "ok"}
