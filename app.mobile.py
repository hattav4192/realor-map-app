import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
import streamlit.components.v1 as components

# ------------------------------
# Google Maps APIキー
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"  # ← あなたのAPIキーに差し替えてください

# ------------------------------
# Googleジオコーディング（住所→座標）
# ------------------------------
def geocode_address(address, api_key):
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
    except:
        pass
    return None, None

# ------------------------------
# 逆ジオコーディング（座標→住所）
# ------------------------------
def reverse_geocode(lat, lon, api_key):
    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        if data['status'] == 'OK':
            return data['results'][0]['formatted_address']
    except:
        pass
    return ""

# ------------------------------
# 距離計算
# ------------------------------
def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ------------------------------
# データ読み込み
# ------------------------------
df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df['用途地域'] = df['用途地域'].fillna('-').astype(str)

# ------------------------------
# 現在地取得JS + 逆ジオ
# ------------------------------
st.title("\U0001F3E0 売土地データ検索ツール（スマホ対応）")

coords = components.html(
    """
    <script>
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            const lat = pos.coords.latitude;
            const lon = pos.coords.longitude;
            const text = lat + "," + lon;
            const input = window.parent.document.querySelector("iframe").contentWindow.document.querySelector("input#coords");
            if (input) input.value = text;
        });
    </script>
    <input type="hidden" id="coords" value="" />
    """,
    height=0
)

coord_input = st.text_input("\U0001F4CD 現在地の座標（自動取得）", key="coords")
address_query = ""

if coord_input and "," in coord_input:
    lat, lon = map(float, coord_input.split(","))
    auto_address = reverse_geocode(lat, lon, GOOGLE_API_KEY)
    address_query = st.text_input("検索中心住所", value=auto_address)
else:
    address_query = st.text_input("検索中心住所（手動入力も可）")

if address_query:
    center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
    if center_lat is None or center_lon is None:
        st.warning("📍 Googleで該当住所が見つかりませんでした。")
        st.stop()
    else:
        st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")
else:
    st.info("検索する住所を入力してください。")
    st.stop()

# ------------------------------
# フィルタ処理（距離のみ）
# ------------------------------
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)

filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

# ------------------------------
# 住所リスト → 選択クリック式
# ------------------------------
st.subheader("\U0001F5FA 検索結果と地図")

if not filtered_df.empty:
    selected_address = st.radio("\U0001F4CC 強調表示したい物件を選択", filtered_df['住所'].tolist())

    # 表
    st.dataframe(filtered_df[['住所', '用途地域', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']])

    # 地図生成
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13, zoom_control=False, dragging=False)

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

    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
