#!/usr/bin/env python3
"""ClipTranslator — メニューバー常駐クリップボード翻訳アプリ

Cmd+C でコピーした英語テキストを自動翻訳し、macOS通知で表示。
メニューバーから翻訳結果をコピー可能。
"""

import json
import re
import threading
import time
import urllib.parse
import urllib.request

import rumps


class ClipTranslator(rumps.App):
    def __init__(self):
        super().__init__("翻", quit_button=None)
        self.last_result = ""
        self.enabled = True

        # メニュー構成
        self.toggle_item = rumps.MenuItem("ON", callback=self.toggle)
        self.copy_item = rumps.MenuItem("翻訳結果をコピー", callback=self.copy_result)
        self.copy_item.set_callback(None)  # 初期は無効
        self.quit_item = rumps.MenuItem("終了", callback=self.quit_app)

        self.menu = [self.toggle_item, self.copy_item, None, self.quit_item]

        # クリップボード監視スレッド開始
        self._monitor_thread = threading.Thread(target=self._monitor_clipboard, daemon=True)
        self._monitor_thread.start()

    def toggle(self, sender):
        self.enabled = not self.enabled
        sender.title = "ON" if self.enabled else "OFF"
        self.title = "翻" if self.enabled else "翻(停止)"

    def copy_result(self, _):
        if self.last_result:
            _set_clipboard(self.last_result)

    def quit_app(self, _):
        rumps.quit_application()

    def _monitor_clipboard(self):
        """NSPasteboard.changeCount() を監視してクリップボード変更を検知"""
        from AppKit import NSPasteboard

        pb = NSPasteboard.generalPasteboard()
        last_count = pb.changeCount()

        while True:
            time.sleep(0.5)
            if not self.enabled:
                last_count = pb.changeCount()
                continue

            count = pb.changeCount()
            if count == last_count:
                continue
            last_count = count

            text = pb.stringForType_("public.utf8-plain-text")
            if not text:
                continue

            text = text.strip()
            if not text or len(text) < 2 or len(text) > 5000:
                continue

            if _is_japanese(text) or _is_password_like(text):
                continue

            try:
                result = _translate(text)
                if result and result != text:
                    self.last_result = result
                    self.copy_item.set_callback(self.copy_result)

                    # 長い翻訳は通知用に切り詰め
                    display = result[:200] + "..." if len(result) > 200 else result
                    rumps.notification(
                        title="翻訳",
                        subtitle="",
                        message=display,
                        sound=False,
                    )
            except Exception:
                pass  # 静かに失敗


def _is_japanese(text):
    """日本語文字が50%以上ならTrue"""
    jp_chars = re.findall(r'[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]', text)
    if not jp_chars:
        return False
    alpha_num = re.sub(r'[\s\d\W]', '', text)
    return len(jp_chars) / max(len(alpha_num), 1) > 0.5


def _is_password_like(text):
    """パスワード風テキスト判定"""
    if len(text) > 100:
        return False
    if ' ' in text:
        return False
    has_alpha = bool(re.search(r'[A-Za-z]', text))
    has_digit = bool(re.search(r'\d', text))
    has_symbol = bool(re.search(r'[^A-Za-z0-9]', text))
    return len(text) >= 8 and has_alpha and has_digit and has_symbol


def _translate(text):
    """Google Translate APIで翻訳"""
    url = (
        "https://translate.googleapis.com/translate_a/single"
        "?client=gtx&sl=auto&tl=ja&dt=t&q=" + urllib.parse.quote(text)
    )
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=10) as res:
        data = json.loads(res.read().decode())
    return "".join(seg[0] for seg in data[0] if seg[0])


def _set_clipboard(text):
    """クリップボードにテキストを設定"""
    from AppKit import NSPasteboard, NSPasteboardTypeString

    pb = NSPasteboard.generalPasteboard()
    pb.clearContents()
    pb.setString_forType_(text, NSPasteboardTypeString)


if __name__ == "__main__":
    ClipTranslator().run()
