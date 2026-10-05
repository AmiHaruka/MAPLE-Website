#!/usr/bin/env python3
"""Build the static documentation search index without third-party packages."""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
JSON_OUTPUT = ROOT / "assets" / "search-index.json"
SCRIPT_OUTPUT = ROOT / "assets" / "search-index.js"
EXCLUDED_PAGES = {"about.html", "home1.html"}
SKIP_TAGS = {"aside", "button", "footer", "header", "nav", "script", "style", "svg"}
HEADING_TAGS = {"h1", "h2", "h3"}


def normalize_text(parts: list[str]) -> str:
    return re.sub(r"\s+", " ", html.unescape(" ".join(parts))).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "section"


class PageParser(HTMLParser):
    def __init__(self, root_tag: str) -> None:
        super().__init__(convert_charrefs=True)
        self.root_tag = root_tag
        self.stack: list[str] = []
        self.ids: set[str] = set()
        self.title_parts: list[str] = []
        self.breadcrumb_parts: list[str] = []
        self.sections: list[dict[str, object]] = []
        self.current: dict[str, object] | None = None
        self.heading_parts: list[str] = []
        self.in_title = False
        self.in_heading = False
        self.breadcrumb_depth: int | None = None

    def in_content(self) -> bool:
        return self.root_tag in self.stack

    def is_skipped(self) -> bool:
        return any(tag in SKIP_TAGS for tag in self.stack)

    def finish_section(self) -> None:
        if not self.current:
            return
        self.current["heading"] = normalize_text(self.current.pop("heading_parts"))
        self.current["text"] = normalize_text(self.current.pop("text_parts"))
        if self.current["heading"]:
            self.sections.append(self.current)
        self.current = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if attrs_dict.get("id"):
            self.ids.add(attrs_dict["id"] or "")
        classes = (attrs_dict.get("class") or "").split()
        self.stack.append(tag)
        if tag == "nav" and "breadcrumb" in classes:
            self.breadcrumb_depth = len(self.stack)
        if tag == "title":
            self.in_title = True
        if tag in HEADING_TAGS and self.in_content() and not self.is_skipped():
            self.finish_section()
            self.current = {
                "level": int(tag[1]),
                "id": attrs_dict.get("id"),
                "heading_parts": [],
                "text_parts": [],
            }
            self.in_heading = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = dict(attrs)
        if attrs_dict.get("id"):
            self.ids.add(attrs_dict["id"] or "")

    def handle_endtag(self, tag: str) -> None:
        if tag in HEADING_TAGS:
            self.in_heading = False
        if tag == "title":
            self.in_title = False
        if tag == self.root_tag:
            self.finish_section()
        if tag == "nav" and self.breadcrumb_depth == len(self.stack):
            self.breadcrumb_depth = None
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index] == tag:
                del self.stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if self.breadcrumb_depth is not None:
            part = normalize_text([data])
            if part and part not in {"/", ">", "›", "→"}:
                self.breadcrumb_parts.append(part)
        if not self.current or not self.in_content() or self.is_skipped():
            return
        key = "heading_parts" if self.in_heading else "text_parts"
        self.current[key].append(data)


def page_type(path: str) -> str:
    if path.startswith("tasks/"):
        return "Task"
    if path.startswith("setup/"):
        return "Setup"
    if path.startswith("tutorials/"):
        return "Tutorial"
    if path.startswith("functions/"):
        return "Function"
    return "Guide"


def display_title(title: str) -> str:
    if re.match(r"^MAPLE\s+(?:-|—)\s+Machine-learning Potential", title, flags=re.I):
        return "MAPLE"
    title = re.sub(
        r"\s+(?:-|—)\s+Machine-learning Potential for Landscape Exploration$",
        "",
        title,
        flags=re.I,
    )
    return re.sub(r"\s+(?:-|—)\s+MAPLE(?:\s+Documentation)?$", "", title, flags=re.I).strip()


