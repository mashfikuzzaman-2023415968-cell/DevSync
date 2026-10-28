# FastAPI questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/fastapi.md`.

## fastapi-legacy-01

API design and HTTP · difficulty 1 · independent solve passed

What is TestClient (from fastapi.testclient) for?

- A. Deploying
- B. Calling the app in tests without running a server ✔
- C. Load testing
- D. Generating clients

Explanation: TestClient runs the ASGI app in-process, so tests can call routes like a client with no server or network.

Approved by: ______

Correction: ______

## fastapi-legacy-02

Validation and schemas · difficulty 2 · independent solve passed

What does `response_model` on a route do?

- A. Sets the HTTP method
- B. Caches the response
- C. Adds authentication
- D. Validates and filters the response to the declared schema ✔

Explanation: response_model validates the returned data against the declared Pydantic schema, drops fields not in it, and documents it in OpenAPI.

Approved by: ______

Correction: ______

## fastapi-legacy-03

API design and HTTP · difficulty 1 · independent solve passed

How do you declare a path parameter?

- A. @app.get('/items/{item_id}') with an item_id argument ✔
- B. Using a global variable
- C. Using Body()
- D. Using Query()

Explanation: A path parameter is a {name} placeholder in the route path plus a function argument of the same name; FastAPI converts and validates it.

Approved by: ______

Correction: ______

## fastapi-legacy-04

API design and HTTP · difficulty 1 · independent solve passed

What is a common use of FastAPI middleware?

- A. Defining models
- B. Writing migrations
- C. Rendering React
- D. Adding headers, timing or request ids to every request ✔

Explanation: Middleware wraps every request and response, which makes it the place for cross-cutting work such as headers, timing and request ids.

Approved by: ______

Correction: ______

## fastapi-legacy-05

Databases and ORM · difficulty 2 · independent solve passed

What does a dependency with `yield` let you do?

- A. Retry requests
- B. Return multiple values
- C. Run cleanup code after the response (e.g. close a DB session) ✔
- D. Stream files

Explanation: A dependency that yields runs its code after the yield once the response is done, so it is the standard pattern to open and close a database session per request.

Approved by: ______

Correction: ______

## fastapi-legacy-06

API design and HTTP · difficulty 1 · independent solve passed

Which is the right way to read an optional query parameter `q`?

- A. def f(q: str | None = None) ✔
- B. It's not possible
- C. request.json()['q'] only
- D. def f(*, body)

Explanation: A parameter that is not in the path and has a default of None is an optional query parameter; str | None = None marks it optional.

Approved by: ______

Correction: ______

## fastapi-legacy-08

Error handling and debugging · difficulty 1 · independent solve passed

How do you raise a 404 from inside an endpoint?

- A. raise HTTPException(status_code=404) ✔
- B. return 404
- C. print(404)
- D. sys.exit(404)

Explanation: raise HTTPException(status_code=404) stops the endpoint and FastAPI turns it into a 404 response with a JSON detail.

Approved by: ______

Correction: ______

## fastapi-legacy-09

API security · difficulty 1 · independent solve passed

Why should passwords never be returned in a response model?

- A. FastAPI hashes them
- B. They are too long
- C. JSON can't encode them
- D. Response models define exactly what leaves the API; secrets must never be exposed ✔

Explanation: A response model is the allow-list of what leaves the API; leaving password fields out of it prevents leaking secrets or hashes.

Approved by: ______

Correction: ______

## fastapi-legacy-10

Async and performance · difficulty 1 · independent solve passed

Which ASGI server is commonly used to run FastAPI?

- A. Tomcat
- B. Uvicorn ✔
- C. Gunicorn sync workers only
- D. Apache mod_php

Explanation: FastAPI is an ASGI framework; Uvicorn is the ASGI server normally used to run it. Tomcat and mod_php are not ASGI servers.

Approved by: ______

Correction: ______

## fastapi-legacy-11

Validation and schemas · difficulty 1 · independent solve passed

What does FastAPI use Pydantic models for?

- A. Validating and serializing request and response data ✔
- B. Scheduling jobs
- C. Templating HTML
- D. Database migrations

Explanation: FastAPI uses Pydantic models to parse and validate request bodies and to serialise and document responses.

Approved by: ______

Correction: ______

## fastapi-legacy-12

Validation and schemas · difficulty 2 · independent solve passed

What does `model_config = ConfigDict(extra='forbid')` do on a Pydantic v2 model?

- A. Makes all fields optional
- B. Ignores type errors
- C. Rejects input that contains fields not declared on the model ✔
- D. Allows any extra fields

Explanation: extra='forbid' makes validation fail (422) when the input has fields that are not declared; the default is to ignore them.

Approved by: ______

Correction: ______

## fastapi-legacy-13

Validation and schemas · difficulty 2 · independent solve passed

What status code does FastAPI return by default for a request body that fails validation?

- A. 404
- B. 400
- C. 500
- D. 422 ✔

Explanation: Request validation failures return 422 Unprocessable Content with a detail list describing each error.

Approved by: ______

Correction: ______

## fastapi-legacy-14

API design and HTTP · difficulty 1 · independent solve passed

What is FastAPI's Depends() used for?

- A. Defining database columns
- B. Running background tasks
- C. Declaring dependencies (e.g. DB sessions, auth) that are resolved per request ✔
- D. Importing modules

