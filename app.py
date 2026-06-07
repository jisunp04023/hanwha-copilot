from dotenv import load_dotenv
load_dotenv()

import anthropic
import sqlite3
import pandas as pd
import plotly.express as px
import json
import re
import os
from io import BytesIO
from PIL import Image
import streamlit as st

API_KEY = os.environ.get("ANTHROPIC_API_KEY")
DB_PATH = "/tmp/hanwha_copilot.db" if os.path.exists("/tmp") else "hanwha_copilot.db"

client = anthropic.Anthropic(api_key=API_KEY)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db(conn):
    conn.executescript("""
    CREATE TABLE IF NOT EXISTS CUS_CTM (
        CTMNO TEXT PRIMARY KEY, GNDR TEXT, BRTHYR INTEGER,
        ADDR TEXT, JOB_GRP TEXT, ESTM_INCM INTEGER
    );
    CREATE TABLE IF NOT EXISTS M_BIZ_MTHY_PS_CR (
        CLS_YYMM TEXT, PLYNO TEXT, CRT_CTMNO TEXT, MN_NRDPS_CTMNO TEXT,
        GDNM TEXT, GD_FLGCD TEXT, IKD_GRPCD TEXT, CHNL_FLGCD TEXT,
        INS_ST TEXT, INS_ND TEXT, DH_STFNO TEXT, CE_STFNO TEXT,
        PRIMARY KEY (CLS_YYMM, PLYNO)
    );
    CREATE TABLE IF NOT EXISTS M_ORG_MTHY_BZ_ORGN (
        CLS_YYMM TEXT, STFNO TEXT, HDQNM TEXT, BRNM TEXT, BZP_NM TEXT,
        PRIMARY KEY (CLS_YYMM, STFNO)
    );
    CREATE TABLE IF NOT EXISTS SAM_STF (
        STFNO TEXT PRIMARY KEY, GNDR TEXT, BRTHYR INTEGER
    );
    """)

    import random
    random.seed(42)

    ADDR_LIST = ["수도권","영남권","호남권","충청권","강원권","제주"]
    ADDR_W    = [0.50,0.22,0.12,0.10,0.04,0.02]
    JOB_LIST  = ["화이트","블루","자영업","주부","전문직"]
    JOB_W     = [0.30,0.25,0.20,0.15,0.10]
    CHNL_WEIGHT = {
        "2023": {"전속":0.32,"GA":0.59,"교차":0.04,"TM":0.08,"CM":0.01},
        "2024": {"전속":0.27,"GA":0.64,"교차":0.04,"TM":0.07,"CM":0.01},
        "2025": {"전속":0.23,"GA":0.68,"교차":0.04,"TM":0.06,"CM":0.01},
        "2026": {"전속":0.21,"GA":0.71,"교차":0.03,"TM":0.04,"CM":0.01},
    }
    LA_INFO = {
        "LA01":{"names":["한화 종합보험","한화 참좋은 종합보험"],"w":0.41},
        "LA02":{"names":["한화 운전자보험","한화 참좋은 운전자보험"],"w":0.17},
        "LA03":{"names":["한화 더 경증 간편건강보험","한화 더 경증 간편건강보험Ⅱ"],"w":0.08},
        "LA04":{"names":["한화 자녀보험"],"w":0.08},
        "LA05":{"names":["한화 간병보험"],"w":0.06},
        "LA06":{"names":["한화 실손보험"],"w":0.05},
        "LA07":{"names":["한화 상해보험"],"w":0.04},
        "LA08":{"names":["한화 재물보험"],"w":0.04},
        "LA09":{"names":["한화 암보험"],"w":0.03},
        "LA10":{"names":["한화 치아보험"],"w":0.02},
        "LA11":{"names":["한화 연금저축보험"],"w":0.01},
        "LA12":{"names":["한화 기타보험"],"w":0.01},
    }
    SIG_PRODUCTS = {
        "LA01": {"202307":["한화 시그니처 여성보험 1.0"],"202401":["한화 시그니처 여성보험 2.0"],"202411":["한화 시그니처 여성보험 3.0"],"202601":["한화 시그니처 여성보험 4.0"]},
        "LA02": {"202401":["한화 시그니처 여성 운전자상해보험"]},
        "LA03": {"202401":["한화 시그니처 여성 3N5 간편건강보험 2.0","한화 시그니처 여성 355 간편건강보험 2.0"],"202411":["한화 시그니처 여성 3N5 간편건강보험 3.0","한화 시그니처 여성 355 간편건강보험 3.0"]},
    }
    HQ_LIST = ["서울본부","경기본부","영남본부","호남본부"]
    BRN_MAP = {"서울본부":["강남사업단","강북사업단","서초사업단"],"경기본부":["수원사업단","성남사업단"],"영남본부":["부산사업단","대구사업단"],"호남본부":["광주사업단","전주사업단"]}
    BZP_MAP = {"강남사업단":["강남지점","역삼지점","삼성지점"],"강북사업단":["종로지점","마포지점"],"서초사업단":["서초지점","방배지점"],"수원사업단":["수원지점","영통지점"],"성남사업단":["분당지점","판교지점"],"부산사업단":["부산지점","해운대지점"],"대구사업단":["대구지점","수성지점"],"광주사업단":["광주지점","전남지점"],"전주사업단":["전주지점","익산지점"]}
    YM_LIST = [f"2023{m:02d}" for m in range(1,13)] + [f"2024{m:02d}" for m in range(1,13)] + [f"2025{m:02d}" for m in range(1,13)] + [f"2026{m:02d}" for m in range(1,5)]

    staff_list = [(f"STF{i:04d}", random.choice(["M","F"]), random.randint(1970,1998)) for i in range(1,201)]
    conn.executemany("INSERT OR IGNORE INTO SAM_STF VALUES (?,?,?)", staff_list)
    stf_ids = [s[0] for s in staff_list]

    stf_org = {}
    for stf in stf_ids:
        hq=random.choice(HQ_LIST); brn=random.choice(BRN_MAP[hq]); bzp=random.choice(BZP_MAP[brn])
        stf_org[stf]=(hq,brn,bzp)
    org_rows=[(ym,stf,*stf_org[stf]) for ym in YM_LIST for stf in stf_ids]
    conn.executemany("INSERT OR IGNORE INTO M_ORG_MTHY_BZ_ORGN VALUES (?,?,?,?,?)", org_rows)

    N_CTM = 50000
    customer_rows = []
    for i in range(1, N_CTM+1):
        t = random.choices(["low","mid","high","vhigh"],[30,40,25,5])[0]
        incm = {"low":random.randint(500,2999),"mid":random.randint(3000,4999),"high":random.randint(5000,9999),"vhigh":random.randint(10000,30000)}[t]
        customer_rows.append((f"CTM{i:07d}", random.choice(["M","F"]), random.randint(1945,2003), random.choices(ADDR_LIST,weights=ADDR_W)[0], random.choices(JOB_LIST,weights=JOB_W)[0], incm))
    conn.executemany("INSERT OR IGNORE INTO CUS_CTM VALUES (?,?,?,?,?,?)", customer_rows)

    cust_dict   = {r[0]:{"gndr":r[1]} for r in customer_rows}
    female_pool = [r[0] for r in customer_rows if r[1]=="F"]
    male_pool   = [r[0] for r in customer_rows if r[1]=="M"]

    def get_chnl(ym):
        wd=CHNL_WEIGHT.get(ym[:4],CHNL_WEIGHT["2026"])
        return random.choices(list(wd.keys()),weights=list(wd.values()))[0]

    def get_sig_name(ym, gd_flg):
        if gd_flg not in SIG_PRODUCTS: return None
        avail=[]
        for launch_ym,names in SIG_PRODUCTS[gd_flg].items():
            if launch_ym<=ym: avail=names
        return random.choice(avail) if avail else None

    def get_la_gd_and_name(ym, gndr):
        codes=list(LA_INFO.keys()); weights=[LA_INFO[c]["w"] for c in codes]
        if ym>="202501":
            weights=[w*0.45 for w in weights]; weights[codes.index("LA03")]=0.40
        if gndr=="F":
            boost={}
            if ym>="202307": boost={"LA01":0.06,"LA02":0.04}
            if ym>="202401": boost={"LA01":0.10,"LA02":0.07,"LA03":0.06}
            if ym>="202411": boost={"LA01":0.13,"LA02":0.09,"LA03":0.09}
            if ym>="202601": boost={"LA01":0.16,"LA02":0.11,"LA03":0.11}
            for c,b in boost.items(): weights[codes.index(c)]+=b
        total=sum(weights); weights=[w/total for w in weights]
        gd_flg=random.choices(codes,weights=weights)[0]
        if gndr=="F" and gd_flg in ["LA01","LA02","LA03"]:
            sig=get_sig_name(ym,gd_flg)
            if sig: return gd_flg,sig
        return gd_flg, random.choice(LA_INFO[gd_flg]["names"])

    def target_female_ratio(ym):
        if ym<"202307": return 0.50
        if ym<"202401": return 0.53
        if ym<"202411": return 0.55
        if ym<"202501": return 0.58
        if ym<"202601": return 0.57
        return 0.62

    random.seed(42)
    N_LA,N_CA,N_FA = 60000,12000,2000
    contract_pool=[]; ply_idx=1

    la_months=[f"{y}{m:02d}" for y in [2021,2022,2023,2024,2025,2026] for m in range(1,13)]
    la_months=[ym for ym in la_months if ym<="202604"]
    la_per_month={}
    for i in range(N_LA):
        ym=la_months[i%len(la_months)]; la_per_month[ym]=la_per_month.get(ym,0)+1

    for ym,n in sorted(la_per_month.items()):
        if n==0: continue
        target_f=target_female_ratio(ym)
        n_female=round(n*target_f); n_male=n-n_female
        female_picks=random.choices(female_pool,k=n_female)
        male_picks=random.choices(male_pool,k=n_male)
        all_picks=female_picks+male_picks; random.shuffle(all_picks)
        sy=int(ym[:4]); sm=int(ym[4:])
        for crt in all_picks:
            gndr=cust_dict[crt]["gndr"]
            gd_flg,gdnm=get_la_gd_and_name(ym,gndr)
            mrd=crt if random.random()<0.7 else random.choice(female_pool if gndr=="F" else male_pool)
            ey=sy+random.randint(3,10); chnl=get_chnl(ym)
            contract_pool.append({"PLYNO":f"PLY{ply_idx:08d}","IKD":"LA","GD_FLG":gd_flg,"GDNM":gdnm,"CHNL":chnl,"CRT":crt,"MRD":mrd,"DH":random.choice(stf_ids),"CE":random.choice(stf_ids),"INS_ST":f"{sy}{sm:02d}01","INS_ND":f"{ey}{sm:02d}01","ACT_ST":f"{sy}{sm:02d}","ACT_ND":f"{ey}{sm:02d}"})
            ply_idx+=1

    for _ in range(N_CA):
        sy=random.randint(2021,2026); sm=random.randint(1,12)
        if sy==2026: sm=random.randint(1,4)
        ym=f"{sy}{sm:02d}"; chnl=get_chnl(ym)
        crt=random.choice(male_pool) if random.random()<0.65 else random.choice(female_pool)
        mrd=f"CTM{random.randint(1,N_CTM):07d}"
        gd_flg=random.choices(["CA01","CA02"],[0.85,0.15])[0]
        gdnm=random.choice(["한화 개인용자동차보험","한화 다이렉트 자동차보험"] if gd_flg=="CA01" else ["한화 업무용자동차보험"])
        ey=sy+random.randint(1,3)
        contract_pool.append({"PLYNO":f"PLY{ply_idx:08d}","IKD":"CA","GD_FLG":gd_flg,"GDNM":gdnm,"CHNL":chnl,"CRT":crt,"MRD":mrd,"DH":random.choice(stf_ids),"CE":random.choice(stf_ids),"INS_ST":f"{sy}{sm:02d}01","INS_ND":f"{ey}{sm:02d}01","ACT_ST":f"{sy}{sm:02d}","ACT_ND":f"{ey}{sm:02d}"})
        ply_idx+=1

    for _ in range(N_FA):
        sy=random.randint(2021,2026); sm=random.randint(1,12)
        if sy==2026: sm=random.randint(1,4)
        ym=f"{sy}{sm:02d}"; chnl=get_chnl(ym)
        crt=f"CTM{random.randint(1,N_CTM):07d}"
        gd_flg=random.choices(["FA01","FA02"],[0.70,0.30])[0]
        gdnm=random.choice(["한화 주택화재보험","한화 일반화재보험"] if gd_flg=="FA01" else ["한화 여행보험"])
        ey=sy+random.randint(1,5)
        contract_pool.append({"PLYNO":f"PLY{ply_idx:08d}","IKD":"FA","GD_FLG":gd_flg,"GDNM":gdnm,"CHNL":chnl,"CRT":crt,"MRD":crt,"DH":random.choice(stf_ids),"CE":random.choice(stf_ids),"INS_ST":f"{sy}{sm:02d}01","INS_ND":f"{ey}{sm:02d}01","ACT_ST":f"{sy}{sm:02d}","ACT_ND":f"{ey}{sm:02d}"})
        ply_idx+=1

    monthly_rows=[]
    for ym in YM_LIST:
        for c in contract_pool:
            if c["ACT_ST"]<=ym<c["ACT_ND"]:
                monthly_rows.append((ym,c["PLYNO"],c["CRT"],c["MRD"],c["GDNM"],c["GD_FLG"],c["IKD"],c["CHNL"],c["INS_ST"],c["INS_ND"],c["DH"],c["CE"]))
    conn.executemany("INSERT OR IGNORE INTO M_BIZ_MTHY_PS_CR VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", monthly_rows)
    conn.commit()

