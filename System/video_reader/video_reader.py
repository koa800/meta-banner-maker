#!/usr/bin/env python3
"""Video Reader — Loom / YouTube URLからTranscript+キーフレーム画像を自動抽出

使い方:
  python3 video_reader.py "https://www.loom.com/share/xxxxx"
  python3 video_reader.py "https://www.youtube.com/watch?v=xxxxx"
  python3 video_reader.py "https://youtu.be/xxxxx"
"""

import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

OUTPUT_BASE = Path.home() / "Downloads" / "video_reader"
YT_DLP = "/opt/homebrew/bin/yt-dlp"
FFMPEG = "/opt/homebrew/bin/ffmpeg"

# --- URL判定 ---

_LOOM_RE = re.compile(r"loom\.com/share/([a-f0-9]{32})")
_YT_RE = re.compile(
    r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})"
)


def detect_source(url: str) -> tuple[str, str]:
    """URLからソース種別とvideo_idを返す。未対応なら例外"""
    m = _LOOM_RE.search(url)
    if m:
        return "loom", m.group(1)
    m = _YT_RE.search(url)
    if m:
        return "youtube", m.group(1)
    raise ValueError(
        f"未対応のURL: {url}\n"
        "対応: loom.com/share/... / youtube.com/watch?v=... / youtu.be/..."
    )


# --- メタデータ ---

def fetch_metadata(url: str, source: str, out_dir: Path) -> dict:
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
        "source": source,
        "url": url,
    }
    (out_dir / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2)
    )
    return meta


# --- Transcript ---

def fetch_transcript(url: str, source: str, out_dir: Path) -> bool:
    """字幕をダウンロードしてプレーンテキストに変換"""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # YouTube: 手動字幕 → 自動生成字幕の順で試す
        # Loom: --write-subs のみ
        if source == "youtube":
            # まず手動字幕（日本語優先）
            ok = _try_download_subs(
                url, tmp_path,
                ["--write-subs", "--sub-lang", "ja,en", "--sub-format", "vtt"],
            )
            if not ok:
                # 自動生成字幕
                ok = _try_download_subs(
                    url, tmp_path,
                    ["--write-auto-subs", "--sub-lang", "ja,en",
                     "--sub-format", "vtt"],
                )
        else:
            ok = _try_download_subs(
                url, tmp_path,
                ["--write-subs", "--sub-format", "vtt"],
            )

        if ok:
            # VTTファイルを探す（日本語優先）
            vtt_files = sorted(tmp_path.glob("*.vtt"))
            ja_files = [f for f in vtt_files if ".ja" in f.name]
            vtt = ja_files[0] if ja_files else (vtt_files[0] if vtt_files else None)
            if vtt:
                plain, timestamped = _parse_vtt(vtt.read_text(encoding="utf-8"))
                if plain.strip():
                    (out_dir / "transcript.txt").write_text(plain)
                    (out_dir / "transcript_ts.txt").write_text(timestamped)
                    return True

    # フォールバック: JSONのsubtitleフィールド or description
    return _fetch_transcript_from_json(url, out_dir)


def _try_download_subs(url: str, tmp_path: Path, extra_args: list) -> bool:
    """yt-dlpで字幕DLを試みる。VTTが1つでもあればTrue"""
    r = subprocess.run(
        [YT_DLP, *extra_args, "--skip-download", "-o", str(tmp_path / "sub"), url],
        capture_output=True, text=True, timeout=60,
    )
    return len(list(tmp_path.glob("*.vtt"))) > 0


def _fetch_transcript_from_json(url: str, out_dir: Path) -> bool:
    """JSON metadataからsubtitle URLを直接取得するフォールバック"""
    r = subprocess.run(
        [YT_DLP, "--dump-json", "--no-download", url],
        capture_output=True, text=True, timeout=60,
    )
    if r.returncode != 0:
        return False
    info = json.loads(r.stdout)

    # subtitles → automatic_captions の順で探す
    for field in ("subtitles", "automatic_captions"):
        subs = info.get(field, {})
        # 日本語 → 英語 → 任意の言語
        for lang in ["ja", "en"] + list(subs.keys()):
            for fmt in subs.get(lang, []):
                sub_url = fmt.get("url", "")
                if not sub_url:
                    continue
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

    # YouTube description が長い場合はそれを保存
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
        if not line or line == "WEBVTT":
            continue
        if line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        # タイムスタンプ行
        if "-->" in line:
            current_ts = line.split("-->")[0].strip()
            parts = current_ts.split(":")
            if len(parts) == 3:
                h, m, s = parts
                s = s.split(".")[0]
                current_ts = f"{h}:{m}:{s}" if int(h) > 0 else f"{m}:{s}"
            continue
        # キュー番号スキップ
        if re.match(r"^\d+$", line):
            continue
        # HTMLタグ・VTTポジションタグ除去
        text = re.sub(r"<[^>]+>", "", line)
        # YouTube自動字幕の重複排除（position/align等のメタも除去）
        text = re.sub(r"align:start position:\d+%", "", text).strip()
        if text and text not in seen:
            seen.add(text)
            plain_parts.append(text)
            ts_parts.append(f"[{current_ts}] {text}")

    return "\n".join(plain_parts), "\n".join(ts_parts)


