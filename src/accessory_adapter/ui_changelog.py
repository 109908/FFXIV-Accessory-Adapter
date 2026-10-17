"""Bilingual changelog dialog for the FF14 Accessory Adapter."""
from __future__ import annotations
import tkinter as tk
from tkinter import ttk

def show_changelog_dialog(parent: tk.Misc, language: str = "zh") -> None:
    is_en = language == "en"
    dialog = tk.Toplevel(parent)
    dialog.title("Changelog" if is_en else "更新日志 / Changelog")
    dialog.geometry("760x560")
    dialog.minsize(600, 440)
    dialog.transient(parent)
    outer = ttk.Frame(dialog, padding=18)
    outer.pack(fill="both", expand=True)
    ttk.Label(outer, text="更新日志 / Changelog", font=("Microsoft YaHei UI", 17, "bold"), anchor="center").pack(fill="x", pady=(0, 14))
    sections = [
        ("v1.0 · 当前版本", "支持非服装类饰品 Mod 的转换工作流。当前版本主要围绕已测试的头部耳朵样本；最终结果仍需在 Penumbra 和游戏内验证。", "v1.0 · Current release", "Supports a conversion workflow for non-clothing accessory mods. This release primarily targets the tested head/ear sample; verify the final result in Penumbra and in-game."),
        ("计划更新 · v1.1", "计划增加分步骤图片指引，帮助用户完成模型导出、文件选择和 Penumbra 绑定操作。具体内容可能随开发进度调整。", "Planned · v1.1", "Planned: add step-by-step image guides for model export, file selection, and binding in Penumbra. Details may change as development progresses."),
        ("使用教程", "可在 B 站观看相关使用教程；具体视频链接可在后续版本补充。", "Tutorial", "Related usage tutorials may be available on Bilibili. A specific video link can be added in a later version."),
    ]
    for zh_title, zh_body, en_title, en_body in sections:
        frame = ttk.LabelFrame(outer, text=en_title if is_en else zh_title, padding=(12, 8))
        frame.pack(fill="x", pady=(0, 10))
        ttk.Label(frame, text=en_body if is_en else zh_body, wraplength=680, justify="left", anchor="w").pack(fill="x", anchor="w")
        ttk.Label(frame, text=zh_body if is_en else en_body, wraplength=680, justify="left", foreground="#555555", anchor="w").pack(fill="x", anchor="w", pady=(6, 0))
    ttk.Label(outer, text="感谢使用。:)  /  Thanks for using the tool. :)", anchor="center").pack(fill="x", pady=(2, 10))
    ttk.Button(outer, text="关闭 / Close", command=dialog.destroy).pack(anchor="e")
    dialog.grab_set()
    dialog.focus_set()
