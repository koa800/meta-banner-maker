// Quick Translator — Service Worker
// Google Translate API中継 + ON/OFF状態管理

let enabled = true;

// 起動時に保存状態を復元
chrome.storage.local.get('enabled', (data) => {
  if (data.enabled !== undefined) enabled = data.enabled;
  updateIcon();
});

// アイコンクリックでON/OFF切替
chrome.action.onClicked.addListener(async (tab) => {
  enabled = !enabled;
  chrome.storage.local.set({ enabled });
  updateIcon();

  // 全タブに状態を通知
  const tabs = await chrome.tabs.query({});
  for (const t of tabs) {
    chrome.tabs.sendMessage(t.id, { type: 'stateChanged', enabled }).catch(() => {});
  }
});

function updateIcon() {
  chrome.action.setBadgeText({ text: enabled ? '' : 'OFF' });
  chrome.action.setBadgeBackgroundColor({ color: '#666' });
}

// content scriptからの翻訳リクエストを処理
chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'getState') {
    sendResponse({ enabled });
    return false;
  }

  if (msg.type === 'translate') {
    if (!enabled) {
      sendResponse({ error: 'disabled' });
      return false;
    }

    translateText(msg.text)
      .then(result => sendResponse({ result }))
      .catch(err => sendResponse({ error: err.message }));

    return true; // 非同期レスポンス
  }
});

async function translateText(text) {
  const url = 'https://translate.googleapis.com/translate_a/single'
    + '?client=gtx&sl=auto&tl=ja&dt=t&q=' + encodeURIComponent(text);

  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status}`);

  const data = await res.json();
  // data[0] は翻訳セグメントの配列、各要素の[0]が翻訳文
  return data[0].map(seg => seg[0]).join('');
}
