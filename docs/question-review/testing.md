# Testing questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/testing.md`.

## testing-legacy-01

Unit testing · difficulty 2 · independent solve passed

In test-driven development (TDD), what comes first?

- A. Deployment
- B. Refactoring
- C. Writing the implementation
- D. Writing a failing test ✔

Explanation: Test-driven development follows red, green, refactor: write a failing test that states the wanted behaviour, make it pass with the simplest code, then clean up. Deployment, implementation-first and refactoring-first all break that order.

Approved by: ______

Correction: ______

## testing-legacy-02

Test design and boundaries · difficulty 2 · independent solve passed

Which statement about 100% code coverage is true?

- A. It is impossible
- B. It proves the code has no bugs
- C. It makes tests faster
- D. It shows every line ran, but not that behaviour is correct ✔

Explanation: Coverage only records which lines or branches executed. A test with no meaningful assertion still raises coverage, so 100% neither proves the absence of bugs nor shows behaviour is correct. It is achievable, and it has no effect on test speed.

Approved by: ______

Correction: ______

## testing-legacy-03

Test design and boundaries · difficulty 1 · independent solve passed

What does code coverage measure?

- A. Number of test files
- B. How many bugs exist
- C. How much code is executed by the tests ✔
- D. Test speed

Explanation: Code coverage is the share of the code's lines, branches or functions that run while the tests execute. It does not count tests, bugs or speed.

Approved by: ______

Correction: ______

## testing-legacy-04

Unit testing · difficulty 1 · independent solve passed

What is a test double such as a mock or stub used for?

- A. Doubling coverage
- B. Load testing
- C. Replacing a real dependency to isolate the code under test ✔
- D. Running tests twice

Explanation: Mocks, stubs and fakes stand in for a real dependency such as a database, clock or network service, so the code under test runs in isolation, fast and deterministically.

Approved by: ______

Correction: ______

## testing-legacy-05

Test automation and CI · difficulty 1 · independent solve passed

What is the testing pyramid's main idea?

- A. Avoid unit tests
- B. Have many fast unit tests, fewer integration tests and few end-to-end tests ✔
- C. Test only in production
- D. Write mostly end-to-end tests

Explanation: The testing pyramid advises many fast, cheap unit tests at the base, fewer integration tests in the middle and a small number of slow, brittle end-to-end tests at the top.

Approved by: ______

Correction: ______

## testing-legacy-06

End-to-end and UI testing · difficulty 1 · independent solve passed

What is an end-to-end (E2E) test?

- A. A database test
- B. A test that drives the full system the way a user would ✔
- C. A test of one function
- D. A lint check

Explanation: An end-to-end test exercises the whole running system through its real entry point, for example a browser clicking through a user flow, rather than a single function or layer.

Approved by: ______

Correction: ______

## testing-legacy-07

Debugging and failure analysis · difficulty 1 · independent solve passed

What should a good bug report include?

- A. Only 'it doesn't work'
- B. The tester's opinion
- C. Steps to reproduce, expected result and actual result ✔
- D. A fix

Explanation: A useful bug report lets someone else reproduce and judge the problem: the steps to reproduce, what was expected and what actually happened. A fix or an opinion is not required.

Approved by: ______

Correction: ______

## testing-legacy-08

Debugging and failure analysis · difficulty 1 · independent solve passed

What is a flaky test?

- A. A skipped test
- B. A test that sometimes passes and sometimes fails without code changes ✔
- C. A test that is slow
- D. A test with no assertions

Explanation: A flaky test gives different results on the same code, usually from timing, shared state, ordering or external dependencies. Slow, skipped or assertion-free tests are different problems.

Approved by: ______

Correction: ______

## testing-legacy-09

Unit testing · difficulty 1 · independent solve passed

What does a unit test check?

- A. A small unit of code in isolation ✔
- B. Server load
- C. The whole system end to end
- D. Visual layout

Explanation: A unit test checks one small piece of code, such as a function or class, in isolation from the database, network and other components.

Approved by: ______

Correction: ______

## testing-legacy-10

API and integration testing · difficulty 2 · independent solve passed

What is a security test for IDOR checking?

- A. Page speed
- B. Spelling
- C. Password strength
- D. That one user cannot access another user's resource by changing an id ✔

Explanation: An IDOR (insecure direct object reference) test logs in as one user, requests another user's resource by changing an id in the URL or body, and expects a refusal such as 403 or 404.

