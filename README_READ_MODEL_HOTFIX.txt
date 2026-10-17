FF14 Accessory Adapter - read_model import hotfix

原因：当前 head.py 导入 accessory_adapter.model_io.read_model，但部分旧项目中的 model_io.py 没有 read_model，因此 EXE 启动时报 ImportError。

应用方法：
1. 关闭正在运行的 FF14-Accessory-Adapter.exe。
2. 将压缩包内 src/accessory_adapter/model_io.py 覆盖到项目同路径。
3. 在项目根目录运行：
   .\.venv\Scripts\python.exe -c "from accessory_adapter.model_io import read_model; print('read_model import OK')"
   如果提示找不到 accessory_adapter，请运行下面这一条（推荐）：
   .\.venv\Scripts\python.exe -c "import sys; sys.path.insert(0, 'src'); from accessory_adapter.model_io import read_model; print('read_model import OK')"
4. 运行测试：
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
5. 通过后重新打包：
   .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm .\FF14-Accessory-Adapter.spec

注意：这份补丁只修复启动时缺少 read_model 的导入错误，不会自动修复其他代码或保证游戏内效果。
