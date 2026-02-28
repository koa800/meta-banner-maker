#!/usr/bin/env python3
"""Loom Video Reader — Loom URLからTranscript+キーフレーム画像を自動抽出"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OUTPUT_BASE = Path.home() / "Downloads" / "loom_reader"
YT_DLP = "/opt/homebrew/bin/yt-dlp"
FFMPEG = "/opt/homebrew/bin/ffmpeg"


def validate_url(url: str) -> str:
    """Loom URLからvideo_idを抽出。無効なら例外"""
    m = re.search(r"loom\.com/share/([a-f0-9]{32})", url)
    if not m:
        raise ValueError(f"無効なLoom URL: {url}")
    return m.group(1)


def fetch_metadata(url: str, out_dir: Path) -> dict:
    """yt-dlpでメタデータ取得"""
    r = subprocess.run(
        [YT_DLP, "--dump-json", "--no-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        raise RuntimeError(f"メタデータ取得失敗: {r.stderr.strip()}")
    info = json.loads(r.stdout)
    meta = {
        "title": info.get("title", ""),
        "duration": info.get("duration", 0),
        "uploader": info.get("uploader", ""),
        "url": url,
    }
    (out_dir / "metadata.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2))
    return meta


def fetch_transcript(url: str, out_dir: Path) -> bool:
    """VTT字幕をダウンロードしてプレーンテキストに変換"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        r = subprocess.run(
            [YT_DLP, "--write-subs", "--sub-format", "vtt",
             "--skip-download", "-o", str(tmp_path / "sub"), url],
            capture_output=True, text=True, timeout=60,
        )
        # VTTファイルを探す
        vtt_files = list(tmp_path.glob("*.vtt"))
        if not vtt_files:
            # yt-dlpのsubtitle抽出に失敗した場合、JSONからtranscript取得を試みる
            return _fetch_transcript_from_json(url, out_dir)

        vtt_text = vtt_files[0].read_text(encoding="utf-8")
        plain, timestamped = _parse_vtt(vtt_text)

        if not plain.strip():
            return False

        (out_dir / "transcript.txt").write_text(plain)
        (out_dir / "transcript_ts.txt").write_text(timestamped)
        return True


