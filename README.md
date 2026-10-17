# FF14 饰品适配器 v1.0（头部耳朵测试版）

第一版聚焦已测试的 Elezen 头部耳朵适配。项目分成三个阶段：

1. **GLB 适配**：读取源 Mod 附件 GLB、源种族原版装备模型（GLB/MDL）、源种族身体/骨架 GLB、目标种族原版装备模型（GLB/MDL）、目标身体/骨架 GLB；优先使用源原版装备 GLB 的 `j_kao` 世界 Y 与目标身体/骨架 GLB 计算高度差，并输出适配 GLB。源/目标装备文件是必需输入：源装备用于确定偏移参考，目标装备作为后续 Penumbra 导入/替换基准。
2. **构建待绑定 PMP**：程序需要目标种族完全原版装备 MDL，将其放入目标种族专属内部路径并创建游戏路径到该 MDL 的 Files 映射。随后用户在 Penumbra 的 Models 中选中这个已映射模型并导入适配 GLB；Penumbra 将模型写回为游戏 MDL。

**重要边界：** 本程序不编译 GLB → MDL，也不声称能通过静态检查替代游戏内测试。第一版只支持 Elezen Female/Male 的 e6047 头部装备测试流程。手、背、尾巴以及任意种族适配暂不支持。

## 在 Windows 上运行 GUI

建议 Python 3.11–3.13，解压项目到普通路径，例如 `E:\python\FF14-Accessory-Adapter-v1`。

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
.\.venv\Scripts\python.exe run_gui.py
```

当前核心模块与 GUI 使用 Python 标准库，无需安装 GLB/PMP 相关第三方库。

## GUI 工作流

### 步骤 1：生成适配 GLB

- 源 Mod 附件模型：通常先在 Penumbra 的 `Advanced Editing → Models` 里选中实际使用的附件模型，执行 `Export to glTF`。源附件可选 `.gltf` 或 `.glb`。
- 源种族原版装备模型：例如原版人狼耳朵模型，可选择 `.gltf`、`.glb` 或 `.mdl`。
- 源种族身体/骨架、目标种族身体/骨架：选择对应的 `.gltf` 或 `.glb`。
- 目标种族原版装备模型：用于确认目标装备资源，选择 `.gltf`、`.glb` 或 `.mdl`。
- 选择输出路径，点击“检查输入并生成适配 GLB”。

原型默认处理 mesh 0，并把所选网格重新绑定到 `j_kao`。正式生成时会优先使用目标装备 GLB/GLTF 的骨架；将目标 Skin 的 joints 顺序、节点层级/局部变换及 inverseBindMatrices 转移到输出 GLB，再按源/目标头部骨骼世界 Y 计算顶点偏移。输出只保留活动场景可达的目标骨架和所选网格，防止未选中的第二网格被导入。若目标装备只提供 MDL，则退回使用目标身体/骨架 GLB；这时必须确认二者骨架一致。此流程仍是当前耳朵样本的专用流程，不是通用任意饰品重定向算法。

### 步骤 2：构建待绑定 PMP（通用，不依赖成功案例）

- 选择使用者自己的原始母版 PMP、步骤 1 的适配 GLB、目标种族完全原版装备 MDL、输出 PMP 路径、目标种族，以及要添加选项的原有选项组。
- 选择母版后，程序会扫描并列出其选项组及现有选项名称。请选中与本次附件对应的组；不要随便把选项加到无关组。
- 不需要成功案例 ZIP，也不需要预先导出的“修改后 MDL”；但必须提供目标种族完全原版装备 MDL，作为待绑定包的占位模型。
- 程序会保留母版其余文件和选项，在所选组里新增目标种族选项；把目标原版 MDL 放入 `elezen female/...` 或 `elezen male/...` 的种族专属目录，并添加游戏模型路径到该 MDL 的 `Files` 映射。`FileSwaps`、`Manipulations` 不继承其他种族配置。
- 若同名选项已经存在，默认拒绝覆盖。只有明确勾选“同名选项已存在时替换”才会替换该选项，并清空它原有的资源映射。
- 目前支持 Penumbra PMP 的 FileVersion 3（独立 `group_*.json`）和 FileVersion 4（`meta.json` 内的 `Groups`）。其他结构会报错，不会猜测修改。

### 输出 PMP 后的 Penumbra 手动步骤

1. 将生成的待绑定 PMP 导入 Penumbra。
2. 进入新建的目标种族选项，打开 `Advanced Editing → Models`。
3. 选择已由 `Files` 映射注册的目标模型 `chara/equipment/e6047/model/c0601e6047_met.mdl`（女精）或 `c0501e6047_met.mdl`（男精）。
4. 展开模型的 `Import/Export`，导入步骤 1 的适配 GLB。Penumbra 会把 glTF 内容写入当前模型资源；GLB 本身不是游戏资源格式。
5. 保存/导出最终 PMP，重新导入检查 MDL 文件是否更新，并在游戏内验证目标选项、耳朵位置和材质。

待绑定 PMP 包含目标种族原版 MDL 占位资源和正确的游戏路径映射，但还不包含导入适配 GLB 后生成的最终 MDL。成功案例 ZIP 只用于开发时对照，不是使用者的必需输入。结构检查通过不等于游戏内效果已验证。

## 自检/命令行

扫描母版有哪些选项组：

```powershell
.\.venv\Scripts\python.exe build_pmp.py --mother "E:\mods\My Mod.pmp" --list-groups
```

注意：`--list-groups` 只扫描母版，不需要指定输出路径。

构建待绑定 PMP（组名需与扫描结果完全一致）：

```powershell
.\.venv\Scripts\python.exe build_pmp.py --mother "E:\mods\My Mod.pmp" --group "Ears" --output "E:\mods\My Mod - Adapter Staging.pmp" --race "Elezen Female"
```

如果确实要替换已存在的同名目标选项，再显式添加 `--replace-existing`。该操作会清空该目标选项现有的文件映射。

## 生成 Windows EXE

在 Windows 项目目录内执行（首次需联网安装 PyInstaller）：

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
.\.venv\Scripts\python.exe -m PyInstaller --clean --noconfirm FF14-Accessory-Adapter.spec
```