Approved by: ______

Correction: ______

## testing-legacy-11

Unit testing · difficulty 1 · independent solve passed

What is the purpose of a test fixture?

- A. Formatting code
- B. Deploying
- C. Setting up a known state or data for tests ✔
- D. Fixing bugs

Explanation: A fixture builds the known starting state a test needs, such as sample data, a database row or a client, and usually tears it down afterwards, so tests are repeatable.

Approved by: ______

Correction: ______

## testing-legacy-12

Test design and boundaries · difficulty 2 · independent solve passed

What is fuzz testing?

- A. Testing documentation
- B. Feeding unexpected or random inputs to find crashes and errors ✔
- C. Testing fonts
- D. Testing animations

Explanation: Fuzz testing feeds large amounts of malformed, unexpected or random input to a program to reveal crashes, hangs and unhandled errors.

Approved by: ______

Correction: ______

## testing-legacy-13

Test design and boundaries · difficulty 2 · independent solve passed

What does boundary value analysis focus on?

- A. Values at and just around the edges of valid ranges ✔
- B. UI colours
- C. Random values
- D. Only valid values

Explanation: Boundary value analysis picks test inputs exactly at, just below and just above the limits of valid ranges, because off-by-one mistakes cluster there.

Approved by: ______

Correction: ______

## testing-legacy-14

Test automation and CI · difficulty 1 · independent solve passed

What is regression testing?

- A. Testing new features only
- B. Testing performance
- C. Testing security
- D. Re-running tests to make sure existing behaviour still works after changes ✔

Explanation: Regression testing re-runs existing tests after a change to confirm that behaviour that used to work still works. It is the main job of an automated suite in CI.

Approved by: ______

Correction: ______

## testing-legacy-15

Test design and boundaries · difficulty 2 · independent solve passed

What is equivalence partitioning?

- A. Splitting inputs into groups expected to behave the same and testing one from each ✔
- B. Parallel testing
- C. Splitting servers
- D. Comparing outputs

Explanation: Equivalence partitioning divides the input domain into classes expected to be handled the same way, then tests one representative per class instead of every value.

Approved by: ______

Correction: ______

## testing-test-design-01

Test design and boundaries · difficulty 1 · independent solve passed

A field accepts an age from 18 to 65 inclusive. Which set of inputs covers both sides of each boundary?

- A. 17, 18, 65 and 66 ✔
- B. 18, 30, 50 and 65
- C. 0, 30, 50 and 100
- D. 17, 30, 50 and 66

Explanation: Boundary value analysis tests just outside and exactly on each edge: 17 and 18 at the lower edge, 65 and 66 at the upper edge. The other sets miss at least one side of a boundary.

Approved by: ______

Correction: ______

## testing-test-design-02

Test design and boundaries · difficulty 1 · independent solve passed

Which of these is a negative test for a login form?

- A. Sign in with valid credentials and check that the dashboard opens
- B. Submit a wrong password and check that sign-in is refused ✔
- C. Check that the login page loads in under two seconds
- D. Tick 'remember me' and check that the cookie lasts 30 days

Explanation: A negative test supplies invalid input or conditions and verifies the system refuses safely. The valid sign-in is a positive test, the load time a performance check and the cookie lifetime a positive feature test.

Approved by: ______

Correction: ______

## testing-test-design-03

Test design and boundaries · difficulty 3 · independent solve passed

A search page has three filters: category (4 options), stock status (2 options) and price band (3 options). What is the smallest number of tests that covers every pair of values taken from any two filters (pairwise coverage)?

- A. 4
- B. 9
- C. 12 ✔
- D. 24

Explanation: Category and price band alone have 4 x 3 = 12 distinct pairs, and one test covers only one such pair, so 12 is a lower bound. Assigning stock status alternately (for example (category + price) mod 2) covers its pairs too, so 12 suffices. 24 is all combinations, 4 only covers each value once.

Approved by: ______

Correction: ______

## testing-test-design-04

Test design and boundaries · difficulty 3 · independent solve passed

A mutation-testing tool changes `>=` to `>` in `if age >= 18`. The whole suite still passes, and the coverage report shows that line as executed. What does this most likely show?

- A. The coverage report is wrong about that line
- B. The code is correct, so no test needs to fail
- C. Mutation testing cannot be applied to comparison operators
- D. No test asserts the behaviour exactly at age 18 ✔

