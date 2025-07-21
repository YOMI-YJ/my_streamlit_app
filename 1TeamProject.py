import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import json
from datetime import datetime, timedelta

def setup_driver():
    """Chrome 드라이버 설정"""
    chrome_options = Options()
    chrome_options.add_argument('--headless')  # 헤드리스 모드
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    chrome_options.add_argument('--disable-gpu')
    chrome_options.add_argument('--window-size=1920,1080')
    chrome_options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36')
    
    driver = webdriver.Chrome(options=chrome_options)
    return driver

def extract_detail_url(card_element):
    """카드에서 상세페이지 링크 추출 (다양한 방법 시도)"""
    # 1. a 태그의 href 속성 확인
    a_tag = card_element.find('a')
    if a_tag and a_tag.get('href'):
        href = a_tag.get('href')
        if href.startswith('http'):
            return href
        elif href.startswith('/'):
            return f"https://www.monthler.kr{href}"
    
    # 2. onclick 속성에서 URL 추출
    onclick = card_element.get('onclick')
    if onclick:
        # onclick="location.href='URL'" 형태에서 URL 추출
        match = re.search(r"location\.href='([^']+)'", onclick)
        if match:
            url = match.group(1)
            if url.startswith('http'):
                return url
            elif url.startswith('/'):
                return f"https://www.monthler.kr{url}"
    
    # 3. data-attribute에서 URL 확인
    for attr in card_element.attrs:
        if 'url' in attr.lower() or 'href' in attr.lower():
            url = card_element.get(attr)
            if url and (url.startswith('http') or url.startswith('/')):
                if url.startswith('/'):
                    return f"https://www.monthler.kr{url}"
                return url
    
    # 4. 부모 요소에서 링크 찾기
    parent = card_element.parent
    if parent:
        parent_a = parent.find('a')
        if parent_a and parent_a.get('href'):
            href = parent_a.get('href')
            if href.startswith('http'):
                return href
            elif href.startswith('/'):
                return f"https://www.monthler.kr{href}"
    
    return None

def parse_d_day(d_day_text):
    """D-day 텍스트를 숫자로 변환"""
    if not d_day_text or pd.isna(d_day_text):
        return None
    
    # "D-30" 형태에서 숫자 추출
    match = re.search(r'D-(\d+)', str(d_day_text))
    if match:
        return int(match.group(1))
    
    # "마감" 등의 텍스트 처리
    if '마감' in str(d_day_text):
        return 0
    
    return None

def parse_fee(fee_text):
    """참가비 텍스트를 숫자로 변환"""
    if not fee_text or pd.isna(fee_text):
        return None
    
    # 숫자만 추출
    numbers = re.findall(r'[\d,]+', str(fee_text))
    if numbers:
        # 쉼표 제거하고 숫자로 변환
        return int(numbers[0].replace(',', ''))
    
    return None

def parse_applicants(applicants_text):
    """지원자 수 텍스트를 숫자로 변환"""
    if not applicants_text or pd.isna(applicants_text):
        return None
    
    # 숫자만 추출
    numbers = re.findall(r'\d+', str(applicants_text))
    if numbers:
        return int(numbers[0])
    
    return None

def categorize_program(name):
    """프로그램명 기반으로 카테고리 분류"""
    name_lower = name.lower()
    
    if any(keyword in name_lower for keyword in ['주거', '숙소', '집', '아파트', '빌라']):
        return '주거지원'
    elif any(keyword in name_lower for keyword in ['취업', '일자리', '채용', '인턴']):
        return '취업지원'
    elif any(keyword in name_lower for keyword in ['창업', '사업', '스타트업']):
        return '창업지원'
    elif any(keyword in name_lower for keyword in ['교육', '학습', '강의', '과정']):
        return '교육지원'
    elif any(keyword in name_lower for keyword in ['문화', '예술', '공연', '전시']):
        return '문화지원'
    elif any(keyword in name_lower for keyword in ['의료', '건강', '병원']):
        return '의료지원'
    else:
        return '기타'

