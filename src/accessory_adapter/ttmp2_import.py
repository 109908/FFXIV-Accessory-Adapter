"""Convert TTMP2 installer archives into a temporary FileVersion 4 PMP staging archive.

This preserves declared groups/options, resource redirections and raw resource payloads.
It does not convert MDL/MTRL/TEX to glTF, and unsupported/ambiguous manifest entries fail safely.
"""
from __future__ import annotations

import json
import re
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any


class TTMP2ImportError(ValueError):
    pass


def _safe_rel(value: str) -> str:
    value = str(value or '').replace('\\', '/').strip('/')
    p = PurePosixPath(value)
    if not value or p.is_absolute() or any(x in ('', '.', '..') for x in p.parts) or re.match(r'^[A-Za-z]:', value):
        raise TTMP2ImportError(f'无效或不安全的 TTMP2 资源路径：{value!r}')
    return '/'.join(p.parts)


def _slug(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9._ -]+', '_', str(value or '').strip()).strip(' .')
    return (value[:80] or 'unnamed')


def convert_ttmp2_to_pmp(source: str | Path, output: str | Path) -> dict[str, Any]:
    """Build a temporary classic-compatible FileVersion 4 PMP from TTMP2."""
    source, output = Path(source), Path(output)
    if source.suffix.casefold() != '.ttmp2':
        raise TTMP2ImportError('输入文件必须是 .ttmp2。')
    if source.resolve() == output.resolve():
        raise TTMP2ImportError('转换输出不能覆盖原始 TTMP2。')
    try:
        with zipfile.ZipFile(source, 'r') as zin:
            manifest = json.loads(zin.read('TTMPL.mpl').decode('utf-8-sig'))
            data_info = zin.getinfo('TTMPD.mpd')
            if not isinstance(manifest.get('ModPackPages'), list):
                raise TTMP2ImportError('TTMPL.mpl 缺少 ModPackPages。')
            meta: dict[str, Any] = {
                'FileVersion': 4,
                'Identifier': str(uuid.uuid4()),
                'LastWrite': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
                'Name': str(manifest.get('Name') or source.stem),
                'Author': str(manifest.get('Author') or ''),
                'Description': str(manifest.get('Description') or ''),
                'Version': str(manifest.get('Version') or '1.0.0'),
                'Website': str(manifest.get('Url') or ''),
                'Groups': [],
            }
            payloads: dict[str, bytes] = {}
            group_names: set[str] = set()
            extracted_count = 0
            with zin.open('TTMPD.mpd', 'r') as data:
                for page_index, page in enumerate(manifest['ModPackPages']):
                    for group_index, source_group in enumerate(page.get('ModGroups') or []):
                        original_group_name = str(source_group.get('GroupName') or f'Group {group_index + 1}')
                        group_name = original_group_name
                        if group_name.casefold() in group_names:
                            group_name = f'{original_group_name} (Page {page_index + 1}, Group {group_index + 1})'
                        group_names.add(group_name.casefold())
                        selection = str(source_group.get('SelectionType') or 'Single').casefold()
                        group_type = 'Multi' if selection in ('multi', 'multiple', 'multi-select') else 'Single'
                        group = {'Type': group_type, 'Id': str(uuid.uuid4()), 'Name': group_name, 'Options': []}
                        for option_index, source_option in enumerate(source_group.get('OptionList') or []):
                            option_name = str(source_option.get('Name') or f'Option {option_index + 1}')
                            option: dict[str, Any] = {
                                'Id': str(uuid.uuid4()), 'Name': option_name, 'Files': {},
                                'Manipulations': source_option.get('Manipulations') or [],
                            }
                            mods = source_option.get('ModsJsons') or []
                            for mod_index, mod in enumerate(mods):
                                try:
                                    game_path = _safe_rel(mod['FullPath'])
                                    offset, size = int(mod['ModOffset']), int(mod['ModSize'])
                                except (KeyError, TypeError, ValueError) as exc:
                                    raise TTMP2ImportError(f'选项“{group_name}/{option_name}”存在无效资源条目：{mod!r}') from exc
                                if offset < 0 or size < 0 or offset + size > data_info.file_size:
                                    raise TTMP2ImportError(f'资源超出 TTMPD.mpd 范围：{game_path}')
                                internal = '/'.join(('ttmp2_import', f'page_{page_index + 1}',
                                    f'{_slug(group_name)}', f'{_slug(option_name)}', game_path))
                                internal = _safe_rel(internal)
                                if game_path.casefold() in {str(k).replace('\\', '/').casefold() for k in option['Files']}:
                                    raise TTMP2ImportError(f'同一选项中存在重复游戏资源路径，无法安全映射：{game_path}')
                                data.seek(offset)
                                raw = data.read(size)
                                if len(raw) != size:
                                    raise TTMP2ImportError(f'资源读取不完整：{game_path}')
                                # Internal package names are unique across groups/options.
                                if internal.casefold() in {k.casefold() for k in payloads}:
                                    internal = internal.rsplit('.', 1)[0] + f'_{mod_index}' + ('.' + internal.rsplit('.', 1)[1] if '.' in internal else '')
                                payloads[internal] = raw
                                option['Files'][game_path] = internal.replace('/', '\\')
                                extracted_count += 1
                            group['Options'].append(option)
                        meta['Groups'].append(group)
            if not meta['Groups']:
                raise TTMP2ImportError('TTMP2 中没有可导入的选项组。')
            output.parent.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(output, 'w', compression=zipfile.ZIP_DEFLATED) as zout:
                zout.writestr('meta.json', json.dumps(meta, ensure_ascii=False, indent=2).encode('utf-8'))
                for internal, raw in payloads.items():
                    zout.writestr(internal, raw)
            return {'source': str(source.resolve()), 'output': str(output.resolve()),
                    'mod_name': meta['Name'], 'group_count': len(meta['Groups']),
                    'option_count': sum(len(g['Options']) for g in meta['Groups']),
                    'resource_count': extracted_count, 'file_version': 4}
    except TTMP2ImportError:
        raise
    except (OSError, zipfile.BadZipFile, KeyError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise TTMP2ImportError(f'无法转换 TTMP2：{exc}') from exc
