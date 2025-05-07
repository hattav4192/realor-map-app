# ✅ PC向け app.py（高機能版 - 現在地取得・地図自動調整・用途地域表示・テーブル行クリック）
# 🔧 モバイル向けバージョンは app_mobile.py として別途提供します（軽量・自動縮小）

import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
from st_aggrid import AgGrid, GridOptionsBuilder
import streamlit.components.v1 as components

GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

def geocode_address(address, api_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    return None, None

def reverse_geocode(lat, lon, api_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        if data['status'] == 'OK':
            return data['results'][0]['formatted_address']
    return ""

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

st.set_page_config(page_title="売土地検索", layout="wide")
st.title("\U0001F3E0 売土地検索（PC版）")

# JavaScriptで現在地を取得するボタン
coords = components.html(
    """
    <script>
    function sendCoords() {
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                const lat = pos.coords.latitude;
                const lon = pos.coords.longitude;
                const coords = lat + "," + lon;
                window.parent.postMessage(coords, "*");
            });
    }
    </script>
    <button onclick="sendCoords()">\uD83D\uDCCD 現在地を取得</button>
    """,
    height=35
)

coord_input = st.text_input("\uD83C\uDF10 緯度,経度（現在地が入ります）", key="coords")
address_query = ""

if coord_input and "," in coord_input:
    lat, lon = map(float, coord_input.split(","))
    auto_address = reverse_geocode(lat, lon, GOOGLE_API_KEY)
    address_query = st.text_input("検索中心住所（取得済）", value=auto_address)
else:
    address_query = st.text_input("検索中心住所（例：浜松市中区）")

if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None or center_lon is None:
    st.error("住所が見つかりませんでした。")
    st.stop()

# データ読み込み・前処理
df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df['用途地域'] = df['用途地域'].fillna('-').astype(str)
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)
filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

st.subheader("\U0001F5FA 検索結果とマップ")

if not filtered_df.empty:
    gb = GridOptionsBuilder.from_dataframe(filtered_df[['住所', '用途地域', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']])
    gb.configure_selection('single')
    grid_response = AgGrid(filtered_df, gridOptions=gb.build(), height=300, width='100%')

    selected_row = grid_response['selected_rows']
    selected_address = selected_row[0]['住所'] if selected_row else None

    # 地図生成と自動ズーム調整
    m = folium.Map()
    bounds = []
    for _, row in filtered_df.iterrows():
        color = "red" if row['住所'] == selected_address else "blue"
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
            icon=folium.Icon(color=color, icon="info-sign")
        ).add_to(m)
        bounds.append([row['latitude'], row['longitude']])

    if bounds:
        m.fit_bounds(bounds)
    st_folium(m, width=1000, height=600)
else:
    st.warning("該当物件がありませんでした。")
