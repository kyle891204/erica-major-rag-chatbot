"""Extract the six project sections from the handbook's embedded document data."""

import hashlib
import json
import re
from dataclasses import dataclass, field
from html.parser import HTMLParser
from urllib.parse import quote


HANDBOOK = "https://yoorhi816.github.io/erica-academic-handbook/"
DATASET = "handbook"
ITEMS = (
    "다전공 제도 안내", "마이크로전공", "부전공",
    "일반다중전공", "융합다중전공", "복수전공",
)


@dataclass
class Element:
    tag: str
    attrs: dict = field(default_factory=dict)
    children: list = field(default_factory=list)

    def elements(self, tag):
        for child in self.children:
            if isinstance(child, Element):
                if child.tag == tag:
                    yield child
                yield from child.elements(tag)

    def text(self):
        if self.attrs.get("aria-hidden") == "true" or self.tag in {"script", "style"}:
            return ""
        if self.tag == "br":
            return "\n"
        result = "".join(child.text() if isinstance(child, Element) else child for child in self.children)
        if self.tag in {"p", "div", "li", "ul", "ol"}:
            return "\n" + result + "\n"
        return result


class Fragment(HTMLParser):
    void = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}

    def __init__(self, html):
        super().__init__()
        self.root = Element("root")
        self.stack = [self.root]
        self.feed(html)
        self.close()

    def handle_starttag(self, tag, attrs):
        node = Element(tag, dict(attrs))
        self.stack[-1].children.append(node)
        if tag not in self.void:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.void:
            self.stack.pop()

    def handle_endtag(self, tag):
        for index in range(len(self.stack) - 1, 0, -1):
            if self.stack[index].tag == tag:
                del self.stack[index:]
                break

    def handle_data(self, data):
        self.stack[-1].children.append(data)


def clean(text):
    return "\n".join(line for part in text.splitlines() if (line := " ".join(part.split())))


def table_grid(rows):
    grid = [{} for _ in rows]
    for index, row in enumerate(rows):
        column = 0
        for cell in row.children:
            if not isinstance(cell, Element) or cell.tag not in {"th", "td"}:
                continue
            while column in grid[index]:
                column += 1
            value = clean(cell.text()).replace("\n", " / ")
            width = int(cell.attrs.get("colspan", 1))
            height = int(cell.attrs.get("rowspan", 1))
            for occupied in grid[index:index + height]:
                for offset in range(width):
                    occupied[column + offset] = value
            column += width
    return grid


def table_passages(table):
    classes = (table.attrs.get("class") or "").split()
    if "faq-table" in classes:
        pending = None
        for row in table.elements("tr"):
            values = list(table_grid([row])[0].values())
            if len(values) != 2:
                continue
            marker, text = values
            if re.fullmatch(r"Q\s*\d+\.", marker):
                pending = text
            elif pending and re.fullmatch(r"A\s*\d+\.", marker):
                yield f"질문: {pending}\n안내: {text}"
                pending = None
        return

    header = next(table.elements("thead"), None)
    header_rows = list(header.elements("tr")) if header else []
    headers = table_grid(header_rows)
    rows = [row for row in table.elements("tr") if row not in header_rows]
    # The eligibility table stores the actual eligibility rule in its header.
    if "double-major-eligibility-table" in classes:
        rows = header_rows + rows
        headers = []
    for row in table_grid(rows):
        pairs = []
        for column, value in sorted(row.items()):
            label = " / ".join(dict.fromkeys(h[column] for h in headers if h.get(column)))
            if value:
                pairs.append(f"{label}: {value}" if label else value)
        if pairs:
            yield " · ".join(dict.fromkeys(pairs))


def blocks(element, section=""):
    if element.tag == "details":
        heading = next((child for child in element.children if isinstance(child, Element) and child.tag == "summary"), None)
        if heading:
            section = " / ".join(filter(None, (section, clean(heading.text()).rstrip("+").strip())))
    if element.tag == "table":
        for row in table_passages(element):
            yield section, row
        return
    if element.tag in {"summary", "script", "style", "button", "dialog", "img", "svg"} or element.attrs.get("aria-hidden") == "true":
        return
    if element.tag in {"p", "li"} and not any(element.elements("table")):
        if text := clean(element.text()):
            yield section, text
        return
    for child in element.children:
        if isinstance(child, Element):
            yield from blocks(child, section)


def build_corpus(html):
    data = re.search(r'<script\b[^>]*\bid="handbook-data"[^>]*>(.*?)</script>', html, re.S)
    if not data:
        raise ValueError("학사 편람의 handbook-data를 찾을 수 없습니다.")
    pages = json.loads(data[1])
    guide = next((page for page in pages if page["title"] == "문서 안내"), None)
    date = re.search(r"편람\s*수정일:\s*(\d{4})\.(\d{2})\.(\d{2})", Fragment(guide["html"]).root.text()) if guide else None
    if not date:
        raise ValueError("문서 안내에 표시된 편람 수정일을 찾을 수 없습니다.")
    revision = "-".join(date.groups())
    selected = {page["title"]: page for page in pages if page["chapter"] == "III. 전공" and page["title"] in ITEMS}
    if selected.keys() != set(ITEMS):
        raise ValueError("전공 제도 항목 6개 중 일부가 누락되었습니다.")

    chunks = []
    for title in ITEMS:
        page = selected[title]
        source_url = HANDBOOK + "#" + quote(page["id"])
        fragment = Fragment(page["html"]).root
        count = 0
        for node in fragment.children:
            if not isinstance(node, Element) or node.tag != "details":
                continue
            for section, text in blocks(node):
                if len(text.encode("utf-8")) > 24_000:
                    raise ValueError(f"메타데이터 제한을 넘는 문단: {title} / {section}")
                count += 1
                chunks.append({
                    "key": f"{ITEMS.index(title) + 1:02d}-{count:03d}",
                    "item_name": title,
                    "section": section,
                    "source_url": source_url,
                    "revision_date": revision,
                    "text": text,
                })
        if count == 0:
            raise ValueError(f"검색할 본문이 없습니다: {title}")

    serialized = json.dumps(chunks, ensure_ascii=False, sort_keys=True).encode("utf-8")
    version = hashlib.sha256(serialized).hexdigest()[:16]
    originals = [{"id": page["id"], "title": page["title"], "html": page["html"]} for page in selected.values()]
    return {"version": version, "revision_date": revision, "chunks": chunks}, originals
