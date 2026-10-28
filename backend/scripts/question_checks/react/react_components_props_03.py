import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: E402,F401

def check(ctx, q):
    out = ctx.node("""
const React = require('react'); const h = React.createElement;
function Inbox(p) { return h('div', null, p.messages.length && h('p', null, 'You have mail')); }
console.log(require('react-dom/server').renderToStaticMarkup(h(Inbox, { messages: [] })));
""")
    ctx.expect_only(q, out)
