#flaskを使用した簡易的なウェブサイト
#the code making simple website with flask
#webサイトの練習用(眼鏡は公開するかも)

from flask import Flask, render_template, request, jsonify, url_for # jsonifyとurl_forを追加
from bs4 import BeautifulSoup
import requests
import random
import time
import sqlite3
import datetime
#以下眼鏡実装用に追加
import os
import cv2
import numpy as np
import mediapipe as mp
from PIL import Image
from werkzeug.utils import secure_filename

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
        time.sleep(random.uniform(20, 30))#リクエスト間隔短くしすぎるとgoogleにブロックされる
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

#Webサイトのルート設定
@app.route('/')
def home():
    return render_template('home.html')


@app.route('/search', methods=['GET', 'POST'])
def search_index():
    keywords = ""
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
    return render_template('index.html', keywords = keywords,results=results)

@app.route('/currency', methods=['GET', 'POST'])
def currency_converter():
    # デフォルト値の設定
    amount = 1000
    from_currency = 'USD'
    to_currency = 'JPY'
    result = None
    rate = None
    error = None

    if request.method == 'POST':
        try:
            # フォームから値を取得
            amount = float(request.form['amount'])
            from_currency = request.form['from_currency']
            to_currency = request.form['to_currency']

            # 外部API (Frankfurter) にリクエストを送信
            # URL例: https://api.frankfurter.app/latest?amount=10&from=USD&to=JPY
            api_url = f"https://api.frankfurter.app/latest?amount={amount}&from={from_currency}&to={to_currency}"
            
            response = requests.get(api_url)
            response.raise_for_status() # エラーチェック
            
            data = response.json()
            
            # 結果を取り出す
            if to_currency in data['rates']:
                result = data['rates'][to_currency]
                # 1単位あたりのレートも計算しておく
                rate = result / amount
            else:
                error = "指定された通貨のデータを取得できませんでした。"

        except ValueError:
            error = "金額には数値を入力してください。"
        except Exception as e:
            error = f"エラーが発生しました: {e}"

    # 通貨リスト（選択肢用）
    currencies = ['JPY', 'USD', 'EUR', 'GBP', 'AUD', 'CAD', 'KRW', 'CNY']

    return render_template('currency.html', 
                           amount=amount, 
                           from_currency=from_currency, 
                           to_currency=to_currency, 
                           result=result, 
                           rate=rate,
                           currencies=currencies,
                           error=error)

@app.route('/periodic-table')
def periodic_table_page():
    # 元素データを取得
    elements = get_elements_data()
    # テンプレートにデータを渡す
    return render_template('periodic_table.html', elements=elements)

