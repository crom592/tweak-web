import json
import os
import random

import requests
import streamlit as st
from google.auth.transport import requests as google_requests
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from google_auth_oauthlib.flow import Flow

# 환경 변수 설정
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "924621236999-a13f9sndsobdaav7idm9d9hrijn8o58e.apps.googleusercontent.com")
# client_secrets_file = os.getenv("GOOGLE_CLIENT_SECRET_PATH", "client_secrets.json")
backend_url = "http://tweak-ec2-alb-1824675680.ap-northeast-2.elb.amazonaws.com"
api_key = "f4328795234b1234567890abcdef0123"



# OAuth 설정
os.environ["OAUTHLIB_INSECURE_TRANSPORT"] = "1"

# Google OAuth 로그인 기능
def login_with_google():
    # Streamlit secrets에서 값 불러오기
    client_id = st.secrets["client_secrets"]["client_id"]
    client_secret = st.secrets["client_secrets"]["client_secret"]
    
    flow = Flow.from_client_config(
        {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.googleapis.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": ["https://tweak-web.streamlit.app"]
            }
        },
        scopes=["https://www.googleapis.com/auth/userinfo.profile", "https://www.googleapis.com/auth/userinfo.email", "openid"],
    )

    query_params = st.query_params

    if 'code' in query_params:
        try:
            code = query_params['code'][0] if isinstance(query_params['code'], list) else query_params['code']
            state = query_params['state'][0] if isinstance(query_params['state'], list) else query_params['state']

            authorization_response = f"http://localhost:8501?state={state}&code={code}"

            flow.fetch_token(authorization_response=authorization_response)
            credentials = flow.credentials

            request = google_requests.Request()
            id_info = id_token.verify_oauth2_token(credentials.id_token, request, GOOGLE_CLIENT_ID)

            st.session_state["user_email"] = id_info.get("email")
            st.session_state["auth_status"] = True

            # SNS 유저 생성 후 토큰 받기
            sns_response = create_sns_user(id_info['sub'], "google", id_info.get("email"))
            if sns_response.status_code == 200:
                sns_data = sns_response.json()
                st.session_state["access_token"] = sns_data['jwt']['access']  # access_token 저장
                st.session_state["refresh_token"] = sns_data['jwt']['refresh']  # refresh_token 저장
                st.rerun()

        except Exception as e:
            st.error(f"로그인 중 오류가 발생했습니다: {e}")
            st.write(f"자세한 오류: {e}")
    else:
        authorization_url, state = flow.authorization_url()
        st.write(f"[Google로 로그인하기]({authorization_url})")

# SNS 유저 생성 요청 (토큰 발급용)
def create_sns_user(sns_id, sns_type, email):
    headers = {
        "X-API-KEY": api_key,
        "Content-Type": "application/json"
    }

    data = {
        "sns_id": sns_id,
        "sns_type": sns_type,
        "email": email
    }

    response = requests.post(f"{backend_url}/sns_user/", json=data, headers=headers)
    return response

# 세션 상태 초기화
if "auth_status" not in st.session_state:
    st.session_state["auth_status"] = False
if "user_email" not in st.session_state:
    st.session_state["user_email"] = None
if "problem_started" not in st.session_state:
    st.session_state["problem_started"] = False
if "current_problem_index" not in st.session_state:
    st.session_state["current_problem_index"] = 0
if "problems" not in st.session_state:
    st.session_state["problems"] = []  # 문제 리스트를 세션 상태로 관리