Explanation: Depends declares a dependency (a callable) that FastAPI calls for each request and injects the result, for example a DB session or the current user.

Approved by: ______

Correction: ______

## fastapi-legacy-15

API design and HTTP · difficulty 1 · independent solve passed

How does FastAPI generate interactive API documentation?

- A. From docstrings only
- B. From the OpenAPI schema it builds from routes and type hints ✔
- C. It cannot
- D. From a YAML file you write

Explanation: FastAPI builds an OpenAPI schema from routes, type hints and models and serves Swagger UI and ReDoc from it automatically.

Approved by: ______

Correction: ______

## fastapi-legacy-16

Async and performance · difficulty 2 · independent solve passed

What is the effect of declaring a route with `async def`?

- A. It is cached
- B. It runs on the event loop, so it should not call blocking code directly ✔
- C. It becomes a background task
- D. It runs in a new process

Explanation: An async def route runs on the event loop; calling blocking code in it (sleep, requests, sync DB) stalls all other requests.

Approved by: ______

Correction: ______

## fastapi-api-design-01

API design and HTTP · difficulty 2 · execution check passed

Both routes are registered in the order shown. What does GET /users/me return?

```
1  @app.get("/users/{user_id}")
2  def get_user(user_id: str):
3      return {"route": "by-id"}
4
5  @app.get("/users/me")
6  def get_me():
7      return {"route": "current-user"}
```

- A. {"route": "current-user"}
- B. Status 404
- C. {"route": "by-id"} ✔
- D. Status 422

Explanation: Starlette matches routes in registration order and the first match wins. /users/{user_id} also matches /users/me (user_id='me'), so get_me is never reached. Declare the fixed path /users/me before the parameterised one.

Approved by: ______

Correction: ______

## fastapi-api-design-02

API design and HTTP · difficulty 2 · execution check passed

What does GET /items?tag=a&tag=b return?

```
1  @app.get("/items")
2  def list_items(tag: list[str] = Query(default=[])):
3      return tag
```

- A. ["a", "b"] ✔
- B. ["b"]
- C. ["a"]
- D. Status 422

Explanation: A list[str] query parameter declared with Query() collects every repeated occurrence of the parameter, so both values arrive as a list. Without Query(), a list annotation would be treated as a request body.

Approved by: ______

Correction: ______

## fastapi-api-design-03

API design and HTTP · difficulty 2 · execution check passed

What does GET /files/docs/readme.txt return?

```
1  @app.get("/files/{name}")
2  def read_file(name: str):
3      return {"name": name}
```

- A. {"name": "docs"}
- B. Status 404 ✔
- C. {"name": "docs/readme.txt"}
- D. Status 422

Explanation: A plain {name} path parameter matches one path segment only and never a slash, so /files/docs/readme.txt matches no route and gives 404. Declaring {name:path} would capture the rest of the path.

Approved by: ______

Correction: ______

## fastapi-api-design-04

API design and HTTP · difficulty 2 · independent solve passed

A client times out and automatically repeats the same request. Which HTTP method is not idempotent by definition, so a blind retry could create a duplicate record?

- A. PUT
- B. DELETE
- C. GET
- D. POST ✔

Explanation: GET, PUT and DELETE are defined as idempotent: repeating them leaves the server in the same state. POST (create, trigger an action) has no such guarantee, so retries need protection such as an idempotency key.

Approved by: ______

Correction: ______

## fastapi-api-design-05

API design and HTTP · difficulty 3 · execution check passed

A client calls GET /items (no trailing slash) and does not follow redirects. What does it receive?

```
1  router = APIRouter(prefix="/items")
2
3  @router.get("/")
4  def list_items():
5      return []
6
7  app.include_router(router)
```

- A. Status 200 with an empty list
- B. Status 404 (route not found)
- C. Status 307 redirect to /items/ ✔
- D. Status 405 (method not allowed)

Explanation: The router prefix plus path "/" makes the route /items/. With default settings Starlette's redirect_slashes answers a request for /items with a 307 redirect to /items/ rather than 404 or serving it directly.

Approved by: ______

Correction: ______

## fastapi-api-design-06

API design and HTTP · difficulty 1 · execution check passed

Which request header supplies the value of x_token?

```
1  @app.get("/ping")
2  def ping(x_token: str = Header()):
3      return {"token": x_token}
```

- A. x_token, with the underscore kept exactly as written in the code
- B. Authorization, as the default header for FastAPI parameters
- C. None: Header() reads the value from the query string instead
- D. X-Token, since underscores become hyphens and names are case-insensitive ✔

Explanation: Header() converts underscores in the parameter name to hyphens (convert_underscores=True by default) and header names are case-insensitive, so X-Token is read. Sending x_token or Authorization leaves the parameter missing (422).

Approved by: ______

Correction: ______

## fastapi-api-design-07

API design and HTTP · difficulty 3 · execution check passed

What does GET /items/abc return?

```
1  @app.get("/items/{item_id}")
2  def by_id(item_id: int):
3      return "by-id"
4
5  @app.get("/items/{slug}")
6  def by_slug(slug: str):
7      return "by-slug"
```

- A. "by-slug"
- B. "by-id"
- C. Status 422 ✔
- D. Status 404

