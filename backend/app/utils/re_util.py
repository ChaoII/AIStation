import re
from functools import lru_cache

# 用户可控正则的安全上限：
# - MAX_PATTERN_LENGTH：模式本身长度上限（超长模式直接拒绝，约束静态分析规模）
# - MAX_TEXT_LENGTH：单次匹配的待匹配文本上限（截断后最坏回溯规模有界）
MAX_PATTERN_LENGTH = 512
MAX_TEXT_LENGTH = 4096


class RegexSafetyError(ValueError):
    """用户正则不满足安全约束（过长 / 存在灾难性回溯结构 / 非法）。"""


def _find_unsafe_repetition(pattern: str) -> str | None:
    """静态检测“无界量词套无界量词”的灾难性回溯结构。

    典型危险模式：``(a+)+$``、``(a*)*``、``(?:\\w+)+``、``(a+){2,}``——内层无界量词
    可匹配的字符由外层无界量词反复切分，输入稍长即指数级回溯。

    实现为线性扫描（非完整正则解析器）：
    - 维护分组栈，记录“分组体内是否出现过无界量词”；
    - 分组闭合后若紧跟无界量词（``*`` / ``+`` / ``{m,}``）且组内也含无界量词 → 拒绝；
    - ``?`` 与有界 ``{m,n}`` 不会放大回溯，放行（如 ``(?:\\.[0-9]+)?`` 属合法模式）。

    返回中文原因字符串；安全则返回 ``None``。

    已知局限：不检测“量词 + 重叠分支交替”类（如 ``(a|a)*``），这类模式依赖
    ``MAX_TEXT_LENGTH`` 截断与规则编译层校验共同约束；如需完全覆盖可后续引入
    ``regex`` 超时引擎。
    """
    stack: list[bool] = []  # 每个未闭合分组：其体内是否出现无界量词
    prev_atom_unbounded = False  # 紧邻左侧原子（可能是分组）是否含无界量词
    i = 0
    n = len(pattern)
    while i < n:
        ch = pattern[i]
        if ch == "\\":
            i += 2  # 转义字符：本身是原子，且不可能是量词
            prev_atom_unbounded = False
            continue
        if ch == "[":
            # 字符类整体是一个原子，跳过（含转义）
            i += 1
            while i < n and pattern[i] != "]":
                if pattern[i] == "\\":
                    i += 1
                i += 1
            i += 1
            prev_atom_unbounded = False
            continue
        if ch == "(":
            stack.append(False)
            prev_atom_unbounded = False
            i += 1
            continue
        if ch == ")":
            inner = stack.pop() if stack else False
            if stack:
                stack[-1] = stack[-1] or inner  # 向内层传播
            prev_atom_unbounded = inner
            i += 1
            continue
        if ch in "*+":
            if prev_atom_unbounded:
                return f"存在嵌套无界量词（如 (a+)+ / (a*)*）：{pattern!r}"
            if stack:
                stack[-1] = True
            prev_atom_unbounded = False
            i += 1
            continue
        if ch == "{":
            match = re.match(r"\{(\d*)(,?)(\d*)\}", pattern[i:])
            if match:
                low, comma, high = match.group(1), match.group(2), match.group(3)
                # {m,} 无上界才危险；{m,n} 与 {,n} 有界，不放大回溯
                if comma and not high and low:
                    if prev_atom_unbounded:
                        return f"存在嵌套无界量词（如 (a+)+）：{pattern!r}"
                    if stack:
                        stack[-1] = True
                    prev_atom_unbounded = False
                i += match.end()
                continue
            prev_atom_unbounded = False
            i += 1
            continue
        if ch in "?|":
            # 有界量词不改变左原子；交替重置原子序列
            if ch == "|":
                prev_atom_unbounded = False
            i += 1
            continue
        prev_atom_unbounded = False
        i += 1
    return None


def validate_regex_pattern(pattern: str) -> re.Pattern:
    """校验并编译用户正则；不安全/非法时抛 :class:`RegexSafetyError`。

    供规则编译层在“保存规则”时调用，把不安全正则提前以明确错误拒绝。
    """
    if not isinstance(pattern, str) or not pattern:
        raise RegexSafetyError("正则不能为空")
    if len(pattern) > MAX_PATTERN_LENGTH:
        raise RegexSafetyError(f"正则长度超过上限 {MAX_PATTERN_LENGTH} 字符")
    reason = _find_unsafe_repetition(pattern)
    if reason:
        raise RegexSafetyError(reason)
    try:
        return re.compile(pattern)
    except re.error as e:
        raise RegexSafetyError(f"正则非法：{e}") from e


@lru_cache(maxsize=512)
def _compile_cached(pattern: str) -> re.Pattern | None:
    """按模式缓存编译结果；不安全/非法模式返回 ``None``。

    使用 ``lru_cache`` 避免每个事件都对同一规则正则现编译（审计 #10 要求）。
    """
    try:
        return validate_regex_pattern(pattern)
    except RegexSafetyError:
        return None


def safe_regex_search(pattern: str, text: str) -> bool:
    """安全执行 ``re.search``：不安全/非法正则或非文本一律视为不命中。

    - 模式经长度与灾难性回溯静态校验，且复用缓存；
    - 待匹配文本截断到 ``MAX_TEXT_LENGTH``，限制最坏回溯规模；
    - 绝不向上抛异常，避免单条脏规则导致整个告警事件被丢弃。
    """
    if not isinstance(text, str):
        return False
    compiled = _compile_cached(pattern) if isinstance(pattern, str) else None
    if compiled is None:
        return False
    return compiled.search(text[:MAX_TEXT_LENGTH]) is not None


def search_string(pattern: str, text: str) -> re.Match[str] | None:
    """
    全字段正则匹配

    参数:
    - pattern (str): 正则表达式模式。
    - text (str): 待匹配的文本。

    返回:
    - re.Match[str] | None: 匹配结果。
    """
    if not pattern or not text:
        return None

    result = re.search(pattern, text)
    return result


def match_string(pattern: str, text: str) -> re.Match[str] | None:
    """
    从字段开头正则匹配

    参数:
    - pattern (str): 正则表达式模式。
    - text (str): 待匹配的文本。

    返回:
    - re.Match[str] | None: 匹配结果。
    """
    if not pattern or not text:
        return None

    result = re.match(pattern, text)
    return result


def is_phone(number: str) -> re.Match[str] | None:
    """
    检查手机号码格式

    参数:
    - number (str): 待检查的手机号码。

    返回:
    - re.Match[str] | None: 匹配结果。
    """
    if not number:
        return None

    phone_pattern = r"^1[3-9]\d{9}$"
    return match_string(phone_pattern, number)


def is_git_url(url: str) -> re.Match[str] | None:
    """
    检查 git URL 格式

    参数:
    - url (str): 待检查的 URL。

    返回:
    - re.Match[str] | None: 匹配结果。
    """
    if not url:
        return None

    git_pattern = r"^(?!(git\+ssh|ssh)://|git@)(?P<scheme>git|https?|file)://(?P<host>[^/]*)(?P<path>(?:/[^/]*)*/)(?P<repo>[^/]+?)(?:\.git)?$"
    return match_string(git_pattern, url)
