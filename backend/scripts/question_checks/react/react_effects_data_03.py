import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    r = js(ctx, """
(async () => {
  let count = 0;
  globalThis.fetch = () => { count++; const n = count; return Promise.resolve({ json: () => Promise.resolve({ name: 'u' + n }) }); };
  const load = (id, setUser) => fetch('/api/users/' + id).then((r) => r.json()).then(setUser);
  const variants = {
    buggy: ({ id }) => { const [u, setUser] = useState(null); useEffect(() => { load(id, setUser); }); return h('h1', null, u ? u.name : 'L'); },
    deps: ({ id }) => { const [u, setUser] = useState(null); useEffect(() => { load(id, setUser); }, [id]); return h('h1', null, u ? u.name : 'L'); },
    callback: ({ id }) => { const [u, setUser] = useState(null);
      const go = useCallback(() => load(id, setUser), [id]); useEffect(() => { go(); }); return h('h1', null, u ? u.name : 'L'); },
    timeout: ({ id }) => { const [u, setUser] = useState(null);
      useEffect(() => { fetch('/api/users/' + id).then((r) => r.json()).then((x) => setTimeout(() => setUser(x), 0)); }); return h('h1', null, u ? u.name : 'L'); },
    body: ({ id }) => { const [u, setUser] = useState(null); load(id, setUser); return h('h1', null, u ? u.name : 'L'); },
  };
  const res = {};
  for (const [name, C] of Object.entries(variants)) {
    count = 0;
    const { c, root } = mountAsync(h(C, { id: 7 }));
    await sleep(250);
    res[name] = { fetches: count, text: c.textContent };
    root.unmount(); await sleep(50);
  }
  console.log(JSON.stringify(res));
})();
""")
    stops = {k: v["fetches"] <= 2 for k, v in r.items()}
    assert not stops["buggy"], r
    assert stops["deps"] and r["deps"]["text"].startswith("u"), r   # loads the user, once
    verify(q, {
        "Pass [id] as the second argument": stops["deps"],
        "Wrap the fetch call in a useCallback": stops["callback"],
        "Call setUser inside a setTimeout": stops["timeout"],
        "Move the fetch call into the component body": stops["body"],
    })
