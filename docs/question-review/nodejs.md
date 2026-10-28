# Node.js questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/nodejs.md`.

## nodejs-legacy-01

API building (Express) · difficulty 1 · independent solve passed

What does middleware mean in Express?

- A. A database layer
- B. A template engine
- C. A load balancer
- D. Functions that run in order on a request and can modify it or end the response ✔

Explanation: Middleware functions sit between the request and the final handler. Each receives (req, res, next), may change req or res, and either ends the response or calls next().

Approved by: ______

Correction: ______

## nodejs-legacy-03

Async and the event loop · difficulty 2 · independent solve passed

Why use streams for large files?

- A. They are required for HTTP
- B. They encrypt data
- C. They compress automatically
- D. They process data in chunks instead of loading it all into memory ✔

Explanation: Streams process data in chunks, so memory use stays flat for large files and processing can start before the whole file is read. They do not compress or encrypt by themselves.

Approved by: ______

Correction: ______

## nodejs-legacy-04

Security basics · difficulty 2 · independent solve passed

What does `npm ci` do differently from `npm install`?

- A. Only installs dev dependencies
- B. Installs exactly from the lock file and fails if it doesn't match package.json ✔
- C. Publishes the package
- D. Updates every dependency

Explanation: npm ci installs exactly what package-lock.json lists, deletes node_modules first and fails if the lock file and package.json disagree. This gives reproducible, tamper-evident installs, which matters for supply-chain safety.

Approved by: ______

Correction: ______

## nodejs-legacy-08

Security basics · difficulty 1 · independent solve passed

What does `process.env` contain?

- A. Command history
- B. The process's environment variables ✔
- C. Open files
- D. The installed packages

Explanation: process.env holds the process's environment variables, the usual place for configuration and secrets that must not be committed to the repository.

Approved by: ______

Correction: ______

## nodejs-legacy-09

Security basics · difficulty 1 · independent solve passed

What is the purpose of package-lock.json?

- A. To list scripts
- B. To record exact dependency versions so installs are reproducible ✔
- C. To store environment variables
- D. To lock the source code

Explanation: package-lock.json records the exact resolved version (and integrity hash) of every dependency, so every install produces the same tree and unexpected upgrades are visible in review.

Approved by: ______

Correction: ______

## nodejs-legacy-10

Async and the event loop · difficulty 2 · independent solve passed

What is the `worker_threads` module for?

- A. Running CPU-heavy JavaScript in parallel threads ✔
- B. Scheduling cron jobs
- C. Managing HTTP workers
- D. Connecting to databases

Explanation: worker_threads runs JavaScript in separate threads with their own event loop, which keeps CPU-heavy work off the main thread.

Approved by: ______

Correction: ______

## nodejs-legacy-11

Async and the event loop · difficulty 1 · independent solve passed

What makes Node.js well suited to I/O-heavy servers?

- A. Its non-blocking, event-driven I/O model ✔
- B. It runs only on Linux
- C. It compiles to native code
- D. It is multi-threaded for JavaScript code

Explanation: Node uses non-blocking, event-driven I/O, so one thread can serve many concurrent connections while operations wait. JavaScript code itself runs on a single thread.

Approved by: ______

Correction: ______

## nodejs-legacy-12

Error handling · difficulty 1 · independent solve passed

How should errors from an awaited promise be handled?

- A. With try/catch around the await ✔
- B. Only with .finally
- C. With process.exit
- D. They can't be caught

Explanation: await turns a rejected promise into a thrown exception, so try/catch around the await handles it.

Approved by: ______

Correction: ______

## nodejs-legacy-13

Async and the event loop · difficulty 1 · independent solve passed

What does `await` do inside an async function?

- A. Blocks the whole process
- B. Converts a callback to sync code
- C. Creates a new thread
- D. Pauses that function until the promise settles, without blocking the event loop ✔

Explanation: await suspends only the async function, letting the event loop run other work, and resumes it when the promise settles.

Approved by: ______

Correction: ______

## nodejs-legacy-14

Async and the event loop · difficulty 2 · independent solve passed

What happens if you run a long CPU-bound loop on Node's main thread?

- A. Node moves it to a GPU
- B. The event loop is blocked and other requests wait ✔
- C. It runs in parallel automatically
- D. Other requests keep being served normally

Explanation: JavaScript runs on one thread, so a long synchronous loop blocks the event loop and every other request waits until it finishes.