def get_elements_data():
    """1番から118番までの全元素データを返す関数（周期表の座標と分類を含む）"""
    elements = [
        # ----------------------------------------------------
        # 第1周期 (Row 1)
        # ----------------------------------------------------
        {"no": 1, "sym": "H", "name": "水素", "col": 1, "row": 1, "cat": "nonmetal", "desc": "宇宙で最も豊富に存在する元素。最も軽い気体。"},
        {"no": 2, "sym": "He", "name": "ヘリウム", "col": 18, "row": 1, "cat": "noble-gas", "desc": "水素に次いで軽い元素。燃えず、反応性に乏しい希ガス。"},
        # ----------------------------------------------------
        # 第2周期 (Row 2)
        # ----------------------------------------------------
        {"no": 3, "sym": "Li", "name": "リチウム", "col": 1, "row": 2, "cat": "alkali", "desc": "最も軽い金属。反応性が高く、電池の材料として重要。"},
        {"no": 4, "sym": "Be", "name": "ベリリウム", "col": 2, "row": 2, "cat": "alkaline-earth", "desc": "軽くて強い金属。X線管の窓などに利用される。"},
        {"no": 5, "sym": "B", "name": "ホウ素", "col": 13, "row": 2, "cat": "metalloid", "desc": "硬く、熱に強い半金属。耐熱ガラスや植物の栄養素。"},
        {"no": 6, "sym": "C", "name": "炭素", "col": 14, "row": 2, "cat": "nonmetal", "desc": "有機化合物の骨格。ダイヤモンド、黒鉛、フラーレンなど多様な形態を持つ。"},
        {"no": 7, "sym": "N", "name": "窒素", "col": 15, "row": 2, "cat": "nonmetal", "desc": "大気の約78%を占める。生物のタンパク質などの構成要素として不可欠。"},
        {"no": 8, "sym": "O", "name": "酸素", "col": 16, "row": 2, "cat": "nonmetal", "desc": "生物の呼吸に不可欠。地殻中で最も多い元素。"},
        {"no": 9, "sym": "F", "name": "フッ素", "col": 17, "row": 2, "cat": "halogen", "desc": "全元素中で最も反応性が高い。歯磨き粉やテフロン加工に利用される。"},
        {"no": 10, "sym": "Ne", "name": "ネオン", "col": 18, "row": 2, "cat": "noble-gas", "desc": "放電すると鮮やかな赤オレンジ色に光る希ガス。"},
        # ----------------------------------------------------
        # 第3周期 (Row 3)
        # ----------------------------------------------------
        {"no": 11, "sym": "Na", "name": "ナトリウム", "col": 1, "row": 3, "cat": "alkali", "desc": "反応性が非常に高いアルカリ金属。塩（食塩）として生命活動に必須。"},
        {"no": 12, "sym": "Mg", "name": "マグネシウム", "col": 2, "row": 3, "cat": "alkaline-earth", "desc": "軽い金属で、構造材料や花火に使われる。植物の葉緑素の構成要素。"},
        {"no": 13, "sym": "Al", "name": "アルミニウム", "col": 13, "row": 3, "cat": "other-metal", "desc": "軽くて加工しやすく、錆びにくい。航空機や缶、サッシなどに広く利用される。"},
        {"no": 14, "sym": "Si", "name": "ケイ素", "col": 14, "row": 3, "cat": "metalloid", "desc": "半導体の主原料。地殻中に酸素に次いで多く存在する。"},
        {"no": 15, "sym": "P", "name": "リン", "col": 15, "row": 3, "cat": "nonmetal", "desc": "DNAやATPの構成要素。肥料や洗剤、マッチに使われる。"},
        {"no": 16, "sym": "S", "name": "硫黄", "col": 16, "row": 3, "cat": "nonmetal", "desc": "火山地帯に産出。ゴムの加硫や硫酸の製造に使われる。"},
        {"no": 17, "sym": "Cl", "name": "塩素", "col": 17, "row": 3, "cat": "halogen", "desc": "毒性のある気体。水道水の殺菌や漂白剤に使われる。"},
        {"no": 18, "sym": "Ar", "name": "アルゴン", "col": 18, "row": 3, "cat": "noble-gas", "desc": "空気中に多く含まれる希ガス。蛍光灯や溶接時の不活性ガスとして利用。"},
        # ----------------------------------------------------
        # 第4周期 (Row 4)
        # ----------------------------------------------------
        {"no": 19, "sym": "K", "name": "カリウム", "col": 1, "row": 4, "cat": "alkali", "desc": "神経伝達や筋肉の収縮に必須。肥料としても重要。"},
        {"no": 20, "sym": "Ca", "name": "カルシウム", "col": 2, "row": 4, "cat": "alkaline-earth", "desc": "骨や歯の主成分。セメントや石灰の原料。"},
        {"no": 21, "sym": "Sc", "name": "スカンジウム", "col": 3, "row": 4, "cat": "transition", "desc": "軽量で高強度。航空宇宙産業やスポーツ用品に使われる。"},
        {"no": 22, "sym": "Ti", "name": "チタン", "col": 4, "row": 4, "cat": "transition", "desc": "軽くて強く、錆びにくい。航空機、医療器具、スポーツ用品に利用。"},
        {"no": 23, "sym": "V", "name": "バナジウム", "col": 5, "row": 4, "cat": "transition", "desc": "鉄鋼の強度と耐熱性を高めるために添加される。"},
        {"no": 24, "sym": "Cr", "name": "クロム", "col": 6, "row": 4, "cat": "transition", "desc": "ステンレス鋼の主成分。錆びにくく光沢があるためメッキに使われる。"},
        {"no": 25, "sym": "Mn", "name": "マンガン", "col": 7, "row": 4, "cat": "transition", "desc": "鉄の製造に不可欠。乾電池の電極材料としても使用。"},
        {"no": 26, "sym": "Fe", "name": "鉄", "col": 8, "row": 4, "cat": "transition", "desc": "最も広く利用される金属。ヘモグロビンの構成要素。"},
        {"no": 27, "sym": "Co", "name": "コバルト", "col": 9, "row": 4, "cat": "transition", "desc": "磁石や超合金、青色の顔料として利用される。"},
        {"no": 28, "sym": "Ni", "name": "ニッケル", "col": 10, "row": 4, "cat": "transition", "desc": "ステンレス鋼や硬貨、充電式電池の材料。"},
        {"no": 29, "sym": "Cu", "name": "銅", "col": 11, "row": 4, "cat": "transition", "desc": "優れた導電性を持つ。電線や電子部品、硬貨に使われる。"},
        {"no": 30, "sym": "Zn", "name": "亜鉛", "col": 12, "row": 4, "cat": "transition", "desc": "鉄の防錆メッキ（トタン）に使われる。生命維持に必須な微量元素。"},
        {"no": 31, "sym": "Ga", "name": "ガリウム", "col": 13, "row": 4, "cat": "other-metal", "desc": "融点が低く、半導体の製造（LEDなど）に使われる。"},
        {"no": 32, "sym": "Ge", "name": "ゲルマニウム", "col": 14, "row": 4, "cat": "metalloid", "desc": "初期のトランジスタに使われた半導体材料。"},
        {"no": 33, "sym": "As", "name": "ヒ素", "col": 15, "row": 4, "cat": "metalloid", "desc": "毒性があるが、半導体や医療用途にも使われる。"},
        {"no": 34, "sym": "Se", "name": "セレン", "col": 16, "row": 4, "cat": "nonmetal", "desc": "光伝導性を持つ。コピー機のドラムや太陽電池に使われる。"},
        {"no": 35, "sym": "Br", "name": "臭素", "col": 17, "row": 4, "cat": "halogen", "desc": "常温で液体のハロゲン。難燃剤や医薬品の原料。"},
        {"no": 36, "sym": "Kr", "name": "クリプトン", "col": 18, "row": 4, "cat": "noble-gas", "desc": "反応性に乏しい希ガス。高効率の照明ランプに使われる。"},
        # ----------------------------------------------------
        # 第5周期 (Row 5)
        # ----------------------------------------------------
        {"no": 37, "sym": "Rb", "name": "ルビジウム", "col": 1, "row": 5, "cat": "alkali", "desc": "光電管や原子時計に使われる反応性の高いアルカリ金属。"},
        {"no": 38, "sym": "Sr", "name": "ストロンチウム", "col": 2, "row": 5, "cat": "alkaline-earth", "desc": "花火の鮮やかな赤色を出すために使われる。"},
        {"no": 39, "sym": "Y", "name": "イットリウム", "col": 3, "row": 5, "cat": "transition", "desc": "テレビのカラーブラウン管の発光体（蛍光体）に使われた。"},
        {"no": 40, "sym": "Zr", "name": "ジルコニウム", "col": 4, "row": 5, "cat": "transition", "desc": "耐食性に優れる。原子力発電所の燃料棒の被覆材。"},
        {"no": 41, "sym": "Nb", "name": "ニオブ", "col": 5, "row": 5, "cat": "transition", "desc": "超電導磁石や高性能鋼材の添加剤。"},
        {"no": 42, "sym": "Mo", "name": "モリブデン", "col": 6, "row": 5, "cat": "transition", "desc": "高温に強く、合金鋼や触媒に使われる。"},
        {"no": 43, "sym": "Tc", "name": "テクネチウム", "col": 7, "row": 5, "cat": "transition", "desc": "安定同位体を持たない、原子番号が最も小さい元素。医療診断に利用。"},
        {"no": 44, "sym": "Ru", "name": "ルテニウム", "col": 8, "row": 5, "cat": "transition", "desc": "プラチナ族元素。耐摩耗性・耐食性が高い。電子部品の電極。"},
        {"no": 45, "sym": "Rh", "name": "ロジウム", "col": 9, "row": 5, "cat": "transition", "desc": "触媒コンバーター（排ガス浄化装置）に使われる高価な金属。"},
        {"no": 46, "sym": "Pd", "name": "パラジウム", "col": 10, "row": 5, "cat": "transition", "desc": "触媒や歯科材料、電子部品に使われる貴金属。"},
        {"no": 47, "sym": "Ag", "name": "銀", "col": 11, "row": 5, "cat": "transition", "desc": "最高の電気伝導性を持つ貴金属。貨幣や食器、写真フィルムに使われた。"},
        {"no": 48, "sym": "Cd", "name": "カドミウム", "col": 12, "row": 5, "cat": "transition", "desc": "かつてニッケルカドミウム電池に使われた。毒性がある。"},
        {"no": 49, "sym": "In", "name": "インジウム", "col": 13, "row": 5, "cat": "other-metal", "desc": "液晶ディスプレイ（LCD）の透明電極（ITO）に使われる。"},
        {"no": 50, "sym": "Sn", "name": "スズ", "col": 14, "row": 5, "cat": "other-metal", "desc": "錫メッキ（ブリキ）や半田（ハンダ）に使われる。"},
        {"no": 51, "sym": "Sb", "name": "アンチモン", "col": 15, "row": 5, "cat": "metalloid", "desc": "半導体や難燃剤として利用される半金属。"},
        {"no": 52, "sym": "Te", "name": "テルル", "col": 16, "row": 5, "cat": "metalloid", "desc": "半導体材料。熱電変換素子に使われる。"},
        {"no": 53, "sym": "I", "name": "ヨウ素", "col": 17, "row": 5, "cat": "halogen", "desc": "殺菌剤（ヨードチンキ）や甲状腺ホルモンの原料。"},
        {"no": 54, "sym": "Xe", "name": "キセノン", "col": 18, "row": 5, "cat": "noble-gas", "desc": "高輝度放電ランプ（自動車のヘッドライトなど）に使われる希ガス。"},
        # ----------------------------------------------------
        # 第6周期 (Row 6)
        # ----------------------------------------------------
        {"no": 55, "sym": "Cs", "name": "セシウム", "col": 1, "row": 6, "cat": "alkali", "desc": "原子時計に使われる、最も反応性の高いアルカリ金属の一つ。"},
        {"no": 56, "sym": "Ba", "name": "バリウム", "col": 2, "row": 6, "cat": "alkaline-earth", "desc": "X線造影剤に使われる。緑色の花火にも利用。"},
        # 57-71 (ランタノイド) は下に配置されるため、メインテーブルのこの位置はスキップ
        {"no": 57, "sym": "La", "name": "ランタン", "col": 3, "row": 6, "cat": "lanthanoid", "desc": "（周期表上ではこの位置）希土類元素の代表。カメラのレンズ、電池、合金に使われる。"},
        {"no": 72, "sym": "Hf", "name": "ハフニウム", "col": 4, "row": 6, "cat": "transition", "desc": "原子炉の制御棒に使われる耐食性の高い金属。"},
        {"no": 73, "sym": "Ta", "name": "タンタル", "col": 5, "row": 6, "cat": "transition", "desc": "腐食しにくい。携帯電話などの小型電子部品のコンデンサーに使われる。"},
        {"no": 74, "sym": "W", "name": "タングステン", "col": 6, "row": 6, "cat": "transition", "desc": "最も融点が高い金属。電球のフィラメントや超硬合金に使われる。"},
        {"no": 75, "sym": "Re", "name": "レニウム", "col": 7, "row": 6, "cat": "transition", "desc": "高温強度に優れる。ジェットエンジンのタービンブレードに使用。"},
        {"no": 76, "sym": "Os", "name": "オスミウム", "col": 8, "row": 6, "cat": "transition", "desc": "最も密度が高い元素。万年筆のペン先などに使われる。"},
        {"no": 77, "sym": "Ir", "name": "イリジウム", "col": 9, "row": 6, "cat": "transition", "desc": "耐食性が極めて高い貴金属。スパークプラグなどに使用。"},
        {"no": 78, "sym": "Pt", "name": "白金 (プラチナ)", "col": 10, "row": 6, "cat": "transition", "desc": "宝飾品や触媒として使われる貴金属。"},
        {"no": 79, "sym": "Au", "name": "金", "col": 11, "row": 6, "cat": "transition", "desc": "非常に安定した貴金属。宝飾品や電子部品に使われる。"},
        {"no": 80, "sym": "Hg", "name": "水銀", "col": 12, "row": 6, "cat": "transition", "desc": "常温で液体の金属。温度計や水銀灯に使われたが、毒性がある。"},
        {"no": 81, "sym": "Tl", "name": "タリウム", "col": 13, "row": 6, "cat": "other-metal", "desc": "毒性が強い金属。光電センサーなどに利用。"},
        {"no": 82, "sym": "Pb", "name": "鉛", "col": 14, "row": 6, "cat": "other-metal", "desc": "密度が高い。バッテリーや放射線遮蔽材に使われるが、毒性がある。"},
        {"no": 83, "sym": "Bi", "name": "ビスマス", "col": 15, "row": 6, "cat": "other-metal", "desc": "重金属だが毒性が低い。美しい結晶を作る。医薬品や低融点合金に使われる。"},
        {"no": 84, "sym": "Po", "name": "ポロニウム", "col": 16, "row": 6, "cat": "metalloid", "desc": "強い放射性を持つ半金属。静電気除去装置に使われる。"},
        {"no": 85, "sym": "At", "name": "アスタチン", "col": 17, "row": 6, "cat": "halogen", "desc": "天然に極微量しか存在しない放射性ハロゲン。"},
        {"no": 86, "sym": "Rn", "name": "ラドン", "col": 18, "row": 6, "cat": "noble-gas", "desc": "放射性を持つ希ガス。自然界にも存在する。"},
        # ----------------------------------------------------
        # 第7周期 (Row 7)
        # ----------------------------------------------------
        {"no": 87, "sym": "Fr", "name": "フランシウム", "col": 1, "row": 7, "cat": "alkali", "desc": "最も重いアルカリ金属。放射性が強く、半減期が短い。"},
        {"no": 88, "sym": "Ra", "name": "ラジウム", "col": 2, "row": 7, "cat": "alkaline-earth", "desc": "強い放射性を持つアルカリ土類金属。かつて夜光塗料に使われた。"},
        # 89-103 (アクチノイド) は下に配置されるため、メインテーブルのこの位置はスキップ
        {"no": 89, "sym": "Ac", "name": "アクチニウム", "col": 3, "row": 7, "cat": "actinoid", "desc": "（周期表上ではこの位置）放射性元素。アクチノイド系列の代表。"},
        {"no": 104, "sym": "Rf", "name": "ラザホージウム", "col": 4, "row": 7, "cat": "transition", "desc": "合成された超重元素。非常に強い放射性を持つ。"},
        {"no": 105, "sym": "Db", "name": "ドブニウム", "col": 5, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 106, "sym": "Sg", "name": "シーボーギウム", "col": 6, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 107, "sym": "Bh", "name": "ボーリウム", "col": 7, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 108, "sym": "Hs", "name": "ハッシウム", "col": 8, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 109, "sym": "Mt", "name": "マイトネリウム", "col": 9, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 110, "sym": "Ds", "name": "ダームスタチウム", "col": 10, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 111, "sym": "Rg", "name": "レントゲニウム", "col": 11, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 112, "sym": "Cn", "name": "コペルニシウム", "col": 12, "row": 7, "cat": "transition", "desc": "合成された超重元素。"},
        {"no": 113, "sym": "Nh", "name": "ニホニウム", "col": 13, "row": 7, "cat": "other-metal", "desc": "日本理化学研究所（理研）が発見。超重元素。"},
        {"no": 114, "sym": "Fl", "name": "フレロビウム", "col": 14, "row": 7, "cat": "other-metal", "desc": "合成された超重元素。"},
        {"no": 115, "sym": "Mc", "name": "モスコビウム", "col": 15, "row": 7, "cat": "halogen", "desc": "合成された超重元素。"},
        {"no": 116, "sym": "Lv", "name": "リバモリウム", "col": 16, "row": 7, "cat": "halogen", "desc": "合成された超重元素。"},
        {"no": 117, "sym": "Ts", "name": "テネシン", "col": 17, "row": 7, "cat": "halogen", "desc": "合成された超重元素。"},
        {"no": 118, "sym": "Og", "name": "オガネソン", "col": 18, "row": 7, "cat": "noble-gas", "desc": "合成された超重元素。最も重い希ガス。"},
        # ----------------------------------------------------
        # 欄外：ランタノイド (Row 9, Col 4-17)
        # ----------------------------------------------------
        {"no": 58, "sym": "Ce", "name": "セリウム", "col": 4, "row": 9, "cat": "lanthanoid", "desc": "ライターの着火石に使われる。酸化剤としても利用。"},
        {"no": 59, "sym": "Pr", "name": "プラセオジム", "col": 5, "row": 9, "cat": "lanthanoid", "desc": "ガラスの色付けや強力な磁石に使われる。"},
        {"no": 60, "sym": "Nd", "name": "ネオジム", "col": 6, "row": 9, "cat": "lanthanoid", "desc": "世界最強の磁石（ネオジム磁石）の主成分。"},
        {"no": 61, "sym": "Pm", "name": "プロメチウム", "col": 7, "row": 9, "cat": "lanthanoid", "desc": "安定同位体を持たないランタノイド。"},
        {"no": 62, "sym": "Sm", "name": "サマリウム", "col": 8, "row": 9, "cat": "lanthanoid", "desc": "強力な磁石や原子力制御棒に使われる。"},
        {"no": 63, "sym": "Eu", "name": "ユウロピウム", "col": 9, "row": 9, "cat": "lanthanoid", "desc": "テレビや照明の発光体（蛍光体）に使われる。"},
        {"no": 64, "sym": "Gd", "name": "ガドリニウム", "col": 10, "row": 9, "cat": "lanthanoid", "desc": "MRI造影剤に使われる。"},
        {"no": 65, "sym": "Tb", "name": "テルビウム", "col": 11, "row": 9, "cat": "lanthanoid", "desc": "蛍光灯やセンサーに使われる。"},
        {"no": 66, "sym": "Dy", "name": "ジスプロシウム", "col": 12, "row": 9, "cat": "lanthanoid", "desc": "強力な磁石の耐熱性を高めるために使われる。"},
        {"no": 67, "sym": "Ho", "name": "ホルミウム", "col": 13, "row": 9, "cat": "lanthanoid", "desc": "最も磁性が強い元素の一つ。"},
        {"no": 68, "sym": "Er", "name": "エルビウム", "col": 14, "row": 9, "cat": "lanthanoid", "desc": "光ファイバー通信の増幅器に使われる。"},
        {"no": 69, "sym": "Tm", "name": "ツリウム", "col": 15, "row": 9, "cat": "lanthanoid", "desc": "X線源やレーザーに使われる。"},
        {"no": 70, "sym": "Yb", "name": "イッテルビウム", "col": 16, "row": 9, "cat": "lanthanoid", "desc": "高精度の原子時計やひずみゲージに使われる。"},
        {"no": 71, "sym": "Lu", "name": "ルテチウム", "col": 17, "row": 9, "cat": "lanthanoid", "desc": "最も重いランタノイド。触媒やシンチレーション検出器に使われる。"},
        # ----------------------------------------------------
        # 欄外：アクチノイド (Row 10, Col 4-17)
        # ----------------------------------------------------
        {"no": 90, "sym": "Th", "name": "トリウム", "col": 4, "row": 10, "cat": "actinoid", "desc": "原子燃料や照明のガス管に使われた。"},
        {"no": 91, "sym": "Pa", "name": "プロトアクチニウム", "col": 5, "row": 10, "cat": "actinoid", "desc": "放射性元素。"},
        {"no": 92, "sym": "U", "name": "ウラン", "col": 6, "row": 10, "cat": "actinoid", "desc": "原子力発電の燃料、核兵器に使われる。"},
        {"no": 93, "sym": "Np", "name": "ネプツニウム", "col": 7, "row": 10, "cat": "actinoid", "desc": "プルトニウムを合成する際の中間体。"},
        {"no": 94, "sym": "Pu", "name": "プルトニウム", "col": 8, "row": 10, "cat": "actinoid", "desc": "核兵器の材料。原子力発電所の燃料。"},
        {"no": 95, "sym": "Am", "name": "アメリシウム", "col": 9, "row": 10, "cat": "actinoid", "desc": "煙探知機の放射線源に使われる。"},
        {"no": 96, "sym": "Cm", "name": "キュリウム", "col": 10, "row": 10, "cat": "actinoid", "desc": "高い放射能を持つ人工元素。"},
        {"no": 97, "sym": "Bk", "name": "バークリウム", "col": 11, "row": 10, "cat": "actinoid", "desc": "合成された超ウラン元素。"},
        {"no": 98, "sym": "Cf", "name": "カリホルニウム", "col": 12, "row": 10, "cat": "actinoid", "desc": "非常に高価な中性子線源。"},
        {"no": 99, "sym": "Es", "name": "アインスタイニウム", "col": 13, "row": 10, "cat": "actinoid", "desc": "水爆実験の生成物として発見。"},
        {"no": 100, "sym": "Fm", "name": "フェルミウム", "col": 14, "row": 10, "cat": "actinoid", "desc": "合成されたアクチノイド。"},
        {"no": 101, "sym": "Md", "name": "メンデレビウム", "col": 15, "row": 10, "cat": "actinoid", "desc": "合成されたアクチノイド。"},
        {"no": 102, "sym": "No", "name": "ノーベリウム", "col": 16, "row": 10, "cat": "actinoid", "desc": "合成されたアクチノイド。"},
        {"no": 103, "sym": "Lr", "name": "ローレンシウム", "col": 17, "row": 10, "cat": "actinoid", "desc": "最も重いアクチノイド。"}
    ]

    # ソート（多分いらん）
    elements.sort(key=lambda x: x['no'])

    return elements