Explanation: Routing matches only on the path pattern; both routes match /items/abc and the first, by_id, wins. Its int validation then fails with 422. FastAPI does not fall through to the next route when validation fails.

Approved by: ______

Correction: ______

## fastapi-api-design-08

API design and HTTP · difficulty 1 · independent solve passed

A mobile app may repeat POST /payments after a network timeout, and a customer must never be charged twice. Which server-side design best achieves this?

- A. Switch the endpoint to GET so that repeated requests are always safe
- B. Return 200 instead of 201 so that clients no longer retry the request
- C. Require an Idempotency-Key header and replay the stored result for a repeated key ✔
- D. Raise the server timeout so that clients never time out and retry

Explanation: The server cannot tell a retry from a new payment unless the client labels it. Storing the result under an idempotency key makes a repeated request return the original outcome without charging again. Changing method, status or timeouts does not remove the duplicate risk.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-01

Validation and schemas · difficulty 1 · independent solve passed

Which Pydantic v2 method builds a model instance directly from a JSON string?

- A. Item.model_validate_json(raw) ✔
- B. Item.from_json(raw)
- C. Item.load_json(raw)
- D. Item.model_parse(raw)

Explanation: model_validate_json parses and validates a JSON string in one step (Pydantic v2). from_json, load_json and model_parse do not exist on BaseModel.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-02

Validation and schemas · difficulty 1 · execution check passed

What does this code print?

```
1  class Item(BaseModel):
2      name: str
3      price: float | None = None
4
5  print(Item(name="pen").price)
```

- A. 0
- B. 0.0
- C. A ValidationError
- D. None ✔

Explanation: price has a default of None, so omitting it is valid and the attribute is None. Nothing is coerced to 0 and no error is raised.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-03

Validation and schemas · difficulty 3 · execution check passed

With Pydantic v2 default settings, which call raises a ValidationError?

```
1  class M(BaseModel):
2      n: int
```

- A. M(n="5")
- B. M(n=5.0)
- C. M(n=5.5) ✔
- D. M(n=True)

Explanation: Default (lax) mode converts the string "5", the whole float 5.0 and the bool True to int. A float with a fractional part such as 5.5 cannot be converted without losing data, so it is rejected.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-04

Validation and schemas · difficulty 3 · execution check passed

What JSON body does GET /item return?

```
1  class Item(BaseModel):
2      name: str
3      tag: str = "none"
4
5  @app.get("/item", response_model=Item, response_model_exclude_unset=True)
6  def get_item():
7      return Item(name="pen")
```

- A. {"name": "pen", "tag": "none"}
- B. {"name": "pen"} ✔
- C. {"name": "pen", "tag": null}
- D. {"tag": "none"}

Explanation: response_model_exclude_unset=True leaves out fields that were never explicitly set on the returned model. tag only has its default value, so it is dropped and only name is sent.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-05

Validation and schemas · difficulty 3 · execution check passed

A client posts {"name": "pen"}. What happens?

```
1  class Item(BaseModel):
2      name: str
3      note: str | None
4
5  @app.post("/items")
6  def create(item: Item):
7      return item
```

- A. Status 422 ✔
- B. {"name": "pen", "note": null}
- C. {"name": "pen", "note": ""}
- D. Status 400

Explanation: In Pydantic v2 a field annotated str | None without a default is required but nullable. Omitting note is a validation error (422). Write note: str | None = None to make it optional.

Approved by: ______

Correction: ______

## fastapi-validation-schemas-06

Validation and schemas · difficulty 2 · execution check passed

A client posts {"name": "pen", "price": 5, "discount": 50}. What does it receive?

```
1  class Item(BaseModel):
2      name: str
3      price: int
4
5  @app.post("/items")
6  def create(item: Item):
7      return item
```

- A. Status 422
- B. {"name": "pen", "price": 5} ✔
- C. {"name": "pen", "price": 5, "discount": 50}
- D. Status 400

Explanation: By default Pydantic ignores fields that are not declared, so the request succeeds and discount is dropped. Only extra='forbid' on the model would make it fail with 422.

Approved by: ______

Correction: ______

## fastapi-authn-authz-01

Authentication and authorization · difficulty 1 · independent solve passed

How should an API store users' passwords?

- A. Encrypted with AES so they can be decrypted at login
- B. As a SHA-256 hash without a salt
- C. As a hash from a slow, salted algorithm such as Argon2 or bcrypt ✔
- D. Base64-encoded

Explanation: Passwords must be stored so that nobody, including the operator, can recover them: a slow salted password hash. Encryption is reversible, unsalted fast hashes fall to rainbow tables and GPUs, and Base64 is only an encoding.

Approved by: ______

Correction: ______

## fastapi-authn-authz-02

Authentication and authorization · difficulty 1 · independent solve passed

A logged-in user without the admin role calls an admin-only endpoint. Which status code fits best?

- A. 401 Unauthorized
- B. 400 Bad Request
- C. 403 Forbidden ✔
- D. 422 Unprocessable Content

Explanation: The caller is authenticated but not permitted, which is 403. 401 means credentials are missing or invalid; 400 and 422 describe malformed input.

Approved by: ______

Correction: ______

## fastapi-authn-authz-03

Authentication and authorization · difficulty 1 · independent solve passed

What does the signature of a signed (not encrypted) JWT guarantee?

