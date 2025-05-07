# ✅ モバイル向け app_mobile.py（現在地取得安定化版）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
import streamlit.components.v1 as components
from st_aggrid import AgGrid, GridOptionsBuilder

GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"

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

def haversine(lat1, lon1, lat2, lon2):
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat/2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon/2)**2
    return R * 2 * atan2(sqrt(a), sqrt(1-a))

st.set_page_config(page_title="売土地検索モバイル", layout="wide")
st.title("📱 売土地検索（スマホ版）")

# 位置取得スクリプトと隠しフォーム（streamlit内部に書き込み）
st.markdown("""
<script>
function sendCoords() {
    navigator.geolocation.getCurrentPosition(
        function(pos) {
            const coords = pos.coords.latitude + "," + pos.coords.longitude;
            const streamlitInput = window.parent.document.querySelectorAll('input[data-baseweb="input"]')[0];
            if (streamlitInput) {
                streamlitInput.value = coords;
                streamlitInput.dispatchEvent(new Event('input', { bubbles: true }));
            }
        },
        function(err) {
            alert("位置情報を取得できませんでした。ブラウザの設定をご確認ください。");
        });
}
</script>
<button onclick="sendCoords()" style="padding:12px 24px; font-size:16px; background-color:#007bff; color:white; border:none; border-radius:6px; cursor:pointer; margin:10px auto; display:block;">📍 現在地を取得</button>
""", unsafe_allow_html=True)

coords = st.text_input("緯度,経度（現在地）")
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

df = pd.read_csv('住所付き_緯度経度付きデータ.csv', encoding='utf-8-sig')
df['用途地域'] = df['用途地域'].fillna('-').astype(str)
df['距離km'] = df.apply(lambda row: haversine(center_lat, center_lon, row['latitude'], row['longitude']), axis=1)
filtered_df = df[df['距離km'] <= 2.0].sort_values(by='坪単価（万円）', ascending=False)

st.subheader("検索結果とマップ")

if not filtered_df.empty:
    gb = GridOptionsBuilder.from_dataframe(filtered_df[['住所', '用途地域', '登録価格（万円）', '坪単価（万円）', '土地面積（坪）', '公開日']])
    gb.configure_selection("single", use_checkbox=False)
    grid = AgGrid(filtered_df, gridOptions=gb.build(), height=300, theme="streamlit")
    selected_rows = grid['selected_rows']
    selected_address = selected_rows[0]['住所'].strip() if isinstance(selected_rows, list) and len(selected_rows) > 0 else None

    m = folium.Map(zoom_control=False, dragging=False)
    bounds = []

    for _, row in filtered_df.iterrows():
        color = "red" if row['住所'].strip() == selected_address else "blue"
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
