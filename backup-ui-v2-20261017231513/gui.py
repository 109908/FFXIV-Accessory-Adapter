"""Tkinter GUI for the generic Penumbra staging-PMP workflow."""
from __future__ import annotations
import json
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
from .penumbra_package import (
    PackageBuildError,
    build_pending_option_pmp,
    inspect_pmp_option_groups,
)
from .workflow import adapt_head_using_references
from .ui_localization import translate_ui_text
from .ui_guide import show_guide_dialog

APP_TITLE = "FF14 饰品适配器 · 第一版"

# File-picker filters intentionally omit an 'All files' option.
MODEL_FILETYPES = (("glTF/GLB 模型 (*.gltf; *.glb)", "*.gltf *.glb"), ("独立 glTF JSON (*.gltf)", "*.gltf"), ("二进制 GLB (*.glb)", "*.glb"))
GLB_FILETYPES = MODEL_FILETYPES
GLB_OUTPUT_FILETYPES = (("二进制 GLB 输出 (*.glb)", "*.glb"),)
EQUIPMENT_MODEL_FILETYPES = (("glTF/GLB 模型 (*.gltf; *.glb)", "*.gltf *.glb"), ("独立 glTF JSON (*.gltf)", "*.gltf"), ("二进制 GLB (*.glb)", "*.glb"), ("FFXIV MDL 模型 (*.mdl)", "*.mdl"))
MDL_FILETYPES = (("MDL 模型 (*.mdl)", "*.mdl"),)
PMP_FILETYPES = (("Penumbra PMP (*.pmp)", "*.pmp"),)
ZIP_FILETYPES = (("ZIP 压缩包 (*.zip)", "*.zip"),)  # kept for legacy tests/tools; not required by the generic workflow


class AdapterApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(APP_TITLE)
        self.language = 'zh'
        self.language_var = tk.StringVar(value='简体中文')
        self.geometry("1080x880")
        self.minsize(930, 780)
        self.configure(padx=12, pady=10)
        self.vars = {k: tk.StringVar() for k in (
            'source_mod_glb', 'source_equipment_model', 'source_body_glb',
            'target_equipment_model', 'target_body_glb', 'output_glb',
            'adapted_glb', 'mother_pmp', 'target_base_mdl', 'output_pmp')}
        self.race_var = tk.StringVar(value='Elezen Female')
        # Default is safe: don't silently erase an existing option's mappings.
        self.replace_var = tk.BooleanVar(value=False)
        self.group_var = tk.StringVar(value='')
        self.group_choice_map: dict[str, str] = {}
        self._status_zh = '步骤 1：选择原 Mod 装备模型、源种族参考模型、目标种族模型及输出路径。'
        self.status_var = tk.StringVar(value=self._status_zh)
        self._build_ui()

    def _build_ui(self):
        header = ttk.Frame(self); header.pack(fill='x', pady=(0, 10))
        header_top = ttk.Frame(header); header_top.pack(fill='x')
        ttk.Label(header_top, text='FF14 饰品适配器', font=('Microsoft YaHei UI', 18, 'bold')).pack(side='left', anchor='w')
        language_box = ttk.Frame(header_top); language_box.pack(side='right')
        ttk.Label(language_box, text='语言 / Language').pack(side='left', padx=(0, 6))
        language_combo = ttk.Combobox(language_box, textvariable=self.language_var, values=('简体中文', 'English'), state='readonly', width=12)
        language_combo.pack(side='left')
        language_combo.bind('<<ComboboxSelected>>', self._on_language_change)
        ttk.Label(header, text='第一版聚焦头部耳朵适配；PMP 构建不依赖成功案例，最终资源绑定由使用者在 Penumbra 中完成。', foreground='#555').pack(anchor='w', pady=(3, 0))

        self.tabs = ttk.Notebook(self); self.tabs.pack(fill='x', expand=False)
        tab1 = ttk.Frame(self.tabs, padding=10); self.tabs.add(tab1, text='步骤 1 · 生成适配 GLB')
        self._row(tab1, 0, '原 Mod 修改后的装备模型（glTF/GLB）', 'source_mod_glb', self._browse_glb_source)
        self._row(tab1, 1, '原种族原版装备模型（glTF/GLB/MDL）', 'source_equipment_model', self._browse_source_equipment)
        ttk.Checkbutton(tab1, text='生成骨骼（当前版本暂不支持）', state='disabled').grid(row=1, column=3, sticky='w', padx=(4, 0), pady=4)
        self._row(tab1, 2, '原种族身体模型（glTF/GLB）', 'source_body_glb', self._browse_source_body)
        ttk.Checkbutton(tab1, text='生成骨骼（当前版本暂不支持）', state='disabled').grid(row=2, column=3, sticky='w', padx=(4, 0), pady=4)
        self._row(tab1, 3, '目标种族原版装备模型（glTF/GLB/MDL）', 'target_equipment_model', self._browse_target_equipment)
        self._row(tab1, 4, '目标种族身体模型（glTF/GLB）', 'target_body_glb', self._browse_target_body)
        self._row(tab1, 5, '输出适配目标种族 GLB 文件路径', 'output_glb', self._browse_output_glb)
        ttk.Button(tab1, text='检查输入并生成适配 GLB', command=self._adapt_glb).grid(row=6, column=1, sticky='w', pady=(10, 2))
        ttk.Button(tab1, text='图片指引', command=lambda: self._show_guide(1)).grid(row=6, column=2, sticky='w', padx=(8, 0), pady=(10, 2))
        ttk.Label(tab1, text='源附件和身体模型支持 .gltf/.glb；装备参考支持 .gltf/.glb/.mdl。使用 .gltf 时，请保留同目录的 .bin 和纹理文件。当前版本主要验证头部耳朵适配，并使用 j_kao 骨骼。', foreground='#555', wraplength=980).grid(row=7, column=0, columnspan=4, sticky='w', pady=(6, 0))

        tab2 = ttk.Frame(self.tabs, padding=10); self.tabs.add(tab2, text='步骤 2 · GLB + 原版 MDL 构建 PMP')
        self._row(tab2, 0, '步骤 1 生成的适配 GLB', 'adapted_glb', self._browse_adapted_glb)
        self._row(tab2, 1, '原 Mod（PMP 格式）', 'mother_pmp', self._browse_mother)
        self._row(tab2, 2, '目标种族原版装备 MDL（必需）', 'target_base_mdl', self._browse_target_base_mdl)
        ttk.Label(tab2, text='要添加选项的原有选项组').grid(row=3, column=0, sticky='w', pady=5)
        self.group_combo = ttk.Combobox(tab2, textvariable=self.group_var, state='readonly', width=72, values=())
        self.group_combo.grid(row=3, column=1, columnspan=2, sticky='ew', padx=8, pady=5)
        ttk.Label(tab2, text='选择步骤 1 的适配 GLB、原 Mod 的 PMP，以及目标种族完全原版装备 MDL。程序会创建目标种族专属模型资源和 Files 映射；不需要成功案例 ZIP。', foreground='#555', wraplength=970).grid(row=4, column=0, columnspan=3, sticky='w', pady=(0, 6))
        self._row(tab2, 5, '输出修改后 PMP 路径', 'output_pmp', self._browse_output_pmp)
        ttk.Label(tab2, text='目标种族').grid(row=6, column=0, sticky='w', pady=5)
        ttk.Combobox(tab2, textvariable=self.race_var, values=('Elezen Female', 'Elezen Male'), state='readonly', width=24).grid(row=6, column=1, sticky='w', pady=5)
        ttk.Checkbutton(tab2, text='同名选项已存在时替换（会清空该选项的资源映射）', variable=self.replace_var).grid(row=7, column=1, sticky='w', pady=5)
        ttk.Button(tab2, text='验证 GLB + MDL，构建并自检 PMP', command=self._build).grid(row=8, column=2, sticky='e', pady=(8, 2))
        ttk.Button(tab2, text='图片指引', command=lambda: self._show_guide(2)).grid(row=8, column=1, sticky='w', pady=(8, 2))
        ttk.Label(tab2, text='重要：输出 PMP 包含目标原版 MDL 占位资源和 Files 映射，但尚未包含适配后的游戏 MDL。步骤 3 需在 Penumbra 的 Models 中选中该映射模型，导入适配 GLB 并保存/导出最终 PMP。', foreground='#555', wraplength=980).grid(row=9, column=0, columnspan=3, sticky='w', pady=(8, 0))

        tab3 = ttk.Frame(self.tabs, padding=14); self.tabs.add(tab3, text='步骤 3 · Penumbra 绑定并保存')
        ttk.Button(tab3, text='图片指引', command=lambda: self._show_guide(3)).pack(anchor='e', pady=(0, 4))
        ttk.Label(tab3, text='在 Penumbra 中完成最终模型绑定', font=('Microsoft YaHei UI', 13, 'bold')).pack(anchor='w', pady=(0, 8))
        penumbra_steps = (
            '1. 导入步骤 2 生成的待绑定 PMP，并启用它。',
            '2. 勾选新增的目标种族选项（例如 Elezen Female）。',
            '3. 进入 Advanced Editing → Models，选择以目标种族和性别开头的模型文件（MDL）。',
            '4. 点击该模型的 Import/Export，导入步骤 1 生成的适配 GLB。Penumbra 会自动转换模型；记得保存修改！',
            '5. （可选）重新导出 PMP，作为新的模组重新导入 Penumbra。',
        )
        for line in penumbra_steps:
            ttk.Label(tab3, text=line, wraplength=970).pack(anchor='w', pady=4)
        ttk.Label(tab3, text='注意：待绑定 PMP 先通过 Penumbra 的模组导入功能导入；Import/Export 中应导入适配 GLB，而不是再次导入 PMP。保存后可选重新导出最终 PMP。', foreground='#555', wraplength=980).pack(anchor='w', pady=(10, 0))

        log_frame = ttk.LabelFrame(self, text='运行日志 / 自检报告', padding=8); log_frame.pack(fill='both', expand=True, pady=(10, 0))
        self.log = tk.Text(log_frame, height=14, wrap='word', font=('Consolas', 9))
        scrollbar = ttk.Scrollbar(log_frame, orient='vertical', command=self.log.yview)
        self.log.configure(yscrollcommand=scrollbar.set)
        self.log.pack(side='left', fill='both', expand=True); scrollbar.pack(side='right', fill='y')
        ttk.Label(self, textvariable=self.status_var, anchor='w', relief='sunken', padding=(6, 5)).pack(fill='x', pady=(8, 0))
        self._initial_log_zh = '已就绪。\n步骤 1：生成适配 GLB。\n步骤 2：选择适配 GLB、原 Mod PMP 和目标种族原版 MDL，创建带有实际模型映射的待绑定 PMP。\n步骤 3：在 Penumbra 的 Models 中选中已映射 MDL，导入 GLB，保存/导出最终 PMP。\n'
        self._initial_log_display = self._t(self._initial_log_zh)
        self._log(self._initial_log_display)
        self._capture_ui_texts()

    def _walk_widgets(self, parent):
        for child in parent.winfo_children():
            yield child
            yield from self._walk_widgets(child)

    def _capture_ui_texts(self):
        # Keep the original Chinese labels so switching languages never loses widget state.
        self._zh_widget_text = {}
        for widget in self._walk_widgets(self):
            if isinstance(widget, (ttk.Entry, ttk.Combobox, tk.Text)):
                continue
            try:
                text = widget.cget('text')
            except tk.TclError:
                continue
            if isinstance(text, str) and text:
                self._zh_widget_text[widget] = text
        self._zh_tab_text = {
            tab_id: self.tabs.tab(tab_id, 'text') for tab_id in self.tabs.tabs()
        }

    def _t(self, text):
        return translate_ui_text(text, self.language)

    def _on_language_change(self, _event=None):
        self.language = 'en' if self.language_var.get() == 'English' else 'zh'
        self._apply_language()

    def _apply_language(self):
        for widget, chinese_text in list(self._zh_widget_text.items()):
            try:
                widget.configure(text=translate_ui_text(chinese_text, self.language))
            except tk.TclError:
                pass
        for tab_id, chinese_text in self._zh_tab_text.items():
            try:
                self.tabs.tab(tab_id, text=translate_ui_text(chinese_text, self.language))
            except tk.TclError:
                pass
        self.title(translate_ui_text(APP_TITLE, self.language))
        self.status_var.set(translate_ui_text(self._status_zh, self.language))
        # Translate the startup hint only while it is still the entire log; preserve later diagnostics.
        if self.log.get('1.0', 'end-1c') == self._initial_log_display:
            self.log.delete('1.0', 'end')
            self._initial_log_display = translate_ui_text(self._initial_log_zh, self.language)
            self._log(self._initial_log_display)

    def _set_status(self, chinese_text, english_text=None):
        self._status_zh = chinese_text
        self.status_var.set(english_text if self.language == 'en' and english_text else translate_ui_text(chinese_text, self.language))

    def _show_guide(self, step):
        show_guide_dialog(self, step=step, language=self.language)

    def _row(self, parent, row, label, key, browse):
        ttk.Label(parent, text=label, width=32, wraplength=245).grid(row=row, column=0, sticky='w', pady=4)
        ttk.Entry(parent, textvariable=self.vars[key]).grid(row=row, column=1, sticky='ew', padx=8, pady=4)
        ttk.Button(parent, text='浏览…', command=browse, width=10).grid(row=row, column=2, pady=4)
        parent.columnconfigure(1, weight=1)

    def _choose(self, key, title, filetypes, save=False):
        localized_filetypes = tuple((self._t(label), pattern) for label, pattern in filetypes)
        if save:
            p = filedialog.asksaveasfilename(title=self._t(title), defaultextension=filetypes[0][1].replace('*', ''), filetypes=localized_filetypes)
        else:
            p = filedialog.askopenfilename(title=self._t(title), filetypes=localized_filetypes)
        if p:
            self.vars[key].set(p)
            return Path(p)
        return None

    def _browse_glb_source(self):
        p = self._choose('source_mod_glb', '选择从 Penumbra 导出的源附件 glTF/GLB', GLB_FILETYPES)
        if p and not self.vars['output_glb'].get(): self.vars['output_glb'].set(str(p.with_name(p.stem + '_adapted.glb')))
    def _browse_source_equipment(self): self._choose('source_equipment_model', '选择源种族原版装备模型（GLB 或 MDL）', EQUIPMENT_MODEL_FILETYPES)
    def _browse_source_body(self): self._choose('source_body_glb', '选择源种族身体/骨架 glTF/GLB', GLB_FILETYPES)
    def _browse_target_equipment(self): self._choose('target_equipment_model', '选择目标种族原版装备模型（GLB 或 MDL）', EQUIPMENT_MODEL_FILETYPES)
    def _browse_target_body(self): self._choose('target_body_glb', '选择目标种族身体/骨架 glTF/GLB', GLB_FILETYPES)
    def _browse_output_glb(self): self._choose('output_glb', '保存适配 GLB', GLB_OUTPUT_FILETYPES, True)
    def _browse_adapted_glb(self): self._choose('adapted_glb', '选择步骤 1 生成的适配 GLB', GLB_OUTPUT_FILETYPES)
    def _browse_target_base_mdl(self): self._choose('target_base_mdl', '选择目标种族完全原版装备 MDL', MDL_FILETYPES)

    def _browse_mother(self):
        p = self._choose('mother_pmp', '选择原始母版 PMP', PMP_FILETYPES)
        if not p:
            return
        if not self.vars['output_pmp'].get():
            self.vars['output_pmp'].set(str(p.with_name(p.stem + ' - Adapter Staging.pmp')))
        try:
            info = inspect_pmp_option_groups(p)
            self.group_choice_map.clear()
            displays = []
            for group in info['groups']:
                options_preview = ', '.join(group['option_names'][:5])
                if len(group['option_names']) > 5:
                    options_preview += ', …'
                display = f"{group['name']}（{group['option_count']} 项：{options_preview or '空组'}）"
                self.group_choice_map[display] = group['name']
                displays.append(display)
            self.group_combo.configure(values=displays)
            self.group_var.set('')
            # Suggest an obviously head/ear-related group only when the hint is unique.
            hints = ('head', 'ear', 'werewolf', '耳', '头')
            suggested = [d for d in displays if any(h in self.group_choice_map[d].casefold() for h in hints)]
            if len(suggested) == 1:
                self.group_var.set(suggested[0])
            elif len(displays) == 1:
                self.group_var.set(displays[0])
            self._log(f"\n=== 母版选项组扫描 ===\nFileVersion: {info['file_version']}\n选项组数：{info['group_count']}\n" + '\n'.join(f"- {d}" for d in displays) + '\n')
            self._set_status(
                f"已读取母版：{info['group_count']} 个选项组；请选择与本次附件对应的组。",
                f"Loaded source PMP: {info['group_count']} option groups. Select the group for this accessory.",
            )
        except Exception as exc:
            self.group_combo.configure(values=())
            self.group_var.set('')
            self._log(f'\n[母版扫描错误] {exc}\n')
            messagebox.showerror(self._t('无法读取母版选项组'), str(exc))

    def _browse_output_pmp(self): self._choose('output_pmp', '保存待绑定 PMP', PMP_FILETYPES, True)

    def _required(self, keys):
        out = {}
        for key in keys:
            value = self.vars[key].get().strip()
            if not value: raise PackageBuildError(f'请先填写/选择：{key}')
            path = Path(value)
            if key not in ('output_glb', 'output_pmp') and not path.is_file(): raise PackageBuildError(f'文件不存在：{path}')
            out[key] = path
        return out

    def _adapt_glb(self):
        try:
            p = self._required(('source_mod_glb', 'source_equipment_model', 'source_body_glb', 'target_equipment_model', 'target_body_glb', 'output_glb'))
            for key in ('source_mod_glb', 'source_body_glb', 'target_body_glb'):
                if p[key].suffix.casefold() not in ('.glb', '.gltf'):
                    raise PackageBuildError(f"{key} 必须选择 .glb 或 .gltf 文件：{p[key].name}")
            for key in ('source_equipment_model', 'target_equipment_model'):
                if p[key].suffix.casefold() not in ('.glb', '.gltf', '.mdl'):
                    raise PackageBuildError(f"{key} 只接受 .glb、.gltf 或 .mdl 文件：{p[key].name}")
            body_name = p['target_body_glb'].name.casefold()
            expected_prefix = 'c0601' if self.race_var.get() == 'Elezen Female' else 'c0501'
            if ('c0501' in body_name or 'c0601' in body_name) and not body_name.startswith(expected_prefix):
                raise PackageBuildError(f"当前选择 {self.race_var.get()}，但目标身体文件名看起来属于另一种族：{p['target_body_glb'].name}")
            target_equip_name = p['target_equipment_model'].name.casefold()
            if ('c0501' in target_equip_name or 'c0601' in target_equip_name) and not target_equip_name.startswith(expected_prefix):
                raise PackageBuildError(f"当前选择 {self.race_var.get()}，但目标原版装备文件名看起来属于另一种族：{p['target_equipment_model'].name}")
            offset_reference = p['source_equipment_model'] if p['source_equipment_model'].suffix.casefold() in ('.glb', '.gltf') else p['source_body_glb']
            target_skeleton_reference = (p['target_equipment_model']
                if p['target_equipment_model'].suffix.casefold() in ('.glb', '.gltf')
                else p['target_body_glb'])
            result = adapt_head_using_references(
                p['source_mod_glb'], offset_reference, p['target_body_glb'], p['output_glb'],
                target_skeleton_glb=target_skeleton_reference,
            )
            result['source_equipment_model'] = str(p['source_equipment_model'].resolve())
            result['source_body_glb'] = str(p['source_body_glb'].resolve())
            result['target_equipment_model'] = str(p['target_equipment_model'].resolve())
            result['offset_reference_used'] = str(offset_reference.resolve())
            result['offset_reference_reason'] = ('源装备为 glTF/GLB，沿用已测试的源装备头部骨骼高度计算。' if p['source_equipment_model'].suffix.casefold() in ('.glb', '.gltf') else '源装备为 MDL，当前版本不能直接从 MDL 解出 j_kao 变换，已改用源身体/骨架 GLB 计算；该偏移需要额外验证。')
            result['target_equipment_usage'] = '目标装备为 GLB/GLTF 时，使用其骨架层级、关节变换和逆绑定矩阵重建输出 Skin；目标装备为 MDL 时退回使用目标身体/骨架 GLB。'
            result['target_skeleton_reference_used'] = str(target_skeleton_reference.resolve())
            report = p['output_glb'].with_suffix('.adapt-report.json')
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            self._log('\n=== GLB 适配结果 ===\n' + json.dumps(result, ensure_ascii=False, indent=2) + f'\n报告：{report}\n')
            self.vars['adapted_glb'].set(str(p['output_glb'].resolve()))
            self._set_status(
                f"GLB 已生成，自动计算偏移：{result['calculated_y_offset']:.6f}；已传递到步骤 2。",
                f"Adapted GLB generated. Calculated offset: {result['calculated_y_offset']:.6f}; passed to Step 2.",
            )
            if self.language == 'en':
                info_text = (f"File: \n{p['output_glb']}\n\nY offset: {result['calculated_y_offset']:.6f}\n\nThe active Skin was rebuilt from the target skeleton (joint hierarchy and inverse bind matrices) and the path was filled into Step 2. Verify ear placement in Penumbra/in game.")
            else:
                info_text = f"文件：\n{p['output_glb']}\n\nY 偏移：{result['calculated_y_offset']:.6f}\n\n已按目标骨架重建活动 Skin（骨骼层级与逆绑定矩阵），并自动填入步骤 2。仍需在 Penumbra/游戏内验证耳朵位置。"
            messagebox.showinfo(self._t('适配 GLB 已生成'), info_text)
        except Exception as exc:
            self._set_status('GLB 适配失败。', 'GLB adaptation failed.')
            self._log(f'\n[错误] {exc}\n'); messagebox.showerror(self._t('适配失败'), str(exc))

    def _build(self):
        try:
            p = self._required(('adapted_glb', 'mother_pmp', 'target_base_mdl', 'output_pmp'))
            if p['adapted_glb'].suffix.casefold() != '.glb':
                raise PackageBuildError('步骤 2 需要步骤 1 输出的 .glb 文件。')
            selected_display = self.group_var.get().strip()
            if not selected_display or selected_display not in self.group_choice_map:
                raise PackageBuildError('请先选择原 Mod 中与本次附件对应的选项组。')
            selected_group = self.group_choice_map[selected_display]
            result = build_pending_option_pmp(
                p['mother_pmp'], p['output_pmp'], adapted_glb=p['adapted_glb'],
                target_base_mdl=p['target_base_mdl'], target_race=self.race_var.get(),
                option_group=selected_group, replace_existing=self.replace_var.get())
            report = p['output_pmp'].with_suffix('.build-report.json')
            report.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
            self._log('\n=== 待绑定 PMP 构建与回读自检 ===\n' + json.dumps(result, ensure_ascii=False, indent=2) + f'\n报告：{report}\n')
            self._set_status(
                f"带 MDL 映射的待绑定 PMP 已生成：{p['output_pmp']}",
                f"Staging PMP with MDL mapping generated: {p['output_pmp']}",
            )
            if self.language == 'en':
                info_text = (f"{p['output_pmp']}\n\nThe GLB and target original MDL passed validation. The PMP includes the target-race placeholder MDL and Files mapping.\n\nNext: in Step 3, open the mapped target MDL in Penumbra → Advanced Editing → Models, import the adapted GLB, then save/export the final mod.")
            else:
                info_text = f"{p['output_pmp']}\n\nGLB 和目标原版 MDL 检查通过；PMP 已包含目标种族 MDL 占位资源及 Files 映射。\n\n下一步：进入步骤 3，在 Penumbra → Advanced Editing → Models 中选择已映射的目标 MDL，导入适配 GLB，再保存/导出最终 Mod。"
            messagebox.showinfo(self._t('待绑定 PMP 已生成'), info_text)
        except Exception as exc:
            self._set_status('待绑定 PMP 构建失败。', 'Staging PMP build failed.'); self._log(f'\n[错误] {exc}\n'); messagebox.showerror(self._t('构建失败'), str(exc))

    def _log(self, text):
        self.log.insert('end', text); self.log.see('end')


def main():
    AdapterApp().mainloop()

if __name__ == '__main__': main()
