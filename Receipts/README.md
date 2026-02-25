# 領収書・請求書

Gmail から取得した領収書を `年/月` で整理しています。

## 保存場所

- **ローカル**: このリポジトリの `Receipts/2026/02/` など
- **個人 Google Drive 経理フォルダ**にまとめたい場合:
  ```bash
  rclone copy "Receipts/2026/" "personal:2026年/2月/" --drive-root-folder-id "1_C74ShJA34R-TAzeJN5lbEGikv_ykAWk" 2>/dev/null
  ```

## Creem / seadance の領収書について

メールに PDF 添付がない場合、本文（HTML）を保存しています。  
**PDF のインボイスが必要な場合**: メール内の「Generate one here」リンク（Creem の注文ページ）から発行できます。

## 同じ領収書を再度取得する場合

```bash
python3 System/receipt_downloader.py "Payment receipt" --from creem
```
