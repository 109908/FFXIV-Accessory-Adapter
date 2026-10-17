"""Image-guide popups for the GUI; guide screenshots can be added later."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from pathlib import Path


GUIDE_TEXT = {
    1: {
        'zh_title': '步骤 1：生成适配 GLB',
        'en_title': 'Step 1: Generate Adapted GLB',
        'zh_body': '选择原 Mod 修改后的装备模型、源种族参考模型和身体模型、目标种族原版装备模型及身体模型，然后指定输出 GLB 路径。导出源种族原版装备模型和身体模型时，请在 Penumbra 导出界面勾选“生成骨骼”。',
        'en_body': 'Select the modified equipment model, source-race reference and body models, target-race original equipment and body models, then choose an output GLB path. When exporting the source-race equipment and body models in Penumbra, check “Generate Skeleton”.',
    },
    2: {
        'zh_title': '步骤 2：构建待绑定 PMP',
        'en_title': 'Step 2: Build Staging PMP',
        'zh_body': '选择步骤 1 输出的适配 GLB、原 Mod 的 PMP、目标种族完全原版装备 MDL，并指定输出 PMP 路径。',
        'en_body': 'Select the adapted GLB from Step 1, the original mod PMP, and the completely original equipment MDL for the target race. Then choose an output PMP path.',
    },
    3: {
        'zh_title': '步骤 3：在 Penumbra 中完成绑定',
        'en_title': 'Step 3: Finish Binding in Penumbra',
        'zh_body': '导入并启用待绑定 PMP，选择新增的目标种族选项，在 Advanced Editing → Models 中打开已映射的 MDL，再通过 Import/Export 导入适配 GLB并保存。',
        'en_body': 'Import and enable the staging PMP, select the new target-race option, open the mapped MDL in Advanced Editing → Models, import the adapted GLB through Import/Export, and save.',
    },
}


def show_guide_dialog(parent: tk.Misc, step: int, language: str = 'zh') -> None:
    """Open a guide popup and display stepN.png if the user has supplied it."""
    info = GUIDE_TEXT.get(step, GUIDE_TEXT[1])
    is_english = language == 'en'
    dialog = tk.Toplevel(parent)
    dialog.title(info['en_title'] if is_english else info['zh_title'])
    dialog.geometry('900x680')
    dialog.minsize(600, 420)
    dialog.transient(parent)

    outer = ttk.Frame(dialog, padding=12)
    outer.pack(fill='both', expand=True)
    ttk.Label(
        outer,
        text=info['en_body'] if is_english else info['zh_body'],
        wraplength=850,
        justify='left',
    ).pack(fill='x', anchor='w', pady=(0, 10))

    image_frame = ttk.LabelFrame(
        outer,
        text='Guide Image' if is_english else '图片指引',
        padding=8,
    )
    image_frame.pack(fill='both', expand=True)
    image_path = Path(__file__).resolve().parent / 'guide_images' / f'step{step}.png'

    if image_path.is_file():
        try:
            image = tk.PhotoImage(file=str(image_path))
            canvas = tk.Canvas(image_frame, highlightthickness=0)
            x_scroll = ttk.Scrollbar(image_frame, orient='horizontal', command=canvas.xview)
            y_scroll = ttk.Scrollbar(image_frame, orient='vertical', command=canvas.yview)
            canvas.configure(xscrollcommand=x_scroll.set, yscrollcommand=y_scroll.set)
            canvas.grid(row=0, column=0, sticky='nsew')
            y_scroll.grid(row=0, column=1, sticky='ns')
            x_scroll.grid(row=1, column=0, sticky='ew')
            image_frame.rowconfigure(0, weight=1)
            image_frame.columnconfigure(0, weight=1)
            canvas.create_image(0, 0, image=image, anchor='nw')
            canvas.configure(scrollregion=(0, 0, image.width(), image.height()))
            # Keep the Tk image alive for the lifetime of this popup.
            dialog._guide_image = image  # type: ignore[attr-defined]
        except tk.TclError as exc:
            ttk.Label(
                image_frame,
                text=(f'Could not load guide image: {exc}' if is_english else f'无法读取指引图片：{exc}'),
                wraplength=800,
            ).pack(fill='both', expand=True, padx=10, pady=10)
    else:
        placeholder = (
            f'Image placeholder: add your screenshot as\n{image_path.name}\n\nExpected location:\n{image_path.parent}'
            if is_english else
            f'图片占位区：后续请将截图命名为\n{image_path.name}\n\n放置目录：\n{image_path.parent}'
        )
        ttk.Label(
            image_frame,
            text=placeholder,
            anchor='center',
            justify='center',
            wraplength=800,
        ).pack(fill='both', expand=True, padx=12, pady=12)

    ttk.Button(outer, text='Close' if is_english else '关闭', command=dialog.destroy).pack(anchor='e', pady=(10, 0))
    dialog.grab_set()
    dialog.focus_set()
