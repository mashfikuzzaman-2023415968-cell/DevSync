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
(async () => {
  const log = [];
  function Counter() {
    const [count, setCount] = useState(0);
    function handleClick() { setCount(count + 5); setTimeout(() => log.push(count), 0); }
    return h('button', { onClick: handleClick }, String(count));
  }
  const { c } = mount(h(Counter));
  click(c.querySelector('button'));
  await sleep(30);
  console.log(String(log[0]));
})();
"""
    )
    ctx.expect_only(q, out)