# DB 없으면 자동 생성
if conn.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'").fetchone()[0] == 0:
    with st.spinner("데이터 초기화 중... (최초 1회, 약 1분 소요)"):
        init_db(conn)

# ──────────────────────────────────────────
# 시스템 프롬프트 v2
# ──────────────────────────────────────────
SYSTEM_PROMPT = """
당신은 한화손해보험 데이터분석 전문 AI 어시스턴트입니다.
SQLite DB에 접근하여 고객 KPI를 분석하고 임원 보고 수준의 인사이트를 제공합니다.

=== 핵심 용어 정의 ===
- 보유고객: 해당 CLS_YYMM에 정상계약이 존재하는 고객 (M_BIZ_MTHY_PS_CR에 있으면 정상계약)
- 신규고객(전사): 당월 보유고객 중 전월에 보유계약이 없던 고객
- 신규고객(채널내): 당월 보유고객 중 전월에 동일 채널 보유계약이 없던 고객
- 신규고객(보종내): 당월 보유고객 중 전월에 동일 보종 보유계약이 없던 고객
- 이탈고객: 전월엔 보유계약 있었는데 당월엔 없는 고객
- 신계약고객: 당월에 보험시기(INS_ST)가 시작된 고객 (INS_ST LIKE CLS_YYMM || '%')
- 장기다건: 장기(IKD_GRPCD='LA') 계약을 2건 이상 보유한 고객
- 자장연계: 자동차 보유고객 중 장기도 보유한 고객
- 자운연계: 자동차 보유고객 중 운전자보험(GD_FLGCD='LA02')도 보유한 고객
- 자동차 고객 집계: 피보험자(MN_NRDPS_CTMNO) 기준
- 장기/일반 고객 집계: 계약자(CRT_CTMNO) 기준

=== 테이블 스키마 ===

[M_BIZ_MTHY_PS_CR] 월별계약 (정상계약만 적재)
- CLS_YYMM        : 기준년월 (PK, 예: 202604)
- PLYNO           : 증권번호 (PK)
- CRT_CTMNO       : 계약자 고객번호
- MN_NRDPS_CTMNO  : 피보험자 고객번호
- GDNM            : 상품명
- GD_FLGCD        : 상품군코드 (LA01~LA12, CA01~CA02, FA01~FA02)
- IKD_GRPCD       : 보종코드 (LA=장기, CA=자동차, FA=일반)
- CHNL_FLGCD      : 채널코드 (전속, GA, 교차, TM, CM)
- INS_ST          : 보험시기 (계약시작일, 예: 20240101)
- INS_ND          : 보험종기 (계약종료일)
- DH_STFNO        : 취급자 설계사ID
- CE_STFNO        : 모집자 설계사ID

[CUS_CTM] 고객
- CTMNO    : 고객번호 (PK)
- GNDR     : 성별 (M=남, F=여)
- BRTHYR   : 출생연도
- ADDR     : 주소 (수도권, 영남권, 호남권, 충청권, 강원권, 제주)
- JOB_GRP  : 직업군 (화이트, 블루, 자영업, 주부, 전문직)
- ESTM_INCM: 추정소득 (만원 단위, 연속형)

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

=== 상품군 코드 ===
LA01=종합, LA02=운전자, LA03=SI(간편건강), LA04=자녀, LA05=간병,
LA06=실손, LA07=상해, LA08=재물, LA09=암, LA10=치아, LA11=연저축, LA12=기타
CA01=개인용자동차, CA02=업무용자동차
FA01=화재, FA02=여행

=== 주요 시그니처 상품 (여성 전용) ===
- 한화 시그니처 여성보험 1.0/2.0/3.0/4.0 (종합형, LA01)
- 한화 시그니처 여성 운전자상해보험 (운전자, LA02)
- 한화 시그니처 여성 3N5/355 간편건강보험 2.0/3.0 (SI, LA03)
- 시그니처 출시: 1.0=202307, 2.0=202401, 3.0=202411, 4.0=202601

=== 소득 구간 기준 ===
CASE WHEN ESTM_INCM < 3000 THEN '3천만원미만'
     WHEN ESTM_INCM < 5000 THEN '3천~5천만원'
     WHEN ESTM_INCM < 10000 THEN '5천만원~1억'
     ELSE '1억이상' END

=== SQL 작성 규칙 ===
1. SQLite 문법만 사용
2. 신규/이탈 고객: 반드시 LEFT JOIN 방식
3. 자동차 고객 수: COUNT(DISTINCT MN_NRDPS_CTMNO)
4. 장기/일반 고객 수: COUNT(DISTINCT CRT_CTMNO)
5. 연령대: (기준년도 - BRTHYR) / 10 * 10 으로 10세 단위
6. 결과 LIMIT 100 이하
7. 데이터 범위: 202301~202604

=== 예시 쿼리 ===

[예시1] 보유고객 수 (전사/채널별/보종별)
SELECT CLS_YYMM, IKD_GRPCD, CHNL_FLGCD,
       COUNT(DISTINCT CRT_CTMNO) AS 보유고객수
FROM M_BIZ_MTHY_PS_CR
WHERE CLS_YYMM = '202604'
GROUP BY CLS_YYMM, IKD_GRPCD, CHNL_FLGCD
ORDER BY IKD_GRPCD, CHNL_FLGCD;

[예시2] 신규고객 수 (전사 기준)
SELECT curr.CLS_YYMM, curr.IKD_GRPCD,
       COUNT(DISTINCT curr.CRT_CTMNO) AS 신규고객수
FROM M_BIZ_MTHY_PS_CR curr
LEFT JOIN M_BIZ_MTHY_PS_CR prev
    ON curr.CRT_CTMNO = prev.CRT_CTMNO
    AND prev.CLS_YYMM = '202603'
WHERE curr.CLS_YYMM = '202604'
    AND prev.CRT_CTMNO IS NULL
GROUP BY curr.CLS_YYMM, curr.IKD_GRPCD;

[예시3] 이탈고객 수
SELECT prev.CLS_YYMM AS 전월, prev.IKD_GRPCD,
       COUNT(DISTINCT prev.CRT_CTMNO) AS 이탈고객수
FROM M_BIZ_MTHY_PS_CR prev
LEFT JOIN M_BIZ_MTHY_PS_CR curr
    ON prev.CRT_CTMNO = curr.CRT_CTMNO
    AND curr.CLS_YYMM = '202604'
WHERE prev.CLS_YYMM = '202603'
    AND curr.CRT_CTMNO IS NULL
GROUP BY prev.CLS_YYMM, prev.IKD_GRPCD;

[예시4] 장기다건 / 자장연계 / 자운연계
WITH
long_term AS (
    SELECT CRT_CTMNO, COUNT(DISTINCT PLYNO) AS 장기계약수
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202604' AND IKD_GRPCD = 'LA'
    GROUP BY CRT_CTMNO
),
auto AS (
    SELECT DISTINCT MN_NRDPS_CTMNO AS CTMNO
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202604' AND IKD_GRPCD = 'CA'
),
driver AS (
    SELECT DISTINCT CRT_CTMNO
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM = '202604' AND GD_FLGCD = 'LA02'
)
SELECT
    COUNT(DISTINCT CASE WHEN lt.장기계약수 >= 2 THEN lt.CRT_CTMNO END) AS 장기다건고객수,
    COUNT(DISTINCT CASE WHEN a.CTMNO IS NOT NULL AND lt.CRT_CTMNO IS NOT NULL
                        THEN a.CTMNO END) AS 자장연계고객수,
    COUNT(DISTINCT CASE WHEN a.CTMNO IS NOT NULL AND d.CRT_CTMNO IS NOT NULL
                        THEN a.CTMNO END) AS 자운연계고객수,
    COUNT(DISTINCT a.CTMNO) AS 자동차보유고객수
FROM auto a
LEFT JOIN long_term lt ON a.CTMNO = lt.CRT_CTMNO
LEFT JOIN driver d ON a.CTMNO = d.CRT_CTMNO;

[예시5] 성별/연령대별 보유고객
SELECT c.GNDR,
       (2026 - cu.BRTHYR) / 10 * 10 AS 연령대,
       COUNT(DISTINCT c.CRT_CTMNO) AS 보유고객수
FROM M_BIZ_MTHY_PS_CR c
JOIN CUS_CTM cu ON c.CRT_CTMNO = cu.CTMNO
WHERE c.CLS_YYMM = '202604' AND c.IKD_GRPCD = 'LA'
GROUP BY c.GNDR, 연령대
ORDER BY c.GNDR, 연령대;

[예시6] 채널별 보유고객 추이 (월별)
SELECT CLS_YYMM, CHNL_FLGCD,
       COUNT(DISTINCT CRT_CTMNO) AS 보유고객수
FROM M_BIZ_MTHY_PS_CR
WHERE IKD_GRPCD = 'LA'
  AND CLS_YYMM >= '202301'
GROUP BY CLS_YYMM, CHNL_FLGCD
ORDER BY CLS_YYMM, 보유고객수 DESC;

[예시7] 상품군별 신계약 비중 변화
SELECT CLS_YYMM, GD_FLGCD,
       COUNT(DISTINCT CRT_CTMNO) AS 신계약고객수
FROM M_BIZ_MTHY_PS_CR
WHERE IKD_GRPCD = 'LA'
  AND INS_ST LIKE CLS_YYMM || '%'
GROUP BY CLS_YYMM, GD_FLGCD
ORDER BY CLS_YYMM, 신계약고객수 DESC;

=== 응답 형식 ===
반드시 아래 JSON 형식으로만 응답하세요. 다른 텍스트는 포함하지 마세요.
{
  "sql": "실행할 SQL",
  "explanation": "이 쿼리가 무엇을 조회하는지 1~2문장 설명"
}
"""

