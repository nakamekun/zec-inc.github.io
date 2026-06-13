"""Tiny YAML-subset loader (stdlib only, no PyYAML dependency).

Supports exactly the structures used by docs/aso/aso-source.yaml:
- nested mappings (space indentation, no tabs)
- block sequences (`- item`, `- key: value` items)
- flow sequences (`[a, b, c]`)
- plain / single-quoted / double-quoted scalars, bool / int / float / null
- block scalars (`|`, `|-`, `>`, `>-`)
- `#` comments (full-line and after whitespace, never inside quotes)

Not supported: anchors, aliases, multi-document streams, complex keys.
"""

from __future__ import annotations

import re


class YamlError(ValueError):
    def __init__(self, message: str, lineno: int):
        super().__init__(f"line {lineno}: {message}")
        self.lineno = lineno


_BOOLS = {"true": True, "false": False}
_NULLS = {"null", "~"}


def load_file(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return load(fh.read())


def load(text: str) -> dict:
    return _Parser(text).parse()


def _strip_comment(line: str) -> str:
    in_single = in_double = False
    for i, ch in enumerate(line):
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        elif ch == "#" and not in_single and not in_double:
            if i == 0 or line[i - 1] in " \t":
                return line[:i]
    return line


def _split_flow(inner: str) -> list[str]:
    parts: list[str] = []
    cur: list[str] = []
    depth = 0
    in_single = in_double = False
    for ch in inner:
        if ch == "'" and not in_double:
            in_single = not in_single
        elif ch == '"' and not in_single:
            in_double = not in_double
        if not in_single and not in_double:
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
            elif ch == "," and depth == 0:
                parts.append("".join(cur))
                cur = []
                continue
        cur.append(ch)
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def _parse_scalar(text: str, lineno: int):
    text = text.strip()
    if text.startswith("["):
        if not text.endswith("]"):
            raise YamlError("unterminated flow sequence", lineno)
        return [_parse_scalar(p, lineno) for p in _split_flow(text[1:-1])]
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        body = text[1:-1]
        if text[0] == '"':
            body = (
                body.replace("\\\\", "\x00")
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\t", "\t")
                .replace("\x00", "\\")
            )
        else:
            body = body.replace("''", "'")
        return body
    low = text.lower()
    if low in _BOOLS:
        return _BOOLS[low]
    if low in _NULLS or text == "":
        return None
    if re.fullmatch(r"[+-]?\d+", text):
        return int(text)
    if re.fullmatch(r"[+-]?\d*\.\d+", text):
        return float(text)
    return text


class _Parser:
    _KEY_RE = re.compile(r"^([A-Za-z0-9_.\-]+):(?:\s+(.*))?$")

    def __init__(self, text: str):
        self.lines = text.splitlines()

    def parse(self):
        i = self._next(0)
        if i is None:
            return {}
        value, j = self._block(i, self._indent_of(i))
        if j is not None:
            raise YamlError("content after top-level block", j + 1)
        return value

    # ---- line helpers ----

    def _stripped(self, i: int) -> str | None:
        line = _strip_comment(self.lines[i])
        if not line.strip():
            return None
        leading = line[: len(line) - len(line.lstrip())]
        if "\t" in leading:
            raise YamlError("tabs are not allowed in indentation", i + 1)
        return line

    def _next(self, i: int) -> int | None:
        while i < len(self.lines):
            if self._stripped(i) is not None:
                return i
            i += 1
        return None

    def _indent_of(self, i: int) -> int:
        line = self._stripped(i)
        return len(line) - len(line.lstrip())

    def _content(self, i: int) -> str:
        return self._stripped(i).strip()

    # ---- block parsing ----

    def _block(self, i: int, indent: int):
        content = self._content(i)
        if content == "-" or content.startswith("- "):
            return self._sequence(i, indent)
        return self._mapping(i, indent)

    def _mapping(self, i: int, indent: int):
        out: dict = {}
        j: int | None = i
        while j is not None:
            line_indent = self._indent_of(j)
            if line_indent < indent:
                break
            if line_indent > indent:
                raise YamlError("unexpected indent", j + 1)
            content = self._content(j)
            m = self._KEY_RE.match(content)
            if not m:
                raise YamlError(f"expected 'key: value', got {content!r}", j + 1)
            key, rest = m.group(1), (m.group(2) or "").strip()
            if key in out:
                raise YamlError(f"duplicate key {key!r}", j + 1)
            if rest in ("|", "|-", ">", ">-"):
                out[key], j = self._block_scalar(j, indent, rest)
            elif rest:
                out[key] = _parse_scalar(rest, j + 1)
                j = self._next(j + 1)
            else:
                nxt = self._next(j + 1)
                if nxt is not None and self._indent_of(nxt) > indent:
                    out[key], j = self._block(nxt, self._indent_of(nxt))
                else:
                    out[key] = None
                    j = nxt
        return out, j

    def _sequence(self, i: int, indent: int):
        out: list = []
        j: int | None = i
        while j is not None and self._indent_of(j) == indent:
            content = self._content(j)
            if content != "-" and not content.startswith("- "):
                break
            rest = content[1:].strip()
            if not rest:
                nxt = self._next(j + 1)
                if nxt is not None and self._indent_of(nxt) > indent:
                    item, j = self._block(nxt, self._indent_of(nxt))
                    out.append(item)
                else:
                    out.append(None)
                    j = nxt
            elif self._KEY_RE.match(rest):
                # `- key: value` item: blank out the dash and parse the
                # item (plus its continuation lines) as a mapping.
                raw = self.lines[j]
                self.lines[j] = raw[:indent] + " " + raw[indent + 1 :]
                item, j = self._mapping(j, indent + 2)
                out.append(item)
            else:
                out.append(_parse_scalar(rest, j + 1))
                j = self._next(j + 1)
        if j is not None and self._indent_of(j) > indent:
            raise YamlError("unexpected indent after sequence item", j + 1)
        return out, j

    def _block_scalar(self, j: int, parent_indent: int, style: str):
        collected: list[str] = []
        content_indent: int | None = None
        k = j + 1
        while k < len(self.lines):
            raw = self.lines[k]
            if not raw.strip():
                collected.append("")
                k += 1
                continue
            line_indent = len(raw) - len(raw.lstrip(" "))
            if line_indent <= parent_indent:
                break
            if content_indent is None:
                content_indent = line_indent
            if line_indent < content_indent:
                raise YamlError("bad indentation inside block scalar", k + 1)
            collected.append(raw[content_indent:])
            k += 1
        while collected and collected[-1] == "":
            collected.pop()
        if style.startswith(">"):
            paragraphs: list[str] = []
            cur: list[str] = []
            for ln in collected:
                if ln == "":
                    paragraphs.append(" ".join(cur))
                    cur = []
                else:
                    cur.append(ln.strip())
            paragraphs.append(" ".join(cur))
            text = "\n".join(paragraphs)
        else:
            text = "\n".join(collected)
        return text.rstrip("\n"), self._next(k)
