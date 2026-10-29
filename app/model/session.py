"""会话数据模型与 JSON 持久化。"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Dict, List, Optional

from .. import __version__
from .protocol import (EXCEPTION_THRESHOLD_DEG, NOTE_FDI_CONFLICT, NOTE_NO_FDI,
                       NOTE_NO_REFERENCE, NOTE_OUTLIER, NOTE_SIDE_UNKNOWN)


def build_note(
    angle_deg: Optional[float],
    fdi: str,
    has_reference: bool,
    threshold: float = EXCEPTION_THRESHOLD_DEG,
    conflict: bool = False,
    side_unknown: bool = False,
) -> str:
    """自动组装 note：无参考线 / 牙位冲突 / 侧别未知 / 异常值 / 未填牙位。

    顺序按「影响可信度的严重程度」排，最需要人看一眼的放前面。
    """
    parts: List[str] = []
    if conflict:
        parts.append(NOTE_FDI_CONFLICT)
    if side_unknown:
        parts.append(NOTE_SIDE_UNKNOWN)
    if not has_reference:
        parts.append(NOTE_NO_REFERENCE)
    elif angle_deg is not None and abs(angle_deg) > threshold:
        parts.append(NOTE_OUTLIER)
    if not fdi:
        parts.append(NOTE_NO_FDI)
    return '；'.join(parts)


@dataclass
class Tooth:
    seq: int
    fdi: str = ''
    root: Dict[str, float] = field(default_factory=lambda: {'x': 0.0, 'y': 0.0})
    crown: Dict[str, float] = field(default_factory=lambda: {'x': 0.0, 'y': 0.0})
    angle_deg: Optional[float] = None
    direction: Optional[str] = None
    confidence: str = ''
    note: str = ''


@dataclass
class ImageData:
    file: str
    width: int = 0
    height: int = 0
    flipped: bool = False
    reference: Optional[Dict] = None  # {x1, y1, x2, y2, type}
    teeth: List[Tooth] = field(default_factory=list)

    def next_seq(self) -> int:
        return max((t.seq for t in self.teeth), default=0) + 1


@dataclass
class Session:
    protocol_version: int = 1
    software_version: str = __version__
    direction_convention: str = 'radiological'
    reference_definition: str = 'palatal_midline'
    apex_exclusion_pct: float = 22.0
    operator_id: str = ''
    patient_id: str = ''
    images: Dict[str, ImageData] = field(default_factory=dict)
    last_dir: str = ''

    def save(self, path: str) -> None:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

    @classmethod
    def load(cls, path: str) -> 'Session':
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        sess = cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})
        sess.images = {}
        for img_path, img in data.get('images', {}).items():
            teeth = [Tooth(**t) for t in img.get('teeth', [])]
            sess.images[img_path] = ImageData(
                file=img.get('file', img_path),
                width=img.get('width', 0),
                height=img.get('height', 0),
                flipped=img.get('flipped', False),
                reference=img.get('reference'),
                teeth=teeth,
            )
        return sess
