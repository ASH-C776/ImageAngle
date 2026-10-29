"""CSV 导出：UTF-8 BOM，纯表格（默认不带注释行），字段值用英文标准码。

设计约定：
- 导出的就是「表格」：默认第一行是表头，之后全是数据行，Excel / pandas 直接可用。
  早期版本在表头前写了 8 行 `#` 注释元数据，Excel 里会当成数据行，看着很怪，
  已改为默认关闭（需要溯源时传 include_meta=True）。
- 字段名与取值都用英文：direction=mesial/distal、confidence=high/medium/low、
  flags=no_reference;no_fdi;outlier;fdi_conflict;side_unknown。中文只保留在界面里，
  避免同一份数据里英文表头配中文值的割裂感，也方便后续统计脚本处理。
"""
from __future__ import annotations

import csv
import os
from typing import Iterable, List, Optional

from ..model.protocol import (NOTE_FDI_CONFLICT, NOTE_NO_FDI, NOTE_NO_REFERENCE,
                              NOTE_OUTLIER, NOTE_SIDE_UNKNOWN)
from ..model.session import ImageData, Session

CSV_FIELDS = [
    'patient_id', 'operator_id', 'image_file', 'image_path', 'image_index',
    'seq', 'tooth_fdi', 'axis_inclination_deg', 'direction',
    'confidence', 'flags',
    'ref_x1', 'ref_y1', 'ref_x2', 'ref_y2',
    'root_x', 'root_y', 'crown_x', 'crown_y',
    'image_width', 'image_height', 'flipped',
]

# 界面中文值 → 导出英文码
_DIRECTION_EN = {'近中': 'mesial', '远中': 'distal'}
_CONFIDENCE_EN = {'高': 'high', '中': 'medium', '低': 'low'}
_FLAG_EN = {
    NOTE_NO_REFERENCE: 'no_reference',
    NOTE_NO_FDI: 'no_fdi',
    NOTE_OUTLIER: 'outlier',
    NOTE_FDI_CONFLICT: 'fdi_conflict',
    NOTE_SIDE_UNKNOWN: 'side_unknown',
}


def _en(mapping: dict, value: Optional[str]) -> str:
    if not value:
        return ''
    return mapping.get(value, value)


def _flags(note: str) -> str:
    """把中文 note 拆成英文 flag 列表（半角分号分隔，未知项原样保留）。

    只按「；」拆分：note 自己用全角「，」连接同一句里的说明
    （如「未填牙位，侧别按图像位置判定」），那条要整体映射，不能拆散。
    """
    if not note:
        return ''
    parts = [p.strip() for p in note.split('；')]
    return ';'.join(_FLAG_EN.get(p, p) for p in parts if p)


def _row(session: Session, img: ImageData, index: int, tooth) -> dict:
    return {
        'patient_id': session.patient_id,
        'operator_id': session.operator_id,
        'image_file': os.path.basename(img.file),
        # 完整路径：不同文件夹下的同名片子（01.png / 01.png）光靠基名分不开，
        # 事后追溯原始影像时必须靠路径。
        'image_path': os.path.abspath(img.file) if img.file else '',
        'image_index': index,
        'seq': tooth.seq,
        'tooth_fdi': tooth.fdi,
        'axis_inclination_deg': '' if tooth.angle_deg is None else f'{tooth.angle_deg:.2f}',
        'direction': _en(_DIRECTION_EN, tooth.direction),
        'confidence': _en(_CONFIDENCE_EN, tooth.confidence),
        'flags': _flags(tooth.note),
        'ref_x1': img.reference['x1'] if img.reference else '',
        'ref_y1': img.reference['y1'] if img.reference else '',
        'ref_x2': img.reference['x2'] if img.reference else '',
        'ref_y2': img.reference['y2'] if img.reference else '',
        'root_x': tooth.root['x'],
        'root_y': tooth.root['y'],
        'crown_x': tooth.crown['x'],
        'crown_y': tooth.crown['y'],
        'image_width': img.width,
        'image_height': img.height,
        'flipped': 'true' if img.flipped else 'false',
    }


def export_session_csv(
    session: Session,
    out_path: str,
    only_path: str | None = None,
    images: Iterable[ImageData] | None = None,
    include_meta: bool = False,
) -> int:
    """导出测量数据为 CSV，返回数据行数。

    images   : 直接给定要导出的图（界面「导出当前图」走这条，避免依赖会话里
               是否登记过该路径 —— 早期实现从 session.images 按路径查，打开的
               新图根本没登记，结果要么 KeyError，要么导出上一次会话的旧数据）。
    only_path: 兼容参数，从 session.images 里按路径取图；找不到则导 0 行。
    include_meta: 是否在表头前写入 `#` 注释元数据（默认否，保持纯表格）。
    """
    if images is None:
        if only_path:
            img = session.images.get(only_path)
            picked: List[ImageData] = [img] if img is not None else []
        else:
            picked = list(session.images.values())
    else:
        picked = [img for img in images if img is not None]

    rows: List[dict] = []
    for idx, img in enumerate(picked, start=1):
        for tooth in img.teeth:
            rows.append(_row(session, img, idx, tooth))

    # UTF-8 BOM 让 Excel 正确识别中文（文件名 / 患者号里可能有中文）
    with open(out_path, 'w', encoding='utf-8-sig', newline='') as f:
        if include_meta:
            f.write('# ImageAngle export\n')
            f.write(f'# protocol_version={session.protocol_version}\n')
            f.write(f'# direction_convention={session.direction_convention}\n')
            f.write(f'# reference_definition={session.reference_definition}\n')
            f.write(f'# apex_exclusion_pct={session.apex_exclusion_pct}\n')
            f.write(f'# total_images={len(picked)}\n')
            f.write(f'# total_teeth={len(rows)}\n')
            f.write('#\n')
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    return len(rows)
