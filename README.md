# ch-drop-watcher

Chrome Hearts / ANTI PROMO（Matty Boy）のオンラインショップを5分ごとにチェックして、
新商品・再入荷・ページ更新があったらスマホに通知するツールです。
GitHub Actions（無料）で動くので、PCを起動しておく必要はありません。

## 自分でも使うには

1. スマホに **ntfy** アプリを入れて、「＋」から他人と被らないトピック名を登録する
2. このリポジトリを **Fork**（右上のボタン）して自分のアカウントにコピーする
3. コピーしたリポジトリの **Settings → Secrets and variables → Actions → New repository secret**
   - Name: `NTFY_TOPIC` / Secret: 手順1のトピック名
4. **Actions** タブで「I understand my workflows, go ahead and enable them」を押して有効化
5. `drop-watcher` → **Run workflow** →「テスト通知だけ送る」にチェックして実行 →「🔔 テスト通知」が届けばOK

## 通知の種類

- 🆕 新商品
- 🔥 再入荷（ANTI PROMO などShopifyのサイトのみ）
- 👀 ページ更新（商品リンクは増えていないが、ページの内容が変わった）

通知をタップすると商品ページが開きます。

## 監視サイトを増やす

`sites.json` にURLを追加するだけ。

## 注意

- GitHubの混雑で、チェックが数分遅れることがあります
- Fork したリポジトリでは、60日間更新がないと自動実行が止まることがあります（Actionsタブから再開できます）
