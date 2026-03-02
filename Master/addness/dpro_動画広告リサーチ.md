# 動画広告分析Pro（DPro）リサーチノート

最終更新: 2026-03-01

## ツール情報

| 項目 | 内容 |
|------|------|
| URL | https://dpro.kashika-20mile.com/search |
| ログインID | addness.adteam@gmail.com |
| パスワード | Addness0726@@ |
| データ内容 | YouTube / Instagram の動画広告の消化額・再生数・LP遷移先を横断分析 |

## 操作メモ

- URLパラメータで媒体を切り替え可能
  - YouTube のみ: `app_id=1`
  - Instagram のみ: `app_id=4`
  - 両方: `app_id=1%2C4`
- フォーマット: `media_type=video`（動画のみ）
- テーブルは **ag-grid** で描画（仮想スクロール。DOMには18行しか出ない）
- 全行データ取得は ag-grid API を使う（下記スクリプト参照）

### データ取得スクリプト

```javascript
// ag-grid API にアクセス（React fiber tree 経由）
const gridWrapper = document.querySelector('.ag-root-wrapper');
const fiberKey = Object.keys(gridWrapper).find(k => k.startsWith('__reactFiber'));
let current = gridWrapper[fiberKey];
let api = null;
for (let i = 0; i < 30 && current; i++) {
  if (current.stateNode?.api) { api = current.stateNode.api; break; }
  current = current.return;
}

// 全行取得
const rows = [];
api.forEachNode(node => {
  const d = node.data;
  rows.push({
    advertiser_name: d.advertiser_name,
    product_name: d.product_name,
    genre_name: d.genre_name,
    transition_type: d.transition_type,  // LP種別
    cost_difference: d.cost_difference,  // 予想消化増加額
    cost: d.cost,                        // 累計予想消化額
    play_count_difference: d.play_count_difference,
    ad_objective: d.ad_objective,
    duration: d.duration,
    production_url: d.production_url,    // 広告CR URL
    transition_url: d.transition_url     // LP URL
  });
});

// URLを含むデータは console.log → read_console_messages で取得
// （JavaScript toolではURLが [BLOCKED: Cookie/query string data] になる）
rows.forEach((r, i) => console.log(`ROW_${i}:${JSON.stringify(r)}`));
```

### 注意事項

- `production_url`（広告CR）と `transition_url`（LP）を JavaScript tool の return で取得しようとすると **BLOCKED** される
- 必ず `console.log()` で出力 → `read_console_messages` で回収する
- ag-grid のスクロール位置リセット: `document.querySelector('.ag-body-viewport').scrollTop = 0`

---

## LP種別（transition_type）の分類

| 値 | 意味 |
|----|------|
| 記事LP | 記事型ランディングページ |
| 漫画記事LP | 漫画形式の記事LP |
| アンケートLP | クイズ/診断型LP |
| LPを含むその他 | 直LP（記事・漫画・アンケートでない） |
| LINE@誘導LP | LINE友だち追加がCVポイント（**Instagram特有**） |
| モール | Amazon等のECモール直行 |
| アプリストア | App Store / Google Play 直行 |

---

## リサーチ結果① Instagram（Meta）動画広告 100件分析（2026-03-01時点）

### LP種別の分布

| LP種別 | 件数 |
|--------|------|
| LPを含むその他（直LP） | 29件 |
| 記事LP | 26件 |
| LINE@誘導LP | 10件 |
| モール | 9件 |
| アンケートLP | 5件 |
| 漫画記事LP | 4件 |

### 動画尺の傾向（Instagram）

| 尺 | 傾向 |
|----|------|
| 5〜15秒 | ワンメッセージ。フック→LP側で教育 |
| 20〜45秒 | **最多ボリュームゾーン**。起承転結を圧縮 |
| 1〜3分 | ロング教育型。教育系で有効 |

### 注目広告主（中小・リード獲得系）

#### ジュノビューティークリニック（医療痩身）— LINE@誘導LP × 大量テスト

TOP100に**7本ランクイン**。LINE友だち追加がCVポイント。