Explanation: The mutant changes behaviour only for age 18. A surviving mutant on an executed line means no test checks that exact value: the tests run the line but do not assert on the boundary. Mutation tools do handle relational operators, and passing here is a gap, not proof of correctness.

Approved by: ______

Correction: ______

## testing-test-design-05

Test design and boundaries · difficulty 2 · execution check passed

The rule says shipping is free for orders of 50.00 or more. Which input exposes the defect in this function?

```
def shipping(total):
    if total > 50:
        return 0
    return 5
```

- A. 50.00 ✔
- B. 49.99
- C. 50.01
- D. 100.00

Explanation: The code uses `>` where the rule needs `>=`. Only an order of exactly 50.00 differs: the function charges 5 instead of 0. The other inputs give the right answer either way.

Approved by: ______

Correction: ______

## testing-test-design-06

Test design and boundaries · difficulty 2 · execution check passed

Under the Gregorian rules, a year divisible by 400 is a leap year. These tests already pass: 2024 is leap, 2023 is not, 1900 is not. Which extra input is the only one of these that exposes the defect?

```
def is_leap(year):
    return year % 4 == 0 and year % 100 != 0
```

- A. 2100
- B. 2000 ✔
- C. 2028
- D. 1999

Explanation: The function ignores the 'divisible by 400' exception, so it says 2000 is not a leap year. 2100 is correctly not leap, 2028 is leap by the plain rule and 1999 is not leap, so those give the right answer with the bug too.

Approved by: ______

Correction: ______

## testing-unit-testing-01

Unit testing · difficulty 2 · execution check passed

Which test fails when this file is run with pytest?

```
def test_round():
    assert round(2.5) == 2

def test_sum():
    assert 0.1 + 0.2 == 0.3

def test_floor():
    assert 7 // 2 == 3

def test_neg_floor():
    assert -7 // 2 == -4
```

- A. test_round
- B. test_floor
- C. test_sum ✔
- D. test_neg_floor

Explanation: 0.1 + 0.2 is 0.30000000000000004 in binary floating point, so == 0.3 fails (pytest.approx is the fix). round(2.5) is 2 (round half to even), 7 // 2 is 3 and -7 // 2 is -4 (floor division), so those pass.

Approved by: ______

Correction: ______

## testing-unit-testing-02

Unit testing · difficulty 2 · execution check passed

What does pytest report for this test?

```
import pytest

def withdraw(balance, amount):
    if amount > balance:
        raise ValueError("insufficient funds")
    return balance - amount

def test_overdraw():
    with pytest.raises(ValueError, match="Insufficient"):
        withdraw(50, 80)
```

- A. Passes: a ValueError is raised, and match ignores case by default
- B. Passes: match is only checked when the exception type is wrong
- C. Errors during collection: match needs a compiled regex pattern
- D. Fails: the pattern does not match, as matching is case-sensitive ✔

Explanation: pytest.raises(match=...) applies re.search to the exception text, which is case-sensitive. 'insufficient funds' does not contain 'Insufficient', so the test fails with 'Regex pattern did not match'. Using 'insufficient' or '(?i)Insufficient' would pass.

Approved by: ______

Correction: ______

## testing-unit-testing-03

Unit testing · difficulty 2 · independent solve passed

A unit test patches every collaborator and asserts only that each mock was called, in a fixed order. After a refactor that keeps the behaviour identical, the test fails. What is the main weakness of this test?

- A. It is tied to the code's internals, not to the behaviour it must provide ✔
- B. It uses too few mocks to isolate the unit from its collaborators
- C. It should have been written as an end-to-end test instead
- D. It lowers the code coverage figure that the pipeline reports

Explanation: Asserting on internal calls and their order couples the test to the implementation, so harmless refactors break it while real behaviour changes may slip through. Prefer asserting observable results or outputs; mock only the boundaries.

Approved by: ______

Correction: ______

## testing-unit-testing-04

Unit testing · difficulty 3 · execution check passed

pytest runs these two tests in file order. What is reported?

```
import pytest

@pytest.fixture(scope="module")
def items():
    return []

def test_add_one(items):
    items.append(1)
    assert len(items) == 1

def test_add_two(items):
    items.append(2)
    assert len(items) == 1
```

- A. Both tests pass
- B. Only the first test passes ✔
- C. Only the second test passes
- D. Both tests fail