生成位置：`dist\FF14-Accessory-Adapter.exe`。如果杀毒软件对单文件打包临时解压有误报，可改用 `--onedir` 构建；不要把用户输入的 PMP/MDL 写进 EXE 本身。

## 本次样本对照结果

- 原始 PMP：FileVersion 3、9 个组、40 个选项。
- 成功男精 V3 ZIP：FileVersion 4、9 个组、41 个选项。
- 两份包中 Lalafell 与 Viera 的 4 条文件映射相同；但 Manipulations 结构不同（原 PMP 每项 40 条，V3 ZIP 每项 3 条），所以程序保留母版已有配置，并让新 Elezen 选项不带旧 Viera 的 Manipulations。
- 男精 V3 新增项有 3 条映射：两个材质路径映射与一个目标种族 MDL 映射。程序按此模式构建女精/男精选项。

## 已知限制

- GLB 原型使用固定网格索引 0，并把所选网格全部重新绑定到 `j_kao`；这只适用于当前已测试的耳朵样例。
- 输出会重建目标 Skin 的 joints 顺序、目标骨骼层级/局部变换和 inverseBindMatrices；这修复了旧版本只改 JOINTS_0、仍保留源骨架矩阵的问题。
- 高度差来自源/目标参考骨架的 `j_kao` 世界 Y；必须在 Penumbra 与游戏中验证最终位置。结构测试通过不等于游戏内表现已验证。
- 构建器只检查 PMP 结构、资源映射路径和输入 MDL 的字节完整性；不解析 MDL 内部几何，也不能证明它含有预期耳朵网格。
- 当前 Linux 开发环境不能直接产出并验证 Windows EXE；请按上述命令在 Windows 生成。


