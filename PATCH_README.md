# FF14 饰品适配器 UI + 更新日志 + 使用须知补丁

本补丁基于你上传的最新项目源代码制作，已保留 `.ttmp2` 输入和转换逻辑。

## 一键应用并重新打包 EXE（Windows）

1. 将此 ZIP 解压到单独目录，不要覆盖项目文件夹。
2. 打开 PowerShell，运行：

```powershell
powershell -ExecutionPolicy Bypass -File "补丁解压目录\apply_and_rebuild.ps1" -ProjectRoot "E:\python\FF14-Accessory-Adapter-v1"
```

把“补丁解压目录”替换为实际解压路径。

脚本会先检查现有项目 GUI 是否仍含 TTMP2 支持，再备份源文件、应用更新，并运行单元测试。只有测试通过才会用 PyInstaller 重新打包。成功后 EXE 位于：

`E:\python\FF14-Accessory-Adapter-v1\dist\FF14-Accessory-Adapter.exe`

## 本次内容

- 主界面增加语言选择、更新日志和使用须知按钮。
- 加回前端文字优化和图片指引弹窗入口（图片可之后放入 `src\accessory_adapter\guide_images\step1.png`、`step2.png`、`step3.png`）。
- 原种族装备模型和身体模型的说明改为“导出时勾选生成骨骼”。这只是导出操作提示，不会假装软件能生成骨骼。
- 更新日志显示 v1.0 已支持非服装类饰品 Mod 转换，v1.1 计划增加图片指引，并提示可在 B 站观看教程。
- 使用须知增加静态模型测试限制、物理效果未经充分验证、可能穿模/抖动的中英双语提示。
- 首次启动弹出须知；旧版已确认过须知的用户也会因须知版本变化再次看到新增说明一次。
- `.pmp` 和 `.ttmp2` 仍可作为步骤 2 的原 Mod 输入。

## 验证说明

已在打包前执行 Python 语法检查及项目单元测试。Windows EXE 必须在 Windows 上生成；本补丁内的 PowerShell 脚本会在你的电脑上执行实际打包。