Explanation: A module-scoped fixture is created once and shared by every test in the module. test_add_one appends 1 and passes; test_add_two then sees a list that already holds 1, appends 2 and its length is 2, so the assertion fails. Function scope (the default) would isolate them.

Approved by: ______

Correction: ______

## testing-unit-testing-05

Unit testing · difficulty 3 · execution check passed

What happens when this test runs?

```
# util.py
def fetch():
    return "real"

# service.py
from util import fetch

def run():
    return fetch()

# test_service.py
from unittest.mock import patch
import service

def test_run():
    with patch("util.fetch", return_value="fake"):
        assert service.run() == "fake"
```

- A. It passes: patch replaces fetch for every module that uses it
- B. It fails with ModuleNotFoundError: util cannot be patched
- C. It fails: service still calls the fetch it imported by name ✔
- D. It passes, but only when this test runs on its own, not in a suite

Explanation: `from util import fetch` binds the name fetch inside the service module. Patching util.fetch replaces the attribute on util only, so service.run() still calls the real function and returns 'real'. Patch where the name is looked up: patch('service.fetch').

Approved by: ______

Correction: ______

## testing-unit-testing-06

Unit testing · difficulty 3 · execution check passed

Which test fails under pytest?

```
import pytest

def test_float():
    assert 0.1 + 0.2 == pytest.approx(0.3)

def test_rel_big():
    assert 1000 == pytest.approx(1001, rel=1e-2)

def test_rel_small():
    assert 100 == pytest.approx(103, rel=0.02)

def test_zero():
    assert 0 == pytest.approx(1e-13)
```

- A. test_float
- B. test_rel_big
- C. test_zero
- D. test_rel_small ✔

Explanation: pytest.approx tolerance is relative to the expected value: 103 x 0.02 = 2.06, but the difference is 3, so test_rel_small fails. test_rel_big allows 10.01 (difference 1), test_float passes with the default 1e-6 relative tolerance and test_zero passes through the default 1e-12 absolute tolerance.

Approved by: ______

Correction: ______

## testing-unit-testing-07

Unit testing · difficulty 3 · execution check passed

What does this script print?

```
from unittest.mock import Mock

m = Mock(side_effect=[1, ValueError("boom"), 3])
out = []
for _ in range(4):
    try:
        out.append(m())
    except ValueError:
        out.append("err")
    except StopIteration:
        out.append("stop")
print(out)
```

- A. [1, 'err', 3, 'stop'] ✔
- B. [1, 'err', 3, 3]
- C. [1, 'err', 'err', 3]
- D. [1, ValueError('boom'), 3, 'stop']

Explanation: With a list side_effect, each call returns the next item, but an exception instance in the list is raised instead of returned. The fourth call finds the list exhausted and raises StopIteration. The values are therefore 1, a caught ValueError, 3 and a caught StopIteration.

Approved by: ______

Correction: ______

## testing-api-integration-01

API and integration testing · difficulty 1 · independent solve passed

A test requests GET /users/9999 and no such user exists. Which status should it expect?

- A. 401 Unauthorized
- B. 404 Not Found ✔
- C. 500 Internal Server Error
- D. 201 Created

Explanation: A well-formed request for a resource that does not exist is answered with 404. 401 means missing or invalid credentials, 500 is a server fault and 201 is for successful creation.

Approved by: ______

Correction: ______

## testing-api-integration-02

API and integration testing · difficulty 1 · independent solve passed

What mainly separates an integration test of an API endpoint from a unit test of its handler function?

- A. It must drive a real browser instead of calling the API directly
- B. It measures only the response time of the endpoint under heavy load
- C. It runs the endpoint with real parts such as the router and database ✔
- D. It checks the JSON shape of replies but never the stored data

Explanation: An integration test checks that components work together, for example request routing, validation and a real database, while a unit test isolates the function with doubles. Neither needs a browser, and integration tests commonly verify stored data too.

Approved by: ______

Correction: ______

## testing-api-integration-03

API and integration testing · difficulty 1 · independent solve passed

Which API test best checks that a protected endpoint enforces authentication?

- A. Call it with a valid token and expect 200
- B. Call it with a valid token and check the response schema
- C. Call it with an unsupported method and expect 405
- D. Call it with no token and expect 401 ✔

Explanation: Enforcement is shown by a request that lacks valid credentials being rejected (401). The valid-token tests are happy paths and the 405 test checks method handling, not authentication.

Approved by: ______

Correction: ______

## testing-api-integration-04

