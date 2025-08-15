#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""app_mobile.py – Streamlit 売土地検索ツール（モバイル版）
2025-08-16 rev6

- 吹き出しに「日付」を確実に表示（NaN/空文字/NaT/None/- を安全処理）
- 一覧表で該当行をクリック（選択）すると、マップの該当ピンを緑色で強調
- スマホ画面向け：スライダー常時表示、面積上限500=500坪以上
- 60坪以下の物件は初期除外
"""

from __future__ import annotations

import os
import urllib.parse
from pathlib import Path
from math import radians, sin, cos, sqrt, atan2

import pandas as pd
import requests
import streamlit as st
import folium
from streamlit_folium import st_folium

# ────────────────────────────────────────────────
# 🔑 Google Maps API Key
# ------------------------------------------------
try:
    from dotenv import load_dotenv, find_dotenv
    load_dotenv(find_dotenv(usecwd=True), override=False)
except ImportError:
    pass

GOOGLE_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "")
CSV_PATH = Path("住所付き_緯度経度付きデータ_1.csv")  # 必要に応じてパスを修正

# ────────────────────────────────────────────────
# ユーティリティ
# ------------------------------------------------
@st.cache_data(show_spinner=False)
def geocode_address(addr: str):
    """住所 → (lat, lon)。API キーが無い場合は (None, None)"""
    if not GOOGLE_API_KEY:
        return None, None
    url = (
        "https://maps.googleapis.com/maps/api/geocode/json?"
        + urllib.parse.urlencode(
            {"address": addr, "key": GOOGLE_API_KEY, "language": "ja"}, safe=":"
        )
    )
    try:
        data = requests.get(url, timeout=5).json()
        if data.get("status") == "OK":
            loc = data["results"][0]["geometry"]["location"]
            return loc["lat"], loc["lng"]
    except Exception:
        pass
    return None, None


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """2点間の距離 (km)"""
    R = 6371.0
    dlat, dlon = map(radians, (lat2 - lat1, lon2 - lon1))
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    return 2 * R * atan2(sqrt(a), sqrt(1 - a))


def _fmt_date(val) -> str:
    """NaN/NaT/None/空文字/'-' を空にし、それ以外は文字列で返す"""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return ""
    try:
        if pd.isna(val):
            return ""
    except Exception:
        pass
    s = str(val).strip()
    return "" if s.lower() in {"", "nan", "nat", "none", "-"} else s


@st.cache_data(show_spinner=False)
def load_data(path: Path) -> pd.DataFrame:
    """CSV読み込み(UTF-8/UTF-8-BOM/Shift-JIS) → 列整形 → 坪/坪単価計算 → 日付整形"""
    # 1. 読み込み
    for enc in ("utf-8-sig", "utf-8", "cp932"):
        try:
            df = pd.read_csv(path, encoding=enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        st.error("CSV読み込みに失敗しました。文字コードをご確認ください。")
        st.stop()

    # 2. 列名整形
    df.columns = df.columns.str.strip()
    df = df.rename(columns={"lat": "latitude", "lng": "longitude"})

    if not {"latitude", "longitude"}.issubset(df.columns):
        st.error("CSVに latitude/longitude 列が見当たりません。")
        st.stop()

    # 3. 面積(坪)列の生成（㎡→坪換算）
    if "土地面積（坪）" not in df.columns:
        if "土地面積（㎡）" in df.columns:
            df["土地面積（坪）"] = (df["土地面積（㎡）"] / 3.305785).round(2)
        else:
            st.error("CSVに土地面積列が見当たりません。")
            st.stop()

    # 4. 数値化
    df["土地面積（坪）"] = pd.to_numeric(
        df["土地面積（坪）"].astype(str).str.replace(",", ""), errors="coerce"
    )

    # 5. 坪単価計算
    price_col = "登録価格（万円）" if "登録価格（万円）" in df.columns else "価格(万円)"
    df[price_col] = pd.to_numeric(df[price_col].astype(str).str.replace(",", ""), errors="coerce")
    df["坪単価（万円/坪）"] = (df[price_col] / df["土地面積（坪）"]).round(1)

    # 6. 日付列の統一
    date_src = None
    for col in ("日付", "掲載日", "更新日", "掲載開始日"):
        if col in df.columns:
            date_src = col
            break
    if date_src:
        df["日付"] = df[date_src].map(_fmt_date)
    else:
        df["日付"] = ""

    return df


# ────────────────────────────────────────────────
# ページ設定
# ------------------------------------------------
st.set_page_config(page_title="売土地検索 (モバイル)", page_icon="🏠", layout="centered")
st.title("🏠 売土地検索（モバイル版）")

# ────────────────────────────────────────────────
# データロード & 60坪以下除外
# ------------------------------------------------
_df = load_data(CSV_PATH)
_df = _df[_df["土地面積（坪）"] > 60].reset_index(drop=True)

# ────────────────────────────────────────────────
# 住所入力
# ------------------------------------------------
st.subheader("① 検索中心の住所を入力")
address = st.text_input("例：浜松市中央区高林1丁目")
if not address:
    st.stop()

center_lat, center_lon = geocode_address(address.strip())
if center_lat is None:
    st.warning("住所が見つかりませんでした。再入力してください。")
    st.stop()

# ────────────────────────────────────────────────
# 検索条件（スライダー常時表示）
# ------------------------------------------------
radius_km = st.slider("検索半径 (km)", 0.5, 5.0, 2.0, 0.1)

MAX_TSUBO_UI = 500
min_t, max_t = st.slider(
    "土地面積 (坪) ※500=500坪以上",
    0,
    MAX_TSUBO_UI,
    (0, MAX_TSUBO_UI),
    step=10,
)

# ────────────────────────────────────────────────
# フィルタ & 距離計算
# ------------------------------------------------
_df["距離(km)"] = _df.apply(
    lambda r: haversine(center_lat, center_lon, r.latitude, r.longitude),
    axis=1,
)
cond = (_df["距離(km)"] <= radius_km) & (_df["土地面積（坪）"] >= min_t)
if max_t < MAX_TSUBO_UI:
    cond &= _df["土地面積（坪）"] <= max_t

flt = _df[cond].copy()

# 並び順（例：距離近い順 or 坪単価高い順）—従来のままなら坪単価降順
flt = flt.sort_values("坪単価（万円/坪）", ascending=False).reset_index(drop=True)

# ────────────────────────────────────────────────
# 一覧テーブル（行クリック＝選択 → ピン強調）
# ------------------------------------------------
st.markdown(f"**② 検索結果：{len(flt)} 件**")

# 表示列
cols_order = [
    "住所", "日付", "距離(km)", "登録価格（万円）", "坪単価（万円/坪）",
    "土地面積（坪）", "用途地域", "取引態様", "登録会員", "TEL",
]
cols = [c for c in cols_order if c in flt.columns]

# 距離・数値整形
flt["距離(km)"] = flt["距離(km)"].round(2)
# 「選択」列を先頭に追加（初期 False）
if "選択" not in flt.columns:
    flt.insert(0, "選択", False)

# セッションに選択インデックスを保持（単一選択）
sel_key = "selected_row_index"
if sel_key not in st.session_state:
    st.session_state[sel_key] = None

# 直前の選択を反映
if st.session_state[sel_key] is not None and 0 <= st.session_state[sel_key] < len(flt):
    flt.loc[:, "選択"] = False
    flt.at[st.session_state[sel_key], "選択"] = True

# 編集不可にしてクリックしやすく（「選択」だけ編集可）
disabled_cols = [c for c in cols if c != "選択"]
edited = st.data_editor(
    flt[["選択"] + [c for c in cols if c != "選択"]],
    hide_index=True,
    height=320,
    use_container_width=True,
    column_config={
        "選択": st.column_config.CheckboxColumn("選択（1件のみ）", help="クリックで行を選択"),
    },
    disabled=disabled_cols,  # 値の変更を防ぎ、タップで選択しやすく
    key="editor_table",
)

# 「選択」列が複数 True になった場合は先頭のみ残す（単一選択に正規化）
true_rows = edited.index[edited["選択"] == True].to_list()
if len(true_rows) > 1:
    # 先頭のみ True、他は False に修正
    keep = true_rows[0]
    edited.loc[:, "選択"] = False
    edited.at[keep, "選択"] = True
    st.session_state[sel_key] = keep
elif len(true_rows) == 1:
    st.session_state[sel_key] = true_rows[0]
else:
    st.session_state[sel_key] = None

selected_idx = st.session_state[sel_key]

# ────────────────────────────────────────────────
# 地図表示（選択行のピンを緑色に）
# ------------------------------------------------
st.markdown("**③ 地図で確認**")
m = folium.Map(location=[center_lat, center_lon], zoom_start=14, control_scale=True)
folium.Marker(
    [center_lat, center_lon],
    tooltip="検索中心",
    icon=folium.Icon(color="red", icon="star"),
).add_to(m)

# 地図の表示範囲（bounds）用に座標を収集
bounds = [[center_lat, center_lon]]

# ピン描画
for i, r in edited.reset_index(drop=True).iterrows():
    # 価格フォーマット
    raw_price = r.get("登録価格（万円）", r.get("価格(万円)", None))
    try:
        price_fmt = f"{float(raw_price):,.0f}"
    except (TypeError, ValueError):
        price_fmt = "-"

    # 日付
    date_txt = _fmt_date(r.get("日付", ""))

    # ポップアップ用 HTML を安全に構築
    popup_parts = []
    popup_parts.append(f"<b>{r.get('住所', '-')}</b>")
    if date_txt:
        popup_parts.append(f"日付：{date_txt}")
    popup_parts.append(f"価格：{price_fmt} 万円")
    if pd.notna(r.get("土地面積（坪）")):
        popup_parts.append(f"面積：{r['土地面積（坪）']:.1f} 坪")
    if pd.notna(r.get("坪単価（万円/坪）")):
        popup_parts.append(
            f"<span style='color:#d46b08;'>坪単価：{r['坪単価（万円/坪）']:.1f} 万円/坪</span>"
        )
    popup_parts.append(f"登録会員：{r.get('登録会員', '-')}")
    popup_parts.append(f"TEL：{r.get('TEL', '-')}")

    popup_html = "<br>".join(popup_parts)

    # 選択行は緑、それ以外は青
    color = "green" if (selected_idx is not None and i == selected_idx) else "blue"

    lat, lon = float(r["latitude"]), float(r["longitude"])
    folium.Marker(
        [lat, lon],
        popup=folium.Popup(popup_html, max_width=260),
        tooltip=r.get("住所", "-"),
        icon=folium.Icon(color=color, icon="home", prefix="fa"),
    ).add_to(m)

    bounds.append([lat, lon])


# すべてのピンが入るように調整（物件があれば）
if len(bounds) > 1:
    m.fit_bounds(bounds, padding=(20, 20))

st_folium(m, width="100%", height=480)
st.caption("Powered by Streamlit ❘ Google Maps Geocoding API")
