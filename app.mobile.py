# ✅ モバイル向け app_mobile.py（ボタン拡大＋全体装飾CSS追加）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
import streamlit.components.v1 as components
from st_aggrid import AgGrid, GridOptionsBuilder

GOOGLE_API_KEY = "YOUR_API_KEY_HERE"

# ------------------------------
# ジオコーディング系
# ------------------------------
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

# ------------------------------
# ページ初期設定とCSS
# ------------------------------
st.set_page_config(page_title="売土地検索モバイル", layout="wide")

st.markdown("""
<style>
body {
    background-color: #f9f9f9;
    font-family: 'Segoe UI', sans-serif;
}
button {
    font-size: 16px;
}
</style>
""", unsafe_allow_html=True)

st.title("📱 売土地検索（スマホ版）")

# ------------------------------
# 現在地取得ボタン
# ------------------------------
components.html("""
<script>
function sendCoords() {
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            const coords = pos.coords.latitude + "," + pos.coords.longitude;
            const input = window.parent.document.querySelector("iframe").contentWindow.document.querySelector("input#coords");
            if (input) input.value = coords;
        });
}
</script>
<div style="text-align: center;">
<button onclick="sendCoords()" style="
    padding: 12px 24px;
    font-size: 16px;
    background-color: #007bff;
    color: white;
    border: none;
    border-radius: 6px;
    cursor: pointer;
    margin: 10px auto;
">
現在地を取得
</button>
</div>
<input type="hidden" id="coords" value="" />
""", height=60)

# ------------------------------
# 検索欄（住所）と逆ジオ
# ------------------------------
coords = st.text_input("緯度,経度（現在地）", key="coords")
address_query = ""

if coords and "," in coords:
    lat, lon = map(float, coords.split(","))
    address_query = reverse_geocode(lat, lon, GOOGLE_API_KEY)

address_query = st.text_input("検索中心住所（自動または手動入力）", value=address_query)
if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None or center_lon is None:
    st.error("住所が見つかりませんでした。")
    st.stop()

# ------------------------------
# データ読み込み・フィルタ
# ------------------------------
df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df['用途地域'] = df['用途地域'].fillna('-').astype(str)
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)
filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

st.subheader("検索結果とマップ")

# ------------------------------
# テーブル＋地図（選択強調）
# ------------------------------
if not filtered_df.empty:
    gb = GridOptionsBuilder.from_dataframe(filtered_df[['住所', '用途地域', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']])
    gb.configure_selection("single", use_checkbox=False)
    grid = AgGrid(filtered_df, gridOptions=gb.build(), height=300, theme="streamlit")
    selected_address = grid['selected_rows'][0]['住所'] if grid['selected_rows'] else None

    m = folium.Map(zoom_control=False, dragging=False)
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

    st_folium(m, width=700, height=500)
else:
    st.warning("該当物件がありませんでした。")