## 从 Penumbra 获取模型（重要）

原始 Mod 通常以 `.pmp` 或 Mod 文件夹提供，并不一定附带独立 GLB。请先在 Penumbra 中打开原 Mod：

1. `Advanced Editing` → `Models`。
2. 在模型列表中选中实际使用的附件模型。
3. 使用 `Export to glTF` 导出到一个单独的素材目录。
4. 如果得到 `.gltf`，请将同目录的 `.bin` 与纹理文件全部保留；本工具会读取同目录的本地配套文件，并将几何缓冲与外部图片打包进输出 GLB。
5. 回到本工具，源附件和身体/骨架可选择 `.gltf` 或 `.glb`；源/目标装备参考可选择 `.gltf`、`.glb` 或 `.mdl`。

当前版本对独立 `.gltf` 的限制：只支持一个本地或 data URI buffer；不访问网络 URL；如果导出结果包含多个 buffer 或外部资源缺失，程序会明确报错。`.mdl` 仅作为装备参考输入，当前不会从 MDL 直接解析网格或骨骼变换。最终适配 GLB 仍需在 Penumbra/兼容模型工具中导入目标装备并生成 MDL。


## 三步工作流（当前版本）

1. **生成适配 GLB**：在 Penumbra 导出源附件和参考模型，在本程序中生成目标种族适配 GLB。
2. **验证 GLB 后构建待绑定 PMP**：必须选择步骤 1 生成的 `.glb`，再选择使用者自己的母版 PMP 和对应选项组。程序检查 GLB 文件头并在报告中记录路径、大小、SHA-256，然后根据母版自身的 FileVersion 3/4 配置结构创建待绑定 PMP。成功案例 ZIP 不是普通用户的必需输入。
3. **在 Penumbra 中完成绑定**：导入待绑定 PMP，进入目标种族选项，选择目标游戏装备资源路径，导入适配 GLB，让 Penumbra/兼容工具生成游戏模型，然后保存/导出最终 PMP。

注意：原始 GLB 是第二步的必需输入，但不会被当作游戏 MDL 资源直接写进 `Files` 映射。第二步生成的 PMP 仍是待绑定工作包，最终模型映射由第三步在 Penumbra 中完成。

## 更新日志 / Changelog

### v1.0
- 支持非服装类饰品 Mod 的转换工作流。当前版本主要围绕已测试的头部耳朵样本；最终结果仍需在 Penumbra 和游戏内验证。
- 步骤 2 支持选择 `.pmp` 或 `.ttmp2` 作为原 Mod 输入。

### 计划更新：v1.1
- 计划增加分步骤图片指引。
- 可在 B 站观看相关使用教程；具体视频链接可在后续补充。

## 重要提示：静态测试与物理效果

本软件目前仅针对静态模型进行测试。含有物理效果（如摆动、碰撞或动态骨骼）的 Mod 尚未充分验证，最终效果不确定，可能出现穿模、抖动或其他异常。请务必在游戏内自行测试。

This software has only been tested with static models so far. Mods with physics effects (such as swinging, collisions, or dynamic bones) have not been fully verified. Final results are uncertain and may include clipping, jitter, or other issues. Please test them in-game.

## 使用限制与许可说明

本项目公开源代码并免费提供，禁止任何形式的商业使用。该限制与通常意义上的 OSI 开源许可证不兼容，因此当前暂不附带标准开源许可证；请勿将本项目标注为 MIT、Apache-2.0 或 GPL 等通常允许商业使用的许可证。

The source code is public and the software is free, but commercial use is prohibited. This restriction is incompatible with the usual OSI definition of open source. No standard open-source license is included yet; do not label this project as MIT, Apache-2.0, GPL, or another license that normally permits commercial use.
