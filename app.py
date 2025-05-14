import streamlit as st
import pandas as pd
import requests
import folium
from streamlit_folium import st_folium
from math import radians, sin, cos, sqrt, atan2

# ------------------------------
# 設定
# ------------------------------
GOOGLE_API_KEY = "AIzaSyA-JMG_3AXD5SH8ENFSI5_myBGJVi45Iyg"
CSV_PATH = "住所付き_緯度経度付きデータ.csv"

# ------------------------------
# 補助関数
# ------------------------------
def geocode_address(address: str, api_key: str):
    """住所→緯度経度（失敗時は None, None）。"""
    try:
        resp = requests.get(
            "https://maps.googleapis.com/maps/api/geocode/json",
            params={"address": address, "key": api_key},
            timeout=5,
        )
        data = resp.json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception:
        pass
    return None, None


def haversine(lat1, lon1, lat2, lon2):
    """2 点間距離（km）。"""
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return R * 2 * atan2(sqrt(a), sqrt(1 - a))


# ------------------------------
# データ読み込み & 前処理
# ------------------------------
@st.cache_data(show_spinner=False)
def load_data(path: str) -> pd.DataFrame:
    df = pd.read_csv(path, encoding="utf-8-sig")

    # ① 列名クリーンアップ（前後の空白除去）
    df.columns = df.columns.str.strip()

    # ② lat/lng → latitude/longitude に統一
    rename_map = {}
    if {"lat", "lng"} <= set(df.columns):
        rename_map.update({"lat": "latitude", "lng": "longitude"})
    df = df.rename(columns=rename_map)

    # ③ 緯度経度列必須チェック
    req_cols = {"latitude", "longitude"}
    if not req_cols <= set(df.columns):
        missing = ", ".join(req_cols - set(df.columns))
        st.error(f"CSV に {missing} 列がありません。列名を確認してください。")
        st.stop()

    # ④ 「土地面積（坪）」を自動生成（無ければ ㎡ → 坪 換算）
    if "土地面積（坪）" not in df.columns:
        if "土地面積（㎡）" in df.columns:
            df["土地面積（坪）"] = (df["土地面積（㎡）"] * 0.3025).round(2)
        else:
            st.error("CSV に『土地面積（坪）』『土地面積（㎡）』のいずれも存在しません。")
            st.stop()

    # ⑤ 数値化（「1,234.56」→1234.56）
    df["土地面積（坪）"] = pd.to_numeric(
        df["土地面積（坪）"].astype(str).str.replace(",", ""),
        errors="coerce",
    )

    return df


df = load_data(CSV_PATH)

# ------------------------------
# Streamlit UI
# ------------------------------
st.title("売土地データ検索ツール")

address_query = st.text_input("🔍 中心としたい住所を入力（例：浜松市中区）")
if not address_query:
    st.info("検索する住所を入力してください。")
    st.stop()

center_lat, center_lon = geocode_address(address_query, GOOGLE_API_KEY)
if center_lat is None:
    st.warning("📍 Google で該当住所が見つかりませんでした。")
    st.stop()
st.success(f"中心座標：{center_lat:.6f}, {center_lon:.6f}")

max_distance = st.slider("📏 検索範囲（km）", 0.0, 10.0, 2.0, 0.1)

min_area, max_area = st.slider(
    "📐 土地面積（坪）の範囲",
    0.0,
    float(df["土地面積（坪）"].max()),
    (0.0, 100.0),
    1.0,
)

# ------------------------------
# 距離計算 & フィルタ
# ------------------------------
df["距離km"] = df.apply(
    lambda r: haversine(center_lat, center_lon, r["latitude"], r["longitude"]),
    axis=1,
)

filtered_df = df[
    (df["距離km"] <= max_distance)
    & (df["土地面積（坪）"] >= min_area)
    & (df["土地面積（坪）"] <= max_area)
].copy()

filtered_df = filtered_df.sort_values("坪単価（万円）", ascending=False)
if len(filtered_df) > 2:
    filtered_df = filtered_df.iloc[1:-1]

# ------------------------------
# 表示 & ダウンロード
# ------------------------------
display_columns = [
    "住所",
    "登録価格（万円）",
    "坪単価（万円）",
    "土地面積（坪）",
    "用途地域",
    "取引態様",
    "登録会員",
    "TEL",
    "公開日",
]
display_columns = [c for c in display_columns if c in filtered_df.columns]

st.subheader(f"🔎 抽出結果：{len(filtered_df)} 件")
st.dataframe(filtered_df[display_columns], use_container_width=True)

csv_data = filtered_df[display_columns].to_csv(index=False, encoding="utf-8-sig")
st.download_button(
    "📥 結果を CSV でダウンロード",
    data=csv_data,
    file_name="filtered_data.csv",
    mime="text/csv",
)

# ------------------------------
# 地図表示
# ------------------------------
if not filtered_df.empty:
    st.subheader("🗺️ 該当物件の地図表示")
    m = folium.Map(location=[center_lat, center_lon], zoom_start=13)

    # 検索中心
    folium.Marker(
        location=[center_lat, center_lon],
        tooltip="検索中心",
        icon=folium.Icon(color="red", icon="star"),
    ).add_to(m)

    for _, row in filtered_df.iterrows():
        popup_html = f"""
        <div style="width:250px;">
          <strong>{row.get('住所','-')}</strong><br>
          <ul style="padding-left:15px;margin:0;">
            <li>価格：{row.get('登録価格（万円）','-')} 万円</li>
            <li>坪単価：{row.get('坪単価（万円）','-')} 万円</li>
            <li>土地面積：{row.get('土地面積（坪）','-')} 坪</li>
            <li>用途地域：{row.get('用途地域','-')}</li>
            <li>取引態様：{row.get('取引態様','-')}</li>
            <li>登録会員：{row.get('登録会員','-')}</li>
            <li>TEL：{row.get('TEL','-')}</li>
            <li>公開日：{row.get('公開日','-')}</li>
          </ul>
        </div>
        """
        folium.Marker(
            location=[row["latitude"], row["longitude"]],
            popup=folium.Popup(popup_html, max_width=300),
            tooltip=row.get("住所", ""),
        ).add_to(m)

    st_folium(m, width=700, height=500)
else:
    st.info("該当する物件がありませんでした。")
