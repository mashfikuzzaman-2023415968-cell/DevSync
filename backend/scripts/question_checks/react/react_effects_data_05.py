import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx, q):
    out = ctx.node(
        PRELUDE
        + """
const log = [];
function Comp({ id }) {
  useEffect(() => { log.push('start ' + id); return () => { log.push('stop ' + id); }; }, [id]);
  return null;
}
const { root } = mount(h(Comp, { id: 1 }));
act(() => { root.render(h(Comp, { id: 2 })); });
console.log(log.join(', '));
"""
    )
    ctx.expect_only(q, out)