API and integration testing · difficulty 2 · independent solve passed

API integration tests share one database and pass alone but fail intermittently when run together, depending on order. What is the best fix?

- A. Give each test its own data and clean up afterwards ✔
- B. Run the tests in the one fixed order that happens to pass
- C. Add a short sleep before each request is sent
- D. Reuse one shared user across all of the tests

Explanation: Order-dependent failures come from tests leaking state into each other. Isolating data per test, with a transaction rollback or cleanup, removes the cause. Fixing the order, sleeping or sharing more state only hides or worsens it.

Approved by: ______

Correction: ______

## testing-api-integration-05

API and integration testing · difficulty 2 · execution check passed

Which status code does this script print?

```
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

app = FastAPI()

class Item(BaseModel):
    name: str
    price: int

@app.post("/items")
def create(item: Item):
    return item

client = TestClient(app)
response = client.post("/items", json={"name": "pen", "price": "abc"})
print(response.status_code)
```

- A. 200
- B. 422 ✔
- C. 400
- D. 500

Explanation: FastAPI validates the body against the Pydantic model before calling the handler. 'abc' cannot be parsed as an int, so it answers 422 Unprocessable Content with error details and the handler never runs.

Approved by: ______

Correction: ______

## testing-api-integration-06

API and integration testing · difficulty 2 · independent solve passed

A frontend team and an API team want to catch a breaking change to a response shape before deploying, without a full shared environment. Which approach fits best?

- A. Load tests that send thousands of requests at the API
- B. Manual exploratory testing of the API after each release
- C. Consumer-driven contract tests run against the API ✔
- D. Frontend unit tests that use hand-written mock data

Explanation: Contract tests record what a consumer relies on and check the provider against it in CI, so a breaking change fails before release. Frontend tests with hand-written mocks cannot notice when the real API changes.

Approved by: ______

Correction: ______

## testing-api-integration-07

API and integration testing · difficulty 2 · independent solve passed

Integration tests run against in-memory SQLite, but production uses PostgreSQL. What is the main risk?

- A. SQLite cannot hold a database in memory while a test is running
- B. In-memory databases are always slower than a real database server
- C. SQLite tests cannot use transactions or roll back between tests
- D. Tests can pass where PostgreSQL would behave differently or fail ✔

Explanation: A different engine differs in dialect, type strictness, constraint and locking behaviour, so a green run says little about production. Running the tests against the same engine, for example in a container, avoids this.

Approved by: ______

Correction: ______

## testing-api-integration-08

API and integration testing · difficulty 3 · execution check passed

The first test sets a dependency override and never removes it. Run in file order under pytest, what is reported?

```
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

app = FastAPI()

def current_user():
    raise HTTPException(status_code=401)

@app.get("/admin")
def admin(user=Depends(current_user)):
    return {"ok": True}

client = TestClient(app)

def test_admin_ok():
    app.dependency_overrides[current_user] = lambda: "admin"
    assert client.get("/admin").status_code == 200

def test_anonymous_rejected():
    assert client.get("/admin").status_code == 401
```

- A. Only the first test passes ✔
- B. Both tests pass
- C. Only the second test passes
- D. Both tests fail

Explanation: The first test sets app.dependency_overrides and never removes it. The override outlives the test, so in the second test current_user returns 'admin' and the endpoint answers 200, not 401. Clearing the overrides in a fixture teardown fixes it.

Approved by: ______

Correction: ______

## testing-api-integration-09

API and integration testing · difficulty 3 · independent solve passed

An integration test sends 20 concurrent POST /orders requests for an item with stock 1 and expects exactly one 201. It sometimes sees two. Which defect does this point to?

- A. Missing validation of the fields in the order request body
- B. A race between reading the stock and updating it without locking ✔
- C. A wrong status code returned for out-of-stock orders
- D. A missing database index on the orders table's key column

Explanation: Two requests read stock 1 before either writes, so both succeed: a check-then-act race. The cure is an atomic conditional update, a row lock or a constraint. Validation, status mapping or an index would not let two orders through.

Approved by: ______

Correction: ______

## testing-api-integration-10

API and integration testing · difficulty 3 · execution check passed

What happens when this script runs with TestClient at its default settings?

```
from fastapi import FastAPI
from fastapi.testclient import TestClient

app = FastAPI()

@app.get("/boom")
def boom():
    raise RuntimeError("unexpected")

client = TestClient(app)
response = client.get("/boom")
print(response.status_code)
```

