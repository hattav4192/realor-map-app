import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
from streamlit_js_eval import get_geolocation

# ------------------------------
# 設定
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"
st.set_page_config(page_title="売土地検索スマホ", layout="centered")

st.title("🏠 売土地検索（スマホ）")
st.markdown("現在地または住所を入力して、2km圏内の土地情報を表示します。")

# ------------------------------
# 逆ジオコーディング
# ------------------------------
def reverse_geocode(lat, lon, api_key):
    url = f"https://maps.googleapis.com/maps/api/geocode/json?latlng={lat},{lon}&key={api_key}"
    data = requests.get(url).json()
    if data.get('status') == 'OK':
        return data['results'][0]['formatted_address']
    return ""

# ------------------------------
# ジオコーディング（住所→座標）
# ------------------------------
def geocode_address(address, api_key):
    try:
        clean = address.strip().replace('　', '').replace(' ', '')
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={clean}&key={api_key}"
        data = requests.get(url).json()
        if data.get('status') == 'OK':
            loc = data['results'][0]['geometry']['location']
            return loc['lat'], loc['lng']
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
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

# ------------------------------
# 入力フォームと現在地取得
# ------------------------------
location = get_geolocation()
if location and location.get("coords"):
    lat0 = location["coords"]["latitude"]
    lon0 = location["coords"]["longitude"]
    default_addr = reverse_geocode(lat0, lon0, GOOGLE_API_KEY)
    address_query = st.text_input("🔍 検索したい中心住所", value=default_addr)
else:
    address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")

if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None:
    st.stop()

# ------------------------------
# データ読み込み・計算
# ------------------------------
csv_file = '住所付き_緯度経度付きデータ.csv'
df = pd.read_csv(csv_file, encoding='utf-8-sig')
df = df.dropna(subset=['latitude', 'longitude'])
df['距離km'] = df.apply(lambda r: haversine(center_lat, center_lon, r['latitude'], r['longitude']), axis=1)
filtered = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

# 異常値除去（最上位・最下位を除去）
if len(filtered) > 2:
    filtered = filtered.iloc[1:-1]

# ------------------------------
# 結果表示
# ------------------------------
st.subheader("📋 該当物件一覧")
cols = [
    '住所', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）',
    '用途地域', '取引態様', '登録会員', 'TEL', '公開日'
]
st.dataframe(filtered[cols])

# ------------------------------
# 地図表示とポップアップ
# ------------------------------
if not filtered.empty:
    st.subheader("🗺️ 地図で確認")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
    folium.Marker([center_lat, center_lon], popup="検索中心（現在地）", icon=folium.Icon(color="red", icon="star")).add_to(m)
    for _, r in filtered.iterrows():
        html = f"""
<div style='width:250px;'>
  <strong>{r['住所']}</strong><br>
  <ul style='padding-left:15px;margin:0;'>
    <li>価格：{r['登録価格（万円）']} 万円</li>
    <li>坪単価：{r['坪単価（万円）']} 万円</li>
    <li>土地面積：{r['土地面積（坪）']} 坪</li>
    <li>用途地域：{r['用途地域']}</li>
    <li>取引態様：{r['取引態様']}</li>
    <li>登録会員：{r['登録会員']}</li>
    <li>TEL：{r['TEL']}</li>
    <li>公開日：{r['公開日']}</li>
  </ul>
</div>
"""
        folium.Marker([r['latitude'], r['longitude']], popup=folium.Popup(html, max_width=300), tooltip=r['住所'], icon=folium.Icon(color="blue", icon="info-sign")).add_to(m)
    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