def navigation_trail(breadcrumb: list[str], title: str) -> list[str]:
    page = display_title(title)
    trail: list[str] = []
    for item in breadcrumb:
        if item.casefold() == "home" or (trail and trail[-1].casefold() == item.casefold()):
            continue
        trail.append(item)
    if trail:
        return trail
    return ["MAPLE"] if page.casefold() == "maple" else ["MAPLE", page]


def parse_page(path: Path) -> list[dict[str, object]]:
    source = path.read_text(encoding="utf-8")
    root_tag = "article" if re.search(r"<article\b", source, re.I) else "main"
    parser = PageParser(root_tag)
    parser.feed(source)
    parser.finish_section()

    relative_path = path.relative_to(ROOT).as_posix()
    title = normalize_text(parser.title_parts)
    used_ids = set(parser.ids)
    documents: list[dict[str, object]] = []

    def allocate_id(section: dict[str, object]) -> None:
        if section["id"]:
            return
        base = slugify(str(section["heading"]))
        section_id = base
        suffix = 2
        while section_id in used_ids:
            section_id = f"{base}-{suffix}"
            suffix += 1
        section["id"] = section_id
        used_ids.add(section_id)

    # main.js generates missing h2/h3 IDs first on pages with an empty auto-TOC.
    if re.search(r"<ul>\s*</ul>", source, re.I):
        for section in parser.sections:
            if section["level"] in {2, 3}:
                allocate_id(section)
    # search.js then gives every remaining indexed heading a stable anchor.
    for section in parser.sections:
        allocate_id(section)

    trail = navigation_trail(parser.breadcrumb_parts, title)
    for section_order, section in enumerate(parser.sections):
        text = str(section["text"])
        documents.append(
            {
                "url": f"{relative_path}#{section['id']}",
                "page": relative_path,
                "title": title,
                "heading": section["heading"],
                "text": text,
                "type": page_type(relative_path),
                "trail": trail,
                "level": section["level"],
                "section_order": section_order,
                "page_entry": section_order == 0 or section["level"] == 1,
            }
        )
    return documents


def build_index() -> str:
    pages = [
        path
        for path in sorted(ROOT.rglob("*.html"))
        if path.relative_to(ROOT).as_posix() not in EXCLUDED_PAGES
        and ".git" not in path.parts
        and ".omx" not in path.parts
    ]
    documents = [document for page in pages for document in parse_page(page)]
    parent_labels = {
        label.casefold()
        for document in documents
        for label in document["trail"][:-1]
    }
    for document in documents:
        terminal = document["trail"][-1].casefold() if document["trail"] else ""
        document["page_role"] = "landing" if terminal in parent_labels else "content"
    payload = {
        "version": 2,
        "source_pages": len(pages),
        "documents": documents,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true", help="fail if the committed index is stale")
    args = parser.parse_args()
    generated = build_index()
    compact_payload = json.dumps(json.loads(generated), ensure_ascii=False, separators=(",", ":"))
    script_generated = "window.MAPLE_SEARCH_INDEX=" + compact_payload + ";\n"
    if args.check:
        json_stale = not JSON_OUTPUT.exists() or JSON_OUTPUT.read_text(encoding="utf-8") != generated
        script_stale = not SCRIPT_OUTPUT.exists() or SCRIPT_OUTPUT.read_text(encoding="utf-8") != script_generated
        if json_stale or script_stale:
            print("Search index is stale. Run tools/build_search_index.py", file=sys.stderr)
            return 1
        print("Search index is current")
        return 0
    JSON_OUTPUT.write_text(generated, encoding="utf-8")
    SCRIPT_OUTPUT.write_text(script_generated, encoding="utf-8")
    payload = json.loads(generated)
    print(
        f"Wrote {len(payload['documents'])} sections from {payload['source_pages']} pages "
        f"to {JSON_OUTPUT.relative_to(ROOT)} and {SCRIPT_OUTPUT.relative_to(ROOT)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