- A. It prints 500 for the failed request
- B. It prints 200 with an error body
- C. It raises RuntimeError at the client.get call ✔
- D. It prints 422 with validation details

Explanation: TestClient defaults to raise_server_exceptions=True, so an unhandled exception in the app is re-raised in the test instead of becoming a 500 response. To assert on the 500 itself, create TestClient(app, raise_server_exceptions=False).

Approved by: ______

Correction: ______

## testing-e2e-ui-01

End-to-end and UI testing · difficulty 1 · independent solve passed

In a Playwright test, which locator for a 'Submit' button is the most resilient to layout changes?

- A. page.locator('xpath=/html/body/div[3]/form/button[2]')
- B. page.locator('div > div > form > button:nth-child(2)')
- C. page.mouse.click(412, 630)
- D. page.getByRole('button', { name: 'Submit' }) ✔

Explanation: Role and accessible-name locators follow what users and assistive technology see, so they survive DOM restructuring. Absolute XPath, positional CSS and screen coordinates break whenever the layout changes.

Approved by: ______

Correction: ______

## testing-e2e-ui-02

End-to-end and UI testing · difficulty 1 · independent solve passed

Why is a fixed sleep, such as waiting 5 seconds, a poor way to wait in a UI test?

- A. It wastes time and still fails on a slower page ✔
- B. It stops the page from loading its own resources
- C. It lowers the coverage figures that the suite reports
- D. Browsers block timers while a test is automating them

Explanation: A fixed delay is either too long, wasting time on every run, or too short on a slow machine, causing flaky failures. Waiting for a concrete condition, such as an element becoming visible, is both faster and more reliable.

Approved by: ______

Correction: ______

## testing-e2e-ui-03

End-to-end and UI testing · difficulty 2 · independent solve passed

This Playwright test fails about one run in ten with an empty text. What is the best fix?

```
await page.getByRole('button', { name: 'Save' }).click();
const text = await page.getByTestId('toast').textContent();
expect(text).toBe('Saved');
```

- A. Add `waitForTimeout(3000)` before reading the text
- B. Use a retrying `expect(...).toHaveText('Saved')` ✔
- C. Catch the assertion error and ignore it
- D. Configure the runner to retry the test five times

Explanation: textContent() reads the toast once, immediately after the click, before the app has rendered it. A web-first assertion such as expect(locator).toHaveText() polls until the condition holds or the timeout ends. A fixed delay stays flaky, and ignoring errors or retrying only hides it.

Approved by: ______

Correction: ______

## testing-e2e-ui-04

End-to-end and UI testing · difficulty 2 · independent solve passed

Several Playwright tests sign in as the same shared user and edit its profile. They pass one at a time but fail when run in parallel. Which fix removes the cause?

- A. Raise the action timeout to 60 seconds
- B. Add a sleep so tests start a few seconds apart
- C. Give each test or worker its own account ✔
- D. Make the tests share cookies between workers

Explanation: Parallel tests editing one account overwrite each other's state, so the failure is a data collision. Isolated accounts per test or worker remove the collision. Longer timeouts, staggered starts and shared cookies leave the shared state in place.

Approved by: ______

Correction: ______

## testing-e2e-ui-05

End-to-end and UI testing · difficulty 3 · independent solve passed

On slow CI machines a Playwright click succeeds (the button was visible, enabled and stable) but nothing happens. The single-page app attaches its handlers only after its scripts finish loading. What is the most reliable fix?

- A. Use `click({ force: true })` to skip the actionability checks
- B. Raise the global test timeout to 10 minutes
- C. Click the button twice in case the first is lost
- D. Wait for a ready signal from the app, then click ✔

Explanation: Actionability checks cover the DOM, not whether the app's JavaScript is attached. Waiting for an application-level readiness signal, such as a rendered element or flag set after hydration, makes the click safe. Forcing, longer timeouts and double clicks do not address it, and a second click may repeat the action.

Approved by: ______

Correction: ______

## testing-e2e-ui-06

End-to-end and UI testing · difficulty 3 · independent solve passed

A visual-regression test compares screenshots. It passes on developers' laptops but fails in CI with tiny font and anti-aliasing differences. What is the best fix?

- A. Create the baselines in the CI container and compare them there ✔
- B. Raise the allowed pixel difference until the failures stop
- C. Skip the visual test whenever the pipeline runs it
- D. Commit new baselines from each developer's own laptop each time

