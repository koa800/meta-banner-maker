// Quick Translator — Content Script
// テキスト選択を検知して翻訳ポップアップを表示

(() => {
  let popup = null;
  let debounceTimer = null;
  let isEnabled = true;

  // 初期状態を取得
  chrome.runtime.sendMessage({ type: 'getState' }, (res) => {
    if (res) isEnabled = res.enabled;
  });

  // ON/OFF状態変更を受信
  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === 'stateChanged') {
      isEnabled = msg.enabled;
      if (!isEnabled) removePopup();
    }
  });

  // 日本語判定（ひらがな・カタカナ・漢字が50%以上なら日本語）
  function isJapanese(text) {
    const jpChars = text.match(/[\u3040-\u309F\u30A0-\u30FF\u4E00-\u9FFF]/g);
    if (!jpChars) return false;
    const alphaNum = text.replace(/[\s\d\p{P}]/gu, '');
    return jpChars.length / (alphaNum.length || 1) > 0.5;
  }

  // パスワード風テキスト判定
  function isPasswordLike(text) {
    if (text.length > 100) return false;
    // 英数字+記号のみで構成、スペースなし、8文字以上
    return /^[^\s]{8,}$/.test(text) && /[A-Za-z]/.test(text)
      && /\d/.test(text) && /[^A-Za-z0-9]/.test(text);
  }

  // ポップアップ削除
  function removePopup() {
    if (popup) {
      popup.classList.add('qt-fadeout');
      setTimeout(() => { popup?.remove(); popup = null; }, 200);
    }
  }

  // ポップアップ表示
  function showPopup(text, x, y) {
    removePopup();

    popup = document.createElement('div');
    popup.className = 'qt-popup';
    popup.textContent = text;

    document.body.appendChild(popup);

    // 画面外にはみ出さないよう位置調整
    const rect = popup.getBoundingClientRect();
    const maxX = window.innerWidth - rect.width - 10;
    const maxY = window.innerHeight - rect.height - 10;
    popup.style.left = Math.min(Math.max(10, x), maxX) + 'px';
    popup.style.top = Math.min(Math.max(10, y + 15), maxY) + 'px';
  }

  // テキスト選択イベント
  document.addEventListener('mouseup', (e) => {
    if (!isEnabled) return;

    // ポップアップ自体のクリックは無視
    if (e.target.closest?.('.qt-popup')) return;

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
      const sel = window.getSelection();
      const text = sel?.toString().trim();

      if (!text || text.length < 2 || text.length > 5000) {
        removePopup();
        return;
      }

      if (isJapanese(text) || isPasswordLike(text)) {
        removePopup();
        return;
      }

      // 翻訳リクエスト
      chrome.runtime.sendMessage({ type: 'translate', text }, (res) => {
        if (chrome.runtime.lastError || !res || res.error) {
          removePopup();
          return;
        }

        // 翻訳結果が元テキストと同じなら表示しない
        if (res.result === text) {
          removePopup();
          return;
        }

        showPopup(res.result, e.pageX, e.pageY);
      });
    }, 300);
  });

  // クリックでポップアップを閉じる
  document.addEventListener('mousedown', (e) => {
    if (popup && !e.target.closest?.('.qt-popup')) {
      removePopup();
    }
  });

  // スクロールでポップアップを閉じる
  document.addEventListener('scroll', removePopup, { passive: true });
})();
