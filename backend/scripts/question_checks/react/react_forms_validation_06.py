import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _jsh import PRELUDE, js, verify  # noqa: F401


def check(ctx, q):
    r = js(
        ctx,
        """
const calls = [];
function SignupForm({ save }) {
  const [email] = useState('bad');
  const [error, setError] = useState('');
  function handleSubmit(e) {
    e.preventDefault();
    setError(email.includes('@') ? '' : 'Invalid email');
    if (!error) save(email);
  }
  return h('form', { onSubmit: handleSubmit }, h('p', null, error), h('button', null, 'Send'));
}
const { c } = mount(h(SignupForm, { save: (e) => calls.push(e) }));
click(c.querySelector('button'));
console.log(JSON.stringify({ calls, message: c.querySelector('p').textContent }));
""",
    )
    msg = r["message"] == "Invalid email"
    verify(
        q,
        {
            "save('bad') is called, and": r["calls"] == ["bad"] and msg,
            "save is not called, and the message": r["calls"] == [] and msg,
            "save is not called, and no message": r["calls"] == [] and not msg,
            "save('bad') is called twice": r["calls"] == ["bad", "bad"] and msg,
        },
    )