Explanation: Font rendering and anti-aliasing differ across operating systems and browser builds. Producing and comparing baselines in one pinned environment removes that noise without weakening the check. A 100% threshold disables it, skipping hides it and per-laptop baselines recreate the mismatch.

Approved by: ______

Correction: ______

## testing-debugging-failures-01

Debugging and failure analysis · difficulty 2 · execution check passed

Each test passes when run alone, but test_b fails when both run together. What is the cause?

```
def add_tag(tag, tags=[]):
    tags.append(tag)
    return tags

def test_a():
    assert add_tag("x") == ["x"]

def test_b():
    assert add_tag("y") == ["y"]
```

- A. pytest runs tests in random order by default
- B. One default list is shared by all calls ✔
- C. pytest reuses the return value of the first test
- D. Strings in assertions are compared by identity

Explanation: A mutable default argument is evaluated once at definition time, so tags keeps growing across calls: test_b sees ['x', 'y']. pytest runs tests in file order by default and does not reuse return values. The fix is tags=None and a new list inside the function.

Approved by: ______

Correction: ______

## testing-debugging-failures-02

Debugging and failure analysis · difficulty 2 · independent solve passed

A bug appeared somewhere in the last 200 commits and a test reproduces it. What is the fastest way to find the commit that introduced it?

- A. Read through the diff of every one of the commits
- B. Revert the 200 commits, then re-apply them one at a time
- C. Run git bisect, with the test as the good/bad check ✔
- D. Ask each author whether their commit caused it

Explanation: git bisect binary-searches the history, so about eight test runs find the culprit among 200 commits, and it can be automated with `git bisect run`. The other approaches take far longer or depend on guesses.

Approved by: ______

Correction: ______

## testing-debugging-failures-03

Debugging and failure analysis · difficulty 2 · independent solve passed

A test passes on a developer's machine but fails in CI every time. What is the best first step?

- A. Re-run the CI job several times until it finally passes
- B. Mark the test as skipped while it runs in CI only, for now
- C. Increase the number of automatic retries for that CI job
- D. Compare the CI and local setups, then reproduce CI locally ✔

Explanation: A consistent difference between environments has a cause that can be found: dependency versions, environment variables, time zone, locale, file paths or test data. Reproducing the CI setup, for example in the same container, reveals it. Re-running, skipping and retries hide the problem.

Approved by: ______

Correction: ______

## testing-debugging-failures-04

Debugging and failure analysis · difficulty 3 · execution check passed

This test passes on some runs and fails on others with no code change. Why?

```
def test_order():
    colours = {"red", "green", "blue"}
    assert list(colours) == ["red", "green", "blue"]
```

- A. Hash randomisation changes the set's iteration order per run ✔
- B. pytest shuffles the contents of sets before every test run
- C. Two tests run in parallel and both change the same set
- D. The assertion compares the two lists by identity, not by value

Explanation: Python randomises string hashes for each process (PYTHONHASHSEED), so a set of strings iterates in different orders between runs. The test depends on an unspecified order; compare sorted(colours) or use a list. pytest does not shuffle sets, nothing here runs in parallel and == compares values.

Approved by: ______

Correction: ______

## testing-debugging-failures-05

Debugging and failure analysis · difficulty 3 · independent solve passed

A test fails about 1 time in 20. After a fix it passed once. How can you best judge whether the fix worked?

- A. Accept the fix, since one passing run proves that it works
- B. Run it hundreds of times and compare the failure rate ✔
- C. Run it three times and accept three green results as proof
- D. Merge it and wait to see whether anyone complains about it

Explanation: With a 5% failure rate, a single run passes 95% of the time and three runs still pass about 86% of the time, so they prove little. Hundreds of runs under the same conditions give a measurable before and after comparison.

Approved by: ______

Correction: ______

## testing-debugging-failures-06

Debugging and failure analysis · difficulty 2 · independent solve passed

A user reports that exports fail 'sometimes'. What is the most useful first step?

- A. Rewrite the entire export module from scratch right away
- B. Double every timeout that the export code uses
- C. Find a failing case and shrink it to the smallest input ✔
- D. Close the report until someone can make it happen again

Explanation: A reliable reproduction, ideally the smallest input, turns a vague report into something testable and gives a failing test to guard the fix. Rewriting, timeouts and closing the report skip the diagnosis.

Approved by: ______

Correction: ______

## testing-automation-ci-01