def _fetch_transcript_from_json(url: str, out_dir: Path) -> bool:
    """JSON metadataからsubtitle/descriptionを取得するフォールバック"""
    r = subprocess.run(
        [YT_DLP, "--dump-json", "--no-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        return False
    info = json.loads(r.stdout)

    # subtitlesフィールドを確認
    subs = info.get("subtitles", {})
    for lang, formats in subs.items():
        for fmt in formats:
            sub_url = fmt.get("url", "")
            if sub_url:
                sr = subprocess.run(
                    ["curl", "-sL", sub_url],
                    capture_output=True, text=True, timeout=30,
                )
                if sr.returncode == 0 and sr.stdout.strip():
                    plain, timestamped = _parse_vtt(sr.stdout)
                    if plain.strip():
                        (out_dir / "transcript.txt").write_text(plain)
                        (out_dir / "transcript_ts.txt").write_text(timestamped)
                        return True

    # descriptionにtranscriptが含まれる場合
    desc = info.get("description", "")
    if len(desc) > 100:
        (out_dir / "transcript.txt").write_text(desc)
        return True

    return False


def _parse_vtt(vtt: str) -> tuple[str, str]:
    """VTTをプレーンテキストとタイムスタンプ付きテキストに変換"""
    lines = vtt.split("\n")
    plain_parts = []
    ts_parts = []
    current_ts = ""
    seen = set()

    for line in lines:
        line = line.strip()
        if not line or line == "WEBVTT" or line.startswith("Kind:") or line.startswith("Language:"):
            continue
        # タイムスタンプ行
        if "-->" in line:
            current_ts = line.split("-->")[0].strip()
            # HH:MM:SS.mmm → MM:SS に簡略化
            parts = current_ts.split(":")
            if len(parts) == 3:
                h, m, s = parts
                s = s.split(".")[0]
                if int(h) > 0:
                    current_ts = f"{h}:{m}:{s}"
                else:
                    current_ts = f"{m}:{s}"
            continue
        # 数字のみの行（キュー番号）をスキップ
        if re.match(r"^\d+$", line):
            continue
        # HTMLタグ除去
        text = re.sub(r"<[^>]+>", "", line)
        if text and text not in seen:
            seen.add(text)
            plain_parts.append(text)
            ts_parts.append(f"[{current_ts}] {text}")

    return "\n".join(plain_parts), "\n".join(ts_parts)


def extract_frames(url: str, duration: int, out_dir: Path) -> int:
    """動画をDL→ffmpegでキーフレーム抽出→動画削除"""
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # フレーム間隔を動画長に応じて決定（5〜20枚目標）
    if duration <= 60:
        interval = max(5, duration // 10)
    elif duration <= 300:
        interval = 15
    elif duration <= 600:
        interval = 30
    else:
        interval = 60

    with tempfile.TemporaryDirectory() as tmp:
        tmp_video = Path(tmp) / "video.mp4"
        # 動画ダウンロード
        r = subprocess.run(
            [YT_DLP, "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
             "-o", str(tmp_video), url],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            print(f"動画DL失敗: {r.stderr.strip()}", file=sys.stderr)
            return 0

        # ffmpegでフレーム抽出
        r = subprocess.run(
            [FFMPEG, "-i", str(tmp_video),
             "-vf", f"fps=1/{interval}",
             "-q:v", "3",
             str(frames_dir / "frame_%03d.jpg")],
            capture_output=True, text=True, timeout=300,
        )
        if r.returncode != 0:
            print(f"フレーム抽出失敗: {r.stderr.strip()}", file=sys.stderr)
            return 0

    # フレームをリネーム（タイムスタンプ付き）
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    for i, f in enumerate(frames):
        sec = i * interval
        new_name = f"frame_{i:03d}_{sec}s.jpg"
        f.rename(frames_dir / new_name)

    return len(frames)


def generate_summary(out_dir: Path, meta: dict, has_transcript: bool, frame_count: int):
    """要約ファイル生成"""
    lines = [
        f"# {meta.get('title', 'Untitled')}",
        f"投稿者: {meta.get('uploader', '不明')}",
        f"長さ: {meta.get('duration', 0)}秒",
        "",
    ]
    if has_transcript:
        transcript = (out_dir / "transcript.txt").read_text()
        # 先頭500文字をプレビュー
        preview = transcript[:500]
        if len(transcript) > 500:
            preview += "..."
        lines.append("## Transcript（プレビュー）")
        lines.append(preview)
        lines.append(f"\n全文: transcript.txt ({len(transcript)}文字)")
    else:
        lines.append("## Transcript")
        lines.append("Transcriptは取得できませんでした。")

    lines.append(f"\n## フレーム画像")
    lines.append(f"{frame_count}枚のキーフレームを抽出: frames/")

    (out_dir / "summary.txt").write_text("\n".join(lines))


def main():
    parser = argparse.ArgumentParser(description="Loom動画からTranscript+キーフレームを抽出")
    parser.add_argument("url", help="Loom共有URL")
    parser.add_argument("--no-frames", action="store_true", help="フレーム抽出をスキップ")
    args = parser.parse_args()

    # 1. URL検証
    video_id = validate_url(args.url)
    out_dir = OUTPUT_BASE / video_id
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {"status": "success", "output_dir": str(out_dir), "video_id": video_id}

    # 2. メタデータ取得
    try:
        meta = fetch_metadata(args.url, out_dir)
        result["title"] = meta.get("title", "")
        result["duration"] = meta.get("duration", 0)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"メタデータ取得失敗: {e}"
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 3. Transcript取得
    try:
        has_transcript = fetch_transcript(args.url, out_dir)
        result["transcript_available"] = has_transcript
    except Exception as e:
        has_transcript = False
        result["transcript_available"] = False
        print(f"Transcript取得エラー: {e}", file=sys.stderr)

    # 4-5. フレーム抽出
    frame_count = 0
    if not args.no_frames:
        try:
            frame_count = extract_frames(args.url, meta.get("duration", 0), out_dir)
        except Exception as e:
            print(f"フレーム抽出エラー: {e}", file=sys.stderr)
    result["frame_count"] = frame_count

    # 6. 要約生成
    generate_summary(out_dir, meta, has_transcript, frame_count)

    # 8. 結果JSON出力
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
