import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    r = js(ctx, """
function replaced(Form) {
  const { c } = mount(h(Form));
  const before = c.querySelector('input'); typeInto(before, 'a');
  const after = c.querySelector('input');
  return before !== after && c.querySelector('input').value === 'a';
}
// the buggy snippet
function Buggy() {
  const [email, setEmail] = useState('');
  function EmailField() { return h('input', { value: email, onChange: (e) => setEmail(e.target.value) }); }
  return h(EmailField);
}
// fix: EmailField declared outside, still controlled, still an inline arrow handler
function Field({ email, setEmail }) { return h('input', { value: email, onChange: (e) => setEmail(e.target.value) }); }
function Fixed() { const [email, setEmail] = useState(''); return h(Field, { email, setEmail }); }
// useState called AFTER the inner component is defined: still remounts
function Reordered() {
  function EmailField() { return h('input', { value: email, onChange: (e) => setEmail(e.target.value) }); }
  const [email, setEmail] = useState('');
  return h(EmailField);
}
console.log(JSON.stringify({ buggy: !replaced(Buggy) ? 'kept' : 'remounted',
  fixed: replaced(Fixed) ? 'remounted' : 'kept', reordered: replaced(Reordered) ? 'remounted' : 'kept' }));
""")
    assert r == {"buggy": "remounted", "fixed": "kept", "reordered": "remounted"}, r
    verify(q, {
        "EmailField is declared inside": r["buggy"] == "remounted" and r["fixed"] == "kept",
        # the fixed version keeps the inline arrow handler yet no longer remounts
        "The onChange handler is an inline": r["fixed"] == "remounted",
        # the fixed version is still a controlled input and keeps its node
        "The input is controlled": r["fixed"] == "remounted",
        # state is not lost (input shows 'a'); moving the hook does not matter
        "useState is called before": r["reordered"] == "kept",
    })