Test automation and CI · difficulty 2 · independent solve passed

Which order of pipeline stages gives developers the fastest useful feedback?

- A. End-to-end tests first, then integration, then unit tests
- B. Integration tests first, then lint, then unit tests
- C. All tests in one slow stage, in random order
- D. Lint and unit tests, then integration, then end-to-end ✔

Explanation: Fail fast: cheap, quick checks run first so most mistakes are reported within a minute or two, and slower, broader suites run only for changes that passed them. Starting with the slowest tests delays the same feedback.

Approved by: ______

Correction: ______

## testing-automation-ci-02

Test automation and CI · difficulty 2 · independent solve passed

A CI test run takes 40 minutes because 2,000 independent tests run one after another. Which change cuts the time without dropping coverage?

- A. Run the tests on parallel workers ✔
- B. Delete the slowest tests from the suite
- C. Run the full suite once a week instead of per commit
- D. Disable the assertions in the slow tests

Explanation: Independent tests can run concurrently, so sharding them across workers or jobs shortens the wall-clock time while keeping every test. Deleting tests, running them rarely or removing assertions reduces what is verified.

Approved by: ______

Correction: ______

## testing-automation-ci-03

Test automation and CI · difficulty 2 · independent solve passed

The deploy step runs even when tests fail. Which line is responsible?

```
1  jobs:
2    test:
3      runs-on: ubuntu-latest
4      steps:
5        - uses: actions/checkout@v4
6        - run: pip install -r requirements.txt
7        - run: pytest || true
8        - run: ./deploy.sh
```

- A. Line 5
- B. Line 7 ✔
- C. Line 6
- D. Line 8

Explanation: `pytest || true` makes the step exit 0 whatever pytest returns, so the job continues to deploy. Without `|| true`, a failing pytest step fails the job and later steps are skipped by default.

Approved by: ______

Correction: ______

## testing-automation-ci-04

Test automation and CI · difficulty 2 · independent solve passed

A CI test calls a live payment sandbox, and builds fail whenever the vendor is down. What is the best change?

- A. Retry the live call ten times before the build is marked as failed
- B. Ignore every test failure that comes from that particular CI job
- C. Stub the vendor and run a few live checks in a non-blocking job ✔
- D. Run the job only at times when the vendor is known to be running

Explanation: Blocking builds on a third party makes the suite unreliable. Fast stubs (kept honest with contract checks) give deterministic results, while a small separate live smoke job still detects vendor changes without blocking merges.

Approved by: ______

Correction: ______

## testing-automation-ci-05

Test automation and CI · difficulty 3 · independent solve passed

A flaky test blocks merges several times a week. Which policy handles it best?

- A. Automatically rerun every failing test in the suite five times
- B. Delete the test permanently without writing a replacement
- C. Turn off the required checks on the whole repository
- D. Quarantine it, non-blocking, with an owner and a deadline ✔

Explanation: Quarantine keeps the main signal trustworthy and unblocks the team, while ownership and a deadline make sure the root cause is fixed. Blanket reruns hide real failures, and deleting or disabling checks removes protection.

Approved by: ______

Correction: ______

## testing-automation-ci-06

Test automation and CI · difficulty 3 · independent solve passed

Four CI jobs run integration tests in parallel against one shared database and fail at random. What is the most robust fix?

- A. Give each job its own database or schema ✔
- B. Add random delays so the jobs rarely overlap
- C. Raise the database connection limit
- D. Retry the failing jobs until they pass

Explanation: Parallel jobs overwrite and delete each other's rows, so the failures are collisions on shared state. A separate database or schema per job, often a throwaway container, removes them. More connections, delays and retries leave the sharing in place.

Approved by: ______

Correction: ______

## testing-automation-ci-07

Test automation and CI · difficulty 3 · execution check passed

A CI step runs `pytest -m smoke`, but no test carries the smoke marker. With pytest at its default settings, what happens?

- A. pytest finds nothing to run, exits with code 0 and the step passes
- B. pytest deselects every test, exits with code 5 and the step fails ✔
- C. pytest exits with code 1, as if a test had failed
- D. pytest exits with code 4 because the marker is unknown

Explanation: When no tests are collected or all are deselected, pytest exits with code 5 (no tests collected), which a CI step treats as a failure. Code 1 means test failures and code 4 a usage error; an unregistered marker used only in -m is not a usage error.

Approved by: ______

Correction: ______
