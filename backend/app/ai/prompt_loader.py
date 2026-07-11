"""jinja2 prompt 模板加载。一场景一文件（app/ai/prompts/*.j2）。

改动 prompts/ 下任何文件后必须跑 make eval（CLAUDE.md 硬性规则 3）。
"""

from functools import lru_cache
from pathlib import Path
from typing import Any

from jinja2 import Environment, FileSystemLoader, StrictUndefined

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@lru_cache
def _env() -> Environment:
    return Environment(
        loader=FileSystemLoader(_PROMPTS_DIR),
        undefined=StrictUndefined,
        autoescape=False,
        trim_blocks=True,
        lstrip_blocks=True,
    )


def render_prompt(template_name: str, **context: Any) -> str:
    return _env().get_template(template_name).render(**context)
