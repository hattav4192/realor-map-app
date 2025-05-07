import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# ------------------------------
# Google Maps APIキー
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

# ------------------------------
# Googleジオコーディング
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

# ------------------------------
# UI: 検索住所入力
# ------------------------------
st.set_page_config(page_title="売土地検索マップ", layout="wide")
st.title("\U0001F3E0 売土地データ検索ツール（スマホ対応）")

address_query = st.text_input("\U0001F50D 中心にしたい住所（例：浜松市中区）を入力", key="address")

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
# サイドバー：検索条件
# ------------------------------
with st.sidebar:
    st.header("\U0001F527 絞り込み条件")
    max_distance = st.slider("\U0001F4CD 距離（km）", 0.0, 10.0, 2.0, 0.1)
    tsubo_min, tsubo_max = float(df['坪単価（万円）'].min()), float(df['坪単価（万円）'].max())
    tsubo_range = st.slider("\U0001F4CA 坪単価（万円）", tsubo_min, tsubo_max, (tsubo_min, tsubo_max))
    area_min, area_max = float(df['土地面積（坪）'].min()), float(df['土地面積（坪）'].max())
    area_range = st.slider("\U0001F4CD 土地面積（坪）", area_min, area_max, (area_min, area_max))

# ------------------------------
# 距離計算とフィルタ
# ------------------------------
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)

filtered_df = df[
    (df['距離km'] <= max_distance) &
    (df['坪単価（万円）'] >= tsubo_range[0]) & (df['坪単価（万円）'] <= tsubo_range[1]) &
    (df['土地面積（坪）'] >= area_range[0]) & (df['土地面積（坪）'] <= area_range[1])
].sort_values(by='坪単価（万円）', ascending=False)

# ------------------------------
# 住所選択（インタラクティブ対応）
# ------------------------------
st.markdown("---")
st.subheader("\U0001F5FA 検索結果と地図")

if not filtered_df.empty:
    address_list = filtered_df['住所'].tolist()
    selected_address = st.selectbox("\U0001F4CD 地図で強調表示したい住所を選択", ["(選択なし)"] + address_list)

    # 表表示
    st.dataframe(filtered_df[['住所', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']])

    # 地図作成
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

    for _, row in filtered_df.iterrows():
        popup_html = f"""
        <div style='width: 250px;'>
            <strong>{row['住所']}</strong><br>
            <ul style='padding-left: 15px; margin: 0;'>
                <li>価格：{row['登録価格（万円）']} 万円</li>
                <li>坪単価：{row['坪単価（万円）']} 万円</li>
                <li>面積：{row['土地面積（坪）']} 坪</li>
                <li>公開日：{row['公開日']}</li>
            </ul>
        </div>
        """
        icon_color = "red" if row['住所'] == selected_address else "blue"

        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row['住所'],
            icon=folium.Icon(color=icon_color, icon="info-sign")
        ).add_to(m)

    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