def crawl_monthler():
    """한달살러 사이트 크롤링"""
    url = "https://www.monthler.kr/"
    driver = setup_driver()
    
    try:
        print("한달살러 사이트에 접속 중...")
        driver.get(url)
        time.sleep(5)  # 페이지 로딩 대기 시간 증가
        
        # 페이지가 완전히 로드될 때까지 대기
        print("페이지 로딩 대기 중...")
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.TAG_NAME, "body"))
        )
        
        data = []
        click_count = 0
        max_clicks = 4  # 최대 4번 "더 보기" 클릭
        max_cards = 50  # 최대 50개 카드 수집
        
        while click_count < max_clicks and len(data) < max_cards:
            # 현재 페이지의 카드들 수집 (여러 선택자 시도)
            cards = []
            
            # 다양한 선택자로 카드 찾기 (한달살러 사이트 구조에 맞게 수정)
            selectors = [
                'li > article',
                'article',
                'li',
                '.program-item',
                '.card',
                '[class*="program"]',
                '[class*="card"]',
                '[class*="item"]',
                'div[class*="program"]',
                'div[class*="card"]',
                'section > div',
                'main > div',
                '.container > div'
            ]
            
            for selector in selectors:
                found_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                if len(found_cards) > 0:
                    cards = found_cards
                    print(f"선택자 '{selector}'로 {len(cards)}개의 카드 발견")
                    break
            
            if len(cards) == 0:
                print("카드를 찾을 수 없습니다. 페이지 구조를 확인합니다...")
                page_source = driver.page_source[:2000]  # 처음 2000자만 출력
                print(f"페이지 소스 일부: {page_source}")
                # 페이지 로딩 대기
                time.sleep(5)
                print("5초 대기 후 다시 시도...")
                # 다시 시도
                for selector in selectors:
                    found_cards = driver.find_elements(By.CSS_SELECTOR, selector)
                    if len(found_cards) > 0:
                        cards = found_cards
                        print(f"재시도: 선택자 '{selector}'로 {len(cards)}개의 카드 발견")
                        break
            
            for card in cards:
                try:
                    # 카드 정보 추출
                    card_html = card.get_attribute('outerHTML')
                    soup = BeautifulSoup(card_html, 'html.parser')
                    
                    # 상세페이지 링크 추출
                    detail_url = extract_detail_url(soup)
                    
                    # 기본 정보 추출
                    name_elem = soup.find(['h3', 'h4', 'h5', 'strong'])
                    name = name_elem.get_text(strip=True) if name_elem else "제목 없음"
                    
                    # 이미지 URL 추출
                    img_elem = soup.find('img')
                    img_url = img_elem.get('src') if img_elem else ""
                    if img_url and img_url.startswith('/'):
                        img_url = f"https://www.monthler.kr{img_url}"
                    
                    # 지역 정보 추출
                    region_elem = soup.find("p", class_="ProgramCard_txt_detail__IQ4KS")
                    region = region_elem.get_text(strip=True) if region_elem else "지역 정보 없음"

                    
                    # 가격 정보 추출
                    fee_elem = soup.find(text=re.compile(r'참가비|비용|가격'))
                    fee = fee_elem.parent.get_text(strip=True) if fee_elem else "가격 정보 없음"
                    
                    # 기간 정보 추출
                    period_elem = soup.find(text=re.compile(r'기간|기한'))
                    period = period_elem.parent.get_text(strip=True) if period_elem else "기간 정보 없음"
                    
                    # D-day 정보 추출
                    d_day_elem = soup.find(text=re.compile(r'D-\d+|마감'))
                    d_day = d_day_elem.get_text(strip=True) if d_day_elem else "D-day 정보 없음"
                    
                    # 지원자 수 추출
                    applicants_elem = soup.find(text=re.compile(r'지원자|신청자'))
                    applicants = applicants_elem.parent.get_text(strip=True) if applicants_elem else "지원자 정보 없음"
                    
                    # 혜택/특징 추출
                    features = []
                    feature_elems = soup.find_all(text=re.compile(r'혜택|특징|지원|제공'))
                    for elem in feature_elems:
                        if elem.parent:
                            features.append(elem.parent.get_text(strip=True))
                    
                    # 데이터 저장 (상세페이지 링크가 없어도 기본 정보는 저장)
                    card_data = {
                        'name': name,
                        'detail_url': detail_url or "",
                        'img_url': img_url,
                        'region': region,
                        'fee': fee,
                        'period': period,
                        'd_day': d_day,
                        'applicants': applicants,
                        'features': features
                    }
                    
                    data.append(card_data)
                    print(f"수집: {name}")
                
                except Exception as e:
                    print(f"카드 처리 중 오류: {e}")
                    continue
            
            # "더 보기" 버튼 클릭
            try:
                more_button = driver.find_element(By.XPATH, "//button[contains(text(), '더 보기') or contains(text(), '더보기')]")
                driver.execute_script("arguments[0].click();", more_button)
                click_count += 1
                print(f"더 보기 버튼 클릭 ({click_count}/{max_clicks})")
                time.sleep(2)
            except NoSuchElementException:
                print("더 이상 '더 보기' 버튼이 없습니다.")
                break
            except Exception as e:
                print(f"더 보기 버튼 클릭 중 오류: {e}")
                break
        
        print(f"총 {len(data)}개의 데이터 수집 완료")
        
    except Exception as e:
        print(f"크롤링 중 오류 발생: {e}")
    
    finally:
        driver.quit()
    
    return data