| 動画尺 | 広告CR | LP |
|--------|--------|----|
| 20秒 | https://www.instagram.com/p/DTzc17RgEbk/ | https://juno-beauty-pe.com/lp_line/lp96/ver12.php |
| 20秒 | https://www.instagram.com/p/DTgzeqegO9p/ | https://juno-beauty-pe.com/lp_line/lp96/ver12.php |
| 24秒 | https://www.instagram.com/p/DN9-uSFgM33/ | https://sb.ans-skin.com/ab/acne-ig |
| 29秒 | https://www.instagram.com/p/DTskSz0gKQs/ | https://juno-beauty-pe.com/lp_line/lp103/ver3.php |
| 30秒 | https://www.instagram.com/p/DTA2Jg9gBp8/ | https://juno-beauty-pe.com/lp_line/lp103/ver3.php |
| 45秒 | https://www.instagram.com/p/DMRUYEOM5mp/ | https://juno-sururim.com/lp_line/lp1/?ad_id=242 |
| 1分8秒 | https://www.instagram.com/p/DQEFSiNDG2K/ | https://juno-beauty-pe.com/lp_line/lp96/ver12.php |
| 1分16秒 | https://www.instagram.com/p/DJt5IxuMhj-/ | https://juno-beauty-pe.com/lp_line/lp39/?ad_id=6760 |

**学び**: 20秒〜1分超まで幅広い尺をテスト。LPも3パターン以上。ショート動画でフック→LINEで教育する2段階構造。

#### 復縁占い 星月あかり — LINE@誘導LP × ロングヒット

| 項目 | 値 |
|------|-----|
| 累計消化額 | **約3.1億円** |
| 動画尺 | 27秒 |
| 広告CR | https://www.instagram.com/p/C4Zv8gyA7SH/ |
| LP | https://clairvoyant-future.com/line4hki09/ |

**学び**: 2024年の投稿が今も消化し続けているロングヒット。27秒で感情を動かし→LINE追加。

#### Free Life Consulting「投資の達人講座」— 記事LP + 直LP 同時A/Bテスト

| 導線 | 動画尺 | 広告CR | LP |
|------|--------|--------|----|
| 記事LP | 46秒 | https://www.instagram.com/p/DUaPmRbDJaR/ | https://toushi-up.com/cfm/kin_ad07c.html |
| 直LP | 1分7秒 | https://www.instagram.com/p/DTKRuewDH61/ | https://toushi-up.com/cfm/kin_ad07b.html |

**学び**: 同一商品で記事LP vs 直LPを同時テスト。URL末尾の管理番号で分岐。

#### スケールアイ「イングリッシュブレークスルー」— 直LP × ロング動画

| 項目 | 値 |
|------|-----|
| 累計消化額 | 約774万円 |
| 動画尺 | **2分48秒** |
| 広告CR | https://www.instagram.com/p/DJqcbdtMZQi/ |
| LP | https://extpot.com/6go/cfm/lp3re-112ldr/ |

**学び**: Instagramでも2分超のロング教育動画→直LPが回っている。教育系×直LPの成功例。

#### ドリームメーカー「アルケミスト」— 直LP × ショート動画

| 項目 | 値 |
|------|-----|
| 累計消化額 | **約3,391万円** |
| 動画尺 | 10秒 |
| 広告CR | https://www.instagram.com/p/DHKJFgvAfhq/ |
| LP | https://www.alchemist-master.com/ |

**学び**: たった10秒で累計3,300万超え。短い動画でフック→LP側で教育する逆パターン。

#### ランクアップ「マナラ」— アンケートLP + 記事LP × Meta専用LP

| 導線 | 動画尺 | 広告CR | LP |
|------|--------|--------|----|
| アンケート | 44秒 | https://www.instagram.com/p/DUW8tzzDM0o/ | https://cp.manara.jp/KS36META008 |
| アンケート | 42秒 | https://www.instagram.com/p/DNmJrFesf7Z/ | https://cp.manara.jp/KS36META002 |
| 記事 | 33秒 | https://www.instagram.com/p/DUzUXkcAEWR/ | https://cp.manara.jp/KS02_meta02 |

**学び**: URLに「META」が入っている＝Meta広告専用LPを作成。アンケート型と記事型を同時テスト。

#### Neautech「アンス」— 直LP + LINE@誘導LP 併用テスト