#以下眼鏡用に作成(後日解説入れる)
# アップロード画像の保存先
UPLOAD_FOLDER = 'static/uploads'
# フォルダがなければ作成
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# 利用可能な眼鏡リストと、顔型との対応
GLASSES_DATABASE = [
    {"id": "square", "name": "スクエア", "file": "square.png", "target": "丸顔"},
    {"id": "round", "name": "ラウンド", "file": "round.png", "target": "四角顔"},
    {"id": "boston", "name": "ボストン", "file": "boston.png", "target": "面長"},
    {"id": "wellington", "name": "ウェリントン", "file": "wellington.png", "target": "面長"},
    {"id": "oval", "name": "オーバル", "file": "oval.png", "target": "逆三角形"},
]

def get_face_landmarks(image_path):
    """顔のランドマークのみを取得するヘルパー関数"""
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5
    )
    
    image = cv2.imread(image_path)
    if image is None:
        return None
    
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(image_rgb)

    if results.multi_face_landmarks:
        return results.multi_face_landmarks[0].landmark
    return None

def overlay_glasses(face_image_path, glasses_image_path, output_path):
    """顔画像に眼鏡を合成して保存する関数"""
    
    # MediaPipeの顔メッシュ検出器を初期化
    mp_face_mesh = mp.solutions.face_mesh
    face_mesh = mp_face_mesh.FaceMesh(
        static_image_mode=True,
        max_num_faces=1,
        refine_landmarks=True,
        min_detection_confidence=0.5
    )

    # 画像を読み込み (OpenCV -> Pillow)
    image = cv2.imread(face_image_path)
    if image is None: return False
    
    # 色変換 (BGR -> RGB)
    image_rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    results = face_mesh.process(image_rgb)

    # 顔が検出されなかった場合
    if not results.multi_face_landmarks: return False

    # Pillow形式に変換（合成作業用）
    pil_image = Image.fromarray(image_rgb)

    # 眼鏡画像が存在するか確認
    if not os.path.exists(glasses_image_path):
        print(f"Error: Glasses image not found at {glasses_image_path}")
        return False

    glasses = Image.open(glasses_image_path).convert("RGBA")

    # 検出されたランドマークを取得
    landmarks = results.multi_face_landmarks[0].landmark
    h, w, _ = image.shape

    # 左目(33) と 右目(263) の座標を取得（MediaPipeの特定ID）
    left_eye = landmarks[33]
    right_eye = landmarks[263]

    # 座標をピクセル単位に変換
    le_x, le_y = int(left_eye.x * w), int(left_eye.y * h)
    re_x, re_y = int(right_eye.x * w), int(right_eye.y * h)

    # 1. 回転角度を計算
    delta_x = re_x - le_x
    delta_y = re_y - le_y
    angle = np.degrees(np.arctan2(delta_y, delta_x))
    # 眼鏡画像を回転（Pillowは時計回りがマイナスなので調整）
    rotated_glasses = glasses.rotate(-angle, expand=True, resample=Image.BICUBIC)

    # 2. サイズ調整
    eye_distance = np.sqrt(delta_x**2 + delta_y**2)
    # 眼鏡の幅を、目の距離の約2.5倍に設定（調整可能）
    glasses_width = int(eye_distance * 2.5)
    # アスペクト比を維持して高さを計算
    aspect_ratio = rotated_glasses.height / rotated_glasses.width
    glasses_height = int(glasses_width * aspect_ratio)
    
    resized_glasses = rotated_glasses.resize((glasses_width, glasses_height), Image.LANCZOS)

    # 3. 位置調整
    # 両目の中点
    center_x = (le_x + re_x) // 2
    center_y = (le_y + re_y) // 2
    
    # 眼鏡画像の貼り付け位置（左上座標）を計算
    paste_x = center_x - glasses_width // 2
    paste_y = center_y - glasses_height // 2 

    # 合成（マスクを使用して透過部分を処理）
    pil_image.paste(resized_glasses, (paste_x, paste_y), resized_glasses)

    # 保存
    pil_image.save(output_path)
    return True

