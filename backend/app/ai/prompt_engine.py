"""提示词引擎：加载与渲染外置提示词模板。

提示词模板放在 ``app/ai/prompts/*.txt``，使用 ``{var}`` 形式占位。
渲染采用正则替换：仅替换 ``{标识符}`` 形式的占位符，不影响 JSON 示例中
字面的 ``{"tasks": ...}`` 等大括号；未提供的变量保留原占位符，便于排查。
"""

import re
from pathlib import Path
from typing import Any

# 匹配 {var} 占位符：仅匹配「字母/数字/下划线」组成的标识符，
# 不匹配 JSON 示例里的 {"tasks": ...} 这类含非标识符字符的内容。
_VAR_PATTERN = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


class PromptEngine:
    """提示词加载与渲染引擎。

    Parameters
    ----------
    prompts_dir:
        提示词目录路径。默认为当前文件同级 ``prompts`` 目录。
        实例化时可传入自定义目录，便于测试或换用其他模板集。
    """

    def __init__(self, prompts_dir: str | Path | None = None) -> None:
        if prompts_dir is None:
            prompts_dir = Path(__file__).parent / "prompts"
        self.prompts_dir = Path(prompts_dir)
        # 模板缓存：name -> 原始模板字符串
        self._cache: dict[str, str] = {}

    def load(self, name: str) -> str:
        """加载提示词模板原文。

        从 ``prompts_dir/{name}.txt`` 读取，带内存缓存。
        文件不存在时抛 FileNotFoundError。

        Parameters
        ----------
        name:
            提示词名称（不含扩展名）。
        """
        if name in self._cache:
            return self._cache[name]
        path = self.prompts_dir / f"{name}.txt"
        if not path.exists():
            raise FileNotFoundError(f"提示词模板不存在: {path}")
        text = path.read_text(encoding="utf-8")
        self._cache[name] = text
        return text

    def render(self, template: str, **vars: Any) -> str:
        """渲染模板，替换 ``{var}`` 占位。

        仅替换形如 ``{var_name}`` 的标识符占位（字母/数字/下划线），
        不影响 JSON 示例里的 ``{"tasks": ...}`` 等字面大括号。
        未提供的变量保留原占位符，便于排查缺失变量。
        """

        def _replace(match: re.Match[str]) -> str:
            key = match.group(1)
            if key in vars:
                return str(vars[key])
            return match.group(0)  # 保留原占位符

        return _VAR_PATTERN.sub(_replace, template)

    def get_prompt(self, name: str, /, **vars: Any) -> str:
        """便捷组合：加载 ``name`` 模板并用 ``vars`` 渲染。

        ``name`` 为仅位置参数，避免与模板变量同名（如 ``{name}``）冲突。
        """
        template = self.load(name)
        return self.render(template, **vars)