- A. The payload is hidden from anyone who holds the token
- B. The token stops working after the user logs out
- C. The password supplied at login was correct
- D. The token content was not altered since it was issued by the holder of the key ✔

Explanation: A signature proves integrity and origin: any change to header or payload breaks it. A signed JWT is only Base64-encoded, so its payload is readable, and logout or password checks are separate mechanisms.

Approved by: ______

Correction: ______

## fastapi-authn-authz-04

Authentication and authorization · difficulty 1 · independent solve passed

Which registered JWT claim holds the time after which the token must be rejected?

- A. iat
- B. nbf
- C. sub
- D. exp ✔

Explanation: exp is the expiration time. iat is when the token was issued, nbf is the time before which it must not be accepted, and sub identifies the subject.

Approved by: ______

Correction: ______

## fastapi-authn-authz-05

Authentication and authorization · difficulty 2 · execution check passed

A client calls GET /me without an Authorization header. What does it receive?

```
1  oauth2 = OAuth2PasswordBearer(tokenUrl="login")
2
3  @app.get("/me")
4  def me(token: str = Depends(oauth2)):
5      return {"token": token}
```

- A. Status 403
- B. Status 422
- C. {"token": null}
- D. Status 401 ✔

Explanation: OAuth2PasswordBearer raises 401 'Not authenticated' (with a WWW-Authenticate: Bearer header) when the header is missing, before the endpoint body runs.

Approved by: ______

Correction: ______

## fastapi-authn-authz-06

Authentication and authorization · difficulty 2 · independent solve passed

The admin screen of a web app is hidden from normal users in the user interface. What else is needed to protect the admin API?

- A. Nothing, because the route is not linked anywhere
- B. A role check on every admin endpoint on the server ✔
- C. A longer, harder-to-guess URL for the admin route
- D. A CORS rule that only allows the admin screen

Explanation: Anything done in the client can be bypassed: users can call the API directly. Authorization must be enforced server-side on each endpoint, for example with a dependency that checks the user's role. Hidden or obscure URLs and CORS do not stop direct requests.

Approved by: ______

Correction: ______

## fastapi-authn-authz-07

Authentication and authorization · difficulty 2 · independent solve passed

A user logs out, but their JWT access token (valid for 7 days) still works. Why?

- A. The token is stateless and stays valid until it expires unless a revocation list exists ✔
- B. JWTs cannot be signed with a secret key, so logout cannot be enforced
- C. The browser caches the token on the server side until the cache is flushed
- D. FastAPI keeps every issued token in memory and forgets it only on restart

Explanation: A server that only verifies signature and exp has no record of issued tokens, so logging out on the client does not invalidate them. Use short lifetimes, refresh tokens, and a revocation or session check when immediate invalidation is needed.

Approved by: ______

Correction: ______

## fastapi-authn-authz-08

Authentication and authorization · difficulty 2 · independent solve passed

GET /orders/{order_id} needs a valid login and returns the order. User B can read user A's order by using its id. Which control is missing?

- A. A check that the order belongs to the current user or that the user may see it ✔
- B. Hashing the order id inside the URL so that it looks less guessable
- C. Requiring HTTPS for every request to this endpoint
- D. Rate limiting the endpoint to a few requests per minute

Explanation: This is broken object-level authorization: being logged in is not enough, the code must verify access to the specific object. The other controls do not decide who may read which order.

Approved by: ______

Correction: ______

## fastapi-authn-authz-09

Authentication and authorization · difficulty 3 · execution check passed

An anonymous client sends GET /admin?role=x with no token. What does it receive?

```
1   def current_user():
2       raise HTTPException(status_code=401)
3 
4   def require_role(role: str):
5       def checker(user=Depends(current_user)):
6           if user.role != role:
7               raise HTTPException(status_code=403)
8           return user
9       return checker
10
11  @app.get("/admin")
12  def admin_panel(user=Depends(require_role)):
13      return {"ok": True}
```

- A. {"ok": true} ✔
- B. Status 401
- C. Status 403
- D. Status 422

Explanation: Depends(require_role) forgets the call parentheses, so FastAPI treats require_role itself as the dependency: role becomes a query parameter and the returned checker function is injected as user. The checker and current_user never run, so the admin route is open.

Approved by: ______

Correction: ______

## fastapi-authn-authz-10

Authentication and authorization · difficulty 3 · independent solve passed

A server decodes incoming JWTs using the algorithm named in each token's own header. What does this allow?

- A. Expired tokens to be replayed by exploiting small differences in clock skew
- B. Cross-site request forgery through cookies sent automatically by the browser
- C. An attacker can pick the algorithm none and forge a token that the server accepts ✔
- D. SQL injection through the sub claim when the user is looked up

Explanation: The token is attacker-controlled, so its header must not decide how it is verified. Servers should pin an allow-list of algorithms (and key types). This is the classic alg=none / algorithm-confusion forgery.

Approved by: ______

Correction: ______

## fastapi-authn-authz-11

Authentication and authorization · difficulty 3 · execution check passed

A client with no Authorization header posts {"qty": "many"}. What status does it get?

```
1  oauth2 = OAuth2PasswordBearer(tokenUrl="login")
2
3  class Order(BaseModel):
4      qty: int
5
6  @app.post("/orders")
7  def create(order: Order, token: str = Depends(oauth2)):
8      return {"qty": order.qty}
```

