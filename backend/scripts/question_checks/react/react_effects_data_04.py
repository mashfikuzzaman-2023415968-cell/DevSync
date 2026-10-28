import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx, q):
    # same code with a 20 ms interval instead of 1000 ms; about ten ticks happen in 250 ms
    out = ctx.node(
        PRELUDE
        + """
(async () => {
  function Ticker() {
    const [count, setCount] = useState(0);
    useEffect(() => {
      const t = setInterval(() => setCount(count + 1), 20);
      return () => clearInterval(t);
    }, []);
    return h('p', null, count);
  }
  const { c } = mountAsync(h(Ticker));
  await sleep(260);
  console.log(c.textContent);
  process.exit(0);
})();
"""
    )
    ctx.expect_only(q, out)
