#!/usr/bin/env python3
from __future__ import annotations
"""Video Reader — Loom / YouTube / 直mp4 URLからTranscript+キーフレーム画像を自動抽出

使い方:
  python3 video_reader.py "https://www.loom.com/share/xxxxx"
  python3 video_reader.py "https://www.youtube.com/watch?v=xxxxx"
  python3 video_reader.py "https://youtu.be/xxxxx"
  python3 video_reader.py "https://video-xxx.fbcdn.net/...mp4?..."
"""

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

OUTPUT_BASE = Path(
    os.environ.get("VIDEO_READER_OUTPUT_BASE", str(Path.home() / "Downloads" / "video_reader"))
)
YT_DLP = "/opt/homebrew/bin/yt-dlp"
FFMPEG = "/opt/homebrew/bin/ffmpeg"
WHISPER_MODEL = os.environ.get("VIDEO_READER_WHISPER_MODEL", "base")
WHISPER_DOWNLOAD_ROOT = Path(
    os.environ.get(
        "VIDEO_READER_WHISPER_ROOT",
        str(Path(__file__).resolve().parent.parent / "data" / "whisper_models"),
    )
)
DEFAULT_MAX_SECONDS = int(os.environ.get("VIDEO_READER_MAX_SECONDS", "0") or "0")
_WHISPER_MODELS: dict[str, object] = {}

# --- URL判定 ---

_LOOM_RE = re.compile(r"loom\.com/share/([a-f0-9]{32})")
_YT_RE = re.compile(
    r"(?:youtube\.com/watch\?.*v=|youtu\.be/|youtube\.com/shorts/)"
    r"([A-Za-z0-9_-]{11})"
)
_DIRECT_MP4_RE = re.compile(r"https?://[^\s]+\.mp4(?:\?[^\s]+)?$")


def detect_source(url: str) -> tuple[str, str]:
    """URLからソース種別とvideo_idを返す。未対応なら例外"""
    m = _LOOM_RE.search(url)
    if m:
        return "loom", m.group(1)
    m = _YT_RE.search(url)
    if m:
        return "youtube", m.group(1)
    if _DIRECT_MP4_RE.match(url):
        return "direct_mp4", hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    raise ValueError(
        f"未対応のURL: {url}\n"
        "対応: loom.com/share/... / youtube.com/watch?v=... / youtu.be/... / 直mp4 URL"
    )


# --- メタデータ ---

