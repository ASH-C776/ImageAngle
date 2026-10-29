"""运行日志 + 全局异常兜底。

为什么需要：打包成 exe 后没有控制台，出了问题只剩「双击没反应」「用着用着数据
没存上」。代码里原本有十几处 `try/except`，其中不少是 `except Exception: pass`，
等于把错误直接丢掉。这里统一把日志写到 `%APPDATA%\\ImageAngle\\app.log`
（1 MB × 3 份轮转），并接管 `sys.excepthook`：未捕获异常先落日志，再弹一个
可复制的错误框，告诉用户日志文件在哪。

原则：**写日志本身绝不能把程序带崩**。文件句柄建不起来就退回 stderr。
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys

from .io import paths

LOG_NAME = 'app.log'
_MAX_BYTES = 1024 * 1024
_BACKUPS = 3
_ROOT = 'imageangle'

_configured = False


def log_path() -> str:
    return os.path.join(paths.data_dir(), LOG_NAME)


def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """配置根 logger（可重复调用，只生效一次）。"""
    global _configured
    logger = logging.getLogger(_ROOT)
    if _configured:
        return logger

    logger.setLevel(level)
    # 不让日志再冒泡到 root：否则某些环境（如 pythonw）会重复输出
    logger.propagate = False
    fmt = logging.Formatter(
        '%(asctime)s %(levelname)-7s %(name)s: %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S')

    if not logger.handlers:
        try:
            fh = logging.handlers.RotatingFileHandler(
                log_path(), maxBytes=_MAX_BYTES, backupCount=_BACKUPS,
                encoding='utf-8')
            fh.setFormatter(fmt)
            logger.addHandler(fh)
        except OSError:
            # 目录不可写时没有文件日志，但绝不因此中断启动
            pass
        sh = logging.StreamHandler(sys.stderr)
        sh.setFormatter(fmt)
        logger.addHandler(sh)

    _configured = True
    try:
        from . import __version__ as _ver
    except Exception:          # pragma: no cover - 打包异常时不该因此中断
        _ver = '?'
    logger.info('--- 启动 ImageAngle %s --- 数据目录: %s', _ver, paths.data_dir())
    return logger


def get_logger(name: str = '') -> logging.Logger:
    """取子 logger（`get_logger('ui.canvas')` → `imageangle.ui.canvas`）。"""
    return logging.getLogger(f'{_ROOT}.{name}' if name else _ROOT)


def _notify(text: str) -> None:
    """弹错误框。抽成独立函数是为了测试能 patch 掉（避免真弹窗阻塞）。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        if QApplication.instance() is None:
            return
        QMessageBox.critical(
            None, 'ImageAngle 出错',
            f'{text}\n\n详细信息已写入日志：\n{log_path()}')
    except Exception:
        pass


def install_excepthook() -> None:
    """接管 sys.excepthook：先写日志，再提示用户，最后保持原有行为。"""
    logger = get_logger()
    previous = sys.excepthook

    def _hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            previous(exc_type, exc, tb)
            return
        logger.error('未捕获异常', exc_info=(exc_type, exc, tb))
        _notify(f'{exc_type.__name__}: {exc}')
        previous(exc_type, exc, tb)

    sys.excepthook = _hook