def analyze_face_shape(landmarks):
    """顔のランドマークから顔型を簡易判定する"""
    if not landmarks: return "不明", None

    # 各部位の座標を取得 (MediaPipeのインデックス)
    top = landmarks[10]    # おでこ上部
    bottom = landmarks[152] # あご先
    left = landmarks[234]   # 左頬
    right = landmarks[454]  # 右頬
    
    # 顔の縦の長さと横の幅を計算
    face_height = bottom.y - top.y
    face_width = right.x - left.x

    # ゼロ除算回避
    if face_width == 0: return "不明", None

    ratio = face_height / face_width

    # 簡易的な判定ロジック
    if ratio > 1.5:
        return "面長", "wellington.png"  # 上下幅のある眼鏡
    elif ratio < 1.2:
        return "丸顔", "square.png"      # 角のある眼鏡
    else:
        # あごの細さをチェック（逆三角判定）
        jaw_left = landmarks[132]
        jaw_right = landmarks[361]
        jaw_width = jaw_right.x - jaw_left.x
        if jaw_width / face_width < 0.7:
            return "逆三角形"  # 丸みのある眼鏡
        else:
            return "四角顔"     # 柔らかい印象の眼鏡


@app.route('/glasses-tryon', methods=['GET', 'POST'])
def glasses_tryon():
    result_image = None
    error = None
    # POSTリクエスト（画像アップロード時）
    if request.method == 'POST':
        file = request.files['file']
        # 画像がアップロードされているか確認
        if file and file.filename != '':
            filename = secure_filename(file.filename)
            upload_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(upload_path)

            # 1. ここでまずランドマークを取得する
            landmarks = get_face_landmarks(upload_path)

            if landmarks:
                # 2. 顔型診断を実行
                face_shape = analyze_face_shape(landmarks)
                
                # 3. 診断結果に基づいておすすめフラグを立てる
                for g in GLASSES_DATABASE:
                    g['is_recommended'] = (g['target'] == face_shape)

                # 4. 診断結果とリストを渡して画面を表示（まだ合成はしない）
                return render_template('glasses.html', 
                                       original_image=filename, 
                                       face_shape=face_shape, 
                                       glasses_list=GLASSES_DATABASE)
            else:
                return render_template('glasses.html', error="顔を検出できませんでした。")
        else:
             return render_template('glasses.html', error="ファイルが選択されていません。")

    # GETリクエスト（最初のアクセス）
    return render_template('glasses.html')

