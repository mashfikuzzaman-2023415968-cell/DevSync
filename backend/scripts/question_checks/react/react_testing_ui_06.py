from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from run_checks import Ctx

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx: Ctx, q: dict[str, Any]) -> None:
    r = js(
        ctx,
        """
(async () => {
  const rtl = require('@testing-library/react');
  const { render, screen, act: ract, cleanup } = rtl;
  const userEvent = require('@testing-library/user-event').default;
  function Counter() { const [n, setN] = useState(0); return h('button', { onClick: () => setN(n + 1) }, 'Count: ' + n); }
  const throws = (fn) => { try { fn(); return false; } catch (e) { return true; } };
  const res = {};
  // original: click not awaited, expectation right away
  render(h(Counter)); userEvent.click(screen.getByRole('button'));
  res.original = !throws(() => screen.getByText('Count: 1')); await new Promise((r) => setTimeout(r, 50)); cleanup();
  // A: awaited
  render(h(Counter)); await userEvent.click(screen.getByRole('button'));
  res.awaited = !throws(() => screen.getByText('Count: 1')); cleanup();
  // B: different query on line 3, still not awaited
  render(h(Counter)); userEvent.click(screen.getByText('Count: 0'));
  res.otherQuery = !throws(() => screen.getByText('Count: 1')); await new Promise((r) => setTimeout(r, 50)); cleanup();
  // C: expectation wrapped in act, still not awaited
  render(h(Counter)); userEvent.click(screen.getByRole('button'));
  res.actWrapped = !throws(() => { ract(() => { screen.getByText('Count: 1'); }); }); await new Promise((r) => setTimeout(r, 50)); cleanup();
  // D: weaker matcher: the query itself is what throws
  render(h(Counter)); userEvent.click(screen.getByRole('button'));
  res.truthy = !throws(() => { if (!screen.getByText('Count: 1')) throw new Error('falsy'); }); await new Promise((r) => setTimeout(r, 50)); cleanup();
  console.log(JSON.stringify(res));
  process.exit(0);
})();
""",
    )
    assert r["original"] is False and r["awaited"] is True, r
    verify(
        q,
        {
            "Await the call on line 3": r["awaited"],
            "Replace getByRole on line 3": r["otherQuery"],
            "Wrap the expectation on line 4": r["actWrapped"],
            "Replace the matcher on line 4": r["truthy"],
        },
    )
