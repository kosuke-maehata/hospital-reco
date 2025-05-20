@echo off
REM → バッチを置いたフォルダへ移動
cd /d "%~dp0"

REM → 仮想環境を有効化
call ".venv\Scripts\activate.bat"

REM → Streamlit アプリを起動（ブラウザ自動オープン）
python -m streamlit run "%~dp0app.py" --server.headless=false

REM → アプリ終了後もウィンドウを残す
pause
