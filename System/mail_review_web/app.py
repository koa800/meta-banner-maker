#!/usr/bin/env python3
"""
メール管理 Web UI
- personal / kohara アカウント切替
- 返信承認・削除確認、一括削除対応
"""

import os
import sys
from pathlib import Path
from flask import Flask, render_template_string, redirect, request, jsonify

SYSTEM_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SYSTEM_DIR))

import mail_manager

app = Flask(__name__)

ACCOUNTS = ["personal", "kohara"]
ACCOUNT_LABELS = {
    "personal": "個人 (koa800sea.nifs@gmail.com)",
    "kohara":   "会社 (kohara.kaito@team.addness.co.jp)",
}


def setup_account(account: str):
    mail_manager.DATA_DIR           = mail_manager.BASE_DIR / "mail_inbox_data" / account
    mail_manager.STATE_FILE         = mail_manager.DATA_DIR / "state.json"
    mail_manager.PENDING_FILE       = mail_manager.DATA_DIR / "pending.json"
    mail_manager.DELETE_REVIEW_FILE = mail_manager.DATA_DIR / "delete_review.json"
    mail_manager.DATA_DIR.mkdir(parents=True, exist_ok=True)


HTML = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>メール管理</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
       background: #f0f2f5; color: #1a1a1a; min-height: 100vh; }

.header { background: #1d4ed8; color: white; padding: 14px 20px;
          display: flex; align-items: center; gap: 12px;
          position: sticky; top: 0; z-index: 10;
          box-shadow: 0 2px 8px rgba(0,0,0,0.2); }
.header h1 { font-size: 1.1em; font-weight: 700; }
.tabs { display: flex; gap: 4px; margin-left: auto; }
.tab { padding: 6px 14px; border-radius: 6px; text-decoration: none;
       color: rgba(255,255,255,0.65); font-size: 0.88em; transition: all .15s; }
.tab:hover { color: white; background: rgba(255,255,255,0.12); }
.tab.active { background: rgba(255,255,255,0.22); color: white; font-weight: 600; }

.main { max-width: 780px; margin: 0 auto; padding: 18px 16px 40px; }

.flash { padding: 10px 14px; border-radius: 8px; margin-bottom: 14px;
         font-size: 0.9em; border: 1px solid; }