- A. Status 403
- B. Status 401 ✔
- C. Status 422
- D. Status 400

Explanation: FastAPI resolves dependencies before it validates body parameters, and the security dependency raises HTTPException 401 immediately. The body error is never reported, which is also what you want: do not tell anonymous callers about your schema.

Approved by: ______

Correction: ______

## fastapi-authn-authz-12

Authentication and authorization · difficulty 2 · independent solve passed

Which design is safest for a password-reset link?

- A. A random single-use token stored hashed that expires within minutes ✔
- B. The Base64 of the user id plus the time of the reset request
- C. An MD5 hash of the email address of the account being reset
- D. A 4-digit code that stays valid for 24 hours after it is sent

Explanation: Reset tokens must be unguessable, single-use and short-lived, and stored hashed so a database leak does not leak working links. Values derived from known data or short numeric codes can be guessed.

Approved by: ______

Correction: ______

## fastapi-databases-orm-01

Databases and ORM · difficulty 1 · independent solve passed

In SQLAlchemy, which call makes the changes of the current transaction permanent?

- A. session.flush()
- B. session.refresh(obj)
- C. session.expunge_all()
- D. session.commit() ✔

Explanation: commit() ends the transaction and persists its changes. flush() only sends pending SQL inside the still-open transaction, refresh() reloads an object, expunge_all() detaches objects.

Approved by: ______

Correction: ______

## fastapi-databases-orm-02

Databases and ORM · difficulty 1 · independent solve passed

Which SQLAlchemy 2.0 call loads a User by its primary key?

- A. session.find(User, user_id)
- B. User.objects.get(id=user_id)
- C. session.fetch_one(User, user_id)
- D. session.get(User, user_id) ✔

Explanation: Session.get(Entity, pk) is the primary-key lookup in 2.0. find and fetch_one do not exist, and Model.objects.get is the Django ORM.

Approved by: ______

Correction: ______

## fastapi-databases-orm-03

Databases and ORM · difficulty 2 · execution check passed

POST /items?name=pen returns 200. What does a later GET /items return?

```
1   def get_db():
2       db = SessionLocal()
3       try:
4           yield db
5       finally:
6           db.close()
7 
8   @app.post("/items")
9   def create_item(name: str, db: Session = Depends(get_db)):
10      db.add(Item(name=name))
11      return {"ok": True}
12
13  @app.get("/items")
14  def list_items(db: Session = Depends(get_db)):
15      return [i.name for i in db.scalars(select(Item))]
```

- A. [] ✔
- B. ["pen"]
- C. Status 500
- D. Status 422

Explanation: Nothing calls commit(). The session only holds the new Item in a transaction; db.close() in the dependency rolls it back, so the row is never stored and the list stays empty. Add db.commit() after db.add().

Approved by: ______

Correction: ______

## fastapi-databases-orm-04

Databases and ORM · difficulty 3 · execution check passed

The author table has 3 rows and Author.books is a relationship() with default settings. How many SELECT statements does this code send?

```
1  authors = db.scalars(select(Author)).all()
2  titles = []
3  for author in authors:
4      titles += [b.title for b in author.books]
```

- A. 1
- B. 3
- C. 4 ✔
- D. 6

Explanation: Lazy loading is the default: one SELECT loads the authors, then each author.books access triggers its own SELECT, 1 + 3 = 4 (the N+1 problem). selectinload(Author.books) would reduce this to 2.

Approved by: ______

Correction: ______

## fastapi-databases-orm-05

Databases and ORM · difficulty 3 · independent solve passed

An async endpoint using AsyncSession reads order.items (a relationship) after the query and fails with MissingGreenlet. What is the right fix?

- A. Close the session before the attribute is accessed in the endpoint
- B. Call session.expire_all() right before the attribute is accessed
- C. Read the attribute inside loop.run_in_executor on a worker thread
- D. Load it in the query, for example with selectinload(Order.items) ✔

Explanation: With asyncio, a lazy load would need implicit blocking I/O, which is not allowed. Eager-load what you need in the query (selectinload or joinedload), or await it explicitly. Closing or expiring the session makes it worse, and threads do not help.

Approved by: ______

Correction: ______

## fastapi-databases-orm-06

Databases and ORM · difficulty 2 · independent solve passed

A module-level db = SessionLocal() is shared by all requests. What is the main risk?

- A. The database refuses to open a second connection for the same process
- B. Concurrent requests share one transaction, so they can roll back each other's changes ✔
- C. Every query runs about twice as slowly because the session is global
- D. Pydantic validation silently stops working for the shared session

Explanation: A Session is not safe to share between concurrent requests: they would use the same transaction, identity map and failure state. Create one session per request, typically in a yield dependency.

Approved by: ______

Correction: ______

## fastapi-async-performance-01

Async and performance · difficulty 1 · independent solve passed

Which FastAPI feature runs a small function after the response has been sent, such as a confirmation email?

- A. Query
- B. APIRouter
- C. BackgroundTasks ✔
- D. TestClient

Explanation: A BackgroundTasks parameter lets the endpoint schedule functions that run after the response is sent, so the client does not wait for them.

Approved by: ______

Correction: ______

## fastapi-async-performance-02