ANALYSIS_PROMPT = """
당신은 한화손해보험 데이터분석 전문 AI 어시스턴트입니다.
SQL 쿼리 결과를 바탕으로 원인을 분석하고 임원 보고 수준의 인사이트를 제공합니다.

반드시 아래 JSON 형식으로만 응답하세요:
{
  "summary": "현황 요약 (2~3문장, 핵심 수치 포함)",
  "anomaly_level": "정상/주의/경보",
  "hypotheses": [
    {"rank": 1, "title": "가설 제목", "description": "근거와 설명 (2~3문장)", "action": "확인/조치 방안"},
    {"rank": 2, "title": "가설 제목", "description": "근거와 설명", "action": "확인/조치 방안"},
    {"rank": 3, "title": "가설 제목", "description": "근거와 설명", "action": "확인/조치 방안"}
  ],
  "report_draft": "【현황】\\n...\\n\\n【원인 분석】\\n...\\n\\n【제언】\\n..."
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
    result = json.loads(raw)
    # SQL 줄바꿈 정리
    sql = result["sql"]
    keywords = ["SELECT","FROM","WHERE","GROUP BY","ORDER BY","HAVING","LEFT JOIN","JOIN","WITH","LIMIT","AND","OR"]
    for kw in keywords:
        sql = sql.replace(f" {kw} ", f"\n{kw} ")
    result["sql"] = sql
    return result

def run_sql(sql):
    try:
        return pd.read_sql(sql, conn), None
    except Exception as e:
        return None, str(e)

def analyze_result(question, sql, df):
    table_text = df.head(10).to_string(index=False)
    if len(df) > 10:
        table_text += f"\n... 외 {len(df)-10}행"
    prompt = f"""
