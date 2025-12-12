#google検索の検索ワードを入力し, タイトルとURLの一覧を出力

from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import requests
import random
import time

# Flaskアプリケーションの初期化
app = Flask(__name__)

# --- 検索ロジックを関数として定義 ---
def search_scholar(keywords):
    search_query = " ".join(keywords.split())
    url = f'https://scholar.google.co.jp/scholar?hl=ja&as_sdt=0%2C5&q={search_query}'
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36"}

    try:
        time.sleep(random.uniform(1, 3))
        res = requests.get(url, headers=headers)
        res.raise_for_status()
    except Exception as e:
        # エラー処理。Webサイトではエラーメッセージを出さず、空のリストを返すのが一般的
        print(f"接続エラーが発生しました: {e}")
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    elems = soup.find_all(class_="gs_rt")
    
    results = [] # 結果をExcelではなく、辞書のリストとして保持
    
    for el in elems:
        link_element = el.find('a')
        
        if link_element and 'href' in link_element.attrs:
            results.append({
                # 結果をタイトルとURLのペアとして保存
                'title': link_element.text,
                'url': link_element.attrs['href']
            })
            
    return results

# --- Webサイトのルート設定 ---
@app.route('/', methods=['GET', 'POST'])
def index():
    results = []
    
    if request.method == 'POST':
        # HTTP POSTリクエスト（フォームが送信されたとき）の処理
        # request.form['keywords'] でHTMLフォームから入力値を取得
        keywords = request.form['keywords']
        if keywords:
            # 検索ロジックを実行し、結果を受け取る
            results = search_scholar(keywords)
            
    # 結果（results）を 'index.html' に渡して表示させる
    # 'GET'リクエスト（初期アクセス）の場合、resultsは空のまま渡される
    return render_template('index.html', results=results)

if __name__ == '__main__':
    # 開発用サーバーを起動 (外部公開用ではない)
    # debug=True にすると、コード変更時に自動で再起動されます
    app.run(debug=True)