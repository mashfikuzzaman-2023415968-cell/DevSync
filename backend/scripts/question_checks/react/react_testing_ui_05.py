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
  const { render, screen, act: ract } = require('@testing-library/react');
  const Banner = ({ show }) => (show ? h('p', null, 'Welcome') : null);
  const throws = async (fn) => { try { await fn(); return false; } catch (e) { return true; } };
  render(h(Banner, { show: false }));
  const res = {
    getByThrows: await throws(() => screen.getByText('Welcome')),
    queryIsNull: screen.queryByText('Welcome') === null,
    findThrows: await throws(() => screen.findByText('Welcome', {}, { timeout: 100 })),
  };
  // wrapping render in act changes nothing
  ract(() => { render(h(Banner, { show: false })); });
  res.getByThrowsAfterAct = await throws(() => screen.getByText('Welcome'));
  console.log(JSON.stringify(res));
  process.exit(0);
})();
""",
    )
    assert r["getByThrows"] and r["queryIsNull"], r
    verify(
        q,
        {
            "Use queryByText on line 3": r["queryIsNull"] and r["getByThrows"],
            "Use findByText on line 3": not r["findThrows"],
            "Wrap line 2 in act": not r["getByThrowsAfterAct"],
            "Replace not.toBeInTheDocument with toBeFalsy": not r["getByThrows"],
        },
    )
