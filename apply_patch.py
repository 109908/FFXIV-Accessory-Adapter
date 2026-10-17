from __future__ import annotations
import argparse
import shutil
from datetime import datetime
from pathlib import Path

FILES = (
    Path('src/accessory_adapter/gui.py'),
    Path('src/accessory_adapter/startup_notice.py'),
    Path('src/accessory_adapter/ui_changelog.py'),
    Path('src/accessory_adapter/ui_localization.py'),
)

def main() -> None:
    parser = argparse.ArgumentParser(description='Apply UI/changelog/notice patch while preserving TTMP2 support.')
    parser.add_argument('project_root', help='Path to FF14-Accessory-Adapter-v1 project')
    args = parser.parse_args()
    root = Path(args.project_root).resolve()
    patch_root = Path(__file__).resolve().parent
    gui_path = root / 'src/accessory_adapter/gui.py'
    if not gui_path.is_file():
        raise SystemExit(f'Project GUI not found: {gui_path}')
    current_gui = gui_path.read_text(encoding='utf-8')
    if 'convert_ttmp2_to_pmp' not in current_gui or '*.ttmp2' not in current_gui:
        raise SystemExit('STOP: current GUI does not show the expected TTMP2 support. No files changed.')
    patch_gui = (patch_root / FILES[0]).read_text(encoding='utf-8')
    if 'convert_ttmp2_to_pmp' not in patch_gui or '*.ttmp2' not in patch_gui:
        raise SystemExit('Patch validation failed: packaged GUI does not contain TTMP2 support.')
    required = [root / FILES[0], root / FILES[1], root / FILES[3], root / 'src/accessory_adapter/ui_guide.py', root / 'README.md', root / '.gitignore'] + [patch_root / p for p in FILES]
    missing = [str(p) for p in required if not p.is_file()]
    if missing:
        raise SystemExit('Missing files; no changes made:\n' + '\n'.join(missing))

    import py_compile
    for rel in FILES:
        source = (patch_root / rel).read_text(encoding='utf-8')
        compile(source, str(rel), 'exec')

    readme_path = root / 'README.md'
    gitignore_path = root / '.gitignore'
    readme_append = patch_root / 'README_APPEND.md'
    gitignore_append = patch_root / 'GITIGNORE_APPEND.txt'
    if not readme_append.is_file() or not gitignore_append.is_file():
        raise SystemExit('Patch is incomplete; README_APPEND.md or GITIGNORE_APPEND.txt is missing.')

    originals = {root / rel: (root / rel).read_bytes() for rel in FILES if (root / rel).is_file()}
    originals[readme_path] = readme_path.read_bytes()
    originals[gitignore_path] = gitignore_path.read_bytes()
    backup = root / '.patch_backups' / ('ui-changelog-notice-' + datetime.now().strftime('%Y%m%d-%H%M%S'))
    backup.mkdir(parents=True, exist_ok=False)
    for path, data in originals.items():
        target = backup / path.relative_to(root)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)

    try:
        for rel in FILES:
            shutil.copy2(patch_root / rel, root / rel)
        readme = readme_path.read_text(encoding='utf-8')
        if '## 更新日志 / Changelog' not in readme:
            readme_path.write_text(readme.rstrip() + '\n\n' + readme_append.read_text(encoding='utf-8').strip() + '\n', encoding='utf-8')
        gitignore = gitignore_path.read_text(encoding='utf-8')
        if '# Local environments, generated builds, backups, and user/mod assets' not in gitignore:
            gitignore_path.write_text(gitignore.rstrip() + '\n' + gitignore_append.read_text(encoding='utf-8').strip() + '\n', encoding='utf-8')
        for rel in FILES:
            py_compile.compile(str(root / rel), doraise=True)
    except Exception:
        for path, data in originals.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        new_changelog = root / 'src/accessory_adapter/ui_changelog.py'
        if new_changelog not in originals and new_changelog.exists():
            new_changelog.unlink()
        raise

    final_gui = gui_path.read_text(encoding='utf-8')
    assert 'convert_ttmp2_to_pmp' in final_gui and '*.ttmp2' in final_gui
    assert '更新日志 / Changelog' in final_gui and 'show_startup_notice(app' in final_gui
    print('Patch applied. TTMP2 support is present in the resulting GUI.')
    print('Backup folder:', backup)
    print('Next: run .\\build_exe_windows.ps1 from the project root to test and rebuild the EXE.')

if __name__ == '__main__':
    main()
