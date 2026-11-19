"""
Drop Watcher — Chrome Hearts / Matty Boy などのオンラインショップを監視して、
新商品・再入荷・ページの変化があったらスマホ（Pushover / ntfyアプリ）に通知する。

仕組み:
  1. Shopify のサイトなら /products.json を読み、新商品と再入荷を検知
  2. それ以外のサイトはページ内の商品リンクを集めて、前回との差分を検知
  3. リンクが取れない場合はページ本文のハッシュで「何か変わった」を検知
前回の状態は state.json に保存する。
"""
import hashlib
import json
import os
import re
import sys
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
PUSHOVER_TOKEN = os.environ.get("PUSHOVER_TOKEN", "")
PUSHOVER_USER = os.environ.get("PUSHOVER_USER", "")
STATE_FILE = "state.json"
SITES_FILE = "sites.json"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en;q=0.8",
}
# 商品ページっぽいURLのパターン（Shopify / Salesforce Commerce Cloud など）
PRODUCT_HINTS = re.compile(r"/(products?|item|items|p)/|\.html($|\?)|pid=", re.I)
# 監視したくないリンク（ログイン・規約など）
IGNORE = re.compile(r"login|account|cart|privacy|terms|policy|contact|location|magazine|instagram", re.I)


def notify(title, message, url=None, priority=1):
    """Pushover（メイン）と ntfy（予備）に通知を送る。
    priority: 0=普通, 1=高（Pushoverの静音時間中も鳴る）"""
    print(f"[NOTIFY] {title}: {message} {url or ''}")
    if PUSHOVER_TOKEN and PUSHOVER_USER:
        data = {"token": PUSHOVER_TOKEN, "user": PUSHOVER_USER,
                "title": title, "message": message, "priority": priority}
        if url:
            data["url"] = url
            data["url_title"] = "商品ページを開く"
        try:
            r = requests.post("https://api.pushover.net/1/messages.json", data=data, timeout=15)
            print("  -> pushover:", r.status_code, "" if r.ok else r.text)
        except requests.RequestException as e:
            print("Pushoverへの送信に失敗:", e)
    if NTFY_TOPIC:
        headers = {"Title": title.encode("utf-8"), "Priority": "urgent", "Tags": "rotating_light"}
        if url:
            headers["Click"] = url
        try:
            r = requests.post(f"https://ntfy.sh/{NTFY_TOPIC}", data=message.encode("utf-8"),
                              headers=headers, timeout=15)
            print("  -> ntfy:", r.status_code)
        except requests.RequestException as e:
            print("ntfyへの送信に失敗:", e)


def fetch(url):
    r = requests.get(url, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r


def try_shopify(base):
    """Shopifyサイトなら {商品ID: {title, url, available}} を返す。違えば None。"""
    root = f"{urlparse(base).scheme}://{urlparse(base).netloc}"
    try:
        r = requests.get(f"{root}/products.json?limit=250", headers=HEADERS, timeout=25)
        data = r.json()
    except Exception:
        return None
    if "products" not in data:
        return None
    out = {}
    for p in data["products"]:
        out[str(p["id"])] = {
            "title": p.get("title", ""),
            "url": f"{root}/products/{p.get('handle', '')}",
            "available": any(v.get("available") for v in p.get("variants", [])),
        }
    return out


def page_snapshot(url):
    """ページ内の商品リンク一覧と本文ハッシュを返す"""
    html = fetch(url).text
    soup = BeautifulSoup(html, "html.parser")
    host = urlparse(url).netloc
    links = {}
    for a in soup.find_all("a", href=True):
        full = urljoin(url, a["href"]).split("#")[0]
        if urlparse(full).netloc != host or IGNORE.search(full):
            continue
        if PRODUCT_HINTS.search(full):
            links[full] = a.get_text(" ", strip=True)[:60]
    for t in soup(["script", "style", "noscript"]):
        t.decompose()
    text = re.sub(r"\s+", " ", soup.get_text(" "))
    return links, hashlib.sha256(text.encode()).hexdigest()


def main():
    with open(SITES_FILE, encoding="utf-8") as f:
        sites = json.load(f)
    try:
        with open(STATE_FILE, encoding="utf-8") as f:
            state = json.load(f)
    except FileNotFoundError:
        state = {}
    first_run = not state

    for site in sites:
        name = site["name"]
        shop = try_shopify(site["urls"][0])
        if shop is not None:
            key = f"shopify::{name}"
            old = state.get(key)
            if old is not None:
                for pid, p in shop.items():
                    if pid not in old:
                        notify(f"🆕 {name} 新商品", p["title"], p["url"])
                    elif p["available"] and not old[pid]["available"]:
                        notify(f"🔥 {name} 再入荷", p["title"], p["url"])
            state[key] = shop
            continue

        for url in site["urls"]:
            try:
                links, digest = page_snapshot(url)
            except Exception as e:
                print(f"{url} の取得に失敗: {e}")
                continue
            old = state.get(url)
            if old is not None:
                new_links = [u for u in links if u not in old["links"]]
                for u in new_links[:5]:
                    notify(f"🆕 {name} 新しい商品リンク", links[u] or u, u)
                # 売り切れ表示が消えた商品 = 再入荷
                restocked = [u for u in links if u in old["links"]
                             and "OUT OF STOCK" in old["links"][u].upper()
                             and "OUT OF STOCK" not in links[u].upper()]
                for u in restocked[:5]:
                    notify(f"🔥 {name} 再入荷", f"{links[u]}  {u.rsplit('/', 1)[-1]}", u)
                if not new_links and not restocked and digest != old["hash"]:
                    notify(f"👀 {name} ページが更新", "ショップページの内容が変わりました", url, priority=0)
            state[url] = {"links": links, "hash": digest}

    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=1, sort_keys=True)

    if first_run:
        notify("✅ Drop Watcher 起動", "監視を始めました。新しい商品が出たら通知します。")


if __name__ == "__main__":
    if "--test" in sys.argv:
        notify("🔔 テスト通知", "これが届けば設定OK!", "https://www.chromehearts.com/")
    else:
        main()
