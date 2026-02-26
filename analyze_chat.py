import re
import os
import glob
import json
import base64
from datetime import datetime, timedelta
from collections import defaultdict

# 파일 경로 및 보안 설정
base_dir = r"d:\바탕화면\카톡내보내기"
REPORT_PASSWORD = "gabom" # 접속용 비밀번호 지정

# KakaoTalk으로 시작하는 .txt 파일들을 찾아서 가장 최근(수정시간 기준) 파일을 선택
kakao_files = glob.glob(os.path.join(base_dir, "KakaoTalk*.txt"))
if kakao_files:
    # 수정 시간(mtime) 기준으로 정렬하여 가장 최신 파일 선택
    log_file_path = max(kakao_files, key=os.path.getmtime)
else:
    # 파일이 없으면 기존 경로를 기본값으로 사용 (또는 에러 처리를 위해 유지)
    log_file_path = os.path.join(base_dir, "260226.txt")

output_report_path = os.path.join(base_dir, "index.html")


def analyze():
    # users_data 구조: {닉네임: {info_missing, greeted, monthly_counts, total_count, entry_date, last_activity_date, in_room}}
    users_data = defaultdict(lambda: {
        'info_missing': [], 
        'greeted': False, 
        'monthly_counts': defaultdict(int),
        'total_count': 0,
        'entry_date': None,
        'last_activity_date': None,
        'in_room': True
    })
    
    all_months = set()
    monthly_totals = defaultdict(int) # 월별 전체 총 대화수
    
    # 최근 30일 집계용
    thirty_days_ago = datetime.now() - timedelta(days=30)
    top_10_30d_counts = defaultdict(int)
    
    def check_info(nick):
        # 시스템 닉네임 예외 처리
        if any(sn in nick for sn in ["오픈채팅봇", "혈액암협회", "KBDCA"]):
            return []
            
        missing = []
        # 1. 역할(Role) 확인
        if not any(r in nick for r in ['환', '보', '본']):
            missing.append("역할(환/보/본) 누락")
        
        # 2. 기수(Stage) 및 나이(Age) 판정 고도화
        # 모든 숫자 추출
        all_numbers = re.findall(r'\d+', nick)
        # 명시적 기수 패턴 (\d+기, \d+기수, \d+A, \d+B, \d+C 등)
        stage_match = re.search(r'(\d+)(?:기|기수|[ABCabc])', nick)
        
        has_age = False
        has_stage = False
        
        if stage_match:
            has_stage = True
            stage_val = stage_match.group(1)
            # 기수로 사용된 숫자 제외하고 남은 숫자가 있는지 확인
            remaining = list(all_numbers)
            if stage_val in remaining:
                remaining.remove(stage_val)
            if remaining:
                has_age = True
        else:
            # 명시적 기수 표기('기' 등)가 없는 경우
            if len(all_numbers) >= 2:
                # 숫자가 2개 이상이면 관례상 나이와 기수가 모두 있다고 간주
                has_age = True
                has_stage = True
            elif len(all_numbers) == 1:
                # 숫자가 하나뿐인데 '기'가 없으면 보통 나이로 적음 (제보 사례)
                has_age = True
                has_stage = False
            else:
                has_age = False
                has_stage = False

        if not has_age:
            missing.append("나이(숫자) 누락")
        if not has_stage:
            missing.append("기수 누락")
        
        # 3. 전체 정보 조각 확인 (병원명 등)
        parts = [p.strip() for p in re.split(r'[/ㅣ| \t\nlI]', nick) if p.strip()]
        # 관례상 [이름, 역할, 나이, 기수, 병원] 등 4~5개 항목이 정석
        if len(parts) < 4:
            # 누락이 이미 떴다면 구체적으로 뭐가 부족한지 추가
            if not ("나이(숫자) 누락" in missing or "기수 누락" in missing):
                # 나이/기수가 있는데도 토큰이 부족하면 병원명 누락일 확률이 높음
                if len(parts) < 3:
                    missing.append("정보 부족(병원명 등)")
            elif len(parts) < 3:
                missing.append("병원명 또는 기타 정보 부족")
        
        return missing

    if not os.path.exists(log_file_path):
        print(f"File not found: {log_file_path}")
        return

    current_date = None
    
    # 성능 최적화: 정규표현식 미리 컴파일
    date_pattern = re.compile(r'^-+ (\d{4})년 (\d{1,2})월 (\d{1,2})일 .+ -+$')
    entry_pattern = re.compile(r'^(.+)님이 들어왔습니다\.')
    exit_pattern = re.compile(r'^(.+?)(님이 나갔습니다\.|님을 내보냈습니다\.)')
    msg_pattern = re.compile(r'^\[(.+?)\] \[.+?\] (.+)$')
    
    with open(log_file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if not line: continue
            
            # 날짜 확인
            date_match = date_pattern.match(line)
            if date_match:
                current_date = datetime(int(date_match.group(1)), int(date_match.group(2)), int(date_match.group(3)))
                continue
            
            # 입장 메시지 확인
            entry_match = entry_pattern.match(line)
            if entry_match:
                nick = entry_match.group(1).strip()
                if nick != "(알 수 없음)":
                    users_data[nick]['in_room'] = True
                    # 입장일 기록 (최초 1회만)
                    if current_date and not users_data[nick]['entry_date']:
                        users_data[nick]['entry_date'] = current_date.strftime('%Y-%m-%d')
                    
                    # 정보 누락 체크 (강제 업데이트)
                    users_data[nick]['info_missing'] = check_info(nick)
                continue

            # 퇴장 메시지 확인 (스스로 나감 또는 강퇴)
            exit_match = exit_pattern.match(line)
            if exit_match:
                nick = exit_match.group(1).strip()
                if nick in users_data:
                    users_data[nick]['in_room'] = False
                continue
            
            # 대화 메시지 확인
            msg_match = msg_pattern.match(line)
            if msg_match:
                nick = msg_match.group(1).strip()
                content = msg_match.group(2).strip()
                
                if nick == "(알 수 없음)": continue
                
                # 정보 업데이트
                if current_date:
                    date_str = current_date.strftime('%Y-%m-%d')
                    if not users_data[nick]['entry_date']:
                        users_data[nick]['entry_date'] = date_str
                    # 마지막 대화일 업데이트
                    users_data[nick]['last_activity_date'] = date_str

                # 정보 누락 상시 업데이트 (강제 업데이트)
                users_data[nick]['info_missing'] = check_info(nick)
                
                if content and content not in ['이모티콘', '사진', '동영상']:
                    users_data[nick]['greeted'] = True
                
                if current_date:
                    month_key = current_date.strftime('%Y-%m')
                    all_months.add(month_key)
                    users_data[nick]['monthly_counts'][month_key] += 1
                    users_data[nick]['total_count'] += 1
                    monthly_totals[month_key] += 1
                    
                    if current_date >= thirty_days_ago:
                        top_10_30d_counts[nick] += 1

    # 제외할 시스템 계정 키워드
    sys_exclude_keywords = ["오픈채팅봇", "KBDCA", "혈액암협회"]
    
    # 최종적으로 "방에 있는 사람"만 필터링 (시스템 계정 제외)
    active_users = {}
    excluded_sys_accounts = []
    
    for nick, data in users_data.items():
        if not data['in_room'] or nick == "(알 수 없음)":
            continue
            
        # 시스템 계정 여부 확인
        if any(kw in nick for kw in sys_exclude_keywords):
            excluded_sys_accounts.append(nick)
            continue
            
        active_users[nick] = data
        
    if excluded_sys_accounts:
        print(f"인원 집계에서 제외된 시스템 계정({len(excluded_sys_accounts)}명): {', '.join(excluded_sys_accounts)}")
    print(f"최종 집계 인원: {len(active_users)}명")
    
    # 인원 집계 완료 후, 중복 이름(base name) 감지
    base_name_counts = defaultdict(int)
    nick_to_base = {}
    
    for nick in active_users:
        # 이름 부분 추출 (구분자 이전)
        base = re.split(r'[/ㅣ| \t\nlI]', nick)[0].strip()
        nick_to_base[nick] = base
        base_name_counts[base] += 1
    
    # 월 목록 정렬
    sorted_months = sorted(list(all_months))
    
    # 총 대화수 순으로 정렬된 멤버 리스트
    sorted_active_users = sorted(active_users.items(), key=lambda x: x[1]['total_count'], reverse=True)
    
    def get_bg_color(count, max_count):
        if count == 0: return ""
        if max_count == 0: return "background-color: #fffde7;"
        ratio = count / max_count
        lightness = 95 - (ratio * 15) # 95(연함) ~ 80(진함)
        return f"background-color: hsl(54, 100%, {lightness}%);"

    # Top 10 (Last 30 Days) 가공
    top_10_30d = sorted(
        [{'nick': n, 'count': c} for n, c in top_10_30d_counts.items() if n in active_users],
        key=lambda x: x['count'], reverse=True
    )[:10]

    # 데이터를 JSON으로 변환 (보안 제거)
    raw_data = {
        'active_users': active_users,
        'top_10_30d': top_10_30d,
        'sorted_months': sorted_months,
        'monthly_totals': monthly_totals,
        'base_name_counts': base_name_counts,
        'nick_to_base': nick_to_base,
        'generation_time': datetime.now().strftime('%m/%d %H:%M')
    }
    
    json_data_str = json.dumps(raw_data, ensure_ascii=False)
    
    # Python 기본 라이브러리를 이용한 암호화 (XOR + Base64)
    def encrypt_data(data_str, pwd):
        data_bytes = data_str.encode('utf-8')
        pwd_bytes = pwd.encode('utf-8')
        encrypted = bytearray()
        for i in range(len(data_bytes)):
            encrypted.append(data_bytes[i] ^ pwd_bytes[i % len(pwd_bytes)])
        return base64.b64encode(encrypted).decode('utf-8')
        
    encrypted_data_str = encrypt_data(json_data_str, REPORT_PASSWORD)

    # HTML 생성
    html_content = f"""
    <!DOCTYPE html>
    <html lang="ko">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
        <title>가봄 오픈채팅 리포트</title>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&family=Noto+Sans+KR:wght@300;400;700&display=swap');
            
            :root {{
                --primary: #2c3e50;
                --primary-gradient: linear-gradient(135deg, #2c3e50 0%, #000000 100%);
                --naver-green: #03c75a;
                --bg: #f0f2f5;
                --card-bg: rgba(255, 255, 255, 0.9);
                --text: #1a1a1a;
                --text-muted: #636e72;
                --border: #dfe6e9;
                --col-0-w: 40px; --col-1-w: 180px; --col-2-w: 80px; 
                --col-3-w: 80px; --col-4-w: 120px; --col-5-w: 40px;
            }}
            
            * {{ box-sizing: border-box; transition: all 0.3s ease; }}
            body {{ 
                font-family: 'Inter', 'Noto Sans KR', sans-serif; 
                background: var(--bg); 
                margin: 0; padding: 0; min-height: 100vh;
                display: flex; flex-direction: column;
            }}
            
            /* 메인 리포트 화면 스타일 */
            /* 로그인 화면 스타일 */
            #login-screen {{
                display: flex; flex-direction: column; align-items: center; justify-content: center;
                height: 100vh; background: var(--primary-gradient); color: white;
                position: absolute; top: 0; left: 0; width: 100%; z-index: 9999;
            }}
            .login-box {{
                background: var(--card-bg); padding: 40px; border-radius: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.5); text-align: center; color: var(--text);
                width: 320px;
            }}
            .login-box input {{
                width: 100%; padding: 12px; margin: 20px 0; border: 1px solid var(--border);
                border-radius: 10px; font-size: 16px; outline: none; text-align: center;
            }}
            .login-box button {{
                width: 100%; padding: 12px; background: var(--naver-green); color: white;
                border: none; border-radius: 10px; font-size: 16px; font-weight: 700; cursor: pointer;
            }}
            #main-content {{ display: none; flex-direction: column; flex: 1; padding: 20px; animation: fadeIn 0.8s ease; height: 100vh; min-height: 400px; overflow: hidden; }}
            
            .header-info {{ background: white; padding: 20px 30px; border-radius: 20px; margin-bottom: 20px; box-shadow: 0 4px 12px rgba(0,0,0,0.05); display: flex; justify-content: space-between; align-items: center; }}
            h1 {{ font-weight: 700; font-size: 1.5em; color: var(--primary); margin: 0; }}
            .meta-info {{ color: var(--text-muted); font-size: 0.85em; font-weight: 500; }}
            
            .table-container {{ background: white; border-radius: 24px; padding: 0 0 10px 0; flex: 1; overflow-y: auto; overflow-x: auto; -webkit-overflow-scrolling: touch; box-shadow: 0 10px 30px rgba(0,0,0,0.08); border: 1px solid var(--border); min-height: 150px; }}
            table {{ border-collapse: separate; border-spacing: 0; font-size: 11px; width: max-content; min-width: 100%; }}
            th, td {{ padding: 10px 8px; text-align: center; border-bottom: 1px solid var(--border); border-right: 1px solid var(--border); }}
            th {{ background: #f8f9fa; color: var(--primary); font-weight: 700; height: 40px; }}
            #header-row th {{ position: sticky; top: 0; z-index: 100; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            #total-row th {{ position: sticky; top: 40px; z-index: 100; box-shadow: 0 2px 5px rgba(0,0,0,0.05); }}
            
            .sticky-0, .sticky-1 {{ position: sticky; background: white; z-index: 10; }}
            .sticky-0 {{ left: 0; width: var(--col-0-w); min-width: var(--col-0-w); max-width: var(--col-0-w); border-left: 1px solid var(--border); }}
            .sticky-1 {{ left: var(--col-0-w); width: var(--col-1-w); min-width: var(--col-1-w); max-width: var(--col-1-w); font-weight: 700; text-align: left; padding-left: 15px; color: var(--primary); }}
            
            #header-row .sticky-0, #header-row .sticky-1 {{ top: 0; z-index: 110; }}
            #total-row .sticky-0, #total-row .sticky-1 {{ top: 40px; z-index: 110; }}
            
            .total-info-row th {{ background: #2c3e50; color: white; }}
            .badge-o {{ background: #e3fcef; color: #00b894; padding: 3px 8px; border-radius: 6px; font-weight: 700; }}
            .badge-x {{ background: #fff0f0; color: #ff7675; padding: 3px 8px; border-radius: 6px; font-weight: 700; }}
            .grand-total {{ font-weight: 800; color: var(--primary); background: #f8f9fa !important; }}

            /* Top 10 모달 스타일 */
            .modal {{
                display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%;
                background: rgba(0,0,0,0.5); z-index: 10000; justify-content: center; align-items: center;
            }}
            .modal-content {{
                background: white; padding: 40px; border-radius: 24px; width: 400px; max-width: 90%;
                box-shadow: 0 20px 50px rgba(0,0,0,0.2); position: relative;
            }}
            .close-modal {{ position: absolute; top: 20px; right: 20px; cursor: pointer; font-size: 1.5em; }}
            .top10-item {{ display: flex; justify-content: space-between; padding: 12px 0; border-bottom: 1px solid #f0f0f0; }}
            .top10-rank {{ font-weight: 800; color: var(--primary); width: 30px; }}
            .top10-nick {{ flex: 1; font-weight: 600; }}
            .top10-count {{ color: #e74c3c; font-weight: 700; }}
            
            .pdf-btn {{
                background: var(--primary); color: white; border: none; padding: 10px 20px;
                border-radius: 12px; font-weight: 600; cursor: pointer; margin-top: 15px; width: 100%;
            }}

            /* 모바일 반응형 스타일 */
            @media (max-width: 768px) {{
                :root {{ --col-0-w: 35px; --col-1-w: 120px; }}
                #main-content {{ padding: 10px; }}
                .header-info {{ flex-direction: column; align-items: flex-start; gap: 15px; padding: 15px 20px; border-radius: 16px; margin-bottom: 15px; }}
                .header-info div {{ width: 100%; justify-content: space-between; }}
                h1 {{ font-size: 1.2em; }}
                .table-container {{ padding: 0 0 5px 0; border-radius: 16px; flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; }}
                table {{ font-size: 10px; }}
                th, td {{ padding: 8px 6px; }}
                .sticky-1 {{ padding-left: 10px; }}
                .modal-content {{ width: 95%; padding: 25px 20px; }}
                h2 {{ font-size: 1.3em; }}
            }}
        </style>
    </head>
    <body>
        <div id="login-screen">
            <div class="login-box">
                <h2 style="margin-top:0;">🔒 보안 리포트</h2>
                <p style="font-size: 14px; color: var(--text-muted); margin-bottom: 20px;">비밀번호를 입력해야 데이터를 확인할 수 있습니다.</p>
                <input type="password" id="pwd" placeholder="비밀번호 입력" onkeypress="if(event.key === 'Enter') checkPwd()">
                <button onclick="checkPwd()">암호 해독 및 열람</button>
                <div id="error-msg" style="color: #e74c3c; font-size: 12px; margin-top: 15px; display: none;">비밀번호가 일치하지 않습니다.</div>
            </div>
        </div>

        <div id="main-content">
            <div class="header-info">
                <h1>📊 가봄 오픈채팅 리포트</h1>
                <div style="display: flex; align-items: center; gap: 15px;">
                    <button class="pdf-btn" style="margin:0; width:auto; background: #e67e22;" onclick="showTop10()">📈 최근 30일 Top 10</button>
                    <div class="meta-info" id="meta-info"></div>
                </div>
            </div>


            <div class="controls-container" style="display:flex; justify-content: flex-end; align-items: center; gap: 10px; padding: 0 10px 12px 0;">
                <span style="font-size: 12px; font-weight: 600; color: var(--primary);">정렬 기준:</span>
                <select id="sortOrder" onchange="renderTable()" style="padding: 6px 12px; border-radius:8px; border: 1px solid var(--border); font-size: 12px; outline:none; background: white; cursor: pointer; box-shadow: 0 2px 4px rgba(0,0,0,0.02);">
                    <option value="total_desc">대화 많은 순 ↓</option>
                    <option value="last_desc">최근 대화 순 ↓</option>
                    <option value="entry_asc">입장일 순 ↑</option>
                    <option value="missing_desc">정보 누락순 ↓</option>
                    <option value="name_asc">닉네임 순</option>
                </select>
            </div>

            <div class="table-container">
                <table id="mainTable">
                    <thead>
                        <tr id="header-row"></tr>
                        <tr class="total-info-row" id="total-row"></tr>
                    </thead>
                    <tbody id="tableBody"></tbody>
                </table>
            </div>
        </div>

        <!-- Top 10 모달 -->
        <div id="top10-modal" class="modal">
            <div class="modal-content">
                <span class="close-modal" onclick="closeTop10()">&times;</span>
                <h2 style="margin-top:0; color:var(--primary);">🏆 최근 30일 Top 10</h2>
                <p style="font-size:0.85em; color:var(--text-muted); margin-bottom:20px;">최근 한 달간 가장 활발하게 활동하신 분들입니다.</p>
                <div id="top10-list"></div>
            </div>
        </div>

        <script>
            const encryptedRawData = "{encrypted_data_str}";
            let decryptedData = null;

            function decrypt_data(b64, pwd) {{
                try {{
                    const binaryString = atob(b64);
                    const bytes = new Uint8Array(binaryString.length);
                    for (let i = 0; i < binaryString.length; i++) {{
                        bytes[i] = binaryString.charCodeAt(i);
                    }}
                    
                    const encoder = new TextEncoder();
                    const pwdBytes = encoder.encode(pwd);
                    
                    for (let i = 0; i < bytes.length; i++) {{
                        bytes[i] = bytes[i] ^ pwdBytes[i % pwdBytes.length];
                    }}
                    
                    const decoder = new TextDecoder('utf-8');
                    return JSON.parse(decoder.decode(bytes));
                }} catch (e) {{
                    return null;
                }}
            }}

            function checkPwd() {{
                const pwd = document.getElementById('pwd').value;
                const data = decrypt_data(encryptedRawData, pwd);
                if (data && data.active_users) {{
                    decryptedData = data;
                    document.getElementById('login-screen').style.display = 'none';
                    document.getElementById('main-content').style.display = 'flex';
                    initReport();
                }} else {{
                    document.getElementById('error-msg').style.display = 'block';
                }}
            }}

            function initReport() {{
                document.getElementById('meta-info').innerText = `* 개인 리포트 | ${{decryptedData.generation_time}} | ${{Object.keys(decryptedData.active_users).length}}명`;
                
                renderTable();
            }}

            function showTop10() {{
                const listDiv = document.getElementById('top10-list');
                listDiv.innerHTML = decryptedData.top_10_30d.map((item, idx) => `
                    <div class="top10-item">
                        <span class="top10-rank">${{idx + 1}}</span>
                        <span class="top10-nick">${{item.nick}}</span>
                        <span class="top10-count">${{item.count}}회</span>
                    </div>
                `).join('');
                document.getElementById('top10-modal').style.display = 'flex';
            }}

            function closeTop10() {{
                document.getElementById('top10-modal').style.display = 'none';
            }}

            function getBgColor(count, maxCount) {{
                if (count === 0) return "";
                if (maxCount === 0) return "background-color: #fffde7;";
                const ratio = count / maxCount;
                const lightness = 95 - (ratio * 15);
                return `background-color: hsl(54, 100%, ${{lightness}}%);`;
            }}

            function renderTable() {{
                const {{ active_users, sorted_months, monthly_totals, base_name_counts, nick_to_base }} = decryptedData;
                const order = document.getElementById('sortOrder').value;
                
                // 헤더 생성
                const header = document.getElementById('header-row');
                header.innerHTML = `
                    <th class="sticky-0">No.</th>
                    <th class="sticky-1">닉네임</th>
                    <th class="sticky-2">입장일</th>
                    <th class="sticky-3">마지막 대화일</th>
                    <th class="sticky-4">누락 항목</th>
                    <th class="sticky-5">인사</th>
                    ${{sorted_months.map(m => `<th>${{m.substring(2)}}</th>`).join('')}}
                    <th class="grand-total">총계</th>
                `;

                // 총합 행 생성
                const totalRow = document.getElementById('total-row');
                totalRow.innerHTML = `
                    <th class="sticky-0">-</th>
                    <th class="sticky-1" style="text-align:center;">월별 총합 (${{Object.keys(active_users).length}}명)</th>
                    <th class="sticky-2">-</th>
                    <th class="sticky-3">-</th>
                    <th class="sticky-4">-</th>
                    <th class="sticky-5">-</th>
                    ${{sorted_months.map(m => `<th>${{monthly_totals[m] || 0}}</th>`).join('')}}
                    <th class="grand-total">${{Object.values(monthly_totals).reduce((a, b) => a + b, 0)}}</th>
                `;

                // 데이터 정렬
                const userList = Object.entries(active_users);
                userList.sort((a, b) => {{
                    const [nickA, dataA] = a;
                    const [nickB, dataB] = b;
                    if (order === 'total_desc') return dataB.total_count - dataA.total_count;
                    if (order === 'last_desc') return (dataB.last_activity_date || "").localeCompare(dataA.last_activity_date || "");
                    if (order === 'entry_asc') return (dataA.entry_date || "9999").localeCompare(dataB.entry_date || "9999");
                    if (order === 'missing_desc') return dataB.info_missing.length - dataA.info_missing.length;
                    if (order === 'name_asc') return nickA.localeCompare(nickB);
                    return 0;
                }});

                const tbody = document.getElementById('tableBody');
                tbody.innerHTML = userList.map(([nick, data], i) => {{
                    const isDuplicate = base_name_counts[nick_to_base[nick]] > 1;
                    return `
                        <tr>
                            <td class="sticky-0">${{i + 1}}</td>
                            <td class="sticky-1 ${{isDuplicate ? 'duplicate-nick' : ''}}">${{nick}}</td>
                            <td class="sticky-2">${{data.entry_date || '-'}}</td>
                            <td class="sticky-3">${{data.last_activity_date || '-'}}</td>
                            <td class="sticky-4 missing-text">${{data.info_missing.join(', ') || '-'}}</td>
                            <td class="sticky-5"><span class="badge-${{data.greeted ? 'o' : 'x'}}">${{data.greeted ? 'O' : 'X'}}</span></td>
                            ${{sorted_months.map(m => {{
                                const count = data.monthly_counts[m] || 0;
                                const maxCount = Math.max(...Object.values(data.monthly_counts), 0);
                                return `<td style="${{getBgColor(count, maxCount)}}">${{count || ""}}</td>`;
                            }}).join('')}}
                            <td class="grand-total">${{data.total_count}}</td>
                        </tr>
                    `;
                }}).join('');
            }}
        </script>
    </body>
    </html>
    """
    
    with open(output_report_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    print(f"Report consolidation completed (Security Mode): {output_report_path}")

if __name__ == "__main__":
    analyze()
