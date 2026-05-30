import streamlit as st
import anthropic
import sqlite3
import pandas as pd
import json
import re

# ──────────────────────────────────────────
# 설정
# ──────────────────────────────────────────
import os
API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DB_PATH = "hanwha_copilot.db"

client = anthropic.Anthropic(api_key=API_KEY)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)

def init_db(conn):
    conn.execute("DROP TABLE IF EXISTS CUS_CTM")
    conn.execute("DROP TABLE IF EXISTS M_BIZ_MTHY_PS_CR")
    conn.execute("DROP TABLE IF EXISTS M_ORG_MTHY_BZ_ORGN")
    conn.execute("DROP TABLE IF EXISTS SAM_STF")

    conn.execute("""
    CREATE TABLE CUS_CTM (
        CTMNO    TEXT PRIMARY KEY,
        GNDR     TEXT,
        BRTHYR   INTEGER,
        ADDR     TEXT,
        JBCD     TEXT,
        INCMGRD  TEXT
    )""")

    conn.execute("""
    CREATE TABLE M_BIZ_MTHY_PS_CR (
        CLS_YYMM        TEXT,
        PLYNO           TEXT,
        CRT_CTMNO       TEXT,
        MN_NRDPS_CTMNO  TEXT,
        GDNM            TEXT,
        GD_FLGCD        TEXT,
        IKD_GRPCD       TEXT,
        CHNL_FLGCD      TEXT,
        INS_ST          TEXT,
        INS_ND          TEXT,
        DH_STFNO        TEXT,
        CE_STFNO        TEXT,
        PRIMARY KEY (CLS_YYMM, PLYNO)
    )""")

    conn.execute("""
    CREATE TABLE M_ORG_MTHY_BZ_ORGN (
        CLS_YYMM  TEXT,
        STFNO     TEXT,
        HDQNM     TEXT,
        BRNM      TEXT,
        BZP_NM    TEXT,
        PRIMARY KEY (CLS_YYMM, STFNO)
    )""")

    conn.execute("""
    CREATE TABLE SAM_STF (
        STFNO   TEXT PRIMARY KEY,
        GNDR    TEXT,
        BRTHYR  INTEGER
    )""")

    import random
    random.seed(42)

    ADDR_LIST  = ["서울", "경기", "부산", "인천", "대구", "대전", "광주", "울산", "기타"]
    JB_LIST    = ["JB01", "JB02", "JB03", "JB04", "JB05"]
    INCM_LIST  = ["H", "M", "L"]
    CHNL_LIST  = ["GA", "TM", "CM", "BK", "CP"]
    IKD_LIST   = ["L", "A", "G"]
    GD_FLG_MAP = {
        "L": ["LF01","LF02","LF03","LF04"],
        "A": ["AF01","AF02"],
        "G": ["GF01","GF02"],
    }
    GD_NM_MAP = {
        "LF01": ["한화암보험","한화암케어"],
        "LF02": ["한화건강보험","한화통합건강"],
        "LF03": ["한화실손보험","한화실손3세대"],
        "LF04": ["한화치아보험"],
        "AF01": ["한화개인자동차","한화다이렉트자동차"],
        "AF02": ["한화업무용자동차"],
        "GF01": ["한화주택화재","한화일반화재"],
        "GF02": ["한화여행보험"],
    }
    HQ_LIST  = ["서울본부","경기본부","영남본부","호남본부"]
    BRN_MAP  = {
        "서울본부": ["강남사업단","강북사업단","서초사업단"],
        "경기본부": ["수원사업단","성남사업단"],
        "영남본부": ["부산사업단","대구사업단"],
        "호남본부": ["광주사업단","전주사업단"],
    }
    BZP_MAP  = {
        "강남사업단": ["강남지점","역삼지점","삼성지점"],
        "강북사업단": ["종로지점","마포지점"],
        "서초사업단": ["서초지점","방배지점"],
        "수원사업단": ["수원지점","영통지점"],
        "성남사업단": ["분당지점","판교지점"],
        "부산사업단": ["부산지점","해운대지점"],
        "대구사업단": ["대구지점","수성지점"],
        "광주사업단": ["광주지점","전남지점"],
        "전주사업단": ["전주지점","익산지점"],
    }
    YM_LIST = [f"{y}{m:02d}" for y in [2023,2024] for m in range(1,13)]

    # SAM_STF
    staff_list = [(f"STF{i:04d}", random.choice(["M","F"]), random.randint(1970,1998))
                  for i in range(1,201)]
    conn.executemany("INSERT INTO SAM_STF VALUES (?,?,?)", staff_list)

    # CUS_CTM
    customer_list = [(f"CTM{i:06d}", random.choice(["M","F"]),
                      random.randint(1950,2000), random.choice(ADDR_LIST),
                      random.choice(JB_LIST), random.choice(INCM_LIST))
                     for i in range(1,3001)]
    conn.executemany("INSERT INTO CUS_CTM VALUES (?,?,?,?,?,?)", customer_list)

    # M_ORG_MTHY_BZ_ORGN
    stf_ids  = [s[0] for s in staff_list]
    stf_org  = {}
    for stf in stf_ids:
        hq  = random.choice(HQ_LIST)
        brn = random.choice(BRN_MAP[hq])
        bzp = random.choice(BZP_MAP[brn])
        stf_org[stf] = (hq, brn, bzp)
    org_list = [(ym, stf, *stf_org[stf]) for ym in YM_LIST for stf in stf_ids]
    conn.executemany("INSERT INTO M_ORG_MTHY_BZ_ORGN VALUES (?,?,?,?,?)", org_list)

    # M_BIZ_MTHY_PS_CR
    contract_pool = []
    for i in range(1, 2001):
        ikd    = random.choice(IKD_LIST)
        gd_flg = random.choice(GD_FLG_MAP[ikd])
        gdnm   = random.choice(GD_NM_MAP[gd_flg])
        chnl   = random.choice(CHNL_LIST)
        crt    = f"CTM{random.randint(1,3000):06d}"
        mrd    = crt if random.random() < 0.7 else f"CTM{random.randint(1,3000):06d}"
        dh     = random.choice(stf_ids)
        ce     = random.choice(stf_ids)
        sy     = random.randint(2022,2024)
        sm     = random.randint(1,12)
        ey     = sy + random.randint(1,5)
        contract_pool.append({
            "PLYNO": f"PLY{i:07d}", "IKD": ikd, "GD_FLG": gd_flg,
            "GDNM": gdnm, "CHNL": chnl, "CRT": crt, "MRD": mrd,
            "DH": dh, "CE": ce,
            "INS_ST": f"{sy}{sm:02d}01", "INS_ND": f"{ey}{sm:02d}01",
            "ACT_ST": f"{sy}{sm:02d}", "ACT_ND": f"{ey}{sm:02d}",
        })

    monthly_rows = [
        (ym, c["PLYNO"], c["CRT"], c["MRD"], c["GDNM"], c["GD_FLG"],
         c["IKD"], c["CHNL"], c["INS_ST"], c["INS_ND"], c["DH"], c["CE"])
        for ym in YM_LIST for c in contract_pool
        if c["ACT_ST"] <= ym < c["ACT_ND"]
    ]
    conn.executemany("INSERT OR IGNORE INTO M_BIZ_MTHY_PS_CR VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", monthly_rows)
    conn.commit()

# DB 초기화 (테이블 없으면 생성)
if conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0:
    init_db(conn)
       
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