Approved by: ______

Correction: ______

## nodejs-legacy-15

Security basics · difficulty 1 · independent solve passed

Which is the safest way to build a SQL query with user input?

- A. String concatenation
- B. Escaping quotes manually
- C. Parameterized queries / placeholders ✔
- D. Template literals

Explanation: Parameterized queries send the SQL text and the values separately, so input can never be interpreted as SQL. Manual escaping and concatenation are error-prone.

Approved by: ______

Correction: ______

## nodejs-legacy-16

Security basics · difficulty 1 · independent solve passed

What is the main risk of storing secrets directly in source code?

- A. Slower startup
- B. Syntax errors
- C. They expire
- D. They leak to anyone who can read the repository or its history ✔

Explanation: Secrets committed to source control are readable by everyone with repository access, remain in history after deletion, and spread to forks and CI logs.

Approved by: ______

Correction: ______

## nodejs-async-event-loop-01

Async and the event loop · difficulty 3 · execution check passed

This script runs as a CommonJS file with `node app.js`. In what order does it print?

```
console.log('A');
setTimeout(() => console.log('B'), 0);
Promise.resolve().then(() => console.log('C'));
process.nextTick(() => console.log('D'));
console.log('E');
```

- A. A, E, D, C, B ✔
- B. A, E, C, D, B
- C. A, E, B, C, D
- D. A, B, C, D, E

Explanation: Synchronous code runs first (A, E). Then the process.nextTick queue is drained, then promise microtasks (C), and only afterwards the timers phase runs the setTimeout callback (B). So the order is A, E, D, C, B.

Approved by: ______

Correction: ______

## nodejs-async-event-loop-02

Async and the event loop · difficulty 3 · execution check passed

Inside the callback of an `fs.readFile` call, three things are scheduled as shown. In what order do they print?

```
const fs = require('fs');
fs.readFile(__filename, () => {
  setTimeout(() => console.log('timeout'), 0);
  setImmediate(() => console.log('immediate'));
  Promise.resolve().then(() => console.log('promise'));
});
```

- A. promise, timeout, immediate
- B. promise, immediate, timeout ✔
- C. immediate, promise, timeout
- D. timeout, immediate, promise

Explanation: When the callback ends, the microtask queue is drained first (promise). The callback runs in the poll phase, so the check phase (setImmediate) comes next, and the timer only fires on the next loop iteration. Inside an I/O callback, immediate always precedes timeout.

Approved by: ______

Correction: ______

## nodejs-async-event-loop-03

Async and the event loop · difficulty 2 · execution check passed

What does this program print?

```
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
async function main() {
  [1, 2, 3].forEach(async (n) => {
    await wait(10);
    console.log(n);
  });
  console.log('done');
}
main();
```

- A. 1, 2, 3, done
- B. 1, done, 2, 3
- C. done, 1, 2, 3 ✔
- D. done

Explanation: forEach ignores the promises returned by its async callbacks, so main() does not wait for them. 'done' prints immediately, then the three timers fire in order. Use for...of with await, or Promise.all with map, to wait.

Approved by: ______

Correction: ______

## nodejs-api-express-01

API building (Express) · difficulty 1 · independent solve passed

Which Express call registers a handler that runs only for HTTP POST requests to /users?

- A. app.listen('/users', handler)
- B. app.create('/users', handler)
- C. app.post('/users', handler) ✔
- D. app.send('/users', handler)

Explanation: Express exposes one method per HTTP verb: app.get, app.post, app.put, app.delete. app.listen starts the server, and create and send are not routing methods.

Approved by: ______

Correction: ______

## nodejs-api-express-02

API building (Express) · difficulty 1 · independent solve passed

What does the built-in `express.json()` middleware do?

- A. Parses JSON request bodies and puts the result on req.body ✔
- B. Sends every response as JSON automatically
- C. Validates request bodies against a JSON schema
- D. Converts the query string into a JSON object

Explanation: express.json() reads requests whose Content-Type is application/json and populates req.body. It does not validate the data or change responses; validation needs a separate library.

Approved by: ______

Correction: ______

## nodejs-api-express-03

API building (Express) · difficulty 2 · independent solve passed

Both routes are registered as shown. A request to GET /users/me gets the response 'by id'. Why?

```
app.get('/users/:id', (req, res) => res.send('by id'));
app.get('/users/me', (req, res) => res.send('profile'));
```