사용자 질문: {question}

실행된 SQL:
{sql}

쿼리 결과 ({len(df)}행, 상위 10행 표시):
{table_text}

위 데이터를 분석하여 원인 가설 3가지와 임원 보고용 초안을 작성해주세요.
"""
    response = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
        system=ANALYSIS_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )
    raw = response.content[0].text.strip()
    raw = re.sub(r"```(?:json)?", "", raw).strip().rstrip("```").strip()
    return json.loads(raw)

def to_excel(df):
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='분석결과')
    return output.getvalue()

def auto_chart(df):
    if df is None or df.empty or len(df.columns) < 2:
        return None
    cols = df.columns.tolist()
    num_cols = df.select_dtypes(include='number').columns.tolist()
    cat_cols = [c for c in cols if c not in num_cols]
    if not num_cols:
        return None
    y_col = num_cols[0]
    date_cols = [c for c in cat_cols if any(k in c for k in ['YM','년월','월','연도','YYMM'])]
    if date_cols and len(df) > 3:
        x_col = date_cols[0]
        df = df.copy()
        if df[x_col].astype(str).str.len().max() == 6:
            df['기준년월'] = df[x_col].astype(str).apply(
                lambda x: x[2:4] + '.' + x[4:6]
            )
            x_col = '기준년월'
        color_col = cat_cols[1] if len(cat_cols) > 1 else None
        if color_col:
            fig = px.line(df, x=x_col, y=y_col, color=color_col,
                         markers=True,
                         labels={x_col: '기준년월', y_col: y_col},
                         color_discrete_sequence=px.colors.qualitative.Set2)
        else:
            fig = px.line(df, x=x_col, y=y_col,
                         markers=True,
                         labels={x_col: '기준년월', y_col: y_col},
                         color_discrete_sequence=['#F37321'])
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            xaxis=dict(title='기준년월', tickangle=-45, type='category'),
        )
        return fig
    if cat_cols:
        x_col = cat_cols[0]
        color_col = cat_cols[1] if len(cat_cols) > 1 else None
        if color_col:
            fig = px.bar(df, x=x_col, y=y_col, color=color_col,
                        barmode='group',
                        color_discrete_sequence=px.colors.qualitative.Set2)
        else:
            fig = px.bar(df, x=x_col, y=y_col,
                        color_discrete_sequence=['#F37321'])
        fig.update_layout(plot_bgcolor='white', paper_bgcolor='white')
        return fig
    return None

# ──────────────────────────────────────────
# Streamlit UI
# ──────────────────────────────────────────
st.set_page_config(
    page_title="고객 트렌드 분석 Copilot",
    page_icon="🔥",
    layout="wide"
)

st.markdown("""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
""", unsafe_allow_html=True)

st.markdown("""
<style>
    
    body, p, div, span, h1, h2, h3, h4, input, button, td, th {
    font-family: 'Noto Sans KR', -apple-system, BlinkMacSystemFont, sans-serif !important;
}
    .stApp { background-color: #FAFAFA; }

    .section-header {
        font-size: 15px; font-weight: 600;
        color: #1A1A1A; margin: 20px 0 12px;
        padding-left: 10px;
        border-left: 3px solid #F37321;
    }

    .kpi-card {
        background: white;
        border: 1px solid #F0F0F0;
        border-top: 3px solid #F89B6C;
        border-radius: 10px;
        padding: 16px 20px;
        text-align: center;
        box-shadow: 0 1px 4px rgba(0,0,0,0.06);
    }
    .kpi-label { font-size: 12px; color: #6B7280; margin-bottom: 4px; }
    .kpi-value { font-size: 28px; font-weight: 700; color: #1A1A1A; }
    .kpi-sub   { font-size: 12px; color: #6B7280; margin-top: 2px; }

    .hypothesis-card {
        background: #FEF3EC;
        border: 1px solid #F89B6C;
        border-left: 4px solid #F37321;
        border-radius: 8px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }

    .report-box {
        background: white;
        border: 1px solid #F0F0F0;
        border-top: 3px solid #F37321;
        border-radius: 8px;
        padding: 20px 24px;
        font-size: 14px;
        line-height: 1.9;
        white-space: pre-wrap;
        color: #1A1A1A;
    }

    .stButton > button {
        background: #F37321 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 500 !important;
        padding: 8px 20px !important;
    }
    .stButton > button:hover { background: #E06010 !important; }

    div[data-testid="column"] .stButton > button {
        background: white !important;
        color: #F37321 !important;
        border: 1.5px solid #F37321 !important;
        border-radius: 8px !important;
        font-size: 13px !important;
        font-weight: 400 !important;
        width: 100% !important;
    }
    div[data-testid="column"] .stButton > button:hover {
        background: #FEF3EC !important;
        color: #E06010 !important;
    }

    .stTabs [data-baseweb="tab-list"] { border-bottom: 2px solid #F89B6C; }
    .stTabs [data-baseweb="tab"] { color: #6B7280; font-weight: 500; }
    .stTabs [aria-selected="true"] {
        color: #F37321 !important;
        border-bottom: 2px solid #F37321 !important;
    }

    .stTextInput > div > div > input {
        border: 1.5px solid #F89B6C !important;
        border-radius: 8px !important;
    }
    .stTextInput > div > div > input:focus {
        border-color: #F37321 !important;
        box-shadow: 0 0 0 2px rgba(243,115,33,0.15) !important;
    }
</style>
""", unsafe_allow_html=True)

# ── 헤더 ──
logo = Image.open("images/logo.jpg")
col_title, col_logo = st.columns([8, 2])
with col_title:
    st.markdown("""
    <h1 style="margin:4px 0 2px; font-size:26px; font-weight:700; color:#1A1A1A;">
        고객 트렌드 분석 Copilot
    </h1>
    <p style="margin:0 0 12px; font-size:13px; color:#6B7280;">
        Customer Analytics Assistant powered by AI
    </p>
    """, unsafe_allow_html=True)
with col_logo:
    st.image(logo, width=180)
st.markdown('<hr style="border:1px solid #F37321; margin: 0 0 20px;">', unsafe_allow_html=True)

# ── KPI 카드 ──
st.markdown('<div class="section-header">보유고객 현황 (2026년 04월 마감 기준)</div>', unsafe_allow_html=True)
col1, col2, col3, col4 = st.columns(4)

df_kpi = pd.read_sql("""
    SELECT IKD_GRPCD,
        CASE WHEN IKD_GRPCD='CA' THEN COUNT(DISTINCT MN_NRDPS_CTMNO)
             ELSE COUNT(DISTINCT CRT_CTMNO) END AS 보유고객수
    FROM M_BIZ_MTHY_PS_CR
    WHERE CLS_YYMM='202604'
    GROUP BY IKD_GRPCD
""", conn)
kpi = dict(zip(df_kpi["IKD_GRPCD"], df_kpi["보유고객수"]))
total = sum(kpi.values())

with col1:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">전체 보유고객</div><div class="kpi-value">{total:,}</div><div class="kpi-sub">명</div></div>', unsafe_allow_html=True)
with col2:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">장기 (LA)</div><div class="kpi-value">{kpi.get("LA",0):,}</div><div class="kpi-sub">명</div></div>', unsafe_allow_html=True)
with col3:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">자동차 (CA)</div><div class="kpi-value">{kpi.get("CA",0):,}</div><div class="kpi-sub">명 · 피보험자 기준</div></div>', unsafe_allow_html=True)
with col4:
    st.markdown(f'<div class="kpi-card"><div class="kpi-label">일반 (FA)</div><div class="kpi-value">{kpi.get("FA",0):,}</div><div class="kpi-sub">명</div></div>', unsafe_allow_html=True)

st.divider()

# ── 질문 영역 ──
st.markdown('<div class="section-header">💬 자연어로 질문하세요</div>', unsafe_allow_html=True)
st.caption("예시 질문을 클릭하거나 직접 입력하세요")

ex_col1, ex_col2, ex_col3, ex_col4 = st.columns(4)
if ex_col1.button("📈 GA채널 성장 추이"):
    st.session_state["question"] = "2023년부터 2026년까지 채널별 장기 보유고객 수 월별 추이 보여줘"
if ex_col2.button("🆕 SI 신상품 출시 효과"):
    st.session_state["question"] = "2025년 이후 장기 신계약 상품군 포트폴리오 변화 분석해줘"
if ex_col3.button("👩 여성 고객 트렌드"):
    st.session_state["question"] = "시그니처 여성보험 출시 이후 여성 신계약 고객 비중 추이 보여줘"
if ex_col4.button("🔗 고객가치 현황"):
    st.session_state["question"] = "202604 기준 장기다건, 자장연계, 자운연계 고객 수 알려줘"

question = st.text_input(
    "질문",
    value=st.session_state.get("question", ""),
    placeholder="예: 2026년 4월 GA채널 장기 신규고객 수와 전월 대비 증감 알려줘",
    label_visibility="collapsed"
)

analyze_btn = st.button("🔍 분석하기", type="primary")

if analyze_btn and question:
    with st.spinner("SQL 생성 중..."):
        try:
            sql_result = ask_to_sql(question)
            sql = sql_result["sql"]
            explanation = sql_result["explanation"]
        except Exception as e:
            st.error(f"SQL 생성 오류: {e}")
            st.stop()

    df, error = run_sql(sql)
    if error:
        st.error(f"쿼리 실행 오류: {error}")
        st.stop()

    st.markdown('<div class="section-header">📊 분석 결과</div>', unsafe_allow_html=True)
    st.caption(f"💡 {explanation}")

    with st.container():
        st.caption("🔍 생성된 SQL")
        st.code(sql, language="sql")
    tab1, tab2, tab3, tab4 = st.tabs(["📋 데이터 테이블", "📈 차트", "🤖 AI 인사이트", "📝 임원 보고 초안"])

    with tab1:
        st.dataframe(df, use_container_width=True)
        excel_data = to_excel(df)
        st.download_button(
            label="⬇️ 엑셀 다운로드",
            data=excel_data,
            file_name="분석결과.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    with tab2:
        fig = auto_chart(df)
        if fig:
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("차트를 그리기에 적합한 데이터 구조가 아닙니다.")

    with tab3:
        with st.spinner("AI 분석 중..."):
            try:
                analysis = analyze_result(question, sql, df)
            except Exception as e:
                st.error(f"분석 오류: {e}")
                st.stop()

        level = analysis.get("anomaly_level", "정상")
        level_color = {"정상": "🟢", "주의": "🟡", "경보": "🔴"}.get(level, "🟢")
        st.markdown(f"**이상 수준:** {level_color} {level}")
        st.markdown(f"**현황 요약:** {analysis.get('summary', '')}")
        st.markdown("**원인 가설**")
        for h in analysis.get("hypotheses", []):
            st.markdown(f"""
<div class="hypothesis-card">
<b>{h['rank']}. {h['title']}</b><br>
{h['description']}<br>
<span style="color:#F37321">→ 조치: {h['action']}</span>
</div>
""", unsafe_allow_html=True)

    with tab4:
        report = analysis.get("report_draft", "") if 'analysis' in dir() else ""
        if not report:
            with st.spinner("보고서 초안 생성 중..."):
                try:
                    analysis = analyze_result(question, sql, df)
                    report = analysis.get("report_draft", "")
                except Exception as e:
                    st.error(f"보고서 생성 오류: {e}")
                    st.stop()

        st.markdown(report)
        st.download_button(
            label="⬇️ 보고서 초안 다운로드 (.txt)",
            data=report.encode('utf-8'),
            file_name="임원보고초안.txt",
            mime="text/plain"
    )