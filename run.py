"""打包与直接运行的统一入口。

为什么不在 `app/main.py` 上直接打包：那个文件是包内模块，用的是相对导入
（`from .ui.main_window import ...`），PyInstaller 把它当脚本执行时会报
`attempted relative import with no known parent package`。这个顶层脚本只做一件事：
把 `app` 当包导入，再调它的 main()。

开发时：`py run.py`
打包后：双击 dist/ImageAngle.exe
"""
from __future__ import annotations

import sys

from app.main import main

if __name__ == '__main__':
    sys.exit(main())