Async and performance · difficulty 2 · execution check passed

Two clients call GET /slow at the same moment on a single worker. Roughly how long until both have their response?

```
1  @app.get("/slow")
2  async def slow():
3      time.sleep(1)
4      return {"ok": True}
```

- A. About 1 second
- B. About 2 seconds ✔
- C. About 0.5 seconds
- D. Under 0.1 seconds

Explanation: time.sleep blocks the event loop inside an async def, so the second request cannot start until the first finishes: about 2 s. With await asyncio.sleep(1) both would finish in about 1 s.

Approved by: ______

Correction: ______

## fastapi-async-performance-03

Async and performance · difficulty 1 · independent solve passed

A nightly report takes 20 minutes and must not be lost if the API process restarts midway. Where should it run?

- A. In FastAPI BackgroundTasks, because they run after the response
- B. In a separate worker fed by a durable task queue such as Celery or ARQ ✔
- C. In an async def endpoint that awaits it before responding
- D. In a thread started from inside the endpoint

Explanation: BackgroundTasks run inside the API process, so they die with it and have no retries or visibility. Long or critical jobs belong in a task queue with its own workers and durable storage.

Approved by: ______

Correction: ______

## fastapi-async-performance-04

Async and performance · difficulty 2 · independent solve passed

An endpoint does CPU-heavy image processing in pure Python. Which change most directly adds true parallelism across requests?

- A. Declare the endpoint as async def so it uses every core
- B. Increase the size of the thread pool
- C. Add await asyncio.sleep(0) inside the loop
- D. Run several worker processes, for example uvicorn --workers or gunicorn ✔

Explanation: Pure-Python CPU work is limited by the GIL: async def and threads do not run it in parallel. Separate processes can use several cores. (Offloading to a process pool or task queue also works.)

Approved by: ______

Correction: ______

## fastapi-error-handling-01

Error handling and debugging · difficulty 1 · independent solve passed

Which feature registers one function that turns a custom exception into a JSON response for the whole app?

- A. @app.middleware("http") on every route
- B. @app.exception_handler(MyError) ✔
- C. @app.on_event("shutdown")
- D. @app.get("/error")

Explanation: exception_handler maps an exception class to a handler returning a Response, so routes can simply raise the exception. The others do not provide that mapping.

Approved by: ______

Correction: ______

## fastapi-error-handling-02

Error handling and debugging · difficulty 2 · execution check passed

What JSON body does the client receive?

```
1  @app.post("/users")
2  def create_user():
3      raise HTTPException(status_code=409, detail={"code": "duplicate"})
```

- A. {"code": "duplicate"}
- B. {"error": {"code": "duplicate"}}
- C. {"detail": {"code": "duplicate"}} ✔
- D. {"detail": "duplicate"}

Explanation: HTTPException's detail can be any JSON-serialisable value; FastAPI wraps it under the key detail, so the dict is nested unchanged.

Approved by: ______

Correction: ______

## fastapi-error-handling-03

Error handling and debugging · difficulty 2 · independent solve passed

A production endpoint crashes with an unexpected exception. Which handling is best?

- A. Return the traceback in the response body for easier reports
- B. Log the traceback with a request id on the server and return a generic 500 message ✔
- C. Catch it and return 200 with an empty body so clients keep working
- D. Catch it with except: pass so the logs stay clean

Explanation: Operators need the detail (logged server-side, correlated by request id); clients should get only a generic message, since tracebacks leak internals and masking errors as success hides failures.

Approved by: ______

Correction: ______

## fastapi-error-handling-04

Error handling and debugging · difficulty 3 · execution check passed

What status does GET /items/2 return?

```
1   DB = {1: "pen"}
2 
3   @app.get("/items/{item_id}")
4   def get_item(item_id: int):
5       try:
6           if item_id not in DB:
7               raise HTTPException(status_code=404, detail="missing")
8           return {"item": DB[item_id]}
9       except Exception:
10          raise HTTPException(status_code=500, detail="failed")
```

- A. Status 404
- B. Status 200
- C. Status 500 ✔
- D. Status 422

Explanation: HTTPException is a subclass of Exception, so the broad except Exception catches the 404 that was just raised and replaces it with a 500. Catch specific exceptions, or re-raise HTTPException.

Approved by: ______

Correction: ______

## fastapi-error-handling-05

Error handling and debugging · difficulty 3 · execution check passed

A client calls GET /no-such-route, which no route matches. What JSON body does it get?

```
1  from fastapi import FastAPI, HTTPException
2  from fastapi.responses import JSONResponse
3
4  app = FastAPI()
5
6  @app.exception_handler(HTTPException)
7  async def custom(request, exc):
8      return JSONResponse({"custom": exc.detail}, status_code=exc.status_code)
```

- A. {"detail": "Not Found"} ✔
- B. {"custom": "Not Found"}
- C. An empty body with status 404
- D. Plain text: Internal Server Error

Explanation: The 404 for an unknown route is raised by Starlette's own HTTPException, the parent class of FastAPI's. A handler registered for fastapi.HTTPException does not catch it, so the default body is used. Register the handler for starlette.exceptions.HTTPException to cover both.

Approved by: ______

Correction: ______

## fastapi-error-handling-06

Error handling and debugging · difficulty 2 · execution check passed

