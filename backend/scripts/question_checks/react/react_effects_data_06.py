import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    r = js(ctx, """
(async () => {
  const delays = { 1: 120, 2: 10 };
  globalThis.fetch = (url) => { const id = Number(url.split('/').pop());
    return new Promise((res) => setTimeout(() => res({ json: () => Promise.resolve({ name: 'user' + id }) }), delays[id])); };
  const view = (u) => h('p', null, u ? u.name : '...');
  const variants = {
    buggy: ({ id }) => { const [u, setUser] = useState(null);
      useEffect(() => { fetch('/api/users/' + id).then((r) => r.json()).then(setUser); }, [id]); return view(u); },
    ignore: ({ id }) => { const [u, setUser] = useState(null);
      useEffect(() => { let ignore = false;
        fetch('/api/users/' + id).then((r) => r.json()).then((x) => { if (!ignore) setUser(x); });
        return () => { ignore = true; }; }, [id]); return view(u); },
    nodeps: ({ id }) => { const [u, setUser] = useState(null);
      useEffect(() => { fetch('/api/users/' + id).then((r) => r.json()).then(setUser); }, []); return view(u); },
    callback: ({ id }) => { const [u, setUser] = useState(null); const set = useCallback((x) => setUser(x), []);
      useEffect(() => { fetch('/api/users/' + id).then((r) => r.json()).then(set); }, [id]); return view(u); },
    asyncEffect: ({ id }) => { const [u, setUser] = useState(null);
      useEffect(async () => { const r = await fetch('/api/users/' + id); setUser(await r.json()); }, [id]); return view(u); },
  };
  const res = {};
  for (const [name, C] of Object.entries(variants)) {
    const { c, root } = mountAsync(h(C, { id: 1 }));
    await sleep(20);
    root.render(h(C, { id: 2 }));
    await sleep(300);
    res[name] = c.textContent;
    root.unmount(); await sleep(20);
  }
  console.log(JSON.stringify(res));
})();
""")
    ok = {k: v == "user2" for k, v in r.items()}   # correct = shows the user for id 2
    assert not ok["buggy"] and r["buggy"] == "user1", r
    verify(q, {
        "Set a local ignore flag": ok["ignore"],
        "Remove id from the dependency array": ok["nodeps"],
        "Wrap setUser in useCallback": ok["callback"],
        "Make the effect callback async": ok["asyncEffect"],
    })
