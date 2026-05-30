import streamlit as st
import anthropic
import sqlite3
import pandas as pd
import json
import re

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
API_KEY = "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"
DB_PATH = "hanwha_copilot.db"

client = anthropic.Anthropic(api_key=API_KEY)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

# ──────────────────────────────────────────
# 시스템 프롬프트
# ──────────────────────────────────────────
SYSTEM_PROMPT = """
당신은 한화손해보험 데이터분석 전문 AI 어시스턴트입니다.
SQLite DB에 접근하여 고객 KPI를 분석하고 답변합니다.
반드시 아래 규칙과 스키마를 따라 SQL을 작성하세요.

=== 핵심 용어 정의 ===
- 보유고객: 해당 CLS_YYMM에 정상계약이 존재하는 고객
- 신규고객(전사): 당월 보유고객 중 전월에 보유계약이 없던 고객
- 신규고객(채널내): 당월 보유고객 중 전월에 동일 채널 보유계약이 없던 고객
- 신규고객(보종내): 당월 보유고객 중 전월에 동일 보종 보유계약이 없던 고객
- 이탈고객: 전월엔 보유계약 있었는데 당월엔 없는 고객
- 신계약고객: 당월에 보험시기(INS_ST)가 시작된 고객
- 장기다건: 장기(IKD_GRPCD=L) 계약을 2건 이상 보유한 고객
- 자장연계: 자동차 보유고객 중 장기도 보유한 고객
- 자운연계: 자동차 보유고객 중 운전자보험(GD_FLGCD=LF02)도 보유한 고객

=== 테이블 스키마 ===

[M_BIZ_MTHY_PS_CR] 월별계약 (정상계약만 적재)
- CLS_YYMM        : 기준년월 (PK, 예: 202412)
- PLYNO           : 증권번호 (PK)
- CRT_CTMNO       : 계약자 고객번호
- MN_NRDPS_CTMNO  : 피보험자 고객번호
- GDNM            : 상품명
- GD_FLGCD        : 상품군코드
- IKD_GRPCD       : 보종코드 (L=장기, A=자동차, G=일반)
- CHNL_FLGCD      : 채널코드 (GA=전속, TM=TM, CM=다이렉트, BK=방카, CP=법인)
- INS_ST          : 보험시기 (계약시작일, 예: 20240101)
- INS_ND          : 보험종기 (계약종료일)
- DH_STFNO        : 취급자 설계사ID
- CE_STFNO        : 모집자 설계사ID

[CUS_CTM] 고객
- CTMNO    : 고객번호 (PK)
- GNDR     : 성별 (M=남, F=여)
- BRTHYR   : 출생연도
- ADDR     : 주소
- JBCD     : 직업코드
- INCMGRD  : 소득등급 (H=고, M=중, L=저)

[M_ORG_MTHY_BZ_ORGN] 월별영업조직
- CLS_YYMM : 기준년월 (PK)
- STFNO    : 설계사ID (PK)
- HDQNM    : 본부명
- BRNM     : 사업단명
- BZP_NM   : 지점명

[SAM_STF] 직원
- STFNO    : 설계사ID (PK)
- GNDR     : 성별
- BRTHYR   : 출생연도

=== SQL 작성 규칙 ===
1. SQLite 문법만 사용
2. 신규/이탈 고객 추출 시 반드시 LEFT JOIN 방식 사용
3. 고객 수는 COUNT(DISTINCT CRT_CTMNO) 사용
4. 연령대 계산: (기준년도 - BRTHYR) / 10 * 10 으로 10세 단위 구분
5. 결과는 LIMIT 100 이하로 제한

=== 예시 쿼리 ===

[예시 1] 보유고객 수 (전사/채널별/보종별)
SELECT CLS_YYMM, IKD_GRPCD, CHNL_FLGCD,
       COUNT(DISTINCT CRT_CTMNO) AS 보유고객수
FROM M_BIZ_MTHY_PS_CR
WHERE CLS_YYMM = '202412'
GROUP BY CLS_YYMM, IKD_GRPCD, CHNL_FLGCD
ORDER BY IKD_GRPCD, CHNL_FLGCD;

[예시 2] 신규고객 수 (전사 기준)
SELECT curr.CLS_YYMM, curr.IKD_GRPCD,
       COUNT(DISTINCT curr.CRT_CTMNO) AS 신규고객수
FROM M_BIZ_MTHY_PS_CR curr
LEFT JOIN M_BIZ_MTHY_PS_CR prev
    ON curr.CRT_CTMNO = prev.CRT_CTMNO
    AND prev.CLS_YYMM = '202411'
WHERE curr.CLS_YYMM = '202412'
    AND prev.CRT_CTMNO IS NULL
GROUP BY curr.CLS_YYMM, curr.IKD_GRPCD;

[예시 3] 이탈고객 수
SELECT prev.CLS_YYMM AS 전월, prev.IKD_GRPCD,
       COUNT(DISTINCT prev.CRT_CTMNO) AS 이탈고객수
FROM M_BIZ_MTHY_PS_CR prev
LEFT JOIN M_BIZ_MTHY_PS_CR curr
    ON prev.CRT_CTMNO = curr.CRT_CTMNO
    AND curr.CLS_YYMM = '202412'
WHERE prev.CLS_YYMM = '202411'
    AND curr.CRT_CTMNO IS NULL
GROUP BY prev.CLS_YYMM, prev.IKD_GRPCD;

[예시 4] 장기다건 / 자장연계 / 자운연계
WITH
long_term AS (
    SELECT CRT_CTMNO, COUNT(DISTINCT PLYNO) AS 장기계약수
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202412' AND IKD_GRPCD = 'L'
    GROUP BY CRT_CTMNO
),
auto AS (
    SELECT DISTINCT CRT_CTMNO
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202412' AND IKD_GRPCD = 'A'
),
driver AS (
    SELECT DISTINCT CRT_CTMNO
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202412' AND GD_FLGCD = 'LF02'
)
SELECT
    COUNT(DISTINCT CASE WHEN lt.장기계약수 >= 2 THEN lt.CRT_CTMNO END) AS 장기다건고객수,
    COUNT(DISTINCT CASE WHEN a.CRT_CTMNO IS NOT NULL AND lt.CRT_CTMNO IS NOT NULL
                        THEN a.CRT_CTMNO END) AS 자장연계고객수,
    COUNT(DISTINCT CASE WHEN a.CRT_CTMNO IS NOT NULL AND d.CRT_CTMNO IS NOT NULL
                        THEN a.CRT_CTMNO END) AS 자운연계고객수,
    COUNT(DISTINCT a.CRT_CTMNO) AS 자동차보유고객수
FROM auto a
LEFT JOIN long_term lt ON a.CRT_CTMNO = lt.CRT_CTMNO
LEFT JOIN driver d ON a.CRT_CTMNO = d.CRT_CTMNO;

[예시 5] 성별/연령대별 보유고객
SELECT c.GNDR,
       (2024 - cu.BRTHYR) / 10 * 10 AS 연령대,
       COUNT(DISTINCT c.CRT_CTMNO) AS 보유고객수
FROM M_BIZ_MTHY_PS_CR c
JOIN CUS_CTM cu ON c.CRT_CTMNO = cu.CTMNO
WHERE c.CLS_YYMM = '202412' AND c.IKD_GRPCD = 'L'
GROUP BY c.GNDR, 연령대
ORDER BY c.GNDR, 연령대;

=== 응답 형식 ===
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
{
  "sql": "실행할 SQL",
  "explanation": "이 쿼리가 무엇을 조회하는지 1~2문장 설명"
}
"""

