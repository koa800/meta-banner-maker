const API = "http://localhost:8765";

const urlInput = document.getElementById("url");
const btnDownload = document.getElementById("download");
const btnScreenshots = document.getElementById("screenshots");
const statusEl = document.getElementById("status");

// Auto-fill with current tab URL if it looks like a video
chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
  const tabUrl = tabs[0]?.url || "";
  if (/instagram\.com\/reel|youtube\.com\/(watch|shorts)|youtu\.be\/|tiktok\.com/i.test(tabUrl)) {
    urlInput.value = tabUrl;
  }
});

btnDownload.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) return;

  setStatus("loading", '<span class="spinner"></span>ダウンロード中...');
  setButtons(true);

  try {
    const res = await fetch(`${API}/download`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (data.status === "ok") {
      setStatus("success", `保存完了: ${data.filename}`);
    } else {
      setStatus("error", `エラー: ${data.message}`);
    }
  } catch (e) {
    setStatus("error", "サーバーに接続できません。server.py を起動してください。");
  } finally {
    setButtons(false);
  }
});

btnScreenshots.addEventListener("click", async () => {
  const url = urlInput.value.trim();
  if (!url) return;

  setStatus("loading", '<span class="spinner"></span>画像抽出中...');
  setButtons(true);

  try {
    const res = await fetch(`${API}/screenshots`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (data.status === "ok") {
      setStatus("success", `${data.count}枚保存: ${data.folder}`);
    } else {
      setStatus("error", `エラー: ${data.message}`);
    }
  } catch (e) {
    setStatus("error", "サーバーに接続できません。server.py を起動してください。");
  } finally {
    setButtons(false);
  }
});

function setButtons(disabled) {
  btnDownload.disabled = disabled;
  btnScreenshots.disabled = disabled;
}

function setStatus(type, html) {
  statusEl.className = type;
  statusEl.innerHTML = html;
}
