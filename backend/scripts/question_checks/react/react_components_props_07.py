from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    out = ctx.node(
        PRELUDE
        + """
function Counter({ label }) {
  const [n, setN] = useState(0);
  return h('button', { onClick: () => setN(n + 1) }, label, ': ', n);
}
function App({ first }) { return first ? h(Counter, { label: 'A' }) : h(Counter, { label: 'B' }); }
const { c, root } = mount(h(App, { first: true }));
click(c.querySelector('button')); click(c.querySelector('button'));
act(() => { root.render(h(App, { first: false })); });
console.log(c.textContent);
"""
    )
    ctx.expect_only(q, out)