def process_data(data):
    """수집된 데이터 전처리"""
    df = pd.DataFrame(data)
    
    if df.empty:
        print("수집된 데이터가 없습니다.")
        return df
    
    # D-day 숫자 변환
    df['d_day_num'] = df['d_day'].apply(parse_d_day)
    
    # D-day가 만료된 프로그램 제외 (D-day가 0 이하인 경우)
    df = df[df['d_day_num'].isna() | (df['d_day_num'] > 0)]
    
    # 참가비 숫자 변환
    df['fee_num'] = df['fee'].apply(parse_fee)
    
    # 지원자 수 숫자 변환
    df['applicants_num'] = df['applicants'].apply(parse_applicants)
    
    # 지역 정보 분리 (시/도, 시군구)
    def extract_region_info(region_text):
        if pd.isna(region_text):
            return None, None

        text = str(region_text).strip()

        # 특수 케이스 우선 처리
        if text in ['전국', '해외']:
            return text, None

        # 시/도 리스트
        cities = ['서울', '부산', '대구', '인천', '광주', '대전', '울산', '세종', 
                '경기', '강원', '충북', '충남', '전북', '전남', '경북', '경남', '제주']

        for city in cities:
            if text.startswith(city):
                rest = text[len(city):].strip()
                return city, rest if rest else None

        # 매칭 안 된 경우
        return None, text

    
    region_info = df['region'].apply(extract_region_info)
    df['region_city'] = [info[0] for info in region_info]
    df['region_district'] = [info[1] for info in region_info]
    
    # 혜택/특징 리스트화
    df['features_list'] = df['features'].apply(lambda x: x if isinstance(x, list) else [])
    
    # 카테고리 분류
    df['category'] = df['name'].apply(categorize_program)
    
    # 수집 시간 추가
    df['collected_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    
    return df

def main():
    """메인 실행 함수"""
    print("=== 한달살러 숙소 데이터 크롤링 시작 ===")
    
    # 1. 크롤링 실행
    print("\n1단계: 데이터 크롤링 중...")
    data = crawl_monthler()
    
    if not data:
        print("크롤링된 데이터가 없습니다.")
        return
    
    # 2. 데이터 전처리
    print("\n2단계: 데이터 전처리 중...")
    df = process_data(data)
    
    if df.empty:
        print("전처리 후 데이터가 없습니다.")
        return
    
  # ✅ 2.5 중복 제거
    print("\n2.5단계: 중복 제거 중...")
    before_dedup = len(df)
    df = df.drop_duplicates(subset=['name', 'region', 'd_day'], keep='first')
    after_dedup = len(df)
    print(f"중복 제거 완료: {before_dedup - after_dedup}개 중복 제거됨 (최종 {after_dedup}개)")

    
    # 3. CSV 파일로 저장
    print("\n3단계: CSV 파일 저장 중...")
    
    # Streamlit 앱에서 사용할 기본 파일명으로 저장
    df.to_csv("monthler_processed.csv", index=False, encoding='utf-8-sig')
    print(f"파일 저장: monthler_processed.csv (Streamlit 앱용)")
    
    # 백업용 타임스탬프 파일명으로도 저장
    backup_filename = f"monthler_processed_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    df.to_csv(backup_filename, index=False, encoding='utf-8-sig')
    print(f"파일 저장: {backup_filename} (백업용)")
    
    print(f"\n=== 크롤링 완료 ===")
    print(f"총 {len(df)}개의 프로그램 데이터 수집")
    print(f"Streamlit 앱에서 사용할 파일: monthler_processed.csv")
    print(f"백업 파일: {backup_filename}")
    
    # 기본 통계 출력
    print(f"\n=== 기본 통계 ===")
    print(f"카테고리별 분포:")
    print(df['category'].value_counts())
    print(f"\n지역별 분포 (상위 10개):")
    print(df['region_city'].value_counts().head(10))

if __name__ == "__main__":
    main() 