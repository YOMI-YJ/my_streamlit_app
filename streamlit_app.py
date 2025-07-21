import pandas as pd
import streamlit as st


# 데이터 불러오기
@st.cache_data
def load_data():
    df = pd.read_csv("monthler_processed.csv")
    df['d_day_num'] = pd.to_numeric(df['d_day_num'], errors='coerce')
    df['applicants_num'] = pd.to_numeric(df['applicants_num'], errors='coerce')
    df['region_city'] = df['region_city'].fillna("지역 정보 없음")
    df['region_district'] = df['region_district'].fillna("지역 정보 없음")
    df['category'] = df['category'].fillna("카테고리 정보 없음")
    return df

df = load_data()

# --- 사이드바 필터 ---
st.sidebar.title("🔍 필터 선택")

# 카테고리
category_options = df['category'].unique().tolist()
selected_categories = st.sidebar.multiselect("카테고리 선택", category_options, default=category_options)

# 지역(시/도) = region_city
city_options = sorted(df['region_city'].unique().tolist())
selected_cities = st.sidebar.multiselect("지역(시/도)", city_options, default=city_options)

# 지역(시/군/구) = region_district
filtered_for_districts = df[df['region_city'].isin(selected_cities)]
district_options = sorted(filtered_for_districts['region_district'].unique().tolist())
selected_districts = st.sidebar.multiselect("지역(시/군/구)", district_options, default=district_options)

# D-day
min_d = int(df['d_day_num'].min(skipna=True))
max_d = int(df['d_day_num'].max(skipna=True))
d_day_range = st.sidebar.slider("D-day 범위", min_value=min_d, max_value=max_d, value=(min_d, max_d))
include_no_d_day = st.sidebar.checkbox("D-day 없는 경우 포함", value=True)

# 지원자 수 정렬
sort_option = st.sidebar.radio("지원자 수 정렬", options=["기본", "오름차순", "내림차순"])

# --- 필터 적용 ---
filtered_df = df[
    df['category'].isin(selected_categories) &
    df['region_city'].isin(selected_cities) &
    df['region_district'].isin(selected_districts)
]

if include_no_d_day:
    filtered_df = filtered_df[
        ((filtered_df['d_day_num'] >= d_day_range[0]) & (filtered_df['d_day_num'] <= d_day_range[1])) |
        (filtered_df['d_day_num'].isna())
    ]
else:
    filtered_df = filtered_df[
        (filtered_df['d_day_num'] >= d_day_range[0]) & (filtered_df['d_day_num'] <= d_day_range[1])
    ]

# 정렬 적용
if sort_option == "오름차순":
    filtered_df = filtered_df.sort_values("applicants_num", ascending=True)
elif sort_option == "내림차순":
    filtered_df = filtered_df.sort_values("applicants_num", ascending=False)

# --- 본문 출력 ---
st.title("📅 한달살러 프로그램 탐색기")
st.markdown(f"### 총 {len(filtered_df)}개 프로그램 발견됨")

for _, row in filtered_df.iterrows():
    st.subheader(row['name'])
    st.markdown(f"📍 지역: {row['region_city']} {row['region_district']}")
    st.markdown(f"⏳ D-day: {row['d_day']}")
    st.markdown(f"🧑 지원자: {row['applicants']}")
    st.markdown(f"📌 카테고리: {row['category']}")
    st.markdown("---")
