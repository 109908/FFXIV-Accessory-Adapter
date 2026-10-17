"""First-run bilingual notice dialog for the FF14 Accessory Adapter."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk

APP_DATA = Path(os.environ.get("APPDATA", str(Path.home())))
NOTICE_FLAG = APP_DATA / "FF14-Accessory-Adapter" / "notice_acknowledged.txt"
NOTICE_VERSION = "notice_v2_static_physics_warning"

NOTICE_SECTIONS = (
    (
        "关于免费与使用限制",
        "本软件免费提供，源代码公开，禁止任何形式的商业使用。",
        "About free use and restrictions",
        "This software is provided free of charge with publicly available source code. Commercial use in any form is prohibited.",
    ),
    (
        "关于代码与后续开发",
        "本项目代码由 GPT-6 模型协助生成。作者目前几乎看不懂代码，因此优化与迭代将根据实际需要进行。欢迎有经验的开发者自行修改、优化与继续开发。",
        "About the code and future development",
        "The code for this project was generated with the assistance of the GPT-6 model. The author currently has very limited coding knowledge, so updates and improvements will be made as needed. Experienced developers are welcome to modify, improve, and continue developing the project.",
    ),
    (
        "关于 Mod 使用授权",
        "请确保你已获得使用相关 Mod 及其资源文件所需的授权。本软件不提供任何游戏原版文件或 Mod 文件。",
        "About mod permissions",
        "Please ensure that you have the necessary permissions to use the relevant mods and their assets. This software does not provide any original game files or mod files.",
    ),
    (
        "关于文件处理与隐私",
        "本软件在本地电脑上处理所选文件，不会主动上传这些文件。请从可信来源获取软件，并自行做好重要文件的备份。",
        "About file processing and privacy",
        "This software processes selected files locally on your computer and does not actively upload them. Please obtain the software from a trusted source and keep backups of important files.",
    ),

    (
        "关于静态测试与物理效果",
        "本软件目前仅针对静态模型进行测试。含有物理效果（如摆动、碰撞或动态骨骼）的 Mod 尚未充分验证，最终效果不确定，可能出现穿模、抖动或其他异常。请务必在游戏内自行测试。",
        "About static testing and physics effects",
        "This software has only been tested with static models so far. Mods with physics effects (such as swinging, collisions, or dynamic bones) have not been fully verified. Final results are uncertain and may include clipping, jitter, or other issues. Please test them in-game.",
    ),
)


def _has_acknowledged() -> bool:
    try:
        return NOTICE_FLAG.is_file() and NOTICE_FLAG.read_text(encoding="utf-8").strip() == NOTICE_VERSION
    except OSError:
        return False


def _save_acknowledgement() -> None:
    try:
        NOTICE_FLAG.parent.mkdir(parents=True, exist_ok=True)
        NOTICE_FLAG.write_text(NOTICE_VERSION + "\n", encoding="utf-8")
    except OSError:
        # The notice should not prevent the app from opening if profile storage is read-only.
        pass


def show_startup_notice(parent: tk.Misc, language: str = "zh", force: bool = False, exit_on_close: bool = True) -> bool:
    """Show the bilingual notice. Acknowledgement is remembered per Windows user profile.

    Returns True when acknowledged, False when the user chooses to exit or closes the window.
    """
    del language  # The notice is intentionally bilingual in either UI language.
    if not force and _has_acknowledged():
        return True

    dialog = tk.Toplevel(parent)
    dialog.title("使用须知 / NOTICE")
    dialog.resizable(True, True)
    dialog.geometry("800x700")
    dialog.minsize(700, 600)
    dialog.configure(background="#F4F6F8")
    dialog.transient(parent)

    outer = ttk.Frame(dialog, padding=(22, 16, 22, 14))
    outer.pack(fill="both", expand=True)

    ttk.Label(
        outer,
        text="使用须知 / NOTICE",
        font=("Microsoft YaHei UI", 17, "bold"),
        anchor="center",
    ).pack(fill="x", pady=(0, 3))
    ttk.Label(
        outer,
        text="请阅读以下说明后继续使用。 / Please read the following before continuing.",
        anchor="center",
        foreground="#555555",
    ).pack(fill="x", pady=(0, 12))

    # A scrollable content region keeps the notice usable on smaller screens.
    content_shell = ttk.Frame(outer)
    content_shell.pack(fill="both", expand=True)
    canvas = tk.Canvas(content_shell, highlightthickness=0, background="#F4F6F8")
    scrollbar = ttk.Scrollbar(content_shell, orient="vertical", command=canvas.yview)
    content = ttk.Frame(canvas, padding=(4, 2, 12, 2))
    content_window = canvas.create_window((0, 0), window=content, anchor="nw")
    canvas.configure(yscrollcommand=scrollbar.set)

    def _sync_scroll_region(_event=None):
        canvas.configure(scrollregion=canvas.bbox("all"))

    def _sync_content_width(event):
        canvas.itemconfigure(content_window, width=event.width)

    content.bind("<Configure>", _sync_scroll_region)
    canvas.bind("<Configure>", _sync_content_width)
    canvas.pack(side="left", fill="both", expand=True)
    scrollbar.pack(side="right", fill="y")

    for index, (heading_zh, body_zh, heading_en, body_en) in enumerate(NOTICE_SECTIONS):
        section = ttk.Frame(content, padding=(0, 4, 0, 7))
        section.pack(fill="x", expand=True)
        ttk.Label(
            section,
            text=f"{index + 1}. {heading_zh}",
            font=("Microsoft YaHei UI", 10, "bold"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ttk.Label(
            section,
            text=body_zh,
            wraplength=730,
            justify="left",
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(2, 4))
        ttk.Label(
            section,
            text=heading_en,
            font=("Segoe UI", 9, "bold"),
            anchor="w",
        ).pack(fill="x", anchor="w")
        ttk.Label(
            section,
            text=body_en,
            wraplength=730,
            justify="left",
            foreground="#555555",
            anchor="w",
        ).pack(fill="x", anchor="w", pady=(2, 0))
        if index < len(NOTICE_SECTIONS) - 1:
            ttk.Separator(content, orient="horizontal").pack(fill="x", pady=(5, 2))

    ttk.Label(outer, text="感谢使用。:)  /  Thanks for using the tool. :)", anchor="center").pack(fill="x", pady=(10, 8))

    button_row = ttk.Frame(outer)
    button_row.pack(fill="x", pady=(2, 0))

    result = {"acknowledged": False}

    def acknowledge():
        _save_acknowledgement()
        result["acknowledged"] = True
        dialog.destroy()

    def exit_application():
        result["acknowledged"] = False
        dialog.destroy()
        try:
            parent.destroy()
        except tk.TclError:
            pass

    green_button = tk.Button(
        button_row,
        text="我已了解\nGot it",
        command=acknowledge,
        bg="#2E8B57",
        activebackground="#267349",
        fg="white",
        activeforeground="white",
        disabledforeground="white",
        relief="flat",
        borderwidth=0,
        padx=24,
        pady=8,
        font=("Microsoft YaHei UI", 10, "bold"),
        cursor="hand2",
    )
    green_button.pack(side="left", expand=True, fill="x", padx=(0, 8))

    red_button = tk.Button(
        button_row,
        text="退出软件\nExit",
        command=exit_application,
        bg="#C62828",
        activebackground="#A61F1F",
        fg="white",
        activeforeground="white",
        disabledforeground="white",
        relief="flat",
        borderwidth=0,
        padx=24,
        pady=8,
        font=("Microsoft YaHei UI", 10, "bold"),
        cursor="hand2",
    )
    red_button.pack(side="left", expand=True, fill="x", padx=(8, 0))

    # On startup, closing the notice exits the app. When reopened from the main UI,
    # the window close button only dismisses the notice.
    def close_notice():
        if exit_on_close:
            exit_application()
        else:
            dialog.destroy()

    dialog.protocol("WM_DELETE_WINDOW", close_notice)
    dialog.update_idletasks()
    try:
        x = parent.winfo_rootx() + max(0, (parent.winfo_width() - dialog.winfo_width()) // 2)
        y = parent.winfo_rooty() + max(0, (parent.winfo_height() - dialog.winfo_height()) // 2)
        dialog.geometry(f"+{x}+{y}")
    except tk.TclError:
        pass
    dialog.grab_set()
    dialog.focus_force()
    parent.wait_window(dialog)
    return result["acknowledged"]
