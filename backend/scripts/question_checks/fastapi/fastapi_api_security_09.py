"""Check for fastapi-api-security-09: attack the route, then each proposed fix."""

CODE = r'''
import warnings
warnings.filterwarnings("ignore")
import json, uuid
from dataclasses import dataclass
from fastapi import FastAPI, Depends, HTTPException, Path
from fastapi.testclient import TestClient

@dataclass
class User:
    org_id: int

def current_user():
    return User(org_id=1)

def build(variant):
    invoices = {"7": {"org_id": 2, "n": "secret"}}  # org 2's invoice
    uid = str(uuid.uuid4())
    invoices[uid] = {"org_id": 2, "n": "secret"}  # uuid ids; this one leaked in a shared link
    app = FastAPI()
    if variant == "scoped":
        @app.get("/orgs/{org_id}/invoices/{invoice_id}")
        def get_invoice(org_id: int, invoice_id: str, user=Depends(current_user)):
            if user.org_id != org_id:
                raise HTTPException(403)
            inv = invoices.get(invoice_id)
            if inv is None or inv["org_id"] != org_id:
                raise HTTPException(404)
            return inv
    else:
        err = 404 if variant == "status404" else 403
        kw = {"invoice_id": str} if False else {}
        if variant == "minlen":
            @app.get("/orgs/{org_id}/invoices/{invoice_id}")
            def get_invoice(org_id: int, invoice_id: str = Path(min_length=1),
                            user=Depends(current_user)):
                if user.org_id != org_id:
                    raise HTTPException(403)
                return invoices[invoice_id]
        else:
            @app.get("/orgs/{org_id}/invoices/{invoice_id}")
            def get_invoice(org_id: int, invoice_id: str, user=Depends(current_user)):
                if user.org_id != org_id:
                    raise HTTPException(err)
                return invoices[invoice_id]
    c = TestClient(app)
    target = uid if variant == "uuid" else "7"
    return c.get(f"/orgs/1/invoices/{target}").status_code, c.get("/orgs/2/invoices/7").status_code

print(json.dumps({v: build(v) for v in ["original", "scoped", "uuid", "status404", "minlen"]}))
'''


def check(ctx, q):
    import json

    got = json.loads(ctx.python(CODE))
    assert got["original"] == [200, 403], got  # the attack works
    assert got["scoped"] == [404, 403], got  # marked fix blocks it
    for variant in ("uuid", "status404", "minlen"):
        assert got[variant][0] == 200, (variant, got)  # every distractor still leaks
    opts = q["options"]
    assert opts[q["correct_index"]].startswith("Look the invoice up by invoice_id and org_id"), opts