# 메인 함수
def main():
    st.set_page_config(page_title="Tweak 로그인", layout="centered")

    st.image("로고.png", use_column_width=True)

    st.title("학습을 시작해 볼까요?")
    st.subheader("영작 학습의 모든 것,\nTWEAK에 오신 걸 환영합니다!")

    if not st.session_state["auth_status"]:
        st.write("구글로 로그인하려면 아래 링크를 클릭하세요:")
        login_with_google()
    else:
        st.write(f"환영합니다, {st.session_state['user_email']}!")

        # 대분류 데이터 요청 (level 1)
        categories_response = requests.get(f"{backend_url}/api-category/?level=1")

        if categories_response.status_code == 200:
            categories_data = categories_response.json()
            categories = categories_data.get('result', [])
            if isinstance(categories, list):
                selected_category = st.selectbox("대분류 선택", [category['name'] for category in categories])

                # 선택된 대분류 정보 가져오기
                selected_category_info = next(category for category in categories if category['name'] == selected_category)
                selected_category_code = selected_category_info['code']

                # 소분류 정보 요청 (level 3)
                subcategories_response = requests.get(f"{backend_url}/api-category/?level=3&code__istartswith={selected_category_code}")

                if subcategories_response.status_code == 200:
                    subcategories_data = subcategories_response.json()
                    subcategories = subcategories_data.get('result', [])

                    if isinstance(subcategories, list):
                        selected_subcategory = st.selectbox("소분류 선택", [subcategory['name'] for subcategory in subcategories])

                        # 선택된 소분류 정보 가져오기
                        selected_subcategory_info = next(subcategory for subcategory in subcategories if subcategory['name'] == selected_subcategory)
                        selected_subcategory_id = selected_subcategory_info['id']  # 소분류 ID 가져오기

                        # 난이도 정보 요청
                        difficulty_response = fetch_difficulty()

                        if difficulty_response.status_code == 200:
                            difficulty_data = difficulty_response.json()

                            if isinstance(difficulty_data, dict) and isinstance(difficulty_data.get('result'), list):
                                difficulties = {difficulty['name']: difficulty['id'] for difficulty in difficulty_data['result']}
                                selected_difficulty_name = st.selectbox("난이도 선택", list(difficulties.keys()))
                                selected_difficulty_id = difficulties[selected_difficulty_name]

                                # Day 선택 추가
                                selected_day = st.selectbox("Day 선택", list(range(1, 11)))

                                if st.button("문제 시작하기"):
                                    # 소분류 ID와 난이도 ID, 선택된 day를 session_state에 저장
                                    st.session_state["subcategory_id"] = selected_subcategory_id
                                    st.session_state["difficulty"] = selected_difficulty_id
                                    st.session_state["category"] = selected_subcategory  # 소분류 이름 저장
                                    st.session_state["day"] = selected_day  # 선택된 day 저장
                                    st.session_state["problem_started"] = True
                                    st.session_state["current_problem_index"] = 0  # 첫 번째 문제부터 시작
                                    st.session_state["problems"] = []  # 문제 리스트 초기화
                                    st.rerun()
                            else:
                                st.error("난이도 데이터를 처리하는 중 문제가 발생했습니다.")
                        else:
                            st.error("난이도 정보를 가져오지 못했습니다.")
                    else:
                        st.error("소분류 데이터를 처리하는 중 문제가 발생했습니다.")
                else:
                    st.error("소분류 정보를 가져오지 못했습니다.")
            else:
                st.error("카테고리 데이터를 처리하는 중 문제가 발생했습니다.")
        else:
            st.error("카테고리 정보를 가져오지 못했습니다.")


# 난이도 API 호출 함수
def fetch_difficulty():
    headers = {
        "Authorization": f"Bearer {st.session_state['access_token']}",
    }
    difficulty_response = requests.get(f"{backend_url}/api-difficulty", headers=headers)
    return difficulty_response


# 문제 API 호출 함수 (소분류 ID 기반으로 문제 한 개씩 조회)
def fetch_next_problem():
    day = st.session_state["day"]
    category_id = st.session_state["subcategory_id"]  # 소분류 ID를 category_id로 사용
    difficulty = st.session_state["difficulty"]

    headers = {
        "Authorization": f"Bearer {st.session_state['access_token']}",
    }

    problem_response = requests.get(
        f"{backend_url}/api-writing/content/",
        params={"day": day, "category_id": category_id, "difficulty": difficulty},
        headers=headers
    )
    st.write(f"Request: {problem_response.request.method} {problem_response.request.url} {problem_response.request.headers}")
    if problem_response.status_code == 200:
        problems_data = problem_response.json()
        st.write(problems_data)
        return problems_data.get('result', [])
    else:
        return []


# 문제 풀이 화면
def problem_page():
    st.title("문제 풀이")

    category = st.session_state['category']
    difficulty = st.session_state['difficulty']
    day = st.session_state['day']
    current_problem_index = st.session_state['current_problem_index']

    st.write(f"소분류: {category}, 난이도: {difficulty}, Day: {day}")

    # 문제를 모두 가져오지 않았다면 API 호출
    if not st.session_state['problems']:
        problems = fetch_next_problem()
        st.write(f"문제 {current_problem_index + 1} / {len(problems)}")
        st.session_state['problems'] = problems

    # 현재 문제 가져오기
    if current_problem_index < len(st.session_state['problems']):
        problem = st.session_state['problems'][current_problem_index]
        correct_answer = problem.get("correct_text")

        if correct_answer is None:
            st.error("정답 데이터가 없습니다. 관리자에게 문의하세요.")
            return

        # 문제를 띄어쓰기 기준으로 셔플하기
        shuffled_sentence = " ".join(random.sample(correct_answer.split(), len(correct_answer.split())))

        st.write(f"문제 {current_problem_index + 1}: {shuffled_sentence}")
        user_answer = st.text_input("문장 순서대로 입력", key=f"user_answer_{current_problem_index}")

        # 정답 제출
        if st.button("정답 제출", key=f"submit_answer_{current_problem_index}"):
            if user_answer == correct_answer:
                st.success("정답입니다!")
            else:
                st.error("오답입니다!")
            st.write(f"정답: {correct_answer}")

            # 다음 문제로 이동
            if current_problem_index < len(st.session_state['problems']) - 1:
                st.session_state['current_problem_index'] += 1
                st.rerun()
            else:
                st.success("모든 문제를 완료했습니다!")
    else:
        st.write("문제 데이터를 불러오지 못했습니다.")



# Main function routing
if st.session_state.get("problem_started"):
    problem_page()
else:
    main()
