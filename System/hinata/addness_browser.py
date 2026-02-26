"""
Addness ブラウザ操作モジュール（日向エージェント用）

- Playwrightで日向のGoogleアカウントからAddnessにログイン
- ゴールページへの遷移
- 「AIと相談」との対話
- コメント投稿
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional

from playwright.sync_api import sync_playwright, Page, BrowserContext
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

logger = logging.getLogger("hinata.addness")

SCRIPT_DIR = Path(__file__).parent
SYSTEM_DIR = SCRIPT_DIR.parent
CHROME_PROFILE_DIR = SYSTEM_DIR / "data" / "hinata_chrome_profile"
SESSION_PATH = SYSTEM_DIR / "data" / "hinata_session.json"
GOOGLE_CREDS_PATH = SYSTEM_DIR / "credentials" / "hinata_google.json"


def _load_google_creds() -> dict:
    """Google認証情報を読み込む。"""
    if not GOOGLE_CREDS_PATH.exists():
        return {}
    try:
        return json.load(open(GOOGLE_CREDS_PATH, "r", encoding="utf-8"))
    except Exception as e:
        logger.error(f"Google認証情報の読み込み失敗: {e}")
        return {}


def launch_browser(playwright, headless: bool = True) -> BrowserContext:
    """日向用のブラウザを起動する。"""
    CHROME_PROFILE_DIR.mkdir(parents=True, exist_ok=True)

    context = playwright.chromium.launch_persistent_context(
        user_data_dir=str(CHROME_PROFILE_DIR),
        headless=headless,
        viewport={"width": 1280, "height": 900},
        args=[
            "--remote-debugging-port=9222",
            "--disable-blink-features=AutomationControlled",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-infobars",
        ],
        ignore_default_args=["--enable-automation"],
    )
    return context


def setup_page(context: BrowserContext) -> Page:
    """ページを作成してbot検知対策を設定する。"""
    page = context.new_page()
    page.add_init_script(
        "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
    )
    return page


def is_logged_in(page: Page) -> bool:
    """Addnessにログイン済みかを確認する。"""
    url = page.url
    return "sign-in" not in url and "sign-up" not in url and "addness.com" in url


def _auto_google_login(page: Page) -> bool:
    """
    Googleログイン画面を自動で通過する。
    認証情報ファイルからメール・パスワードを読み込んで入力する。
    """
    creds = _load_google_creds()
    if not creds.get("email") or not creds.get("password"):
        logger.warning("Google認証情報が不足。自動ログイン不可")
        return False

    try:
        # メールアドレス入力
        email_input = page.locator('input[type="email"]')
        if email_input.count() > 0:
            logger.info("Googleメールアドレスを入力中...")
            email_input.fill(creds["email"])
            time.sleep(1)
            page.locator('button:has-text("次へ"), #identifierNext').first.click()
            time.sleep(5)

        # パスワード入力
        pw_input = page.locator('input[type="password"]')
        if pw_input.count() > 0:
            logger.info("Googleパスワードを入力中...")
            pw_input.fill(creds["password"])
            time.sleep(1)
            page.locator('button:has-text("次へ"), #passwordNext').first.click()
            time.sleep(5)

        # TOTP入力（2段階認証が有効な場合）
        totp_input = page.locator('input[type="tel"]#totpPin, input[name="totpPin"]')
        if totp_input.count() > 0 and creds.get("totp_secret"):
            try:
                import pyotp
                totp = pyotp.TOTP(creds["totp_secret"])
                code = totp.now()
                logger.info("TOTP コードを入力中...")
                totp_input.fill(code)
                time.sleep(1)
                page.locator('button:has-text("次へ")').first.click()
                time.sleep(5)
            except ImportError:
                logger.error("pyotp がインストールされていません")
                return False

        logger.info("Google自動ログイン完了")
        return True

    except Exception as e:
        logger.error(f"Google自動ログイン失敗: {e}")
        return False


def login(page: Page, start_url: str, timeout_ms: int = 300_000) -> bool:
    """
    Addnessにログインする。
    セッションが残っていれば自動ログイン。
    Google認証情報があれば自動でGoogleログインを通過する。
    """
    logger.info("Addnessにアクセス中...")
    page.goto(start_url, wait_until="networkidle", timeout=60_000)
    time.sleep(3)

    if is_logged_in(page):
        logger.info("ログイン済み")
        return True

    logger.info("ログインが必要です。自動ログインを試みます...")

    # Googleログインボタンを探してクリック
    google_btn = page.locator(
        'button:has-text("Google"), a:has-text("Google"), '
        '[data-provider="google"], [class*="google"]'
    )
    if google_btn.count() > 0:
        google_btn.first.click()
        time.sleep(5)
    else:
        # Addnessが直接Googleログインにリダイレクトする場合もある
        logger.info("Googleボタンが見つからない。リダイレクトを待機...")
        time.sleep(3)

    # Googleログイン画面かどうか確認
    if "accounts.google.com" in page.url:
        if _auto_google_login(page):
            # ログイン後、Addnessにリダイレクトされるのを待つ
            try:
                page.wait_for_url("**/goals/**", timeout=60_000)
                time.sleep(3)
                logger.info("自動ログイン成功")
                return True
            except PlaywrightTimeoutError:
                # リダイレクトがgoals以外の場合
                if is_logged_in(page):
                    logger.info("自動ログイン成功（ゴール以外のページ）")
                    return True
                logger.warning("自動ログイン後のリダイレクト待ちタイムアウト")

    # 自動ログイン失敗時はフォールバック（手動待機）
    logger.info("自動ログイン失敗。手動ログインを待機します...")
    try:
        page.wait_for_url("**/goals/**", timeout=timeout_ms)
        time.sleep(3)
        logger.info("手動ログイン成功")
        return True
    except PlaywrightTimeoutError:
        logger.error("ログインタイムアウト")
        return False


def find_my_goal(page: Page, my_goal_url: Optional[str] = None) -> Optional[str]:
    """
    自分のゴールに遷移する。

    Args:
        page: Playwrightページ
        my_goal_url: config.jsonで指定されたゴールURL（あれば直接遷移）

    Returns:
        ゴールページのURL。見つからなければNone。
    """
    try:
        # 設定でゴールURLが指定されていれば直接遷移
        if my_goal_url:
            page.goto(my_goal_url, wait_until="networkidle", timeout=30_000)
            time.sleep(2)
            if "/goals/" in page.url and "root" not in page.url:
                logger.info(f"設定のゴールURLに遷移: {my_goal_url}")
                return my_goal_url
            else:
                logger.warning(f"設定のゴールURLへの遷移に失敗: {page.url}")

        # 自動探索: 「実行」ページから自分のゴールを探す
        page.goto("https://www.addness.com/todo/execution", wait_until="networkidle", timeout=30_000)
        time.sleep(3)

        # ゴールリンクを探す（/goals/root は除外）
        goal_links = page.locator('a[href*="/goals/"]').all()
        for link in goal_links:
            href = link.get_attribute("href")
            if href and "/goals/root" not in href and "/goals/" in href:
                goal_url = f"https://www.addness.com{href}" if href.startswith("/") else href
                page.goto(goal_url, wait_until="networkidle", timeout=30_000)
                time.sleep(2)
                logger.info(f"実行ページから自分のゴールを発見: {goal_url}")
                return goal_url

        logger.warning("ゴールが見つかりませんでした")
        return None

    except Exception as e:
        logger.error(f"ゴール探索に失敗: {e}")
        return None


def goto_goal(page: Page, goal_url: str) -> bool:
    """指定のゴールページに遷移する。"""
    try:
        page.goto(goal_url, wait_until="networkidle", timeout=30_000)
        time.sleep(2)
        logger.info(f"ゴールページに遷移: {goal_url}")
        return True
    except PlaywrightTimeoutError:
        logger.error(f"ゴールページ遷移タイムアウト: {goal_url}")
        return False


def open_ai_consultation(page: Page) -> bool:
    """「AIと相談」パネルを開く。"""
    try:
        ai_btn = page.locator("text=AIと相談")
        if ai_btn.count() > 0:
            ai_btn.first.click()
            time.sleep(2)
            logger.info("「AIと相談」パネルを開いた")
            return True
        else:
            logger.warning("「AIと相談」ボタンが見つからない")
            return False
    except Exception as e:
        logger.error(f"AIと相談の操作に失敗: {e}")
        return False


def start_ai_conversation(page: Page) -> bool:
    """「会話を開始」ボタンをクリックする。"""
    try:
        start_btn = page.locator("text=会話を開始")
        if start_btn.count() > 0:
            start_btn.first.click()
            time.sleep(2)
            logger.info("AI会話を開始")
            return True
        else:
            logger.info("「会話を開始」ボタンなし（既に会話中の可能性）")
            return True
    except Exception as e:
        logger.error(f"会話開始に失敗: {e}")
        return False


def send_ai_message(page: Page, message: str, wait_seconds: int = 30) -> Optional[str]:
    """
    「AIと相談」にメッセージを送信し、返答を取得する。

    Args:
        page: Playwrightページ
        message: 送信するメッセージ
        wait_seconds: AI返答の最大待ち時間

    Returns:
        AIからの返答テキスト。取得できなければNone。
    """
    try:
        # AIチャットの入力欄を探す（「AIに相談...」プレースホルダー）
        chat_input = page.locator(
            'input[placeholder*="AIに相談"], '
            'textarea[placeholder*="AIに相談"], '
            'input[placeholder*="AI"], '
            'textarea[placeholder*="AI"], '
            '[contenteditable="true"]'
        ).last
        if chat_input.count() == 0:
            logger.error("AIチャット入力欄が見つからない")
            return None

        chat_input.click()
        time.sleep(0.5)
        chat_input.fill(message)
        time.sleep(0.5)

        # 送信（Enter or 送信ボタン）
        page.keyboard.press("Enter")
        logger.info(f"AIにメッセージ送信: {message[:50]}...")

        # AI返答を待つ
        time.sleep(5)  # 最低待ち時間
        response_text = _wait_for_ai_response(page, wait_seconds)
        return response_text

    except Exception as e:
        logger.error(f"AIメッセージ送信に失敗: {e}")
        return None


def _wait_for_ai_response(page: Page, max_wait: int = 30) -> Optional[str]:
    """AIの返答が完了するまで待ち、最新の返答を取得する。"""
    last_text = ""
    stable_count = 0

    for _ in range(max_wait):
        time.sleep(1)
        try:
            # チャットメッセージのコンテナから最新のAI返答を取得
            messages = page.locator('[class*="message"], [class*="chat"], [class*="response"]').all()
            if messages:
                current_text = messages[-1].inner_text()
                if current_text == last_text and current_text:
                    stable_count += 1
                    if stable_count >= 3:  # 3秒間テキストが変わらなければ完了
                        logger.info("AI返答を取得")
                        return current_text
                else:
                    stable_count = 0
                    last_text = current_text
        except Exception:
            continue

    if last_text:
        return last_text
    return None


def post_comment(page: Page, comment: str) -> bool:
    """ゴールページにコメントを投稿する。"""
    try:
        comment_input = page.locator(
            'textarea[placeholder*="コメント"], '
            '[placeholder*="コメントを送信"], '
            'textarea[placeholder*="メンション"]'
        ).first

        if comment_input.count() == 0:
            logger.error("コメント入力欄が見つからない")
            return False

        comment_input.click()
        time.sleep(0.5)
        comment_input.fill(comment)
        time.sleep(0.5)

        # Cmd+Enter で送信
        page.keyboard.press("Meta+Enter")
        time.sleep(2)
        logger.info(f"コメント投稿: {comment[:50]}...")
        return True

    except Exception as e:
        logger.error(f"コメント投稿に失敗: {e}")
        return False


def check_comments_for_instructions(page: Page) -> Optional[str]:
    """
    ゴールページのコメント欄から甲原さんの指示を確認する。
    最新のコメントで「日向」宛のメンションや指示を探す。
    """
    try:
        comments = page.locator('[class*="comment"], [class*="activity"], [class*="mention"]').all()
        if not comments:
            return None

        # 最新5件のコメントをチェック
        for comment in comments[-5:]:
            text = comment.inner_text()
            if "日向" in text or "@日向" in text or "ひなた" in text:
                logger.info(f"Addnessコメントで指示を発見: {text[:80]}...")
                return text

        return None
    except Exception as e:
        logger.error(f"コメント確認に失敗: {e}")
        return None


def get_goal_info(page: Page) -> dict:
    """現在のゴールページから情報を取得する。"""
    try:
        info = page.evaluate("""
            () => {
                const title = document.querySelector('h1, [class*="title"]');
                const body = document.body.innerText;
                return {
                    title: title ? title.innerText.trim() : '',
                    url: window.location.href,
                    text_content: body.substring(0, 5000)
                };
            }
        """)
        return info
    except Exception as e:
        logger.error(f"ゴール情報取得に失敗: {e}")
        return {"title": "", "url": page.url, "text_content": ""}