# ──────────────────────────────────────────
# 함수
# ──────────────────────────────────────────
def ask_to_sql(question):
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=1000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": question}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
    return json.loads(raw)

def run_sql(sql):
    try:
        return pd.read_sql(sql, conn), None
    except Exception as e:
        return None, str(e)

# ──────────────────────────────────────────
# Streamlit 화면
# ──────────────────────────────────────────
st.set_page_config(
    page_title="고객 KPI 분석 Copilot",
    page_icon="📊",
    layout="wide"
)

st.title("📊 고객 KPI 분석 Copilot")
st.caption("한화손해보험 데이터Biz파트 · 자연어로 고객 데이터를 분석하세요")

st.divider()

# 상단 KPI 카드
st.subheader("이번 달 보유고객 현황 (2024년 12월)")
col1, col2, col3 = st.columns(3)

df_kpi = pd.read_sql("""
    SELECT IKD_GRPCD, COUNT(DISTINCT CRT_CTMNO) AS 보유고객수
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202412'
    GROUP BY IKD_GRPCD
""", conn)

kpi_map = dict(zip(df_kpi["IKD_GRPCD"], df_kpi["보유고객수"]))
col1.metric("장기 (L)", f"{kpi_map.get('L', 0):,}명")
col2.metric("자동차 (A)", f"{kpi_map.get('A', 0):,}명")
col3.metric("일반 (G)", f"{kpi_map.get('G', 0):,}명")

st.divider()

# 채팅 인터페이스
st.subheader("💬 자연어로 질문하세요")

# 질문 예시 버튼
st.caption("예시 질문")
ex_col1, ex_col2, ex_col3 = st.columns(3)
if ex_col1.button("장기 채널별 보유고객 수"):
    st.session_state["question"] = "2024년 12월 장기 보유고객 수를 채널별로 알려줘"
if ex_col2.button("신규고객 전월 대비 증감"):
    st.session_state["question"] = "2024년 12월 신규고객이 전월 대비 얼마나 늘었어?"
if ex_col3.button("여성 고객 연령대 분포"):
    st.session_state["question"] = "2024년 12월 장기 여성 고객 연령대별 분포 알려줘"

# 질문 입력창
question = st.text_input(
    "질문 입력",
    value=st.session_state.get("question", ""),
    placeholder="예: 2024년 12월 GA채널 장기 신규고객 수 알려줘",
    label_visibility="collapsed"
)

if st.button("분석하기", type="primary") and question:
    with st.spinner("분석 중..."):
        result = ask_to_sql(question)
        df, error = run_sql(result["sql"])

    st.markdown(f"**설명:** {result['explanation']}")

    with st.expander("생성된 SQL 보기"):
        st.code(result["sql"], language="sql")

    if error:
        st.error(f"쿼리 오류: {error}")
    else:
        st.dataframe(df, use_container_width=True)