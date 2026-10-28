import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx, q):
    r = js(
        ctx,
        """
function view(useReducerFn) {
  function App() {
    const [state, dispatch] = useReducerFn();
    return h('div', null, h('button', { onClick: () => dispatch({ type: 'add', item: 'x' }) }, 'Add'),
      h('ul', null, state.items.map((it, k) => h('li', { key: k }, it))));
  }
  const { c } = mount(h(App));
  const n = () => c.querySelectorAll('li').length;
  click(c.querySelector('button')); const one = n();
  click(c.querySelector('button')); const two = n();
  return [one, two];
}
function buggy(state, action) { if (action.type === 'add') { state.items.push(action.item); return state; } return state; }
function copy(state, action) { if (action.type === 'add') { state.items.push(action.item); return { ...state }; } return state; }
function pure(state, action) { if (action.type === 'add') return { ...state, items: [...state.items, action.item] }; return state; }
const init = () => ({ items: [] });
const res = {
  buggy: view(() => useReducer(buggy, init())),
  copy: view(() => useReducer(copy, init())),
  pure: view(() => useReducer(pure, init())),
  wrapped: view(() => useReducer(useCallback(buggy, []), init())),
};
console.log(JSON.stringify(res));
""",
    )
    assert r["buggy"] == [0, 0], r  # stays empty, even after a second click
    assert r["pure"] == [1, 2] and r["copy"] == [1, 2], r  # arrays work; a new reference fixes it
    verify(
        q,
        {
            "The reducer returns the same state": r["buggy"] == [0, 0] and r["copy"] == [1, 2],
            "dispatch only schedules": r["buggy"][1] > 0,
            "useReducer cannot hold an array": r["pure"][0] == 0,
            "The reducer must be wrapped in useCallback": r["wrapped"][0] > 0,
        },
    )