def _probe_direct_duration(url: str) -> int:
    r = subprocess.run(
        [
            "/opt/homebrew/bin/ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            url,
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe失敗: {r.stderr.strip()}")
    return int(float(r.stdout.strip() or "0"))


def fetch_metadata(url: str, source: str, out_dir: Path, title_hint: str = "") -> dict:
    """yt-dlpでメタデータ取得"""
    if source == "direct_mp4":
        meta = {
            "title": title_hint or f"direct_mp4_{out_dir.name}",
            "duration": _probe_direct_duration(url),
            "uploader": "meta_direct",
            "source": source,
            "url": url,
        }
        (out_dir / "metadata.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2)
        )
        return meta

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

def _format_seconds_label(seconds: float) -> str:
    whole = int(seconds)
    minutes, sec = divmod(whole, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def _transcribe_direct_video(
    url: str,
    out_dir: Path,
    *,
    whisper_model: str = WHISPER_MODEL,
    max_seconds: int | None = None,
) -> bool:
    WHISPER_DOWNLOAD_ROOT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = Path(tmp) / "audio.wav"
        cmd = [
            FFMPEG,
            "-y",
            "-i",
            url,
        ]
        if max_seconds and max_seconds > 0:
            cmd.extend(["-t", str(max_seconds)])
        cmd.extend(
            [
                "-vn",
                "-acodec",
                "pcm_s16le",
                "-ar",
                "16000",
                "-ac",
                "1",
                str(audio_path),
            ]
        )
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
        if r.returncode != 0 or not audio_path.exists():
            raise RuntimeError(f"音声抽出失敗: {r.stderr.strip()}")

        import whisper

        model = _WHISPER_MODELS.get(whisper_model)
        if model is None:
            model = whisper.load_model(whisper_model, download_root=str(WHISPER_DOWNLOAD_ROOT))
            _WHISPER_MODELS[whisper_model] = model
        with open(os.devnull, "w", encoding="utf-8") as sink, redirect_stdout(sink), redirect_stderr(sink):
            result = model.transcribe(str(audio_path), language="ja", fp16=False, verbose=False)

    segments = result.get("segments", [])
    plain_parts = [segment.get("text", "").strip() for segment in segments if segment.get("text")]
    timestamped_parts = [
        f"[{_format_seconds_label(segment.get('start', 0.0))}] {segment.get('text', '').strip()}"
        for segment in segments
        if segment.get("text")
    ]
    plain = " ".join(part for part in plain_parts if part).strip()
    timestamped = "\n".join(part for part in timestamped_parts if part).strip()
    if not plain:
        return False

    (out_dir / "transcript.txt").write_text(plain, encoding="utf-8")
    (out_dir / "transcript_ts.txt").write_text(timestamped, encoding="utf-8")
    return True


def fetch_transcript(
    url: str,
    source: str,
    out_dir: Path,
    *,
    whisper_model: str = WHISPER_MODEL,
    max_seconds: int | None = None,
) -> bool:
    """字幕をダウンロードしてプレーンテキストに変換"""
    if source == "direct_mp4":
        return _transcribe_direct_video(
            url,
            out_dir,
            whisper_model=whisper_model,
            max_seconds=max_seconds,
        )

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

def extract_frames(
    url: str,
    duration: int,
    out_dir: Path,
    *,
    source: str = "",
    max_seconds: int | None = None,
) -> int:
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
        input_path = url
        if source != "direct_mp4":
            tmp_video = Path(tmp) / "video.mp4"
            r = subprocess.run(
                [
                    YT_DLP,
                    "-f",
                    "bestvideo[ext=mp4][height<=720]+bestaudio[ext=m4a]/best[ext=mp4][height<=720]/best",
                    "-o",
                    str(tmp_video),
                    url,
                ],
                capture_output=True,
                text=True,
                timeout=dl_timeout,
            )
            if r.returncode != 0:
                print(f"動画DL失敗: {r.stderr.strip()}", file=sys.stderr)
                return 0
            input_path = str(tmp_video)

        cmd = [FFMPEG, "-i", str(input_path)]
        if max_seconds and max_seconds > 0:
            cmd.extend(["-t", str(max_seconds)])
        cmd.extend(
            [
                "-vf",
                f"fps=1/{interval},scale=640:-1",
                "-q:v",
                "5",
                str(frames_dir / "frame_%03d.jpg"),
            ]
        )
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=dl_timeout)
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
    source_label = {"loom": "Loom", "youtube": "YouTube", "direct_mp4": "Direct MP4"}.get(
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


# --- transcript 要約（長い動画用） ---

SUMMARIZE_THRESHOLD = 3000  # これ以上の transcript は要約する
SUMMARIZE_MODEL = "claude-sonnet-4-5-20241022"


def summarize_transcript(transcript: str, meta: dict) -> str | None:
    """長い transcript を Sonnet で要約する。APIキー未設定時は None"""
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        # config.json からフォールバック
        config_path = Path(__file__).resolve().parent.parent / "line_bot_local" / "config.json"
        if config_path.exists():
            try:
                cfg = json.loads(config_path.read_text(encoding="utf-8"))
                api_key = cfg.get("anthropic_api_key", "")
            except Exception:
                pass
    if not api_key:
        return None

    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        title = meta.get("title", "")
        duration = meta.get("duration", 0)
        dur_str = f"{duration // 60}分{duration % 60}秒" if duration >= 60 else f"{duration}秒"

        response = client.messages.create(
            model=SUMMARIZE_MODEL,
            max_tokens=800,
            system="あなたは動画の内容を正確に要約するアシスタントです。",
            messages=[{
                "role": "user",
                "content": (
                    f"以下は「{title}」（{dur_str}）の動画のTranscriptです。\n\n"
                    f"この動画の内容を以下の形式で要約してください:\n"
                    f"1. 概要（2-3文）\n"
                    f"2. 主要な手順・ポイント（箇条書き）\n"
                    f"3. 重要なキーワード・固有名詞\n\n"
                    f"---\n{transcript[:8000]}\n---"
                ),
            }],
        )
        return response.content[0].text.strip()
    except Exception as e:
        print(f"Transcript要約エラー: {e}", file=sys.stderr)
        return None


def process_video_url(
    url: str,
    *,
    out_dir: Path | None = None,
    no_frames: bool = False,
    whisper_model: str = WHISPER_MODEL,
    max_seconds: int | None = None,
    title_hint: str = "",
) -> dict:
    source, video_id = detect_source(url)
    target_out_dir = out_dir or OUTPUT_BASE / f"{source}_{video_id}"
    target_out_dir.mkdir(parents=True, exist_ok=True)

    result = {
        "status": "success",
        "output_dir": str(target_out_dir),
        "source": source,
        "video_id": video_id,
    }

    meta = fetch_metadata(url, source, target_out_dir, title_hint=title_hint)
    result["title"] = meta.get("title", "")
    result["duration"] = meta.get("duration", 0)

    has_transcript = fetch_transcript(
        url,
        source,
        target_out_dir,
        whisper_model=whisper_model,
        max_seconds=max_seconds,
    )
    result["transcript_available"] = has_transcript

    frame_count = 0
    if not no_frames:
        frame_count = extract_frames(
            url,
            meta.get("duration", 0),
            target_out_dir,
            source=source,
            max_seconds=max_seconds,
        )
    result["frame_count"] = frame_count

    generate_summary(target_out_dir, meta, has_transcript, frame_count)

    if has_transcript:
        transcript_path = target_out_dir / "transcript.txt"
        if transcript_path.exists():
            transcript_text = transcript_path.read_text(encoding="utf-8")
            if len(transcript_text) > SUMMARIZE_THRESHOLD:
                summary = summarize_transcript(transcript_text, meta)
                if summary:
                    result["transcript_summary"] = summary
                    result["transcript_text"] = transcript_text[:1000]
                else:
                    result["transcript_text"] = transcript_text[:3000]
            else:
                result["transcript_text"] = transcript_text

    return result


# --- main ---

def main():
    parser = argparse.ArgumentParser(
        description="Loom/YouTube/直mp4動画からTranscript+キーフレームを抽出"
    )
    parser.add_argument("url", help="Loom or YouTube URL")
    parser.add_argument("--no-frames", action="store_true",
                        help="フレーム抽出をスキップ")
    parser.add_argument("--whisper-model", default=WHISPER_MODEL,
                        help="直mp4 URL を文字起こしする Whisper モデル")
    parser.add_argument("--max-seconds", type=int, default=DEFAULT_MAX_SECONDS,
                        help="先頭何秒までを読むか。0なら全文")
    parser.add_argument("--title-hint", default="",
                        help="直mp4 URL のときに使うタイトル補助")
    args = parser.parse_args()
    try:
        result = process_video_url(
            args.url,
            no_frames=args.no_frames,
            whisper_model=args.whisper_model,
            max_seconds=args.max_seconds or None,
            title_hint=args.title_hint,
        )
    except Exception as e:
        result = {"status": "error", "error": str(e), "url": args.url}
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(1)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