- A. Express always prefers the route with the dynamic segment
- B. The word 'me' is reserved and cannot be a literal path
- C. Express runs routes in registration order and the first matching one responds ✔
- D. A path can only be handled by a single route per app

Explanation: Express tries routes and middleware in the order they were registered, and the first handler that sends a response ends the cycle. '/users/:id' matches 'me', so the more specific route must be registered first.

Approved by: ______

Correction: ______

## nodejs-api-express-04

API building (Express) · difficulty 2 · independent solve passed

Every request to this server hangs until the client times out. What is wrong?

```
app.use((req, res, next) => {
  console.log(req.method, req.url);
});
app.get('/', (req, res) => res.send('ok'));
```

- A. app.use must be registered after the routes
- B. console.log blocks the event loop until the request ends
- C. The middleware neither calls next() nor sends a response ✔
- D. res.send needs a return statement in front of it

Explanation: A middleware must either end the response or call next() to pass control on. This one does neither, so the request never reaches the route and no response is sent.

Approved by: ______

Correction: ______

## nodejs-api-express-05

API building (Express) · difficulty 2 · independent solve passed

POST /orders with a JSON body fails with `TypeError: Cannot read properties of undefined (reading 'total')`. What is the cause?

```
app.post('/orders', (req, res) => {
  res.json({ total: req.body.total });
});
app.use(express.json());
```

- A. The route should use app.put for bodies
- B. req.body only exists on GET requests
- C. express.json() must be called inside the handler
- D. The body parser is registered after the route, so req.body is never populated ✔

Explanation: Middleware only affects handlers registered after it. Because express.json() comes after the POST route, req.body is still undefined when the handler runs. Register body parsers before the routes.

Approved by: ______

Correction: ______

## nodejs-api-express-06

API building (Express) · difficulty 3 · independent solve passed

For an unknown id the client correctly receives the 404, but the server also logs `ERR_HTTP_HEADERS_SENT`. What fixes this?

```
app.get('/items/:id', async (req, res) => {
  const item = await db.find(req.params.id);
  if (!item) {
    res.status(404).json({ error: 'not found' });
  }
  res.json(item);
});
```

- A. Return from the handler after sending the 404 response ✔
- B. Wrap the db.find call in a try/catch block
- C. Call res.end() after the final res.json
- D. Move the db.find call out of the handler

Explanation: Without a return, execution continues after the 404 and res.json tries to send a second response, which throws ERR_HTTP_HEADERS_SENT. Writing `return res.status(404).json(...)` stops the handler.

Approved by: ______

Correction: ______

## nodejs-api-express-07

API building (Express) · difficulty 3 · independent solve passed

A router is mounted with `app.use('/api', router)` and contains `router.get('/users', ...)`. Inside that handler, what is `req.path` for GET /api/users?x=1?

- A. /api/users
- B. /users ✔
- C. /users?x=1
- D. /api/users?x=1

Explanation: When a router is mounted at a prefix, Express strips the mount path from req.url before the router sees it, and req.path is the path part without the query string, so it is '/users'. req.originalUrl keeps the full '/api/users?x=1'.

Approved by: ______

Correction: ______

## nodejs-error-handling-01

Error handling · difficulty 1 · independent solve passed

In Express, how does a route handler pass an error on to the error-handling middleware?

- A. Call res.fail(err)
- B. Return the error object from the handler
- C. Call next(err) ✔
- D. Call app.emit('stop', err)

Explanation: Calling next with an argument tells Express to skip the remaining normal handlers and go straight to the error-handling middleware. Returning a value or inventing methods such as res.fail does nothing.

Approved by: ______

Correction: ______

## nodejs-error-handling-02

Error handling · difficulty 2 · execution check passed

What happens when this script runs?

```
try {
  setTimeout(() => {
    throw new Error('boom');
  }, 0);
} catch (e) {
  console.log('caught');
}
```

- A. It prints 'caught' and exits normally
- B. It prints 'caught' and then crashes
- C. It prints nothing and exits normally
- D. The process crashes with an uncaught exception and 'caught' is never printed ✔

Explanation: The callback runs later from the event loop, after the try block has already finished, so the catch clause is no longer on the stack. The error becomes an uncaught exception and terminates the process.

Approved by: ______

Correction: ______

## nodejs-error-handling-03

Error handling · difficulty 2 · execution check passed

