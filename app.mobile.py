# ✅ モバイル向け app_mobile.py（自動で現在地を取得し入力欄に反映）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
from streamlit_js_eval import get_geolocation

GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

# ------------------------------
# 逆ジオコーディング
# ------------------------------
def reverse_geocode(lat, lon, api_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}"
    response = requests.get(url)
    data = response.json()
    if data['status'] == 'OK':
        return data['results'][0]['formatted_address']
    return ""

# ------------------------------
# ジオコーディング（住所→座標）
# ------------------------------
def geocode_address(address, api_key):
    try:
        address = address.strip().replace('　', '').replace(' ', '')
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={address}&key={api_key}"
        response = requests.get(url)
        data = response.json()
        if data['status'] == 'OK':
            location = data['results'][0]['geometry']['location']
            return location['lat'], location['lng']
        else:
            st.error(f"住所が見つかりません（APIステータス: {data['status']}）")
    except Exception as e:
        st.error(f"ジオコーディング中にエラーが発生しました: {e}")
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
# レイアウトと説明
# ------------------------------
st.set_page_config(page_title="売土地検索（スマホ）", layout="centered")
st.title("🏠 売土地検索（スマホ）")
st.markdown("現在地または住所を入力して、2km圏内の土地情報を表示します。")

# ------------------------------
# 現在地取得 → 自動で住所入力欄に反映
# ------------------------------
location = get_geolocation()
if location and "coords" in location:
    lat = location["coords"]["latitude"]
    lon = location["coords"]["longitude"]
    reverse_address = reverse_geocode(lat, lon, GOOGLE_API_KEY)
    address_query = st.text_input("🔍 検索したい中心住所", value=reverse_address)
else:
    address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")

if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None or center_lon is None:
    st.stop()

# ------------------------------
# データ読み込みと距離計算
# ------------------------------
df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df = df.dropna(subset=['latitude', 'longitude'])

df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)
filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

if len(filtered_df) > 2:
    filtered_df = filtered_df.iloc[1:-1]

# ------------------------------
# 結果表示
# ------------------------------
st.subheader("📋 該当物件一覧")
display_columns = ['住所', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']
display_columns = [col for col in display_columns if col in filtered_df.columns]
st.dataframe(filtered_df[display_columns])

# ------------------------------
# 地図表示
# ------------------------------
if not filtered_df.empty:
    st.subheader("🗺️ 地図で確認")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    folium.Marker(
        location=[center_lat, center_lon],
        popup="検索中心（現在地）",
        icon=folium.Icon(color="red", icon="star")
    ).add_to(m)
    for _, row in filtered_df.iterrows():
        popup_html = f"""
<div style='width: 250px;'>
  <strong>{row['住所']}</strong><br>
  <ul style='padding-left: 15px; margin: 0;'>
    <li>価格：{row['登録価格（万円）']} 万円</li>
    <li>坪単価：{row['坪単価（万円）']} 万円</li>
    <li>土地面積：{row['土地面積（坪）']} 坪</li>
    <li>公開日：{row['公開日']}</li>
  </ul>
</div>
"""
        folium.Marker(
            location=[row['latitude'], row['longitude']],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row['住所'],
            icon=folium.Icon(color="blue", icon="info-sign")
        ).add_to(m)
    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
