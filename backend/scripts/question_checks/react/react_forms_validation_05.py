import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    r = js(ctx, """
function field(trim, initial) {
  return function NameField() {
    const [name, setName] = useState(initial);
    return h('input', { value: name, onChange: (e) => setName(trim ? e.target.value.trim() : e.target.value) });
  };
}
function typed(C) {
  const { c } = mount(h(C)); const input = c.querySelector('input');
  typeInto(input, 'John'); typeInto(input, 'John '); return input.value;
}
console.log(JSON.stringify({ buggy: typed(field(true, '')), noTrim: typed(field(false, '')), nullStart: typed(field(true, null)) }));
""")
    assert r["buggy"] == "John" and r["noTrim"] == "John ", r
    verify(q, {
        "trim() in onChange strips": r["buggy"] == "John" and r["noTrim"] == "John ",
        # same controlled input without trim() keeps the space
        "A controlled input with value": r["noTrim"] != "John ",
        # starting from null changes nothing
        "useState('') should start as null": r["nullStart"] == "John ",
        # the space reached onChange on the input event, with no blur needed
        "onChange only fires on blur": r["noTrim"] != "John ",
    })
