# アカウント・認証情報

最終更新: 2026-03-17

## 情報ラベル

- 所有元: self
- 開示レベル: self-only
- 承認必須: always
- 共有先: 僕

## Googleアカウント

- **甲原**: `koa800sea.nifs@gmail.com`（Claude Max 20x, Google API）
- **秘書**: `koa800.secretary@gmail.com`（Claude Max 5x, 秘書専用）
- **パスワード**: `System/credentials/secretary_google.txt`（秘書Google PW: Koa800sea）, `System/credentials/hinata_google.json`

## Claude Code 設定

- `~/.claude/settings.json` で `bypassPermissions`（フルオート）設定済み
- 削除系・プロセス・HTTP削除・クラウド・Git破壊的・決済は承認必須（`ask` リスト）

## お名前.com ドメインメール

- **アドレス**: `k.kohara@addness.co.jp`
- **用途**: DS.INSIGHTメール配信先（Yahoo!ビジネスID紐付き）
- **Webメール**: Roundcube（https://webmail74.onamae.ne.jp/）※転送設定・フィルター不可
- **IMAP接続**: `mail.addness.co.jp:993`（SSL）
- **認証情報**: `System/credentials/onamae_imap.json`
- **Orchestrator連携**: `dsinsight_mail_check` が IMAP で直接メール取得 → LINE転送

## Tailscale

- MacBook: `100.112.73.6` / Mac Mini (`mac-mini-agent`): `100.96.200.105`
- MagicDNS有効。SSH: `ssh koa800@mac-mini-agent`
