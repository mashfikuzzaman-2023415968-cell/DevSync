import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    out = ctx.node(PRELUDE + """
function Row({ name }) { const [label] = useState(name); return h('li', null, label); }
function List() {
  const [names, setNames] = useState(['A', 'B', 'C']);
  return h(React.Fragment, null,
    h('button', { onClick: () => setNames(names.slice(1)) }, 'Remove first'),
    h('ul', null, names.map((n, i) => h(Row, { key: i, name: n }))));
}
const { c } = mount(h(List));
click(c.querySelector('button'));
console.log(Array.from(c.querySelectorAll('li')).map((l) => l.textContent).join(', '));
""")
    ctx.expect_only(q, out)
