#google検索の検索ワードを入力し, タイトルとURLの一覧を出力

from flask import Flask, render_template, request
from bs4 import BeautifulSoup
import requests
import random
import time
import sqlite3
import datetime

#データベース作成(キャッシュ用)
DATABASE = 'scholar_cache.db'
# キャッシュの有効期間
CACHE_DURATION_HOURS = 24 #24時間保持

def get_db_connection():
    conn = sqlite3.connect(DATABASE) #データベースに接続し接続オブジェクトを返す
    conn.row_factory = sqlite3.Row #結果を辞書形式で取得できるようにする
    return conn

def init_db():
    conn = get_db_connection()
    # テーブルを作成（キーワード、HTMLデータ、保存日時を記録）
    conn.execute('''
        CREATE TABLE IF NOT EXISTS cache (
            keyword TEXT PRIMARY KEY,
            html_content TEXT NOT NULL,
            timestamp DATETIME NOT NULL
        )
    ''')
    conn.commit()
    conn.close()

# Flaskアプリケーションの初期化(インスタンス作成)
app = Flask(__name__)
# アプリケーション起動時にdbを初期化
with app.app_context():
    init_db()


# --- 検索ロジックを関数として定義 ---
def search_scholar(keywords):
    search_query = " ".join(keywords.split())

    conn = get_db_connection()
    current_time = datetime.datetime.now()

    # キャッシュの確認
    cached_result = conn.execute(
        'SELECT html_content, timestamp FROM cache WHERE keyword = ?', 
        (search_query,)
    ).fetchone()

    if cached_result:
        # キャッシュの保存日時を取得
        cached_time = datetime.datetime.strptime(cached_result['timestamp'], '%Y-%m-%d %H:%M:%S.%f')
        # キャッシュが有効期間内かチェック
        time_diff = current_time - cached_time

        if time_diff < datetime.timedelta(hours=CACHE_DURATION_HOURS):
            print(f"[{search_query}]：キャッシュから結果を読み込みます。")
            html_content = cached_result['html_content']
            conn.close()
            # キャッシュされたHTMLを直接BeautifulSoupで処理する
            return parse_scholar_html(html_content)
        else:
            print(f"[{search_query}]：キャッシュが期限切れです。再スクレイピングします。")
            # 期限切れの場合は古いキャッシュを削除
            conn.execute('DELETE FROM cache WHERE keyword = ?', (search_query,))
            conn.commit()

    url = f'https://scholar.google.co.jp/scholar?hl=ja&as_sdt=0%2C5&q={search_query}'
    
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"}

    try:
        time.sleep(random.uniform(8, 16))#リクエスト間隔短くしすぎるとgoogleにブロックされる
        res = requests.get(url, headers=headers)
        res.raise_for_status()
        html_content=res.text

        #新しい結果をキャッシュに保存
        conn.execute(
            'INSERT INTO cache (keyword, html_content, timestamp) VALUES (?, ?, ?)',
            (search_query, html_content, current_time)
        )
        conn.commit()
        print(f"[{search_query}]：新しい結果をキャッシュに保存しました。")
        conn.close()
        
        # スクレイピング処理へ
        return parse_scholar_html(html_content)
    
    except requests.exceptions.HTTPError as e:
        print(f"接続エラー（{e}）が発生しました。検索に失敗しました。")
        conn.close()
        return []
    except Exception as e:
        # エラー処理。Webサイトではエラーメッセージを出さず、空のリストを返すのが一般的
        print(f"接続エラーが発生しました: {e}")
        return []

def parse_scholar_html(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
    
    results = [] # 結果をExcelではなく、辞書のリストとして保持
    
    for result_div in soup.find_all('div', class_='gs_r gs_or gs_scl'):
        title_tag = result_div.find('h3', class_='gs_rt')
        snippet_tag = result_div.find('div', class_='gs_rs')
        source_tag = result_div.find('div', class_='gs_a')
        link_tag = title_tag.find('a') if title_tag else None

        title = title_tag.text if title_tag else 'タイトルなし'
        link = link_tag['href'] if link_tag else '#'
        snippet = snippet_tag.text if snippet_tag else '概要なし'
        source = source_tag.text if source_tag else '著者情報なし'

        results.append({
            'title': title,
            'link': link,
            'snippet': snippet,
            'source': source
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