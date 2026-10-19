"""Generate `docs/design/erd.svg` from the SQLAlchemy models (spec §17.0).

Dependency-free: reads `Base.metadata`, lays the tables out in a grid, draws each as a box
listing its columns (primary keys marked PK, foreign keys marked FK → target), and connects
foreign keys to their referenced tables with light lines. Deterministic, so the committed SVG
only changes when the schema does. Run with `make erd`.
"""

from __future__ import annotations

import html
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import app.models  # noqa: E402,F401 - importing registers every table on the metadata
from app.db.base import Base  # noqa: E402

# ERD_PATH lets the containerized `make erd` target write to the mounted docs folder.
OUT = Path(os.environ.get("ERD_PATH") or ROOT.parent / "docs" / "design" / "erd.svg")

COL_W = 230
ROW_H = 18
HEADER_H = 26
PAD = 40
GAP_X = 70
GAP_Y = 50
PER_ROW = 4


def _type_name(column: object) -> str:
    """A short, readable column type."""
    try:
        return type(getattr(column, "type")).__name__.lower()  # noqa: B009
    except Exception:
        return "?"


def _column_line(column: object) -> str:
    name = getattr(column, "name", "?")
    flags = []
    if getattr(column, "primary_key", False):
        flags.append("PK")
    fks = getattr(column, "foreign_keys", set())
    target = None
    for fk in fks:
        flags.append("FK")
        target = fk.column.table.name
        break
    label = f"{name}: {_type_name(column)}"
    if flags:
        label += "  " + " ".join(flags)
    if target:
        label += f" → {target}"
    return label


def build_svg() -> str:
    tables = list(Base.metadata.sorted_tables)
    boxes: dict[str, tuple[int, int, int, int]] = {}  # name -> (x, y, w, h)
    # Grid layout: equal column width, row height from the tallest box in that row.
    x = PAD
    y = PAD
    row_height = 0
    col = 0
    for table in tables:
        h = HEADER_H + ROW_H * len(table.columns) + 8
        boxes[table.name] = (x, y, COL_W, h)
        row_height = max(row_height, h)
        col += 1
        if col >= PER_ROW:
            col = 0
            x = PAD
            y += row_height + GAP_Y
            row_height = 0
        else:
            x += COL_W + GAP_X
    width = PAD * 2 + PER_ROW * COL_W + (PER_ROW - 1) * GAP_X
    height = y + row_height + PAD

    parts: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="sans-serif" font-size="12">',
        f'<rect width="{width}" height="{height}" fill="#f7f8fa"/>',
        '<defs><marker id="a" markerWidth="8" markerHeight="8" refX="6" refY="3" orient="auto">'
        '<path d="M0,0 L6,3 L0,6 Z" fill="#94a3b8"/></marker></defs>',
    ]

    # Foreign-key edges first (behind the boxes).
    for table in tables:
        if table.name not in boxes:
            continue
        x0, y0, w0, h0 = boxes[table.name]
        for fk in table.foreign_keys:
            target = fk.column.table.name
            if target not in boxes or target == table.name:
                continue
            x1, y1, w1, h1 = boxes[target]
            parts.append(
                f'<line x1="{x0 + w0 // 2}" y1="{y0 + h0 // 2}" '
                f'x2="{x1 + w1 // 2}" y2="{y1 + h1 // 2}" stroke="#cbd5e1" '
                f'stroke-width="1" marker-end="url(#a)"/>'
            )

    # Table boxes.
    for table in tables:
        x0, y0, w0, h0 = boxes[table.name]
        parts.append(
            f'<rect x="{x0}" y="{y0}" width="{w0}" height="{h0}" rx="6" fill="#ffffff" '
            f'stroke="#334155" stroke-width="1"/>'
        )
        parts.append(
            f'<rect x="{x0}" y="{y0}" width="{w0}" height="{HEADER_H}" rx="6" fill="#1e293b"/>'
        )
        parts.append(
            f'<text x="{x0 + 10}" y="{y0 + 18}" fill="#ffffff" font-weight="bold">'
            f"{html.escape(table.name)}</text>"
        )
        cy = y0 + HEADER_H + 14
        for column in table.columns:
            parts.append(
                f'<text x="{x0 + 10}" y="{cy}" fill="#0f172a">'
                f"{html.escape(_column_line(column))}</text>"
            )
            cy += ROW_H

    parts.append("</svg>\n")
    return "\n".join(parts)


def main() -> int:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_svg(), encoding="utf-8")
    print(f"erd: wrote {OUT} ({len(list(Base.metadata.tables))} tables)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