A client calls GET /search with no query string. What is the loc of the first item of the response's detail list?

```
1  @app.get("/search")
2  def search(q: str):
3      return {"q": q}
```

- A. ["body", "q"]
- B. ["path", "q"]
- C. ["q"]
- D. ["query", "q"] ✔

Explanation: Validation errors report where the problem is: first the source (query, path, header, cookie or body), then the field name. A missing query parameter gives ["query", "q"].

Approved by: ______

Correction: ______

## fastapi-api-security-01

API security · difficulty 1 · independent solve passed

Where should a deployed API keep its JWT signing key and database password?

- A. In environment variables or a secrets manager, never committed to git ✔
- B. In a .env file committed to the repository for convenience
- C. Hard-coded in settings.py with a note to rotate it later
- D. In the frontend bundle so the browser can sign tokens

Explanation: Secrets must stay out of source control and client code: inject them at deploy time from the environment or a secrets manager so they can be rotated and access-controlled.

Approved by: ______

Correction: ______

## fastapi-api-security-02

API security · difficulty 1 · independent solve passed

Which control most directly limits password guessing against POST /login?

- A. Serving the whole API over HTTPS only, with HSTS enabled
- B. Rate limiting by account and IP address, with backoff or lockout ✔
- C. A strict CORS allow-list that names only the official frontend
- D. Hiding the login route from the generated OpenAPI documentation

Explanation: Brute force is about the number of attempts, so attempts must be throttled. HTTPS protects traffic in transit, CORS only affects browsers, and an undocumented route is still reachable.

Approved by: ______

Correction: ______

## fastapi-api-security-03

API security · difficulty 2 · execution check passed

The users table holds ann and bob. What does GET /users with the query parameter name set to x' OR '1'='1 return?

```
1  @app.get("/users")
2  def find_user(name: str, db: Session = Depends(get_db)):
3      query = text(f"SELECT name FROM users WHERE name = '{name}'")
4      return [row[0] for row in db.execute(query)]
```

- A. ["ann", "bob"] ✔
- B. []
- C. Status 422
- D. Status 500

Explanation: The f-string pastes input into the SQL, which becomes WHERE name = 'x' OR '1'='1', true for every row: SQL injection. Use bound parameters, text("... WHERE name = :name") with params, or the ORM expression language.

Approved by: ______

Correction: ______

## fastapi-api-security-04

API security · difficulty 2 · independent solve passed

An API allows only https://app.example.com in its CORS settings. Which statement is true?

- A. It is enforced by browsers, so a script on another server can still call the API ✔
- B. It authenticates callers, so other origins can never get data
- C. It encrypts traffic between browser and API
- D. The server rejects every request from other origins before routing

Explanation: CORS is a browser rule about which web origins may read responses. curl or another server is not bound by it, so it is no replacement for authentication and authorization.

Approved by: ______

Correction: ______

## fastapi-api-security-05

API security · difficulty 3 · execution check passed

Any logged-in user can send {"name": "ann", "is_admin": true} to PATCH /me and become an admin. Which change fixes it?

```
1  class ProfileUpdate(BaseModel):
2      name: str
3      is_admin: bool = False
4
5  @app.patch("/me")
6  def update_me(body: ProfileUpdate):
7      user.update(body.model_dump())
8      return user
```

- A. Add model_config = ConfigDict(extra='forbid') to ProfileUpdate
- B. Remove is_admin from ProfileUpdate and change it only through admin-only code ✔
- C. Add response_model=ProfileUpdate to the route
- D. Change @app.patch to @app.put

Explanation: This is mass assignment: a client-writable schema contains a privileged field. The field must not be in the input model. extra='forbid' does nothing because is_admin is declared, response_model only filters output, and the HTTP method changes nothing.

Approved by: ______

Correction: ______

## fastapi-api-security-06

API security · difficulty 1 · independent solve passed

GET /preview?url=... fetches the given URL on the server and returns its text. Which risk is most serious?

- A. SQL injection through the URL string
- B. Clickjacking of the preview page
- C. Any website being able to read the response because of CORS
- D. Attackers can make the server request internal addresses such as cloud metadata (SSRF) ✔

Explanation: A user-controlled URL fetched from inside your network is server-side request forgery: it can reach services and metadata endpoints that outsiders cannot. Mitigate with allow-lists, blocking private ranges and no redirects.

Approved by: ______

Correction: ______

## fastapi-api-security-07

API security · difficulty 2 · independent solve passed

A list endpoint accepts ?limit= with no upper bound. Which problem does this create and how do you fix it?

- A. Callers can request huge pages and exhaust resources; cap it with Query(le=100) ✔
- B. Callers can inject SQL; escape the value by hand
- C. Responses may be cached forever; add a Cache-Control header
- D. Tokens may leak; rotate the signing key

Explanation: Unbounded page sizes allow unrestricted resource consumption, a classic API risk. Validate and cap pagination parameters, for example limit: int = Query(20, ge=1, le=100).

Approved by: ______

Correction: ______

## fastapi-async-performance-05

Async and performance · difficulty 3 · execution check passed

What does this program print when it runs?

```
1  async def job(name, delay, fail=False):
2      await asyncio.sleep(delay)
3      if fail:
4          raise ValueError(name)
5      print(name, "done")
6
7  async def main():
8      try:
9          await asyncio.gather(job("a", 0.1, True), job("b", 0.3))
10     except ValueError as e:
11         print("caught", e)
12     await asyncio.sleep(0.5)
13
14 asyncio.run(main())
```

