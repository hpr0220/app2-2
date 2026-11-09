"""우리집 혜택 알리미 — 단일 화면 Streamlit 앱.
실행: python -m streamlit run app.py
개인정보/비밀번호/API 키를 입력받거나 저장하지 않는다.

[데이터 수정 안내]
1. REAL_BENEFITS에 아래 Benefit 형식으로 항목을 추가한다. id는 영구적으로 고유하게 유지한다.
2. 공식 원문을 직접 확인한 경우에만 source_url, verified_on, 조건/서류를 기록한다.
   verified_on은 실제 확인일이다. 앱 실행일로 자동 갱신하지 않는다.
3. 날짜는 YYYY-MM-DD, 미확인 값은 None. 상시접수가 원문에 명시된 경우만
   period_kind='always'로 설정한다. 기간이 일부라도 불명확하면 'unknown'으로 둔다.
   fixed는 시작/종료일이 모두 확인된 공고에만 쓴다. 마감시각은 별도 period_note에 쓴다.
4. regions={'서울특별시': ('강남구', '서초구')}처럼 제한하거나, 전국 서비스는
   regions={}로 둔다. 검색 UI는 전국 17개 시·도를 지원한다. 시 소속 일반구는 시 단위로 선택한다.
5. tags는 기본 조건 관련성 검색용이다. 반드시 모두 충족해야 하는 조건은
   required_tags에 별도로 둔다. 여러 tags는 OR, required_tags는 AND이다.
6. age_min/age_max는 사용자가 입력한 본인의 연령이다. 자녀 연령을 넣지 않는다.
7. 예시는 DEMO_BENEFITS에만 넣고 demo=True를 유지한다. 실제 공고와 섞지 않는다.
8. 공식 API/DB를 붙일 때 load_benefits()만 교체하면 화면/필터 코드는 재사용 가능하다.
   API 키는 st.secrets['API_KEY'] 등 Streamlit 비밀정보 설정으로 읽는다.
   실제 API는 이 버전에 연결되어 있지 않다. 사용자 조건을 공용 캐시에 저장하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from html import escape
from io import BytesIO
from urllib.parse import urlsplit
import ipaddress
import re
import streamlit as st

KST = timezone(timedelta(hours=9))
CHECKED_ON = '2026-11-05'  # 아래 공식 원문을 실제 열람한 날짜. 자동 변경 금지.
# 시 소속 비자치 일반구(예: 수원시 영통구)는 시로 통합해 선택한다.
# 세종은 별도 자치 시군구가 없으므로 '세종특별자치시' 1개 선택지를 제공한다.
# 제주는 행정시 2개를 제공한다. 읍면동 단위는 지원하지 않는다.
# 내장 목록은 기존 시군구 목록을 기반으로 명칭 및 이관을 보정했다.
# 대구 군위군, 강원/전북 특별자치도 명칭, 인천 2026-07 개편(서해구 포함) 반영.
REGIONS = {
    '서울특별시': tuple('강남구 강동구 강북구 강서구 관악구 광진구 구로구 금천구 노원구 도봉구 동대문구 동작구 마포구 서대문구 서초구 성동구 성북구 송파구 양천구 영등포구 용산구 은평구 종로구 중구 중랑구'.split()),
    '부산광역시': tuple('강서구 금정구 기장군 남구 동구 동래구 부산진구 북구 사상구 사하구 서구 수영구 연제구 영도구 중구 해운대구'.split()),
    '대구광역시': tuple('군위군 남구 달서구 달성군 동구 북구 서구 수성구 중구'.split()),
    '인천광역시': tuple('강화군 검단구 계양구 남동구 미추홀구 부평구 서해구 연수구 영종구 옹진군 제물포구'.split()),
    '광주광역시': tuple('광산구 남구 동구 북구 서구'.split()),
    '대전광역시': tuple('대덕구 동구 서구 유성구 중구'.split()),
    '울산광역시': tuple('남구 동구 북구 울주군 중구'.split()),
    '세종특별자치시': ('세종특별자치시',),
    '경기도': tuple('가평군 고양시 과천시 광명시 광주시 구리시 군포시 김포시 남양주시 동두천시 부천시 성남시 수원시 시흥시 안산시 안성시 안양시 양주시 양평군 여주시 연천군 오산시 용인시 의왕시 의정부시 이천시 파주시 평택시 포천시 하남시 화성시'.split()),
    '강원특별자치도': tuple('강릉시 고성군 동해시 삼척시 속초시 양구군 양양군 영월군 원주시 인제군 정선군 철원군 춘천시 태백시 평창군 홍천군 화천군 횡성군'.split()),
    '충청북도': tuple('괴산군 단양군 보은군 영동군 옥천군 음성군 제천시 증평군 진천군 청주시 충주시'.split()),
    '충청남도': tuple('계룡시 공주시 금산군 논산시 당진시 보령시 부여군 서산시 서천군 아산시 예산군 천안시 청양군 태안군 홍성군'.split()),
    '전북특별자치도': tuple('고창군 군산시 김제시 남원시 무주군 부안군 순창군 완주군 익산시 임실군 장수군 전주시 정읍시 진안군'.split()),
    '전라남도': tuple('강진군 고흥군 곡성군 광양시 구례군 나주시 담양군 목포시 무안군 보성군 순천시 신안군 여수시 영광군 영암군 완도군 장성군 장흥군 진도군 함평군 해남군 화순군'.split()),
    '경상북도': tuple('경산시 경주시 고령군 구미시 김천시 문경시 봉화군 상주시 성주군 안동시 영덕군 영양군 영주시 영천시 예천군 울릉군 울진군 의성군 청도군 청송군 칠곡군 포항시'.split()),
    '경상남도': tuple('거제시 거창군 고성군 김해시 남해군 밀양시 사천시 산청군 양산시 의령군 진주시 창녕군 창원시 통영시 하동군 함안군 함양군 합천군'.split()),
    '제주특별자치도': ('서귀포시', '제주시'),
}
REGION_SOURCE = 'https://mois.go.kr/frt/bbs/type001/commonSelectBoardArticle.do?bbsId=BBSMSTR_000000000055&nttId=128138'
INCHEON_SOURCE = 'https://www.incheon.go.kr/IC010205/view?repDt=2026-07-02&repSeq=DOM_0000000015062218'
DEFAULT_APP_URL = 'https://y2qvnmkifx2jgcdoynk6s9.streamlit.app/'
AGE_BANDS = {
    '선택 안 함': (None, None), '만 0~18세': (0, 18), '만 19~34세': (19, 34),
    '만 35~49세': (35, 49), '만 50~64세': (50, 64), '만 65~74세': (65, 74),
    '만 75세 이상': (75, 150),
}
TAGS = ['학생', '취업준비생', '직장인', '자영업자', '자녀 양육 가구', '기타']
CATEGORIES = ['생활·복지', '교육', '취업', '주거', '소상공인', '문화']


@dataclass(frozen=True)
class Benefit:
    id: str
    name: str
    summary: str
    categories: tuple[str, ...]
    tags: tuple[str, ...]
    target: str
    extra_checks: tuple[str, ...]
    method: str
    documents: tuple[str, ...]
    agency: str
    source_url: str | None
    verified_on: str | None
    regions: dict[str, tuple[str, ...]]
    period_kind: str = 'unknown'  # always / fixed / unknown
    start: str | None = None
    end: str | None = None
    period_note: str = ''
    age_min: int | None = None
    age_max: int | None = None
    required_tags: tuple[str, ...] = ()
    demo: bool = False


# 공식 원문 확인 데이터. 전국 사업과 일부 지역 사업만 수록하며 전수 수집이 아니다.
# 종료 공고는 자동으로 기본 결과에서 분리한다. 확인일을 실행일로 바꾸지 않는다.
REAL_BENEFITS = (
    Benefit(
        id='real-training-card', name='국민내일배움카드',
        summary='직업능력개발훈련 수강에 필요한 훈련비의 일부 또는 전액을 지원하는 제도입니다. 과정별 지원 범위와 본인부담금은 공식 안내를 확인하세요.',
        categories=('교육', '취업'), tags=('학생', '취업준비생', '직장인', '자영업자'),
        target='훈련 필요성이 인정되는 사람. 공무원·사립학교 교직원, 만 75세 이상 등은 지원 제외 대상이며 학생·근로자·자영업자에게 별도 제외 기준이 있습니다.',
        extra_checks=(
            '훈련 필요성 심사와 다른 정부지원 훈련 참여 여부',
            '학생: 졸업까지 남은 수업연한, 고등학생은 졸업예정 여부',
            '근로자: 기업 규모·연령·임금, 자영업자: 연 매출, 특수형태근로종사자: 월 소득 등 제외 기준',
            '공무원·사립학교 교직원 해당 여부와 예산·과정별 지원 조건',
        ),
        method='가까운 고용센터 방문 또는 고용24를 통해 신청합니다. 이 앱에서는 신청을 접수하지 않습니다.',
        documents=('직업능력개발계좌(내일배움카드) 발급 신청서', '개인정보 수집·이용 동의서',
                   '본인에게 해당하는 지원대상별 입증 서류(담당 기관 확인)'),
        agency='고용노동부 / 고용센터 · 문의 1350',
        source_url='https://www.gov.kr/portal/service/serviceInfo/149200000026',
        verified_on=CHECKED_ON, regions={}, age_max=74,
        period_note='열람한 공식 안내에서 신청 시작·마감일 또는 상시신청 문구를 확인하지 못했습니다. 고용센터에 접수 가능 여부를 확인하세요.',
    ),
    Benefit(
        id='real-childcare', name='아이돌봄서비스 정부지원',
        summary='양육공백이 있는 가정의 아이돌봄서비스 이용에 대한 정부지원 안내입니다. 서비스 유형과 가구소득 등에 따라 지원 범위가 달라집니다.',
        categories=('생활·복지',), tags=('자녀 양육 가구',), required_tags=('자녀 양육 가구',),
        target='대상아동·양육공백·다른 자녀양육 지원과의 중복금지 기준을 충족하고 소득 판정을 받는 가구. 영아종일제는 생후 3개월~만 36개월, 시간제 등은 생후 3개월~만 12세 아동 기준을 확인합니다.',
        extra_checks=('자녀의 정확한 연령·국적 등 대상아동 기준', '양육공백 인정 여부와 가구소득·가구원 수',
                      '보육료·유아학비·부모급여 등과의 중복지원 제한 및 서비스 시간',
                      '지역 제공기관의 연계 가능 여부와 국민행복카드 준비'),
        method='아동 주소지 읍·면·동 주민센터 방문 또는 복지로 온라인 신청. 온라인 신청 가능 가구에 제한이 있으므로 공식 안내를 확인하세요.',
        documents=('사회보장급여 신청(변경)서', '본인 가구에 해당하는 정부지원 자격 증빙자료',
                   '필요시 양육공백 입증서류(행정정보 연계로 제출이 불필요한 서류는 담당 기관 확인)'),
        agency='아이돌봄서비스 / 주소지 주민센터·시군구 및 지역 서비스 제공기관',
        source_url='https://idolbom.go.kr/front/srvcUtztnGuide/govApply',
        verified_on=CHECKED_ON, regions={},
        period_note='열람한 정부지원 신청 안내에서 확정 신청 기간을 확인하지 못했습니다. 거주지 주민센터·제공기관에 접수 및 연계 가능 여부를 확인하세요.',
    ),
)

# 지역별 결과가 실제로 달라지도록, 확인한 지역 사업을 별도로 관리한다.
# 서울 사업 페이지는 열람 시 대기 화면만 반환되어 이번 실제 데이터에는 추가하지 않았다.
REGIONAL_BENEFITS = (
    Benefit(
        id='real-gg-basic-2026-q4', name='2026년 4분기 경기도 청년기본소득',
        summary='분기별 25만 원을 지역화폐로 지원하는 사업입니다. 해당 분기 생년월일과 거주기간 등 추가 조건을 확인하세요.',
        categories=('생활·복지',), tags=(),
        target='신청일 기준 경기도 주민등록자 중 해당 분기 지급 대상 청년. 4분기 대상 생년월일은 2001-10-02~2002-10-01이며, 경기도에 3년 이상 계속 또는 합산 10년 이상 거주해야 합니다. 성남시·고양시는 2026년 사업 제외입니다.',
        extra_checks=('분기별 연령 기준일과 출생일 범위(현재 만 나이와 다를 수 있음)',
                      '주민등록상 거주지와 경기도 연속 3년 또는 합산 10년 거주 이력',
                      '자동 신청 여부·이전 지급 이력·소급 또는 일시금 신청 조건'),
        method='잡아바 어플라이에서 온라인 신청합니다. 경기도 공식 안내의 신청 링크를 이용하세요.',
        documents=('주민등록초본(마이데이터 이용 동의 시 자동 제출)',
                   '기초생활수급자 증명서(해당자에 한함)'),
        agency='경기도 / 주소지 시·군 · 경기도 콜센터 031-120, 사업 콜센터 1877-0566',
        source_url='https://www.gg.go.kr/contents/contents.do?ciIdx=1037&menuId=2736',
        verified_on=CHECKED_ON,
        regions={'경기도': tuple(x for x in REGIONS['경기도'] if x not in ('성남시', '고양시'))},
        period_kind='fixed', start='2026-11-02', end='2026-12-01',
        period_note='공식 안내의 2026년 4분기 일정: 첫날 09:00부터 마지막 날 18:00까지. 현재 접수·예산·변경 공지는 공식 안내를 재확인하세요.',
        # 현재 나이가 아닌 분기 기준일의 생년월일로 판단하므로 숫자 나이 필터를 적용하지 않는다.
    ),
    Benefit(
        id='real-busan-didim-2026', name='2026년 부산 청년디딤돌카드 플러스 모집',
        summary='미취업 청년의 사회진입 활동비와 취업역량 강화 프로그램을 지원한 모집 공고입니다. 해당 모집의 신청은 종료되었습니다.',
        categories=('취업', '생활·복지'), tags=('취업준비생', '직장인'),
        target='공고일 2026-03-03 기준 부산 거주, 1986-01-01~2008-12-31 출생 미취업·미창업 청년 중 최종학력 졸업·중퇴·제적자. 재학생은 제외되며 주 30시간 미만 근로자는 증빙 등 별도 조건이 있습니다.',
        extra_checks=('건강보험료를 기준으로 한 소득 조건', '근로시간·고용보험 가입·사업자등록 여부',
                      '과거 수혜와 유사사업·실업급여 등 중복지원 제한',
                      '재학·군복무·공무원 임용시험 최종 합격 등 제외 여부'),
        method='해당 모집은 종료되었습니다. 당시에는 디딤돌카드 홈페이지에서 온라인 접수했습니다. 이후 모집 여부는 공식 공고를 확인하세요.',
        documents=('참여신청서', '구직활동계획서', '개인정보 수집·이용 및 제3자 제공·조회 동의서',
                   '최종학력 졸업·제적·중퇴 증명서 등 공고의 해당 서류'),
        agency='부산경제진흥원 · 051-600-1874, 1875 / 부산진구청 안내',
        source_url='https://www.busanjin.go.kr/index.busanjin?menuCd=DOM_000001701005007000',
        verified_on=CHECKED_ON, regions={'부산광역시': ()},
        period_kind='fixed', start='2026-03-09', end='2026-03-27',
        period_note='확인한 해당 모집은 2026-03-09 10:00~2026-03-27 18:00이며 종료되었습니다. 상시 사업으로 해석하지 마세요.',
    ),
)
NATIONAL_EXTRA_BENEFITS = (
    Benefit(
        id='real-culture-2026', name='2026년 문화누리카드 신규발급·재충전',
        summary='문화예술·국내관광·체육활동 가맹점에서 사용할 수 있는 문화누리카드 발급 안내입니다. 1인당 연간 기본 지원금은 15만 원이며 일부 생애주기 대상자는 추가 지원을 확인할 수 있습니다.',
        categories=('문화', '생활·복지'), tags=(),
        target='2020-12-31 이전 출생자 중 기초생활수급자 및 차상위계층. 2026년 대상 출생일과 수급 자격을 확인해야 합니다.',
        extra_checks=('기초생활수급자 또는 차상위계층 자격과 해당 출생일',
                      '주민등록주소지 시·군·구 예산 잔여 여부(소진 시 조기 마감)',
                      '자동재충전 여부와 신규·재충전·재발급 절차의 차이',
                      '추가지원 대상 출생연도와 추가지원 예산'),
        method='주민센터 방문 또는 문화누리 누리집·모바일 앱 등을 통해 신규발급·재충전합니다. 발급 방식별 요건은 공식 안내를 확인하세요.',
        # 공식 공고 본문에 제출서류 목록이 없어 서류를 추정하지 않는다.
        documents=(), agency='한국문화예술위원회 / 주소지 주민센터 · 고객지원 1544-3412',
        source_url='https://www.mnuri.kr/notice/userNotice/detail.do?nttId=43151',
        verified_on=CHECKED_ON, regions={}, period_kind='fixed',
        start='2026-02-02', end='2026-11-30',
        period_note='카드 신규발급·재충전 기간입니다. 사용기간이나 재발급 기간과 다릅니다. 지역 예산 소진 시 조기 마감될 수 있습니다. 정확한 접수 마감시각은 발급 화면에서 확인하세요.',
    ),
)
REAL_BENEFITS = REAL_BENEFITS + NATIONAL_EXTRA_BENEFITS + REGIONAL_BENEFITS



# 지역 상세 데이터: 공식 안내 요약. 연도 미확정 안내는 현재 모집으로 간주하지 않는다.
# 추가 시 id/name/summary/target/extra_checks/method/documents/agency/source_url/regions를 작성.
# 시군 한정이면 regions={'전라남도': ('영암군',)}처럼 지정한다.
# 개인별 생일·출산일에 따른 기한은 이 앱에서 계산하지 않는다(생년월일 미수집).
LOCAL_DETAIL_BENEFITS = (
    Benefit(
        id='local-seoul-voucher', name='서울형 주택바우처 · 일반바우처',
        summary='서울의 저소득 민간 월세 가구에 월세 일부를 지원합니다. 공식 안내 기준 1인 가구 월 12만 원부터 6인 가구 월 17만 원까지 가구원 수에 따라 다릅니다.',
        categories=('주거','생활·복지'), tags=(),
        target='서울시 민간 월세 주택·고시원·주거용 오피스텔 가구. 보증금 1억 6,500만 원 이하, 소득평가액 기준 중위소득 60% 이하, 재산가액 2억 원 이하를 모두 확인해야 합니다.',
        extra_checks=('금융재산 8,000만 원 초과 및 가구원 자동차 2대 이상 소유 시 제외',
                      '생계·의료·주거급여 수급, 공공임대, 외국인만으로 구성된 가구 제외',
                      '부양의무자와의 임대차 또는 전대차 제외; 확정일자·계약 당사자 등 확인',
                      '가구원 수와 소득평가액·재산 평가, 현재 접수 여부'),
        method='신청권자가 신청서와 증빙서류를 작성해 거주지 동주민센터 담당자에게 제출합니다. 가구원·대리인별 위임 요건을 확인하세요.',
        documents=('서울형 주택바우처 신청서','차상위계층 확인서 및 발급신청서','개인정보 이용 및 제공 사전동의서',
                   '임대차계약서 사본','가족관계증명서','신청자 통장 사본','신청자 신분증'),
        agency='서울특별시 주거복지과 · 02-2133-7992 / 주소지 동주민센터',
        source_url='https://housing.seoul.go.kr/site/main/content/sh_061010', verified_on=CHECKED_ON,
        regions={'서울특별시':()}, period_note='2026년 기준이 포함된 공식 사업 안내입니다. 안내 본문에서 확정 접수 시작·종료일을 확인하지 못해 기간 확인 필요로 표시합니다.'),
    Benefit(
        id='local-seoul-basement', name='서울형 주택바우처 · 반지하 거주가구 이주 지원',
        summary='요건을 충족하는 반지하 가구가 지상층으로 이주하면 월 20만 원, 최장 72개월 지원하는 안내입니다. 2년 단위 연장 심사가 있습니다.',
        categories=('주거','생활·복지'),tags=(),
        target='2022-08-09 당시 서울 반지하 주택에 거주하고 2022-08-10 이후 지상층으로 이주한 가구. 신청 당시 소득이 전년도 도시근로자 가구당 월평균소득 100% 이하(특정 이주지원 대출 실행자는 예외)인지 확인합니다.',
        extra_checks=('과거 반지하 실거주와 건축물대장상 지하층 여부',
                      '공공임대 입주·주거급여·청년월세지원·자가소유 등 제외 요건',
                      '고시원·쪽방·옥탑방·근린생활시설로 이주 또는 기준일 이후 반지하 신규 입주 제외',
                      '지상층 전입신고·확정일자, 소득과 2년 단위 연장 자격'),
        method='이주한 지상층 거주지 관할 동주민센터에 신청서와 증빙서류를 제출합니다. 선정 여부와 지급일은 관할 자치구에 문의합니다.',
        documents=('신청서','개인정보 이용 및 제공 사전동의서','신청자 신분증',
                   '반지하·지상층 각각의 임대차계약서 사본 또는 월세 이체 증빙','통장 사본',
                   '주거취약계층 이주지원 버팀목 대출 거래약정서(해당자)'),
        agency='서울특별시 주거복지과 · 02-2133-7996 / 이주지 동주민센터',
        source_url='https://housing.seoul.go.kr/site/main/content/sh01_061031',verified_on=CHECKED_ON,
        regions={'서울특별시':()},period_note='공식 안내에 확정 접수 시작·마감일이 명시되지 않아 기간 확인 필요입니다. 과거 거주 기준일은 신청 마감일이 아닙니다.'),
    Benefit(
        id='local-seoul-rent-2026',name='2026년 서울시 청년월세지원 모집',
        summary='서울 거주 청년에게 월 최대 20만 원, 최대 12개월(생애 1회) 월세를 지원한 모집입니다. 2026년 해당 모집은 종료되었습니다.',
        categories=('주거',),tags=(),
        target='서울 주민등록 월세 거주 청년. 공식 안내의 신청연도 연령 19~39세(군복무 최대 3살 연장), 보증금 8,000만 원 이하·월세 60만 원 이하, 중위소득 48% 초과~150% 이하 무주택 요건 등을 확인합니다. 유형별 가구 요건이 다릅니다.',
        extra_checks=('월세 60만 원 초과 시 보증금 환산액과 합계 90만 원 이하 예외',
                      '일반재산 1억 3,000만 원 초과·차량가액 2,500만 원 이상 등 제외 기준',
                      '서울시 이전 수혜·국토부 및 자치구 월세지원·서울 청년수당 등 중복 제한',
                      '공공임대·수급자·부모와 임대차 등 제외 여부; 적격자 중 유형별 전산추첨'),
        method='해당 모집은 종료되었습니다. 당시 서울주거포털 청년월세지원에서 온라인 신청했습니다. 새 모집은 별도 공고를 확인해야 합니다.',
        documents=('확정일자 있는 임대차계약서 전체 사본(유형별 대체서류 확인)',
                   '최근 3개월(2026년 2~4월) 월세 이체확인증(예외 증빙 확인)',
                   '본인 기준 상세 가족관계증명서(공고일 이후 발급)',
                   '행정정보 공동이용 사전동의서(비동의 시 대체서류)',
                   '한부모가족증명서·전세사기피해 결정문·병적증명서 등 해당 서류'),
        agency='서울주택도시공사 청년월세지원센터 · 1833-2030 / 다산콜센터 120',
        source_url='https://housing.seoul.go.kr/site/main/content/sh01_060513',verified_on=CHECKED_ON,
        regions={'서울특별시':()},period_kind='fixed',start='2026-05-06',end='2026-05-19',
        period_note='2026-05-06 10:00~05-19 18:00 모집 종료. 서류 공식 안내: https://housing.seoul.go.kr/site/main/content/sh01_060513_7 . 종료 공고를 현재 모집으로 해석하지 마세요.'),
    Benefit(
        id='local-incheon-angel',name='인천 천사(1040) 지원금',
        summary='2023년 이후 출생 아동의 양육을 지원하는 인천 사업입니다. 1~7세 연 120만 원의 인천e음 포인트를 지원하며 거주·신청기한 심사가 필요합니다.',
        categories=('생활·복지',),tags=('자녀 양육 가구',),required_tags=('자녀 양육 가구',),
        target='공식 안내상 2026년 대상은 2023~2025년생. 매년 생일 기준 부 또는 모와 주민등록을 같이 두고 인천에서 1년 이상 계속 거주하는 아동 등이 대상이며 부모 사망·친권상실·위탁보호 등의 별도 유형도 있습니다.',
        extra_checks=('아동 생일·출생연도와 부모 동거 주민등록·계속 거주기간',
                      '2026년 전입 아동은 안내상 2027년부터 조건 충족 시 신청 가능; 전입자 월할 산정 별도 확인',
                      '생일 포함 120일 이내 최초 신청 여부; 매년 자동지급 자격 유지',
                      '신청자 명의 인천e음 가입·비교통 카드 종류와 구별 지급 카드 확인'),
        method='아동 부 또는 모가 정부24(보조금24)에서 천사지원금을 검색해 신청합니다. 온라인이 불가능한 보호자는 주소지 행정복지센터에 문의하세요. 공식 페이지의 신청하기 버튼으로 이동할 수 있습니다.',
        documents=(),agency='인천광역시 영유아정책과 · 032-440-2839 / 미추홀콜센터 032-120 / 주소지 행정복지센터',
        source_url='https://www.incheon.go.kr/earlychild/EC060101',verified_on=CHECKED_ON,
        regions={'인천광역시':()},period_note='개인별 신청기한: 아동 생일 포함 120일 이내. 생일을 수집하지 않아 남은 날짜는 계산하지 않습니다. 최초 1회 신청 뒤 자격에 따라 매년 자동지급되는 제도이며 이 앱의 자동 알림 기능이 아닙니다. 서류 목록은 보호자 유형별로 담당 기관 확인이 필요합니다.'),
    Benefit(
        id='local-gg-postpartum',name='경기도 산후조리비 지원',
        summary='출생아 1명당 50만 원을 지역화폐로 지원합니다. 쌍둥이는 100만 원 등 출생아 수에 비례하며 출생등록·거주 요건을 확인합니다.',
        categories=('생활·복지',),tags=('자녀 양육 가구',),required_tags=('자녀 양육 가구',),
        target='부 또는 모가 출생일 및 신청일 현재 경기도 주민등록을 두고 실제 거주하며, 신청 시 출생 후 12개월이 지나지 않은 영아가 경기도에 출생등록되어 있어야 합니다.',
        extra_checks=('출생일·신청일 거주 및 실제 거주·경기도 출생등록',
                      '출생일 기준 12개월 이내 신청; 이사한 경우 출생등록 시군 신청 원칙',
                      '외국인·다문화 가정의 체류자격·서류·방문신청 별도 기준',
                      '지역화폐 시군별 사용처·유효기간과 발급방식'),
        method='출생신고 완료 후 경기민원24에서 본인이 온라인 신청하거나 출생등록 관할 주민센터를 방문합니다. 온라인 대리신청 및 외국인 신청은 불가하므로 방문 창구를 확인하세요.',
        documents=('가족관계증명서','신청인 주민등록등본(행정정보 공동이용 미연계 시)',
                   '신청인 주민등록초본(행정정보 공동이용 미연계 시)'),
        agency='경기도 / 출생등록 관할 주민센터·시군 보건소 (공식 페이지에 시군별 담당자 연락처 제공)',
        source_url='https://gg24.gg.go.kr/svcreqst/selectSvcReqst.do?svc_seq=803',verified_on=CHECKED_ON,
        regions={'경기도':()},period_kind='always',
        period_note='공식 안내상 상시 접수이지만 개인별로 출산일~출생일 기준 12개월 이내라는 신청기한이 있습니다. 이 앱은 출생일을 수집하지 않아 개인 마감일을 계산하지 않습니다.'),
    Benefit(
        id='local-gg-interview-2026',name='2026년 경기도 청년면접수당 모집',
        summary='면접 1회당 지역화폐 5만 원, 연 최대 3회 지원한 사업입니다. 2026년 안내에는 모집 완료 및 추가 모집 미진행으로 표시되어 있습니다.',
        categories=('취업',),tags=('취업준비생','직장인'),
        target='신청일 경기도 주민등록 청년 중 구직 면접 응시자. 안내상 18~39세, 병역이행 시 최대 3년 연장과 2026년 면접 응시 기준 등을 확인합니다.',
        extra_checks=('해당 연도 출생일 범위·병역 연령 연장',
                      '실업급여·경기여성취업지원금 등 유사사업 중복 제한',
                      '전화·문자 면접, 교육훈련 면접, 가족 대표 사업장 면접 등 제외',
                      '1차에 한한 전년도 12월 면접 소급 예외; 2026년 추가모집 미진행 안내'),
        method='해당 모집은 종료되었습니다. 당시 잡아바 어플라이 온라인 접수이며, 이후 연도 모집을 자동 추정하지 않습니다.',
        documents=('신청서 및 개인정보 활용동의서(온라인 작성)','주민등록등본(마이데이터 연동 또는 첨부)',
                   '채용공고문','면접확인서 또는 대체서약서와 면접사실 증빙'),
        agency='경기도 / 경기도 공식 청년면접수당 안내',
        source_url='https://www.gg.go.kr/contents/contents.do?ciIdx=987029&menuId=265937',verified_on=CHECKED_ON,
        regions={'경기도':()},period_kind='fixed',start='2026-06-24',end='2026-07-07',
        period_note='공식 페이지의 2026년 모집일정 6/24~7/7 모집완료 및 추가모집 미진행 안내 기준. 오래된 11월 모집 예정 안내를 현재 모집으로 적용하지 않습니다.'),
    Benefit(
        id='local-jn-culture-guide',name='전남 청년 문화복지카드 · 사업 안내',
        summary='전남 청년의 문화생활·자기계발을 위한 연 25만 원 지원 사업 안내입니다. 이번에 확인한 안내에는 연도별 접수기간이 없어 현재 모집 여부를 별도로 확인해야 합니다.',
        categories=('문화','생활·복지'),tags=(),age_min=19,age_max=28,
        target='확인한 도청 사업 안내상 공고일 기준 전남에 2년 이상 거주한 19~28세 청년. 연도별 출생일 범위와 기준일은 실제 모집 공고가 우선합니다.',
        extra_checks=('전남 계속 거주기간·공고 기준일·해당 연도 출생일 범위',
                      '공공기관 근무자·학교 밖 청소년 교육수당·전남 여성농업인 바우처 등 제외',
                      '문화누리카드 대상자는 차액 지원 등 중복 조건',
                      '확인 안내의 적용연도·현재 모집·시군별 예산과 사용처'),
        method='주소지 읍면동 행정복지센터 또는 농협·광주은행 누리집을 이용하는 사업으로 안내되어 있습니다. 현행 시군 공고에서 접수처를 먼저 확인하세요.',
        documents=(),agency='전라남도 청년희망과 · 061-286-2832 / 주소지 시군·행정복지센터',
        source_url='https://www.jeonnam.go.kr/contentsView.do?menuId=brand0401000000',verified_on=CHECKED_ON,
        regions={'전라남도':()},period_note='사업 안내이지 현재 접수 중인 모집 공고 확인이 아닙니다. 적용연도·신청기간·서류는 시군의 해당 연도 공고 확인 필요. 기간 미확정이므로 마감일까지 남은 날짜는 계산하지 않습니다.'),
    Benefit(
        id='local-yeongam-ship-guide',name='영암군 조선업 희망공제 · 사업 안내',
        summary='영암군 주소를 둔 조선기업 생산직 신규 정규직 입사자 대상 안내입니다. 1년 만기 450만 원 공제 적립(근로자 150만 원·지원금 300만 원) 구조로 안내되어 있습니다.',
        categories=('취업','생활·복지'),tags=('직장인',),
        target='전남도 공식 정책 안내상 영암군에 주소를 둔 조선기업 생산직 신규 입사자(정규직). 실제 참여기업·신규입사 인정 기간은 운영기관의 현행 공고로 확인해야 합니다.',
        extra_checks=('영암군 주민등록·조선기업 정규직 생산직 신규입사 여부',
                      '현재 사업 운영·참여기업·입사 인정기간·소득·중복가입 제한 등 미확인 조건',
                      '본인 납입 150만 원과 유지기간·중도해지 조건; 무조건 지급되는 현금 아님'),
        method='도청 안내상 기업별로 전남인력개발원에 신청하는 방식입니다. 근무 기업과 운영기관에 현행 모집 여부·서류를 먼저 문의하세요.',
        documents=(),agency='전남인력개발원 · 061-461-2841 / 전라남도 일자리경제과 · 061-286-5034',
        source_url='https://www.jeonnam.go.kr/contentsView.do?menuId=brand0401000000',verified_on=CHECKED_ON,
        regions={'전라남도':('영암군',)},period_note='도청 정책 안내에서 사업 구조만 확인했습니다. 현재 연도의 모집 공고·기간·서류는 확인하지 못했으며 개인 신청 가능 여부도 기업·운영기관 확인 필요입니다.'),
)
REAL_BENEFITS = REAL_BENEFITS + LOCAL_DETAIL_BENEFITS

# 추가 상세 출처(각 서비스별 실제 열람 링크만 추가)
SUPPLEMENTARY_SOURCES = {
    'local-seoul-rent-2026': (('필수서류 공식 안내','https://housing.seoul.go.kr/site/main/content/sh01_060513_7'),),
    'local-incheon-angel': (('정부24·보조금24 신청 상세','https://plus.gov.kr/portal/benefitV2/benefitTotalSrvcList/benefitSrvcDtl?svcSeq=2171418&bnefType=all&svcId=628000000781'),),
}


def filter_scope(items, scope):
    if scope == '우리 지역 한정':
        return [b for b in items if b.regions]
    if scope == '전국 공통':
        return [b for b in items if not b.regions]
    return list(items)


def render_official_search(province, district):
    # 로그인·맞춤검색 결과는 가져오거나 재현하지 않는다. 공식 사이트에서 직접 선택하도록 안내.
    with st.expander('등록되지 않은 지역 혜택 더 찾기 · 보조금24·복지로'):
        st.write(f'공식 사이트에서 거주지를 {province} {district}로 선택하고, 원하는 사업명을 검색하세요. 이 앱은 로그인된 맞춤조회 결과를 가져오지 않습니다.')
        st.link_button('정부24에서 보조금24·혜택 찾기', 'https://plus.gov.kr/',use_container_width=True)
        st.link_button('복지로에서 복지서비스·맞춤형급여안내 찾기','https://www.bokjiro.go.kr/',use_container_width=True)
        st.caption('보조금24·복지로 링크는 추가 탐색 경로입니다. 연동·자동 수집·자격조회가 구현된 것은 아닙니다. 개인정보와 인증정보는 해당 공식 사이트에서만 입력하세요.')
        st.code(f'{province} {district} 지원사업 신청 공고',language=None)
        st.write('지역 홈페이지의 고시·공고 / 복지 / 청년 / 출산·보육 메뉴도 확인하세요. 종료 공고는 새 모집으로 보지 말고 해당 연도 변경 공지를 확인하세요.')


def build_demo_benefits() -> tuple[Benefit, ...]:
    # 고정된 기준일에 대한 가상 일정. 실행일마다 마감일을 미루지 않는다.
    # 시간이 지나 예시들이 종료되어도 종료 목록에서 검증할 수 있다.
    base = date(2026, 11, 5)
    cases = (
        ('study', '가상 학습 준비 서비스', ('교육',), ('학생',), 'fixed', -5, 3, {}),
        ('career', '가상 취업 준비 서비스', ('취업',), ('취업준비생',), 'fixed', -3, 18, {}),
        ('home', '가상 주거 상담 서비스', ('주거', '생활·복지'), (), 'always', None, None, {}),
        ('shop', '가상 점포 운영 상담', ('소상공인',), ('자영업자',), 'unknown', None, None, {}),
        ('culture', '가상 마포 문화 체험', ('문화',), (), 'fixed', -20, -1, {'서울특별시': ('마포구',)}),
        ('family', '가상 가족 체험 서비스', ('생활·복지', '문화'), ('자녀 양육 가구',), 'fixed', 10, 30, {}),
    )
    items = []
    for key, title, categories, tags, kind, start_delta, end_delta, regions in cases:
        items.append(Benefit(
            id=f'demo-{key}', name=f'[기능 시연용 예시] {title}',
            summary='실제 존재하거나 신청 가능한 지원사업이 아닙니다. 검색·마감일·관심 혜택·서류 체크를 시험하기 위한 가상 항목입니다.',
            categories=categories, tags=tags, target='시연용으로 정한 조건이며 실제 자격요건이 아닙니다.',
            extra_checks=('가상 예시이므로 실제 신청이나 수혜 판단에 사용할 수 없음',),
            method='시연 전용: 실제 신청 창구가 없습니다.',
            documents=('시연용 준비 항목 A (실제 서류 아님)', '시연용 준비 항목 B (실제 서류 아님)'),
            agency='가상 운영기관 (실존 기관 아님)', source_url=None, verified_on=None,
            regions=regions, period_kind=kind,
            start=(base + timedelta(days=start_delta)).isoformat() if start_delta is not None else None,
            end=(base + timedelta(days=end_delta)).isoformat() if end_delta is not None else None,
            period_note='2026-11-05를 기준으로 작성한 고정된 가상 일정입니다. 공식 공고의 기간이 아닙니다.',
            demo=True,
        ))
    return tuple(items)


DEMO_BENEFITS = build_demo_benefits()


# ── 데이터/판정 계층: Streamlit 화면과 독립적인 함수 ──
def today_kst() -> date:
    return datetime.now(KST).date()


def parse_date(value: str | None) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except (ValueError, TypeError):
        return None


def load_benefits(demo: bool) -> list[Benefit]:
    """향후 API/DB 연동 교체 지점. 공식 데이터와 가상 데이터는 절대 합치지 않는다."""
    return list(DEMO_BENEFITS if demo else REAL_BENEFITS)


def period_status(b: Benefit, today: date) -> tuple[str, int | None]:
    start, end = parse_date(b.start), parse_date(b.end)
    # 종료일이 확인되면 일부 날짜 누락 공고도 종료 목록으로 분리한다.
    if start and end and start > end:
        return '기간 확인 필요', None
    if end and end < today:
        return '종료', (end - today).days
    if b.period_kind == 'always' and not b.start and not b.end:
        return '상시 신청', None
    if b.period_kind != 'fixed' or not start or not end:
        return '기간 확인 필요', None
    if today < start:
        return '신청 예정', (start - today).days
    left = (end - today).days
    return ('마감 임박' if left <= 7 else '신청 중'), left


def match_reasons(b: Benefit, province: str, district: str, age: str,
                  tags: list[str], categories: list[str]) -> list[str] | None:
    reasons = []
    if b.regions:
        if province not in b.regions:
            return None
        allowed = b.regions[province]
        if allowed and district not in allowed:
            return None
        reasons.append(f'지역 일치: {province} {district}')
    else:
        reasons.append('전국 공통 서비스 · 선택한 지역에서도 확인 가능' if not b.demo else '시연 지역 범위 일치')
    lo, hi = AGE_BANDS.get(age, (None, None))
    if lo is not None and hi is not None:
        if (b.age_min is not None and hi < b.age_min) or (b.age_max is not None and lo > b.age_max):
            return None
        if b.age_min is not None or b.age_max is not None:
            reasons.append('선택한 연령대가 안내 연령 범위와 겹침; 정확한 만 나이는 추가 확인 필요')
    elif b.age_min is not None or b.age_max is not None:
        reasons.append('연령을 선택하지 않아 연령 자격은 추가 확인 필요')
    if tags:
        if b.required_tags and not set(b.required_tags).issubset(tags):
            return None
        overlap = sorted(set(tags).intersection(b.tags))
        if b.tags and not overlap:
            return None
        reasons.append('해당 조건 일치: ' + ', '.join(overlap) if overlap else '선택한 상태와 무관하게 살펴볼 수 있는 항목')
    elif b.tags:
        reasons.append('해당 조건 미선택: 대상 조건 확인 필요')
    if b.id == 'real-gg-basic-2026-q4':
        reasons.append('분기 기준일의 출생일 범위로 심사하므로 연령대 대신 생년월일 추가 확인 필요')
    if categories:
        overlap = [x for x in b.categories if x in categories]
        if not overlap:
            return None
        reasons.append('관심 분야 일치: ' + ', '.join(overlap))
    return reasons


def filter_benefits(items: list[Benefit], today: date, province: str, district: str,
                    age: str, tags: list[str], categories: list[str], query: str,
                    active_only: bool, ended: bool = False) -> list[tuple[Benefit, list[str]]]:
    result = []
    for b in items:
        reasons = match_reasons(b, province, district, age, tags, categories)
        if reasons is None or query.strip().casefold() not in b.name.casefold():
            continue
        status, _ = period_status(b, today)
        if (status == '종료') != ended:
            continue
        if not ended and active_only and status not in ('상시 신청', '신청 중', '마감 임박'):
            continue
        result.append((b, reasons))
    return result


def sort_results(rows: list[tuple[Benefit, list[str]]], today: date, order: str):
    def key(row):
        b = row[0]
        status, _ = period_status(b, today)
        end = parse_date(b.end)
        if status == '종료':
            return (0, -(end.toordinal() if end else 0), b.name)
        if status in ('마감 임박', '신청 중'):
            return (0, end.toordinal(), b.name)
        if status == '신청 예정':
            return (1, (parse_date(b.start) or date.max).toordinal(), b.name)
        return (2 if status == '상시 신청' else 3, date.max.toordinal(), b.name)
    return sorted(rows, key=(lambda row: row[0].name) if order == '혜택명 순' else key)


def validate_public_url(value: str) -> tuple[bool, str]:
    """QR은 접속 URL만 담는다. URL을 서버에서 조회하지 않는다."""
    value = value.strip()
    if not value or len(value) > 1800 or re.search(r'\s', value):
        return False, '공백 없이 HTTPS 주소를 입력해 주세요(최대 1,800자).'
    try:
        parts = urlsplit(value)
        host = parts.hostname or ''
        port = parts.port
        if parts.scheme != 'https' or not host or parts.username or parts.password:
            return False, '아이디·비밀번호가 포함되지 않은 HTTPS 배포 주소가 필요합니다.'
        if parts.query or parts.fragment:
            return False, '개인정보·인증 토큰 노출을 피하려고 ? 또는 # 뒤의 값이 없는 기본 앱 주소만 허용합니다.'
        if port not in (None, 443):
            return False, '기본 HTTPS 포트의 공개 배포 주소를 사용해 주세요.'
        if host == 'localhost' or host.endswith(('.localhost', '.local')) or '.' not in host:
            return False, '다른 스마트폰에서도 열 수 있는 공개 배포 주소를 입력해 주세요.'
        try:
            ipaddress.ip_address(host)
            return False, 'IP 주소 대신 공개 배포 도메인 주소를 입력해 주세요.'
        except ValueError:
            pass
        host.encode('idna')
    except (ValueError, UnicodeError):
        return False, '주소 형식을 확인해 주세요.'
    return True, value


def official_link_valid(url: str) -> bool:
    try:
        parts = urlsplit(url)
        host = (parts.hostname or '').lower()
        return (parts.scheme == 'https' and not parts.username and not parts.password
                and parts.port in (None, 443)
                and (host.endswith('.go.kr') or host in ('www.gov.kr', 'gov.kr', 'www.mnuri.kr', 'mnuri.kr')))
    except ValueError:
        return False


def reset_search():
    # 위젯 생성 전에 실행되는 콜백. 관심 혜택·서류 준비 상태는 지우지 않는다.
    for key in ('province', 'district', 'age', 'tags', 'categories', 'query', 'active_only', 'order', 'scope'):
        st.session_state.pop(key, None)


def clear_active_filter():
    st.session_state['active_only'] = False


def available_region(b: Benefit, province: str, district: str) -> bool:
    return not b.regions or (province in b.regions and
                            (not b.regions[province] or district in b.regions[province]))


def make_qr_png(url: str) -> bytes:
    import qrcode
    qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
                       box_size=10, border=4)
    qr.add_data(url)
    qr.make(fit=True)
    image = qr.make_image(fill_color='#142b49', back_color='white')
    output = BytesIO()
    image.save(output, format='PNG')
    return output.getvalue()


# ── 화면 계층 ──
CSS = '''
<style>
:root { color-scheme: light; }
.stApp, [data-testid="stHeader"] { background: #ffffff; color: #142b49; }
.block-container { max-width: 850px; padding-top: 1.7rem; padding-bottom: 3rem; }
h1,h2,h3 { color: #142b49 !important; letter-spacing: -.035em; }
h1 { font-size: 2rem !important; } h2 { font-size: 1.45rem !important; }
h3 { font-size: 1.18rem !important; }
p, li, label, [data-testid="stMarkdownContainer"] { line-height: 1.7; }
[data-testid="stCaptionContainer"] { color: #52677a !important; }
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: 16px; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-primary"],
[data-testid="stBaseButton-linkButton"], [data-testid="stBaseButton-downloadButton"]
{ min-height: 46px; border-radius: 10px; }
[data-baseweb="input"], [data-baseweb="select"] > div { min-height: 46px; background: #f5f9fb; color: #142b49; }
input { color: #142b49 !important; -webkit-text-fill-color: #142b49; }
[data-testid="stExpander"] summary { min-height: 46px; color: #142b49; }
[data-testid="stBaseButton-secondary"], [data-testid="stBaseButton-linkButton"],
[data-testid="stBaseButton-downloadButton"] { color: #142b49; background: #f0faf7; border-color: #9bcfc2; }
[data-testid="stCheckbox"] label { min-height: 44px; align-items: center; }
.badge { display: inline-block; padding: .22rem .7rem; margin: .2rem .3rem .2rem 0;
 border-radius: 24px; font-size: .94rem; font-weight: 700; }
.b-open { background: #d9f3eb; color: #135844; }
.b-urgent { background: #ffeadc; color: #853d13; }
.b-check { background: #fff3cc; color: #654c00; }
.b-muted { background: #e9eef4; color: #354b64; }
.intro { border-left: 5px solid #55bba8; padding: .6rem 1rem;
 background: #f1faf7; border-radius: 0 12px 12px 0; margin-bottom: 1rem; }
@media(max-width: 640px) {
 .block-container { padding: 1rem 1rem 2rem; }
 h1 { font-size: 1.7rem !important; }
}
</style>
'''


def remember_checked(bid: str, index: int, widget_key: str):
    # 체크박스가 화면에서 사라져도 독립적인 세션 상태에는 유지한다.
    st.session_state['document_checks'][(bid, index)] = bool(st.session_state[widget_key])


def render_documents(b: Benefit, location: str):
    if not b.documents:
        st.info('확인된 준비서류가 없습니다. 담당 기관에서 최신 목록을 확인하세요.')
        return
    st.caption('모든 서류가 모든 신청자에게 필요한 것은 아닙니다. 실제 파일이나 개인정보는 업로드하지 마세요.')
    checks = st.session_state['document_checks']
    for i, doc in enumerate(b.documents):
        key = f'doc_{location}_{b.id}_{i}'
        st.session_state[key] = checks.get((b.id, i), False)
        st.checkbox(doc, key=key, on_change=remember_checked, args=(b.id, i, key))
    count = sum(bool(checks.get((b.id, i), False)) for i in range(len(b.documents)))
    st.caption(f'준비 체크 {count}/{len(b.documents)} · 자격 심사나 서류 제출이 완료되었다는 뜻이 아닙니다.')


def render_card(b: Benefit, reasons: list[str], today: date, location: str):
    status, days = period_status(b, today)
    badge_class = ('b-urgent' if status == '마감 임박' else 'b-open'
                   if status in ('상시 신청', '신청 중') else 'b-muted')
    with st.container(border=True):
        st.subheader(b.name)
        st.markdown(f'<span class="badge {badge_class}">{escape(status)}</span>'
                    '<span class="badge b-check">추가 확인 필요</span>', unsafe_allow_html=True)
        st.caption(('지역 한정 · ' + ' / '.join(p + ((' ' + ', '.join(ds)) if ds else ' 전체') for p, ds in b.regions.items())) if b.regions else '전국 공통 서비스')
        st.write(b.summary)
        if '개인별' in b.period_note or '사업 안내이지' in b.period_note or '사업 구조만' in b.period_note:
            st.info(b.period_note)
        if status in ('마감 임박', '신청 중'):
            left_text = '오늘 마감 (마감시각 확인 필요)' if days == 0 else f'마감까지 {days}일'
            st.write(f'**신청 기간:** {b.start} ~ {b.end} · **{left_text}**')
        elif status == '신청 예정':
            st.write(f'**신청 기간:** {b.start} ~ {b.end} · 시작까지 {days}일')
        elif status == '종료':
            st.write(f'**신청 기간:** {b.start or "시작일 미확인"} ~ {b.end} · 종료된 공고')
        elif status == '상시 신청':
            st.write('**신청 기간:** 상시 신청 · 고정 마감일 없음')
        else:
            st.write('**신청 기간 / 남은 날짜:** 기간 확인 필요')
            if b.start or b.end:
                st.caption(f'기록된 날짜: 시작 {b.start or "미확인"} / 마감 {b.end or "미확인"} (전체 기간 미확정)')
        short_reason = next((r for r in reasons if r.startswith('해당 조건 일치')), reasons[0] if reasons else '직접 선택한 관심 혜택')
        st.write('**보여주는 이유:** ' + short_reason)
        st.caption('분야: ' + ' · '.join(b.categories))
        saved = b.id in st.session_state['favorites']
        if st.button('★ 관심 혜택에서 빼기' if saved else '☆ 관심 혜택에 담기',
                     key=f'save_{location}_{b.id}', use_container_width=True):
            if saved:
                st.session_state['favorites'].discard(b.id)
            else:
                st.session_state['favorites'].add(b.id)
            st.rerun()
        # 종료/관심 목록 자체가 접이식이므로 내부에 expander를 중첩하지 않는다.
        details = st.expander('대상·신청 방법·준비서류 확인') if location == 'results' else st.container()
        with details:
            st.markdown('**지역 제한 · 거주지 확인**')
            st.write(' / '.join(p + ((' ' + ', '.join(ds)) if ds else ' 전체') for p, ds in b.regions.items()) if b.regions else '전국 공통')
            st.caption('현재 지역 선택만으로 거주기간·실거주·가족 동거·사업장 소재지까지 확인된 것은 아닙니다.')
            st.markdown('**기본 조건 관련성 상세**')
            for reason in reasons:
                st.write('• ' + reason)
            st.markdown('**대상 및 주요 조건**')
            st.write(b.target)
            st.markdown('**추가 확인 필요**')
            for text in b.extra_checks or ('소득·재산·가구 구성·중복 수혜 등 공식 공고의 최종 조건',):
                st.write('• ' + text)
            st.caption('이 앱은 소득·재산·가구 구성·정확한 만 나이·중복 수혜 여부를 심사하지 않습니다.')
            st.markdown('**기간 관련 안내**')
            st.write(b.period_note or '공식 공고에서 예산 소진·마감시각·변경 공지를 확인하세요.')
            st.markdown('**신청 방법**')
            st.write(b.method)
            st.markdown('**준비서류 체크**')
            render_documents(b, location)
            st.markdown('**담당 기관**')
            st.write(b.agency)
        if b.demo:
            st.caption('정보 확인일: 해당 없음 · 기능 시연용 가상 데이터 · 공식 안내 링크 없음')
        else:
            checked = parse_date(b.verified_on)
            st.caption(f'정보 확인일: {b.verified_on if checked else "확인일 미등록"} · 실시간 자동 갱신 아님')
            if checked and (today - checked).days > 30:
                st.warning('확인일로부터 30일이 넘었습니다. 현재 조건과 접수 여부를 공식 안내에서 다시 확인하세요.')
            if b.source_url:
                if official_link_valid(b.source_url):
                    st.link_button('공식 안내에서 최종 확인 ↗', b.source_url, use_container_width=True)
                    for label, link in SUPPLEMENTARY_SOURCES.get(b.id, ()):
                        if official_link_valid(link):
                            st.link_button(label, link, use_container_width=True)
                else:
                    st.warning('공식 링크 형식 확인이 필요합니다. 담당 기관에 문의하세요.')
            else:
                st.warning('공식 안내 링크가 등록되지 않았습니다. 담당 기관에 확인하세요.')


def render_qr():
    with st.expander('QR코드 만들기 · 배포 주소 공유'):
        st.write('배포가 끝난 앱의 HTTPS 주소를 넣으세요. QR코드는 보안장치가 아니라 접속 주소입니다.')
        st.caption('URL은 QR 생성에만 사용하며 앱에서 해당 사이트를 조회하지 않습니다. 개인정보나 비밀키를 넣지 마세요.')
        url = st.text_input('배포된 앱 주소', placeholder='https://your-app.streamlit.app', key='qr_address', value=DEFAULT_APP_URL)
        if url:
            valid, value = validate_public_url(url)
            if not valid:
                st.warning(value)
            else:
                try:
                    png = make_qr_png(value)
                    st.image(png, caption='배포 주소 접속용 QR코드', width=240)
                    st.code(value, language=None)
                    st.download_button('QR코드 PNG 내려받기', data=png, file_name='our_home_benefits_qr.png',
                                       mime='image/png', use_container_width=True)
                    st.caption('QR 생성은 배포 성공이나 접속 가능 여부를 검증하지 않습니다. 휴대폰으로 직접 스캔해 확인하세요. 비공개 앱은 별도 접근 권한이 필요합니다.')
                except Exception:
                    st.error('QR 이미지를 만들지 못했습니다. requirements.txt 설치 여부와 주소 길이를 확인해 주세요.')


def main():
    st.set_page_config(page_title='우리집 혜택 알리미', page_icon='🏡', layout='centered',
                       initial_sidebar_state='collapsed')
    st.markdown(CSS, unsafe_allow_html=True)
    st.session_state.setdefault('favorites', set())
    st.session_state.setdefault('document_checks', {})
    today = today_kst()
    st.title('🏡 우리집 혜택 알리미')
    st.write('우리 가족이 확인해 볼 만한 공공서비스를 찾아보세요.')
    st.caption('전국 17개 시·도 지역 선택 · 공식 정부 서비스 아님 · 이름·주민등록번호 입력 없음')
    st.caption('최종 자격과 실제 접수 여부는 공식 공고·담당 기관에서 확인하세요.')

    c1, c2 = st.columns(2)
    with c1:
        province = st.selectbox('거주 시·도', list(REGIONS), key='province')
    # 상위 지역 변경 후 유효하지 않은 시군구 값이 남지 않도록 초기화한다.
    districts = REGIONS.get(province, ())
    if st.session_state.get('district') not in districts:
        st.session_state.pop('district', None)
    with c2:
        district = st.selectbox('거주 시·군·구', districts, key='district')
    age = st.selectbox('본인의 연령대 (만 나이 기준)', list(AGE_BANDS), key='age')
    with st.expander('해당 조건·관심 분야 선택'):
        tags = st.multiselect('해당 조건 · 복수 선택 가능', TAGS, key='tags')
        categories = st.multiselect('관심 분야 · 복수 선택 가능', CATEGORIES, key='categories')
        st.caption('선택하지 않으면 넓게 찾아봅니다. 복수 상태는 하나 이상 관련되면 표시하며, 별도 필수 조건은 함께 확인합니다. 연령은 본인 기준이며 자녀 연령은 수집하지 않습니다.')
        st.caption('선택한 연령대가 일부만 겹쳐도 표시될 수 있습니다. 분기별 기준일로 심사하는 사업은 해당 출생일을 별도 확인하세요.')
    scope = st.selectbox('서비스 범위', ['전체', '우리 지역 한정', '전국 공통'], key='scope')
    query = st.text_input('혜택명 검색', placeholder='예: 내일배움, 문화누리', max_chars=100, key='query')
    c1, c2 = st.columns(2)
    with c1:
        active_only = st.checkbox('신청 중인 혜택만 보기', key='active_only')
    with c2:
        order = st.selectbox('정렬', ['마감 가까운 순', '혜택명 순'], key='order')
    st.button('검색 조건 초기화', on_click=reset_search, use_container_width=True)

    # 시연은 화면 흐름 아래쪽에서만 선택. 공식 데이터가 기본이며 혼합 표시하지 않는다.
    demo = st.session_state.get('demo_mode', False)
    all_items = load_benefits(demo)
    items = filter_scope(all_items, scope)
    args = dict(items=items, today=today, province=province, district=district, age=age,
                tags=tags, categories=categories, query=query, active_only=active_only)
    broad = filter_benefits(**{**args, 'active_only': False})
    current = sort_results(filter_benefits(**args), today, order)
    closed = sort_results(filter_benefits(**args, ended=True), today, order)
    unknown_count = sum(period_status(b, today)[0] == '기간 확인 필요' for b, _ in broad)
    if demo:
        st.warning('기능 시연용 예시만 표시 중입니다. 모든 사업·기관·조건·일정이 가상이며 실제 신청할 수 없습니다. 아래 ‘기능 시연’에서 해제할 수 있습니다.')
    else:
        region_items = [b for b in all_items if b.regions and available_region(b, province, district)]
        national_count = sum(not b.regions for b in all_items)
        region_label = province if province == district else f'{province} {district}'
        st.caption(f'{region_label} · 지역 사업 {len(region_items)}건 / 전국 공통 {national_count}건 등록 (종료 포함·조건 적용 전)')
        if not region_items:
            st.caption('이 지역의 자체 사업은 아직 등록되지 않았습니다. 아래는 전국 공통 서비스입니다. 지역 사업이 없다는 뜻은 아닙니다.')
    st.header(f'확인해 볼 만한 혜택 {len(current)}건')
    st.caption(f'{today.isoformat()} 한국 시간 기준 · 확인된 일정에 따른 분류이며 실시간 접수 보장은 아닙니다.')
    if unknown_count:
        st.caption(f'현재 기본 검색 조건에 기간 미확인 {unknown_count}건이 있습니다. ‘신청 중’ 필터에서는 제외되지만 실제 신청 불가라는 뜻은 아닙니다.')
    if active_only:
        st.caption('확인된 접수기간에 해당하는 항목과 상시 신청만 표시합니다. 예정·종료·기간 미확인 항목은 제외합니다. 예산 소진 여부는 별도 확인이 필요합니다.')
    if not all_items:
        st.info('아직 등록된 정보가 없습니다. 운영자가 공식 정보를 등록하면 표시됩니다.')
    elif not current:
        if active_only and broad:
            st.info('다른 기본 조건에 맞는 항목은 있지만, 접수 중이라고 확인할 수 있는 등록 항목이 없습니다. 기간 미확인 또는 신청 예정 항목도 확인하려면 아래 버튼을 누르세요.')
            st.button('접수 상태 제한 풀고 보기', on_click=clear_active_filter, use_container_width=True)
        else:
            st.info('현재 조건에 맞는 등록 항목이 없습니다. 검색어를 지우거나, 관심 분야·해당 조건을 줄이거나, 위의 ‘검색 조건 초기화’를 눌러 보세요. 이 앱에 없다고 실제 혜택이 없는 것은 아닙니다.')
    # 지역 한정 서비스를 먼저 표시하고 각 그룹 안에서는 선택한 정렬을 유지한다.
    for regional, heading in ((True, '📍 선택한 지역에 한정된 서비스'), (False, '🌏 전국 공통 서비스')):
        group = [(b,r) for b,r in current if bool(b.regions) == regional]
        if group:
            st.subheader(f'{heading} · {len(group)}건')
            for b,reasons in group:
                render_card(b,reasons,today,'results')
    render_official_search(province,district)
    with st.expander(f'종료된 공고 별도로 보기 · {len(closed)}건'):
        st.caption('지역·연령·조건·분야·검색어는 적용하고 ‘신청 중’ 필터는 적용하지 않습니다.')
        if not closed:
            st.write('현재 조건에 맞는 종료 공고가 없습니다.')
        for b, reasons in closed:
            render_card(b, reasons, today, 'closed')
    selected = [b for b in all_items if b.id in st.session_state['favorites']]
    with st.expander(f'★ 내 관심 혜택 · 현재 모드 {len(selected)}건'):
        st.caption('검색 조건과 무관하게 표시합니다. 서비스 범위 필터와도 무관합니다. 다른 데이터 모드의 관심 혜택은 해당 모드로 바꾸면 다시 표시됩니다.')
        if not selected:
            st.write('카드의 ‘관심 혜택에 담기’를 눌러 모아 보세요.')
        for b in selected:
            render_card(b, ['직접 선택한 관심 혜택 · 현재 검색 조건과 무관'], today, 'favorites')
    st.caption('관심 혜택·준비서류 체크는 현재 접속 세션에서만 유지됩니다. 새로고침·연결 해제·앱 재시작 시 사라질 수 있으며 기기 간 동기화되지 않습니다. 개인정보·서류 파일은 수집하지 않습니다.')
    render_qr()
    with st.expander('이 앱을 만든 이유 · 지원 범위·출처'):
        st.markdown('**몰라서 놓치는 혜택을 줄이는 작은 행정 길잡이**')
        st.write('행정직 공무원을 꿈꾸며 주민의 행정정보 접근성을 높이기 위해 만든 학습 프로젝트입니다. 공공정보를 쉬운 말로 연결하고, 확인되지 않은 조건을 숨기지 않는 것을 목표로 합니다.')
        st.write('전국 17개 시·도에서 거주 지역을 선택할 수 있습니다. 시 소속 일반구는 시 단위로 통합하며, 세종은 단일 선택지, 제주는 두 행정시를 제공합니다. 읍·면·동 단위는 지원하지 않습니다.')
        st.write('전국 모든 혜택을 수집한 앱이 아닙니다. 전국 공통 3건과 지역 한정 10건(서울 3·경기 3·부산 1·인천 1·전남 2)을 수록했습니다. 종료 모집과 적용연도·기간 추가 확인이 필요한 사업 안내를 포함합니다. 나머지 지역 자체 사업은 아직 등록되지 않았으며, 공식 사이트 추가 탐색을 제공합니다.')
        st.write('경기도 청년기본소득은 성남·고양 제외를 반영합니다. 부산 공고는 종료 영역에 표시합니다. 이후 모집을 자동 추정하지 않습니다.')
        st.markdown(f'[행정안전부 행정구역 현황 자료]({REGION_SOURCE}) · [인천 2026년 개편 안내]({INCHEON_SOURCE})')
        st.caption(f'내장 지역 목록 점검일 {CHECKED_ON}. 행정구역은 자동 갱신되지 않습니다. 정책은 각 카드의 공식 링크와 확인일을 참고하세요.')
        st.write('연령대와 상태는 관련성 검색을 위한 기본 조건입니다. 소득·재산·가구 구성·중복 수혜·정확한 출생일은 심사하지 않으며 최종 자격은 담당 기관에서 확인해야 합니다.')
        st.write('이 앱의 ‘알리미’는 접속했을 때 정보와 마감일을 보여주는 기능입니다. 실제 신청, 문자·이메일·푸시 발송, 영구 보관은 하지 않습니다.')
        st.write('확장 기능: 공식 API 자동 갱신, 지역 사업 추가, 변경 이력, 다국어·쉬운 말 안내, 동의 기반 자동 알림. 영구 저장에는 별도 저장소·개인정보 보호 설계가 필요합니다. 자동 알림에는 외부 발송 서비스·스케줄러·수신 동의가 필요합니다.')
        st.write('API 키는 Streamlit Community Cloud 설정의 Secrets에 보관하고 st.secrets로 읽으세요. 공개 GitHub에는 키·비밀번호·개인정보를 올리지 마세요. 현재 버전은 키가 필요 없습니다.')
    with st.expander('기능 시연 · 가상 데이터로 시험하기'):
        st.checkbox('기능 시연용 예시 사용 (가상 데이터만 표시)', key='demo_mode')
        st.caption('선택하면 공식 데이터 대신 가상 항목만 표시합니다. 고정된 가상 일정(2026-11-05 기준)이며 실제 사업이 아닙니다. 날짜가 지나면 종료 영역으로 이동합니다. 지역 시연 항목은 마포구에서 확인할 수 있습니다.')
    st.caption('지역 한정 서비스를 먼저, 전국 공통을 다음에 표시합니다. 각 구분 안의 마감순 정렬: 접수 중(마감 빠른 순) → 신청 예정 → 상시 → 기간 미확인. 종료는 별도 영역에서 최근 마감순으로 표시합니다.')


if __name__ == '__main__':
    main()