.flash.ok  { background: #d1fae5; border-color: #6ee7b7; color: #065f46; }
.flash.err { background: #fee2e2; border-color: #fca5a5; color: #7f1d1d; }

.count-bar { background: white; border-radius: 10px; padding: 10px 16px;
             margin-bottom: 18px; display: flex; gap: 20px; align-items: center;
             box-shadow: 0 1px 3px rgba(0,0,0,0.08); font-size: 0.9em; }
.count-item { display: flex; align-items: center; gap: 6px; color: #374151; }
.badge { color: white; font-size: 0.75em; padding: 2px 8px;
         border-radius: 99px; font-weight: 600; }
.badge.blue { background: #1d4ed8; }
.badge.red  { background: #ef4444; }
.acct-label { margin-left: auto; color: #9ca3af; font-size: 0.82em; }

.sec-header { display: flex; align-items: center; justify-content: space-between;
              margin: 22px 0 10px; }
.sec-title { font-size: 0.95em; font-weight: 700; color: #374151;
             display: flex; align-items: center; gap: 8px; }
.btn-bulk { padding: 6px 14px; border: none; border-radius: 7px;
            font-size: 0.82em; cursor: pointer; font-weight: 600;
            text-decoration: none; display: inline-block; transition: opacity .15s; }
.btn-bulk:hover { opacity: 0.82; }
.btn-bulk-del  { background: #ef4444; color: white; }
.btn-bulk-skip { background: #6b7280; color: white; }

.card { background: white; border-radius: 12px; padding: 16px;
        margin-bottom: 10px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
.from    { font-weight: 600; font-size: 0.93em; color: #111; }
.subject { color: #374151; font-size: 0.88em; margin: 4px 0 2px; }
.snippet { color: #6b7280; font-size: 0.83em; line-height: 1.5; margin: 6px 0; }
.reason  { font-size: 0.8em; color: #2563eb; margin-bottom: 8px; }
.suggested { background: #f0fdf4; border-left: 3px solid #22c55e;
             padding: 8px 12px; border-radius: 0 6px 6px 0;
             font-size: 0.86em; color: #166534; margin: 8px 0;
             white-space: pre-wrap; word-break: break-word; }
.no-reply { font-size: 0.82em; color: #9ca3af; margin: 4px 0 8px; font-style: italic; }
textarea { width: 100%; border: 1px solid #d1d5db; border-radius: 8px;
           padding: 8px 10px; font-size: 0.88em; resize: vertical;
           min-height: 80px; font-family: inherit; margin: 8px 0 0; line-height: 1.5; }
textarea:focus { outline: none; border-color: #2563eb;
                 box-shadow: 0 0 0 2px rgba(37,99,235,0.15); }
.btns { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px; }
.btn { padding: 8px 16px; border: none; border-radius: 8px; font-size: 0.86em;
       cursor: pointer; font-weight: 500; text-decoration: none;
       display: inline-block; transition: opacity .15s; }
.btn:hover { opacity: 0.85; }
.btn-send { background: #16a34a; color: white; }
.btn-hold { background: #f59e0b; color: white; }
.btn-del  { background: #ef4444; color: white; }
.btn-skip { background: #e5e7eb; color: #374151; }
.btn-folder { background: #8b5cf6; color: white; }
.empty { text-align: center; color: #9ca3af; padding: 28px;
         background: white; border-radius: 12px; font-size: 0.88em; }

/* モーダル */
.modal-overlay { display: none; position: fixed; top: 0; left: 0; right: 0; bottom: 0;
                 background: rgba(0,0,0,0.5); z-index: 100; align-items: center; justify-content: center; }
.modal-overlay.active { display: flex; }
.modal { background: white; border-radius: 14px; padding: 20px; width: 90%; max-width: 400px;
         max-height: 80vh; overflow-y: auto; box-shadow: 0 10px 40px rgba(0,0,0,0.3); }
.modal h2 { font-size: 1.05em; margin-bottom: 14px; color: #111; }
.modal-sender { background: #f3f4f6; padding: 8px 12px; border-radius: 8px;
                font-size: 0.85em; color: #374151; margin-bottom: 14px; word-break: break-all; }
.modal label { display: block; font-size: 0.85em; color: #374151; margin-bottom: 6px; font-weight: 500; }
.modal select, .modal input[type="text"] {
    width: 100%; padding: 10px 12px; border: 1px solid #d1d5db; border-radius: 8px;
    font-size: 0.9em; margin-bottom: 12px; }
.modal select:focus, .modal input:focus { outline: none; border-color: #8b5cf6; }
.modal-check { display: flex; align-items: center; gap: 8px; margin-bottom: 16px; font-size: 0.85em; }
.modal-check input { width: 18px; height: 18px; }
.modal-btns { display: flex; gap: 8px; }
.modal-btns .btn { flex: 1; text-align: center; padding: 10px; }
.btn-cancel { background: #e5e7eb; color: #374151; }
.btn-create { background: #8b5cf6; color: white; }
.new-label-row { display: flex; gap: 8px; margin-bottom: 12px; }
.new-label-row input { flex: 1; margin-bottom: 0; }
.new-label-row button { padding: 8px 14px; background: #22c55e; color: white;
                        border: none; border-radius: 8px; cursor: pointer; font-size: 0.85em; }
</style>
</head>
<body>
<div class="header">
  <h1>📬 メール管理</h1>
  <div class="tabs">
    {% for acc in accounts %}
    <a href="/?account={{ acc }}" class="tab {{ 'active' if acc == account else '' }}">
      {{ acc_labels[acc].split('(')[0].strip() }}
    </a>
    {% endfor %}
  </div>
</div>

<div class="main">
  {% if flash %}
  <div class="flash {{ 'err' if 'エラー' in flash else 'ok' }}">{{ flash }}</div>
  {% endif %}

  <div class="count-bar">
    <div class="count-item">✉️ 返信待ち <span class="badge blue">{{ pending|length }}</span></div>
    <div class="count-item">🗑️ 削除確認 <span class="badge red">{{ reviews|length }}</span></div>
    <span class="acct-label">{{ acc_labels[account] }}</span>
  </div>

  <!-- ===== 返信承認 ===== -->
  <div class="sec-header">
    <div class="sec-title">✉️ 返信承認 <span class="badge blue">{{ pending|length }}</span></div>
    {% if pending %}
    <a href="/bulk_clear_pending/{{ account }}"
       class="btn-bulk btn-bulk-del"
       onclick="return confirm('返信待ちをすべて削除して学習しますか？')">
      すべて削除して学習
    </a>
    {% endif %}
  </div>
  {% if pending %}
    {% for p in pending %}
    <div class="card">
      <div class="from">{{ p['from'] }}</div>
      <div class="subject">{{ p['subject'] }}</div>
      <div class="snippet">{{ p['snippet'][:150] }}{% if p['snippet']|length > 150 %}...{% endif %}</div>
      {% if p['suggested_reply'] %}
      <div class="suggested">{{ p['suggested_reply'] }}</div>
      {% else %}
      <div class="no-reply">（返信提案なし）</div>
      {% endif %}
      <form method="post" action="/reply/{{ account }}/{{ p['message_id'] }}">
        <textarea name="reply_text" placeholder="返信文を編集してから「送信」してください">{{ p['suggested_reply'] or '' }}</textarea>
        <div class="btns">
          <button class="btn btn-send" name="action" value="send">送信</button>
          <button class="btn btn-hold" name="action" value="hold">保留</button>
          <button class="btn btn-del"  name="action" value="delete">削除して学習</button>
          <button type="button" class="btn btn-folder" onclick="openFilterModal('{{ p['from'] }}', '{{ p['message_id'] }}')">📁 振り分け</button>
        </div>
      </form>
    </div>
    {% endfor %}
  {% else %}
  <div class="empty">✅ 返信待ちはありません</div>
  {% endif %}

  <!-- ===== 削除確認 ===== -->
  <div class="sec-header">
    <div class="sec-title">🗑️ 削除確認 <span class="badge red">{{ reviews|length }}</span></div>
    {% if reviews %}
    <a href="/bulk_delete/{{ account }}"
       class="btn-bulk btn-bulk-del"
       onclick="return confirm('削除確認待ちをすべてゴミ箱に移動して学習しますか？')">
      一括削除して学習
    </a>
    {% endif %}
  </div>
  {% if reviews %}
    {% for r in reviews %}
    <div class="card">
      <div class="from">{{ r['from'] }}</div>
      <div class="subject">{{ r['subject'] }}</div>
      <div class="snippet">{{ r['snippet'][:150] }}{% if r['snippet']|length > 150 %}...{% endif %}</div>
      <div class="reason">理由: {{ r['reason'] or '不明' }}</div>
      <div class="btns">
        <a href="/delete/{{ account }}/{{ r['message_id'] }}" class="btn btn-del">削除して学習</a>
        <a href="/keep/{{ account }}/{{ r['message_id'] }}"   class="btn btn-hold">保留</a>
        <button type="button" class="btn btn-folder" onclick="openFilterModal('{{ r['from'] }}', '{{ r['message_id'] }}')">📁 振り分け</button>
      </div>
    </div>
    {% endfor %}
  {% else %}
  <div class="empty">✅ 削除確認待ちはありません</div>
  {% endif %}
</div>

<!-- フィルター設定モーダル -->
<div class="modal-overlay" id="filterModal">
  <div class="modal">
    <h2>📁 フォルダ振り分け設定</h2>
    <div class="modal-sender" id="modalSender"></div>
    <label>既存のフォルダを選択:</label>
    <select id="labelSelect">
      <option value="">-- 選択してください --</option>
    </select>
    <label>または新しいフォルダを作成:</label>
    <div class="new-label-row">
      <input type="text" id="newLabelName" placeholder="フォルダ名を入力">
      <button type="button" onclick="createNewLabel()">作成</button>
    </div>
    <div class="modal-check">
      <input type="checkbox" id="skipInbox" checked>
      <span>受信トレイをスキップ（フォルダに直接入れる）</span>
    </div>
    <div class="modal-btns">
      <button class="btn btn-cancel" onclick="closeFilterModal()">キャンセル</button>
      <button class="btn btn-create" onclick="createFilter()">設定する</button>
    </div>
  </div>
</div>

<script>
const account = "{{ account }}";
let currentSender = "";
let currentMsgId = "";
let labels = [];

async function loadLabels() {
  try {
    const res = await fetch(`/api/labels/${account}`);
    const data = await res.json();
    if (data.labels) {
      labels = data.labels;
      const select = document.getElementById("labelSelect");
      select.innerHTML = '<option value="">-- 選択してください --</option>';
      labels.forEach(l => {
        const opt = document.createElement("option");
        opt.value = l.id;
        opt.textContent = l.name;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.error("ラベル取得エラー:", e);
  }
}

function openFilterModal(sender, msgId) {
  currentSender = sender;
  currentMsgId = msgId;
  document.getElementById("modalSender").textContent = sender;
  document.getElementById("labelSelect").value = "";
  document.getElementById("newLabelName").value = "";
  document.getElementById("skipInbox").checked = true;
  document.getElementById("filterModal").classList.add("active");
  loadLabels();
}

function closeFilterModal() {
  document.getElementById("filterModal").classList.remove("active");
}

async function createNewLabel() {
  const name = document.getElementById("newLabelName").value.trim();
  if (!name) { alert("フォルダ名を入力してください"); return; }
  try {
    const res = await fetch(`/api/create_label/${account}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({name})
    });
    const data = await res.json();
    if (data.label) {
      await loadLabels();
      document.getElementById("labelSelect").value = data.label.id;
      document.getElementById("newLabelName").value = "";
      alert(`フォルダ「${data.label.name}」を作成しました`);
    } else {
      alert("エラー: " + (data.error || "作成に失敗しました"));
    }
  } catch (e) {
    alert("エラー: " + e);
  }
}

async function createFilter() {
  const labelId = document.getElementById("labelSelect").value;
  const newName = document.getElementById("newLabelName").value.trim();
  const skipInbox = document.getElementById("skipInbox").checked;
  if (!labelId && !newName) {
    alert("フォルダを選択するか、新しいフォルダ名を入力してください");
    return;
  }
  try {
    const res = await fetch(`/api/filter/${account}`, {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({
        sender: currentSender,
        label_id: labelId,
        label_name: newName,
        skip_inbox: skipInbox,
        msg_id: currentMsgId
      })
    });
    const data = await res.json();
    if (data.ok) {
      alert(data.message);
      closeFilterModal();
      location.reload();
    } else {
      alert("エラー: " + (data.error || "失敗しました"));
    }
  } catch (e) {
    alert("エラー: " + e);
  }
}

document.getElementById("filterModal").addEventListener("click", function(e) {
  if (e.target === this) closeFilterModal();
});
</script>
</body>
</html>
"""


def base_redirect(account, flash):
    return redirect(f"/?account={account}&flash={flash}")


@app.route("/")
def index():
    account = request.args.get("account", "personal")
    if account not in ACCOUNTS:
        account = "personal"
    setup_account(account)
    return render_template_string(
        HTML,
        account=account,
        accounts=ACCOUNTS,
        acc_labels=ACCOUNT_LABELS,
        pending=mail_manager.load_pending(),
        reviews=mail_manager.load_delete_review(),
        flash=request.args.get("flash", ""),
    )


# ───────── 返信承認（1件） ─────────

@app.route("/reply/<account>/<msg_id>", methods=["POST"])
def reply_action(account, msg_id):
    if account not in ACCOUNTS:
        return base_redirect("personal", "不正なアカウント")
    setup_account(account)
    action     = request.form.get("action", "skip")
    reply_text = request.form.get("reply_text", "").strip()
    pending    = mail_manager.load_pending()
    item       = next((p for p in pending if p["message_id"] == msg_id), None)
    if not item:
        return base_redirect(account, "メールが見つかりません")
    remaining = [p for p in pending if p["message_id"] != msg_id]

    if action == "send":
        if not reply_text:
            return base_redirect(account, "エラー: 返信文が空です")
        try:
            service = mail_manager.get_gmail_service(account)
            orig = {
                "from":              item["from"],
                "subject":           item["subject"],
                "thread_id":         item["thread_id"],
                "message_id_header": item.get("message_id_header"),
            }
            if mail_manager.send_reply(service, orig, reply_text, item["from"]):
                mail_manager.save_pending(remaining)
                return base_redirect(account, f"✅ 返信を送信しました（{item['from']}）")
            return base_redirect(account, "エラー: 送信に失敗しました")
        except Exception as e:
            return base_redirect(account, f"エラー: {e}")

    elif action == "hold":
        mail_manager.save_pending(remaining)
        state = mail_manager.load_state()
        held = state.get("held_message_ids", [])
        if msg_id not in held:
            held.append(msg_id)
            state["held_message_ids"] = held
            mail_manager.save_state(state)
        try:
            service = mail_manager.get_gmail_service(account)
            mail_manager.archive_message(service, msg_id)
        except Exception:
            pass
        return base_redirect(account, f"✅ 保留しました（今後表示されません）")

    elif action == "delete":
        try:
            service = mail_manager.get_gmail_service(account)
            mail_manager.trash_message(service, msg_id)
            state     = mail_manager.load_state()
            count_map = state.get("not_needed_count", {})
            blocked   = set(state.get("blocked_senders", []))
            auto_del  = set(state.get("auto_delete_senders", []))
            sender    = item["from"]
            auto_del.add(sender)
            count_map[sender] = count_map.get(sender, 0) + 1
            state["auto_delete_senders"] = list(auto_del)
            state["not_needed_count"]    = count_map
            flash = f"✅ 削除して学習しました: {sender}"
            if count_map[sender] >= mail_manager.NOT_NEEDED_THRESHOLD and sender not in blocked:
                if mail_manager.create_block_filter(service, sender):
                    blocked.add(sender)
                    state["blocked_senders"] = list(blocked)
                    flash += "（ブロック済み）"
            mail_manager.save_state(state)
            mail_manager.save_pending(remaining)
            return base_redirect(account, flash)
        except Exception as e:
            return base_redirect(account, f"エラー: {e}")

    # skip
    return base_redirect(account, "スキップしました")


# ───────── 返信待ち 一括除外 ─────────

@app.route("/bulk_clear_pending/<account>")
def bulk_clear_pending(account):
    if account not in ACCOUNTS:
        return base_redirect("personal", "不正なアカウント")
    setup_account(account)
    pending   = mail_manager.load_pending()
    state     = mail_manager.load_state()
    count_map = state.get("not_needed_count", {})
    blocked   = set(state.get("blocked_senders", []))
    auto_del  = set(state.get("auto_delete_senders", []))
    try:
        service = mail_manager.get_gmail_service(account)
        newly_blocked = []
        for item in pending:
            mail_manager.trash_message(service, item["message_id"])
            sender = item["from"]
            auto_del.add(sender)
            count_map[sender] = count_map.get(sender, 0) + 1
            if count_map[sender] >= mail_manager.NOT_NEEDED_THRESHOLD and sender not in blocked:
                if mail_manager.create_block_filter(service, sender):
                    blocked.add(sender)
                    newly_blocked.append(sender)
        state["auto_delete_senders"] = list(auto_del)
        state["not_needed_count"]    = count_map
        state["blocked_senders"]     = list(blocked)
        mail_manager.save_state(state)
        mail_manager.save_pending([])
        flash = f"✅ {len(pending)} 件を削除して学習しました"
        if newly_blocked:
            flash += f"（{len(newly_blocked)} 件ブロック）"
        return base_redirect(account, flash)
    except Exception as e:
        return base_redirect(account, f"エラー: {e}")


# ───────── 削除確認（1件） ─────────

@app.route("/delete/<account>/<msg_id>")
def approve_delete(account, msg_id):
    if account not in ACCOUNTS:
        return base_redirect("personal", "不正なアカウント")
    setup_account(account)
    reviews   = mail_manager.load_delete_review()
    state     = mail_manager.load_state()
    count_map = state.get("not_needed_count", {})
    blocked   = set(state.get("blocked_senders", []))
    auto_del  = set(state.get("auto_delete_senders", []))
    item = next((r for r in reviews if r["message_id"] == msg_id), None)
    if not item:
        return base_redirect(account, "メールが見つかりません")
    remaining = [r for r in reviews if r["message_id"] != msg_id]
    try:
        service = mail_manager.get_gmail_service(account)
        mail_manager.trash_message(service, msg_id)
        sender = item["from"]
        auto_del.add(sender)
        state["auto_delete_senders"] = list(auto_del)
        count_map[sender] = count_map.get(sender, 0) + 1
        state["not_needed_count"] = count_map
        flash = f"✅ 削除しました: {sender}"
        if count_map[sender] >= mail_manager.NOT_NEEDED_THRESHOLD and sender not in blocked:
            if mail_manager.create_block_filter(service, sender):
                blocked.add(sender)
                state["blocked_senders"] = list(blocked)
                flash += "（ブロック済み）"
        mail_manager.save_state(state)
        mail_manager.save_delete_review(remaining)
        return base_redirect(account, flash)
    except Exception as e:
        return base_redirect(account, f"エラー: {e}")


# ───────── 削除確認 一括削除 ─────────

@app.route("/bulk_delete/<account>")
def bulk_delete(account):
    if account not in ACCOUNTS:
        return base_redirect("personal", "不正なアカウント")
    setup_account(account)
    reviews   = mail_manager.load_delete_review()
    state     = mail_manager.load_state()
    count_map = state.get("not_needed_count", {})
    blocked   = set(state.get("blocked_senders", []))
    auto_del  = set(state.get("auto_delete_senders", []))
    try:
        service = mail_manager.get_gmail_service(account)
        deleted = 0
        newly_blocked = []
        for item in reviews:
            mail_manager.trash_message(service, item["message_id"])
            sender = item["from"]
            auto_del.add(sender)
            count_map[sender] = count_map.get(sender, 0) + 1
            if count_map[sender] >= mail_manager.NOT_NEEDED_THRESHOLD and sender not in blocked:
                if mail_manager.create_block_filter(service, sender):
                    blocked.add(sender)
                    newly_blocked.append(sender)
            deleted += 1
        state["auto_delete_senders"] = list(auto_del)
        state["not_needed_count"]    = count_map
        state["blocked_senders"]     = list(blocked)
        mail_manager.save_state(state)
        mail_manager.save_delete_review([])
        flash = f"✅ {deleted} 件を一括削除しました"
        if newly_blocked:
            flash += f"（{len(newly_blocked)} 件ブロック）"
        return base_redirect(account, flash)
    except Exception as e:
        return base_redirect(account, f"エラー: {e}")


# ───────── 保留（削除確認から除外＋今後非表示） ─────────

@app.route("/keep/<account>/<msg_id>")
def keep_mail(account, msg_id):
    if account not in ACCOUNTS:
        return base_redirect("personal", "不正なアカウント")
    setup_account(account)
    reviews   = mail_manager.load_delete_review()
    remaining = [r for r in reviews if r["message_id"] != msg_id]
    mail_manager.save_delete_review(remaining)
    state = mail_manager.load_state()
    held = state.get("held_message_ids", [])
    if msg_id not in held:
        held.append(msg_id)
        state["held_message_ids"] = held
        mail_manager.save_state(state)
    try:
        service = mail_manager.get_gmail_service(account)
        mail_manager.archive_message(service, msg_id)
    except Exception:
        pass
    return base_redirect(account, "✅ 保留しました（今後表示されません）")


# ───────── ラベル・フィルター API ─────────

@app.route("/api/labels/<account>")
def api_labels(account):
    """ラベル一覧を返す"""
    if account not in ACCOUNTS:
        return jsonify({"error": "不正なアカウント"}), 400
    setup_account(account)
    try:
        service = mail_manager.get_gmail_service(account)
        labels = mail_manager.get_labels(service)
        return jsonify({"labels": labels})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/create_label/<account>", methods=["POST"])
def api_create_label(account):
    """新しいラベルを作成"""
    if account not in ACCOUNTS:
        return jsonify({"error": "不正なアカウント"}), 400
    setup_account(account)
    label_name = request.json.get("name", "").strip()
    if not label_name:
        return jsonify({"error": "ラベル名が空です"}), 400
    try:
        service = mail_manager.get_gmail_service(account)
        label = mail_manager.create_label(service, label_name)
        if label:
            return jsonify({"label": label})
        return jsonify({"error": "作成に失敗しました"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/filter/<account>", methods=["POST"])
def api_create_filter(account):
    """送信者→ラベルのフィルターを作成"""
    if account not in ACCOUNTS:
        return jsonify({"error": "不正なアカウント"}), 400
    setup_account(account)
    data = request.json or {}
    sender = data.get("sender", "").strip()
    label_id = data.get("label_id", "").strip()
    label_name = data.get("label_name", "").strip()
    skip_inbox = data.get("skip_inbox", True)
    msg_id = data.get("msg_id")

    if not sender:
        return jsonify({"error": "送信者が空です"}), 400
    if not label_id and not label_name:
        return jsonify({"error": "ラベルが指定されていません"}), 400

    try:
        service = mail_manager.get_gmail_service(account)
        if not label_id and label_name:
            label = mail_manager.create_label(service, label_name)
            if not label:
                return jsonify({"error": "ラベル作成に失敗しました"}), 500
            label_id = label["id"]
            label_name = label["name"]

        if mail_manager.create_label_filter(service, sender, label_id, skip_inbox):
            if msg_id:
                modify_body = {"addLabelIds": [label_id]}
                if skip_inbox:
                    modify_body["removeLabelIds"] = ["INBOX"]
                try:
                    service.users().messages().modify(
                        userId="me", id=msg_id, body=modify_body
                    ).execute()
                except Exception:
                    pass
                state = mail_manager.load_state()
                held = state.get("held_message_ids", [])
                if msg_id not in held:
                    held.append(msg_id)
                    state["held_message_ids"] = held
                    mail_manager.save_state(state)
                reviews = mail_manager.load_delete_review()
                remaining = [r for r in reviews if r["message_id"] != msg_id]
                if len(remaining) < len(reviews):
                    mail_manager.save_delete_review(remaining)
                pending = mail_manager.load_pending()
                remaining_p = [p for p in pending if p["message_id"] != msg_id]
                if len(remaining_p) < len(pending):
                    mail_manager.save_pending(remaining_p)
            return jsonify({"ok": True, "message": f"フィルター作成完了: {sender} → {label_name or 'ラベル'}"})
        return jsonify({"error": "フィルター作成に失敗しました"}), 500
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    print(f"✅ メール管理 Web UI → http://localhost:{port}")
    app.run(host="0.0.0.0", port=port, debug=False)