What happens when this script runs on Node 20 with default settings?

```
async function load() {
  throw new Error('fail');
}
async function main() {
  try {
    load();
  } catch (err) {
    console.log('handled');
  }
}
main();
```

- A. The process crashes on an unhandled rejection and 'handled' is never printed ✔
- B. It prints 'handled' and exits normally
- C. It prints 'handled' and then crashes
- D. It prints nothing and exits normally

Explanation: load() is not awaited, so its rejected promise is not part of the try block and catch never sees it. Nobody handles the rejection, and since Node 15 an unhandled rejection terminates the process. Writing `await load()` would be caught.

Approved by: ______

Correction: ______

## nodejs-error-handling-04

Error handling · difficulty 3 · execution check passed

What does this code print?

```
Promise.resolve()
  .then(() => { throw new Error('one'); })
  .catch((e) => { console.log('caught', e.message); throw new Error('two'); })
  .then(() => console.log('then'))
  .catch((e) => console.log('final', e.message));
```

- A. caught one, then
- B. caught one, final two ✔
- C. caught one, then, final two
- D. caught one, final one

Explanation: The first catch logs 'caught one' and throws a new error, so the promise returned by catch rejects. The following then is skipped, and the last catch receives the new error and prints 'final two'.

Approved by: ______

Correction: ______

## nodejs-error-handling-05

Error handling · difficulty 2 · independent solve passed

Express does not use this function as an error handler and returns its default error page instead. Why?

```
app.use((err, req, res) => {
  res.status(500).json({ error: 'something failed' });
});
```

- A. Error handlers must be registered before all routes
- B. Error handlers can only call res.send, not res.json
- C. Express recognises error handlers by their four parameters, and next is missing ✔
- D. The status code 500 is reserved for the default handler

Explanation: Express tells error-handling middleware apart by its arity: it must declare four parameters (err, req, res, next), even if next is unused. With three parameters it is treated as ordinary middleware. Error handlers belong after the routes.

Approved by: ______

Correction: ______

## nodejs-security-basics-01

Security basics · difficulty 2 · independent solve passed

How should an API store user passwords?

- A. Hash them once with SHA-256 without a salt
- B. Encrypt them with AES using a key kept in an environment variable
- C. Encode them with Base64 in the database
- D. Hash them with a slow salted algorithm such as bcrypt or Argon2 ✔

Explanation: Passwords need a deliberately slow, salted password-hashing function so stolen hashes are expensive to crack. A fast unsalted hash is easy to brute-force, and encrypted or encoded passwords can be recovered.

Approved by: ______

Correction: ______

## nodejs-security-basics-02

Security basics · difficulty 3 · independent solve passed

A route serves uploaded files by name. Which change is the most robust protection against path traversal such as `../../etc/passwd`?

```
app.get('/files/:name', (req, res) => {
  const file = path.join(UPLOAD_DIR, req.params.name);
  res.sendFile(file);
});
```

- A. Resolve the full path and reject it unless it starts inside UPLOAD_DIR ✔
- B. Remove the first occurrence of '../' from the name
- C. Reject names that contain the word 'etc'
- D. Wrap the name in encodeURIComponent before joining

Explanation: path.join normalises the '..' segments, so the result can leave UPLOAD_DIR. Resolving to an absolute path and checking that it stays under the base directory is reliable. Stripping '../' once can be bypassed with input like '....//', and keyword blocklists miss other targets.

Approved by: ______

Correction: ______

## nodejs-security-basics-03

Security basics · difficulty 3 · execution check passed

A server merges parsed JSON from a request into an object using this function. After the attack payload below is processed, what does `console.log({}.admin)` print?

```
const merge = (target, source) => {
  for (const key in source) {
    if (typeof source[key] === 'object' && source[key] !== null) {
      target[key] = merge(target[key] || {}, source[key]);
    } else {
      target[key] = source[key];
    }
  }
  return target;
};
merge({}, JSON.parse('{"__proto__": {"admin": true}}'));
console.log({}.admin);
```

- A. undefined
- B. true ✔
- C. false
- D. It throws a TypeError

Explanation: JSON.parse creates an own property named __proto__. The recursive merge then reads target['__proto__'], which is Object.prototype, and writes admin onto it. Every object now inherits admin: true. This is prototype pollution; block __proto__, constructor and prototype keys.

Approved by: ______

Correction: ______
