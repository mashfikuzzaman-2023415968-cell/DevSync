import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    out = ctx.node(PRELUDE + """
const log = [];
function Results() {
  const [n, setN] = useState(0);
  const options = { limit: 10 };
  useEffect(() => { log.push('load'); }, [options]);
  return h('button', { onClick: () => setN(n + 1) }, n);
}
const { c } = mount(h(Results));
click(c.querySelector('button')); click(c.querySelector('button'));
console.log(log.length);
""")
    ctx.expect_only(q, out)
