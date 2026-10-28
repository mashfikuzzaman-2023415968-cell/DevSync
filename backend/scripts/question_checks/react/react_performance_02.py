from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    r = js(
        ctx,
        """
function run(optionsFor) {
  const renders = [];
  const ListView = React.memo(function ListView({ options }) {
    renders.push('render');
    return h('ul', null, h('li', null, options.sort));
  });
  function Page() {
    const [text, setText] = useState('');
    return h(React.Fragment, null,
      h('input', { value: text, onChange: (e) => setText(e.target.value) }),
      h(ListView, { options: optionsFor() }));
  }
  const { c } = mount(h(Page));
  typeInto(c.querySelector('input'), 'a'); typeInto(c.querySelector('input'), 'ab');
  return renders.length;
}
const stable = { sort: 'asc' };
console.log(JSON.stringify({ inline: run(() => ({ sort: 'asc' })), hoisted: run(() => stable) }));
""",
    )
    assert r == {"inline": 3, "hoisted": 1}, r
    verify(
        q,
        {
            "The inline object literal": r["inline"] == 3 and r["hoisted"] == 1,
            "React.memo compares props only on the first": r["hoisted"]
            != 1,  # memo skips later renders
            "React.memo does not work for components that render lists": r["hoisted"] != 1,
            "A parent state update always forces": r["hoisted"] != 1,
        },
    )
