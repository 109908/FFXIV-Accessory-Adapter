FF14 饰品适配器 - 步骤 2 原 Mod TTMP2 导入补丁

用途
- 步骤 2「原始母版」文件选择器同时接受 .pmp 和 .ttmp2。
- 选择 TTMP2 后，读取 TTMPL.mpl 和 TTMPD.mpd，生成内部临时 PMP 形态包。
- 将 TTMP2 的组/选项、原始游戏资源路径映射以及对应资源字节保留下来。
- 选项组下拉框继续使用现有流程；原始 TTMP2 文件路径仍显示在界面中。
- 转换缓存放在原文件同目录的 .ff14_adapter_cache 文件夹。

安装
1. 先关闭 EXE，并备份项目。
2. 将补丁内文件按目录覆盖到项目根目录 E:\python\FF14-Accessory-Adapter-v1。
3. 运行：
   .\.venv\Scripts\python.exe -m unittest discover -s tests -v
4. 测试通过后重新构建：
   .\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm .\FF14-Accessory-Adapter.spec

重要限制
- 本补丁实现步骤 2 的 TTMP2 元数据与原始资源导入，不把 MDL 自动转换成 GLB。
- 现有 build_pending_option_pmp 仍然把新增目标模型硬编码为 e6047 / c0601e6047_met.mdl 或 c0501e6047_met.mdl。
- 因此它可用于验证 TTMP2 的导入、选项组读取和资源保留；但对 nonkie donut ears 这类原始路径为 chara/accessory/a0047/... 的饰品，不能据此认为目标种族模型路径已经正确适配。该样本要真正端到端构建，还需将构建器泛化为根据所选原始资源路径和目标种族生成对应 accessory MDL 映射。
- 转换后的 .pmp 是内部中间包；不要把它当作已验证可直接安装的最终 Mod。
