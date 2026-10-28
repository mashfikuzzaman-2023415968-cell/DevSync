"""Check for fastapi-api-security-05: attack the original route, then each proposed fix."""

CODE = r'''
import warnings
warnings.filterwarnings("ignore")
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, ConfigDict

def build(variant):
    user = {"name": "bob", "is_admin": False}
    app = FastAPI()
    if variant == "remove_field":
        class ProfileUpdate(BaseModel):
            name: str
    elif variant == "forbid":
        class ProfileUpdate(BaseModel):
            model_config = ConfigDict(extra="forbid")
            name: str
            is_admin: bool = False
    else:
        class ProfileUpdate(BaseModel):
            name: str
            is_admin: bool = False
    kwargs = {"response_model": ProfileUpdate} if variant == "response_model" else {}
    route = app.put if variant == "put" else app.patch

    @route("/me", **kwargs)
    def update_me(body: ProfileUpdate):
        user.update(body.model_dump())
        return user

    r = TestClient(app).request("PUT" if variant == "put" else "PATCH", "/me",
                                json={"name": "ann", "is_admin": True})
    return r.status_code, user["is_admin"]

print(json.dumps({v: build(v) for v in ["original", "remove_field", "forbid", "response_model", "put"]}))
'''


def check(ctx, q):
    import json

    got = json.loads(ctx.python(CODE))
    assert got["original"] == [200, True], got  # the attack works on the snippet
    assert got["remove_field"] == [200, False], got  # marked fix: not an admin afterwards
    for variant in ("forbid", "response_model", "put"):
        assert got[variant][1] is True, (variant, got)  # every distractor still lets the attacker in
    opts = q["options"]
    assert opts[q["correct_index"]].startswith("Remove is_admin"), opts
    assert sorted(o.split()[0] for i, o in enumerate(opts) if i != q["correct_index"]) == ["Add", "Add", "Change"], opts
