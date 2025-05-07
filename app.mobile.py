# ✅ モバイル向け app_mobile.py（スマホ軽量版＆JSなし安全動作）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

# ------------------------------
# ジオコーディング関数
# ------------------------------
def geocode_address(address, api_key):
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        st.write("📦 Google Maps API レスポンス", data)
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    except Exception as e:
        st.error(f"APIエラー: {e}")
    return None, None

# ------------------------------
# 距離計算（ハバースイン法）
# ------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lat2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ------------------------------
# ページ設定
# ------------------------------
st.set_page_config(page_title="売土地検索モバイル", layout="wide")
st.title("📱 売土地検索（スマホ対応軽量版）")

# ------------------------------
# 入力（現在地または手入力）
# ------------------------------
st.info("※現在地はスマホのGPS機能が必要です。位置が取得できない場合は住所を手入力してください。")
address_query = st.text_input("🔍 検索したい住所を入力（例：浜松市中央区北島町）")
if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None or center_lon is None:
    st.error("住所が見つかりませんでした。Google APIキーまたは住所を確認してください。")
    st.stop()

# ------------------------------
# データ読み込みとフィルタ処理
# ------------------------------
df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df['用途地域'] = df['用途地域'].fillna('-').astype(str)
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)
filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

# ------------------------------
# 地図の表示のみ（表は非表示）
# ------------------------------
st.subheader("🗺️ 該当物件の地図")
if filtered_df.empty:
    st.warning("該当物件がありませんでした。")
    st.stop()

m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
bounds = []

for _, row in filtered_df.iterrows():
    popup_html = f"""
    <div style='width: 250px;'>
        <strong>{row['住所']}</strong><br>
        <ul style='padding-left: 15px; margin: 0;'>
            <li>用途地域：{row['用途地域']}</li>
            <li>価格：{row['登録価格（万円）']} 万円</li>
            <li>坪単価：{row['坪単価（万円）']} 万円</li>
            <li>面積：{row['土地面積（坪）']} 坪</li>
            <li>公開日：{row['公開日']}</li>
        </ul>
    </div>
    """
    folium.Marker(
        location=[row['latitude'], row['longitude']],
        popup=folium.Popup(popup_html, max_width=300),
        icon=folium.Icon(color="blue", icon="info-sign")
    ).add_to(m)
    bounds.append([row['latitude'], row['longitude']])

if bounds:
    m.fit_bounds(bounds)

st_folium(m, width=700, height=500)
