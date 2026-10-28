"""Check for fastapi-validation-schemas-03: evaluate every option; only the marked one may raise."""

CODE = r"""
import warnings
warnings.filterwarnings("ignore")
import json
from pydantic import BaseModel, ValidationError

class M(BaseModel):
    n: int

raised = []
for src in json.loads(OPTIONS):
    try:
        eval(src)
        raised.append(False)
    except ValidationError:
        raised.append(True)
print(json.dumps(raised))
"""


def check(ctx, q):
    import json

    got = json.loads(ctx.python(f"OPTIONS = {json.dumps(json.dumps(q['options']))}\n" + CODE))
    want = [i == q["correct_index"] for i in range(4)]
    assert got == want, f"raises per option {got}, expected {want}"
