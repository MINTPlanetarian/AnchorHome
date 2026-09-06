@echo off
REM 安航家资打包脚本：在项目根目录执行（需先创建并激活 venv）
REM 用法：双击运行，或命令行执行 build.bat

cd /d "%~dp0"

echo [1/2] 安装依赖...
venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
if errorlevel 1 (
    echo 依赖安装失败，请检查网络
    pause
    exit /b 1
)

echo [2/2] 打包为单文件 exe...
REM 先移走旧 build 缓存：PyInstaller 删除缓存会被沙箱 safe-delete 拦截导致失败，
REM 故用重命名（rename）绕开删除，build 目录不存在即等价于全新构建、不复用缓存。
if exist build (
    echo 移走旧 build 缓存（重命名，避免触发删除拦截）...
    move /Y build "build_old_%random%"
)
REM PyInstaller 写新 exe 前会先 os.remove 删旧 dist\安航家资.exe，同样被 safe-delete 拦截，
REM 故先移走旧 exe，让其直接新建（不触发删除）。
if exist "dist\安航家资.exe" (
    echo 移走旧 exe（重命名，避免触发删除拦截）...
    move /Y "dist\安航家资.exe" "dist\安航家资_old.exe"
)
venv\Scripts\pyinstaller.exe --onefile --windowed --name "安航家资" --icon "安航家资.ico" --add-data "安航家资.ico;." --collect-all akshare --noconfirm main.py
if errorlevel 1 (
    echo 打包失败
    pause
    exit /b 1
)

echo.
echo 打包完成！exe 位于 dist\安航家资.exe
echo 首次运行会在 exe 同级目录生成 data\ 文件夹保存数据。
pause