- A. caught a
- B. caught a, then b done ✔
- C. b done, then caught a
- D. The ValueError escapes main() and the program crashes

Explanation: gather() re-raises the first exception immediately, but without return_exceptions it does not cancel the other awaitables. Job b keeps running and prints "b done" during the final sleep. Use a TaskGroup or cancel explicitly if siblings must stop.

Approved by: ______

Correction: ______

## fastapi-async-performance-06

Async and performance · difficulty 3 · execution check passed

One worker with default settings serves these routes. A load test fires 50 simultaneous requests at /a, and later 50 simultaneous requests at /b. About how long does each batch take?

```
1  @app.get("/a")
2  def a():
3      time.sleep(0.1)
4      return {"ok": True}
5
6  @app.get("/b")
7  async def b():
8      time.sleep(0.1)
9      return {"ok": True}
```

- A. About 0.1 s for /a and about 0.1 s for /b
- B. About 0.1 s for /a and about 5 s for /b
- C. About 0.2 s for /a and about 5 s for /b ✔
- D. About 5 s for /a and about 5 s for /b

Explanation: Sync def routes run in the threadpool, whose default limit is 40 threads, so 50 requests need two waves (about 0.2 s). The async def route blocks the event loop itself, so its 50 sleeps run strictly one after another (about 5 s).

Approved by: ______

Correction: ______

## fastapi-async-performance-07

Async and performance · difficulty 3 · execution check passed

After every POST /export the client gets its response at once, but all other requests then hang for about 3 seconds. What is the cause?

```
1  async def build_report():
2      time.sleep(3)
3
4  @app.post("/export")
5  async def export(bg: BackgroundTasks):
6      bg.add_task(build_report)
7      return {"queued": True}
```

- A. build_report is async def but blocks, so it runs on the event loop; a plain def task would run in the threadpool ✔
- B. BackgroundTasks run before the response is sent, so the worker is busy until they finish
- C. Making export a plain def would move build_report to a worker thread and fix the stall
- D. BackgroundTasks keep the request's resources locked until the task ends

Explanation: Starlette awaits async background tasks directly on the event loop, and runs plain def tasks in the threadpool. A blocking call inside an async def task therefore freezes the loop after the response. The route's own sync/async form does not change where the task runs.

Approved by: ______

Correction: ______

## fastapi-api-security-08

API security · difficulty 3 · execution check passed

A single-page app on app.example.com authenticates with a session cookie. A page on evil.example sends a credentialed request with that cookie to this API. What happens?

```
1  app.add_middleware(
2      CORSMiddleware,
3      allow_origins=["*"],
4      allow_credentials=True,
5  )
```

- A. Browsers reject the wildcard together with credentials, so the request is blocked
- B. The API answers with Access-Control-Allow-Origin "*", which browsers refuse for credentialed requests
- C. Only app.example.com is allowed because credentials restrict a wildcard to the page's own site
- D. The API echoes evil.example as the allowed origin with credentials, so that page can read the response ✔

Explanation: When a cookie is sent, Starlette's CORSMiddleware does not answer with "*"; it reflects the caller's Origin and sets Allow-Credentials true. The wildcard plus credentials combination therefore lets any site read authenticated responses. List explicit origins instead.

Approved by: ______

Correction: ______

## fastapi-api-security-09

API security · difficulty 3 · execution check passed

A user of organisation 1 requests /orgs/1/invoices/<id> with the id of an invoice that belongs to organisation 2, and gets it. Which change closes the hole?

```
1  @app.get("/orgs/{org_id}/invoices/{invoice_id}")
2  def get_invoice(org_id: int, invoice_id: str,
3                  user=Depends(current_user)):
4      if user.org_id != org_id:
5          raise HTTPException(403)
6      return INVOICES[invoice_id]
```

- A. Make invoice ids random UUIDs, so they cannot be guessed
- B. Look the invoice up by invoice_id and org_id together and return 404 when it is not found ✔
- C. Return 404 instead of 403 on line 5, so org existence is not revealed
- D. Declare invoice_id with Path(min_length=8) so malformed ids are rejected

Explanation: The org check passes because the path org_id is the caller's own; the invoice id is never tied to it (an IDOR). Scope the lookup to the verified org. Random ids only hide the problem: a leaked or shared id still works. Status codes and format validation do not enforce ownership.

Approved by: ______

Correction: ______

## fastapi-api-security-10

API security · difficulty 3 · execution check passed

This login-complete route tries to allow only same-site redirects. Which value of the next query parameter still sends the browser to another host?

```
1  @app.get("/login/done")
2  def done(next: str = "/"):
3      if not next.startswith("/"):
4          next = "/"
5      return RedirectResponse(next)
```

- A. https://evil.example/x
- B. evil.example.net/x
- C. //evil.example/x ✔
- D. javascript:alert(1)

Explanation: A leading "//" is a protocol-relative URL: it starts with "/" so the check passes, and the browser treats evil.example as the host. Absolute URLs and javascript: values fail the check. Safer: parse the value and require an empty scheme and netloc, or map names to known paths.

Approved by: ______

Correction: ______
