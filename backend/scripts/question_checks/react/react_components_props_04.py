from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    out = ctx.node("""
const React = require('react'); const h = React.createElement;
function Badge({ color = 'gray' }) { return h('span', { className: 'badge-' + color }); }
console.log(require('react-dom/server').renderToStaticMarkup(h(Badge, { color: null })));
""")
    ctx.expect_only(q, out)
