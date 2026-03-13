# UTAGE 動画管理 / メディア管理 exact メモ

## current 入口

- `メディア管理`
- `動画管理`

代表 route
- メディア一覧: `/media`
- 動画一覧: `/media/video`

## current の representative folder

### メディア管理

- `AIカレッジ`
- `AIビジネスコース`
- `スキルプラス事業部_シーライクス参考`
- `自己成長セミナー（CTA：スキルプラススタートダッシュ）`

### 動画管理

- `スキルプラス`
- `スキルプラス_ショート動画コース`
- `ライトプラン導線`
- `秘密の部屋 導線`
- `ゼロから始めるAI完全攻略3日間合宿`
- `AIビジネスコース`
- `生成AI CAMP`

## exact に見る順番

1. folder
2. asset 名
3. 用途
4. upload
5. 動画なら
   - `サムネイル変更`
   - `チャプター設定`
   - `分析`

## メディア管理

- 基本操作
  - `新規アップロード`
  - `新規フォルダ`
- upload input
  - `file[]`

## 動画管理

- 基本操作
  - `新規アップロード`
  - `新規フォルダ`
  - `開く`
  - `名称変更`
  - `サムネイル変更`
  - `チャプター設定`
  - `分析`
  - `ダウンロード`
  - `削除`
- upload input
  - `file`
- 一覧カード footer
  - `埋め込み用URL`

## チャプター設定

- modal で開く
- load
  - `/media/video/chapter/load`
- save
  - `/video/chapter/update`
- 入力
  - `chapter`
  - `video_id`
- current 書式
  - `00:00 はじめに`
  - `07:15 5つの集客メソッド`
  - `15:20 まとめ`

### current 実例

- 動画
  - `20260203_スキルプラスのこれまで_Addnessに繋がるビジョン_この会社がどこに向かうか.mov`
- `video_id = IVrMCzvoMWMC`
- `/media/video/chapter/load`
  - `chapter = null`

## 分析

- modal で開く
- 入力
  - `date_from`
  - `date_to`
  - `表示`
- 取得先
  - `/media/video/analytics`
- current で見る値
  - `インプレッション数`
  - `視聴数`
  - `視聴維持率`

### current 実例

- 動画
  - `20260203_スキルプラスのこれまで_Addnessに繋がるビジョン_この会社がどこに向かうか.mov`
- `video_id = IVrMCzvoMWMC`
- 全期間で
  - `impression = 89`
  - `impression_unique = 44`
  - `play = 61`
  - `play_unique = 36`
- 維持率
  - `00:00:00 = 93.88%`
  - `00:24:33 = 30.61%`
  - `00:58:55 = 24.49%`
  - `01:01:22 = 12.24%`

## Addness 側での重要解釈

- 動画とメディアは page の付属物ではなく、再利用される asset library
- page 修正時は、まず media/video 側に asset があるか確認した方が安全
- 動画は「上げた」で終わりではなく、
  - サムネイル
  - チャプター
  - 分析
 まで見て初めて運用理解になる