# --- フレーム抽出 ---

def extract_frames(url: str, duration: int, out_dir: Path) -> int:
    """動画をDL→ffmpegでキーフレーム抽出→動画削除"""
    frames_dir = out_dir / "frames"
    frames_dir.mkdir(exist_ok=True)

    # フレーム間隔: 人間の視聴体験に近い密度（5秒間隔デフォルト）
    interval = 5  # デフォルト5秒ごと
    if duration > 3600:
        interval = 10  # 1時間超: 10秒ごと

    # タイムアウト: 動画長+120秒（余裕）、最低600秒
    dl_timeout = max(600, duration + 120)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_video = Path(tmp) / "video.mp4"
        r = subprocess.run(
            [YT_DLP,
             "-f", "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best",
             "-o", str(tmp_video), url],
            capture_output=True, text=True, timeout=dl_timeout,
        )
        if r.returncode != 0:
            print(f"動画DL失敗: {r.stderr.strip()}", file=sys.stderr)
            return 0

        r = subprocess.run(
            [FFMPEG, "-i", str(tmp_video),
             "-vf", f"fps=1/{interval},scale=640:-1",
             "-q:v", "5",
             str(frames_dir / "frame_%03d.jpg")],
            capture_output=True, text=True, timeout=dl_timeout,
        )
        if r.returncode != 0:
            print(f"フレーム抽出失敗: {r.stderr.strip()}", file=sys.stderr)
            return 0

    # タイムスタンプ付きリネーム
    frames = sorted(frames_dir.glob("frame_*.jpg"))
    for i, f in enumerate(frames):
        sec = i * interval
        f.rename(frames_dir / f"frame_{i:03d}_{sec}s.jpg")

    return len(frames)


# --- 要約 ---

def generate_summary(out_dir: Path, meta: dict, has_transcript: bool, frame_count: int):
    """summary.txt 生成"""
    source_label = {"loom": "Loom", "youtube": "YouTube"}.get(
        meta.get("source", ""), meta.get("source", "")
    )
    dur = meta.get("duration", 0)
    dur_str = f"{dur // 60}分{dur % 60}秒" if dur >= 60 else f"{dur}秒"

    lines = [
        f"# {meta.get('title', 'Untitled')}",
        f"ソース: {source_label}",
        f"投稿者: {meta.get('uploader', '不明')}",
        f"長さ: {dur_str}",
        "",
    ]

    if has_transcript:
        transcript = (out_dir / "transcript.txt").read_text()
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


# --- main ---

def main():
    parser = argparse.ArgumentParser(
        description="Loom/YouTube動画からTranscript+キーフレームを抽出"
    )
    parser.add_argument("url", help="Loom or YouTube URL")
    parser.add_argument("--no-frames", action="store_true",
                        help="フレーム抽出をスキップ")
    args = parser.parse_args()

    # 1. URL判定
    source, video_id = detect_source(args.url)
    out_dir = OUTPUT_BASE / f"{source}_{video_id}"
    out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "success",
        "output_dir": str(out_dir),
        "source": source,
        "video_id": video_id,
    }

    # 2. メタデータ
    try:
        meta = fetch_metadata(args.url, source, out_dir)
        result["title"] = meta.get("title", "")
        result["duration"] = meta.get("duration", 0)
    except Exception as e:
        result["status"] = "error"
        result["error"] = f"メタデータ取得失敗: {e}"
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    # 3. Transcript
    try:
        has_transcript = fetch_transcript(args.url, source, out_dir)
        result["transcript_available"] = has_transcript
    except Exception as e:
        has_transcript = False
        result["transcript_available"] = False
        print(f"Transcript取得エラー: {e}", file=sys.stderr)

    # 4-5. フレーム抽出
    frame_count = 0
    if not args.no_frames:
        try:
            frame_count = extract_frames(
                args.url, meta.get("duration", 0), out_dir
            )
        except Exception as e:
            print(f"フレーム抽出エラー: {e}", file=sys.stderr)
    result["frame_count"] = frame_count

    # 6. 要約
    generate_summary(out_dir, meta, has_transcript, frame_count)

    # 7. transcript本文をJSON出力に含める（coordinatorが内容を理解するため）
    if has_transcript:
        transcript_path = out_dir / "transcript.txt"
        if transcript_path.exists():
            transcript_text = transcript_path.read_text(encoding="utf-8")
            result["transcript_text"] = transcript_text[:3000]

    # 8. 結果出力
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
