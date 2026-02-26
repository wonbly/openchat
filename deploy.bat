@echo off
echo ==============================================
echo 🚀 카톡 리포트 생성 및 GitHub 자동 배포 스크립트 🚀
echo ==============================================
echo.

echo [1/3] 파이썬 스크립트 실행하여 최신 index.html 갱신 중...
python analyze_chat.py
if %errorlevel% neq 0 (
    echo ❌ 파이썬 실행 중 오류가 발생했습니다.
    pause
    exit /b %errorlevel%
)

echo.
echo [2/3] 변경된 리포트를 Git에 추가 및 커밋 중...
git add index.html
git commit -m "Auto Update: 최신 카톡 대화 리포트 갱신"

echo.
echo [3/3] GitHub 원격 서버(main 브랜치)로 밀어올리는 중...
git push origin main
if %errorlevel% neq 0 (
    echo ❌ 업로드 중 오류가 발생했습니다. (원격 저장소 연결 확인 필요)
    pause
    exit /b %errorlevel%
)

echo.
echo ✅ 성공적으로 서버에 배포되었습니다! 웹사이트에서 확인해보세요.
pause
