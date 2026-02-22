#!/usr/bin/env python3
"""Local video download server using yt-dlp."""

import os
import subprocess
import json
import re
import uuid
import glob
from pathlib import Path
from typing import Optional

from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app, origins=["chrome-extension://*"])

DOWNLOAD_DIR = str(Path.home() / "Downloads")


def _sanitize_url(url: str) -> Optional[str]:
    """Basic URL validation."""
    url = url.strip()
    if re.match(r"^https?://", url):
        return url
    return None


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/info", methods=["GET"])
def info():
    url = request.args.get("url", "").strip()
    url = _sanitize_url(url)
    if not url:
        return jsonify({"status": "error", "message": "Invalid URL"}), 400

    try:
        result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return jsonify({"status": "error", "message": result.stderr.strip()}), 400

        data = json.loads(result.stdout)
        return jsonify({
            "status": "ok",
            "title": data.get("title", ""),
            "duration": data.get("duration"),
            "thumbnail": data.get("thumbnail", ""),
            "uploader": data.get("uploader", ""),
        })
    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Timeout fetching info"}), 504
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/download", methods=["POST"])
def download():
    data = request.get_json(silent=True) or {}
    url = _sanitize_url(data.get("url", ""))
    if not url:
        return jsonify({"status": "error", "message": "Invalid URL"}), 400

    outtmpl = os.path.join(DOWNLOAD_DIR, "%(title)s.%(ext)s")

    try:
        result = subprocess.run(
            [
                "yt-dlp",
                "-S", "vcodec:h264,acodec:aac",
                "--recode-video", "mp4",
                "-o", outtmpl,
                "--no-playlist",
                "--print", "after_move:filepath",
                url,
            ],
            capture_output=True, text=True, timeout=120,
        )

        if result.returncode != 0:
            return jsonify({"status": "error", "message": result.stderr.strip()}), 400

        filepath = result.stdout.strip().split("\n")[-1]
        filename = os.path.basename(filepath)

        return jsonify({
            "status": "ok",
            "filename": filename,
            "path": filepath,
        })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Download timed out (120s)"}), 504
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/screenshots", methods=["POST"])
def screenshots():
    data = request.get_json(silent=True) or {}
    url = _sanitize_url(data.get("url", ""))
    if not url:
        return jsonify({"status": "error", "message": "Invalid URL"}), 400

    tmp_video = f"/tmp/vdl_{uuid.uuid4().hex}.mp4"
    tmp_frames = f"/tmp/vdl_frames_{uuid.uuid4().hex}"

    try:
        # 1. Download video to temp file
        dl_result = subprocess.run(
            [
                "yt-dlp",
                "-S", "vcodec:h264,acodec:aac",
                "--recode-video", "mp4",
                "-o", tmp_video,
                "--no-playlist",
                url,
            ],
            capture_output=True, text=True, timeout=120,
        )
        if dl_result.returncode != 0:
            return jsonify({"status": "error", "message": dl_result.stderr.strip()}), 400

        # 2. Get duration with ffprobe
        probe_result = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_format", tmp_video,
            ],
            capture_output=True, text=True, timeout=15,
        )
        duration = float(json.loads(probe_result.stdout)["format"]["duration"])

        # 3. Fixed 2-second interval
        interval = 2.0

        # 4. Get title for folder name
        info_result = subprocess.run(
            ["yt-dlp", "--dump-json", "--no-download", url],
            capture_output=True, text=True, timeout=30,
        )
        title = "video"
        if info_result.returncode == 0:
            info_data = json.loads(info_result.stdout)
            title = re.sub(r'[\\/:*?"<>|]', '_', info_data.get("title", "video"))

        # 5. Extract frames with ffmpeg
        os.makedirs(tmp_frames, exist_ok=True)
        subprocess.run(
            [
                "ffmpeg", "-i", tmp_video,
                "-vf", f"fps=1/{interval}",
                "-q:v", "2",
                os.path.join(tmp_frames, "%03d.jpg"),
            ],
            capture_output=True, text=True, timeout=60,
        )

        # 6. Move to ~/Downloads/{title}_frames/
        folder_name = f"{title}_frames"
        dest_dir = os.path.join(DOWNLOAD_DIR, folder_name)
        os.makedirs(dest_dir, exist_ok=True)

        jpg_files = sorted(glob.glob(os.path.join(tmp_frames, "*.jpg")))
        for f in jpg_files:
            os.rename(f, os.path.join(dest_dir, os.path.basename(f)))

        count = len(jpg_files)

        return jsonify({
            "status": "ok",
            "folder": folder_name,
            "count": count,
        })

    except subprocess.TimeoutExpired:
        return jsonify({"status": "error", "message": "Processing timed out"}), 504
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500
    finally:
        # Cleanup temp files
        if os.path.exists(tmp_video):
            os.remove(tmp_video)
        if os.path.exists(tmp_frames):
            for f in glob.glob(os.path.join(tmp_frames, "*")):
                os.remove(f)
            os.rmdir(tmp_frames)


if __name__ == "__main__":
    print(f"Video downloader server starting on http://localhost:8765")
    print(f"Download directory: {DOWNLOAD_DIR}")
    app.run(host="127.0.0.1", port=8765, debug=False)
