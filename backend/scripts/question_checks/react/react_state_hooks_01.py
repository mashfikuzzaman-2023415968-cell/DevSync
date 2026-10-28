import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    out = ctx.node(PRELUDE + """
function C() {
  const [count, setCount] = useState(0);
  function handleClick() { setCount(count + 1); setCount(count + 1); setCount((c) => c + 1); }
  return h('button', { onClick: handleClick }, String(count));
}
const { c } = mount(h(C));
click(c.querySelector('button'));
console.log(c.textContent);
""")
    ctx.expect_only(q, out)
