# ✅ モバイル向け app_mobile.py（住所入力を補正・異常値除外）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

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

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')

st.title("売土地データ検索（スマホ版）")
address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")

if address_query:
    center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
    if center_lat is None or center_lon is None:
        st.stop()
    else:
        st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")
else:
    st.info("検索する住所を入力してください。")
    st.stop()

max_distance = 2.0

df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)

filtered_df = df[df['距離km'] <= max_distance].sort_values(by='坪単価（万円）', ascending=False)

# 上下1件ずつ除外（異常値とみなす）
if len(filtered_df) > 2:
    filtered_df = filtered_df.iloc[1:-1]

# 表示・CSV出力
st.subheader(f"🔎 抽出結果：{len(filtered_df)} 件")
display_columns = ['住所', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']
display_columns = [col for col in display_columns if col in filtered_df.columns]
st.dataframe(filtered_df[display_columns])

csv = filtered_df[display_columns].to_csv(index=False, encoding='utf-8-sig')
st.download_button("📥 結果をCSVでダウンロード", data=csv, file_name='filtered_data.csv', mime='text/csv')

if not filtered_df.empty:
    st.subheader("🗺️ 該当物件の地図表示")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)
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