@app.route('/apply-glasses', methods=['POST'])
def apply_glasses():
    """ユーザーが選んだ眼鏡を合成するAPI"""
    data = request.json
    image_filename = data.get('image')
    glasses_id = data.get('glasses_id')

    if not image_filename or not glasses_id:
        return jsonify({"success": False, "error": "データが不足しています"})
    
    # 選択された眼鏡のファイル名を取得
    glass_info = next(g for g in GLASSES_DATABASE if g['id'] == glasses_id)
    if not glass_info:
        return jsonify({"success": False, "error": "指定された眼鏡が見つかりません"})
    
    glasses_path = os.path.join('static/glasses', glass_info['file'])
    face_path = os.path.join(app.config['UPLOAD_FOLDER'], image_filename)
    
    result_filename = f"result_{glasses_id}_{image_filename}"
    output_path = os.path.join(app.config['UPLOAD_FOLDER'], result_filename)

    # 合成処理実行 (以前作成した overlay_glasses 関数)
    success = overlay_glasses(face_path, glasses_path, output_path)

    if success:
        return jsonify({"success": True, "result_url": url_for('static', filename='uploads/' + result_filename)})
    else:
        return jsonify({"success": False, "error": "合成に失敗しました"})

#デバッグ
if __name__ == '__main__':
    # 開発用サーバーを起動 (外部用ではない)
    app.run(debug=True)#bebug on コード変更時に自動で再起動
    #app.run(debug=False)