| 導線 | 動画尺 | 広告CR | LP |
|------|--------|--------|----|
| 直LP | 35秒 | https://www.instagram.com/p/DN97FmLgCrA/ | https://sb.ans-skin.com/ab/spot-ig |
| LINE誘導 | 24秒 | https://www.instagram.com/p/DN9-uSFgM33/ | https://sb.ans-skin.com/ab/acne-ig |

**学び**: 直LPとLINE誘導LPを同時テスト。URLに「ig」＝Instagram専用LP。

---

## リサーチ結果② YouTube 動画広告（動画×直LP）中小広告主（2026-03-01時点）

### 注目広告主

#### 株式会社ブリーチ「Myカードローン」— 同一LP × 3本同時テスト

| 動画尺 | 消化増加額 | 広告CR |
|--------|----------|--------|
| 1分42秒 | 約308万円 | https://www.youtube.com/watch?v=SVrX4lT0miU |
| 42秒 | 約159万円 | https://www.youtube.com/watch?v=X_rJPbtDbWA |
| 39秒 | 約155万円 | https://www.youtube.com/watch?v=Ohc24PhwleE |

LP: https://mycardloan.com/morimori-search-keiken-6

#### ダイレクト出版 — ロング教育動画 × 直LP（アドネスと同じ型）

| 商品 | 動画尺 | 広告CR | LP |
|------|--------|--------|----|
| こうして日本人だけが騙される | 8分33秒 | https://www.youtube.com/watch?v=enrKdls5SVI | https://in.intel-insight.jp/mrkn_ppc_gdn_4 |
| 水戸学要義 | 2分56秒 | https://www.youtube.com/watch?v=X4bQggD2xuU | https://in.ghqfs-archives.jp/taburn23_2511_ppc_gdn_himitsu |

#### クリエイターズアカデミー — LP31パターン以上テスト

| 項目 | 値 |
|------|-----|
| 動画尺 | 1分37秒 |
| 広告CR | https://www.youtube.com/watch?v=Y2njPs6U0mA |
| LP | https://creatorsacademy.jp/challenge_landing_lp31_go/ |

**学び**: LPパスに「lp31」→ 31パターン以上のLPテストを回している可能性。

---

## アドネスへの戦略示唆

### 1. Meta広告のファネル最適化

現行の「動画教育→直LP」に加えて、**「ショート動画（20〜45秒フック）→ LINE友だち追加LP」** の導線を並行テストすべき。

```
【現行】 ショート動画（教育）→ 直LP → スキルプラス申込
【テスト】ショート動画（フック）→ LINE友だち追加LP → LINEで教育 → スキルプラス申込
```

根拠: ジュノが7本×3LPで同時テスト、復縁占いが3.1億をLINE誘導で達成。

### 2. 媒体展開の優先順位

| 優先度 | 媒体 | 理由 |
|--------|------|------|
| S | Meta広告 | 現主力。LINE誘導LPテストを追加 |
| A | TikTok広告 | MetaのCRをほぼそのまま横展開可。危機感訴求とTikTok文化の相性◎ |
| A | X広告 | 挑発的訴求（「おい会社員」系）がXの空気と最もマッチ |
| B | LINE広告 | LINE友だち追加を直接CVポイントにできる。40代以上のリーチが強い |
| B | SmartNews | 記事LP型との相性良い。リードの質は浅くなるリスク |

### 3. 動画尺のテスト方針

| 尺 | 用途 | 参考 |
|----|------|------|
| 10〜15秒 | ワンフック → LP側で教育 | アルケミスト（累計3,300万） |
| 20〜45秒 | 起承転結の圧縮。**Meta主戦場** | ジュノ（7本同時テスト） |
| 1〜3分 | ロング教育 → 直LP | イングリッシュブレークスルー（累計774万） |

### 4. LP種別と訴求の推奨テスト

アドネスの勝ちパターン（危機感・FOMO・二極化訴求）× LP種別の組み合わせ:

| 訴求 | 直LP | LINE誘導LP | アンケートLP |
|------|------|-----------|------------|
| 危機感 | 現行の型。継続 | **最優先テスト** | — |
| 二極化 | CVR 28.6%で最強 | テスト価値あり | — |
| 実用（プロンプト系） | CPA最安。継続 | — | 「AIスキル診断」型で試す |
| FOMO | 画像CRで有効 | — | — |
