# ✅ モバイル向け app_mobile.py（軽量・スマホUI最適化）
import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2
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

st.set_page_config(page_title="売土地検索モバイル", layout="wide")
st.title("\U0001F3E0 売土地検索（スマホ版）")

# 現在地ボタンで取得 → 座標取得
def get_coords_via_js():
    components.html(
        """
        <script>
        function sendCoords() {
            navigator.geolocation.getCurrentPosition(
                function(pos) {
                    const lat = pos.coords.latitude;
                    const lon = pos.coords.longitude;
                    const coords = lat + "," + lon;
                    const input = window.parent.document.querySelector("iframe").contentWindow.document.querySelector("input#coords");
                    if (input) input.value = coords;
                });
        }
        </script>
        <button onclick="sendCoords()">\uD83D\uDCCD 現在地を取得</button>
        <input type="hidden" id="coords" value="" />
        """,
        height=50
    )

get_coords_via_js()
coord_input = st.text_input("\uD83C\uDF10 緯度,経度（現在地）", key="coords")
address_query = ""

if coord_input and "," in coord_input:
    lat, lon = map(float, coord_input.split(","))
    address_query = reverse_geocode(lat, lon, GOOGLE_API_KEY)

address_query = st.text_input("検索中心住所（自動または手動入力）", value=address_query)

if not address_query:
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None or center_lon is None:
    st.error("住所が見つかりませんでした。")
    st.stop()

# データ読み込み・前処理
df = pd