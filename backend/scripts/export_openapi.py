"""导出 OpenAPI schema 到 stdout 或文件，供 make gen-api 生成前端 TS client。

用法：uv run python scripts/export_openapi.py [输出路径]
"""

import json
import sys
from pathlib import Path

from app.main import app


def main() -> None:
    schema = json.dumps(app.openapi(), ensure_ascii=False, indent=2)
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(schema, encoding="utf-8")
        print(f"OpenAPI schema written to {out}")
    else:
        print(schema)


if __name__ == "__main__":
    main()
