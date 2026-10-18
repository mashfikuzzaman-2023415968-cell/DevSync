"""Source of the skill-test question bank (spec §7.2, §17 Phase 3): 8 skills × 16 questions.

`python scripts/build_question_bank.py alembic/seed/skills_and_questions_v1.json` writes the
frozen seed that migration 0004 loads. Correct answers are spread evenly across the four option
positions (reproducibly), so guessing one letter never pays. Edit questions here, never in the
JSON, and have a team member review them for accuracy (DECISIONS D29).
"""

import hashlib
import json
import random
import sys
from typing import Any


def Q(text: str, options: list[str], answer: int, d: int = 2) -> dict[str, Any]:  # noqa: N802
    return {"text": text, "options": options, "answer": answer, "difficulty": d}


skills: list[dict[str, Any]] = [
    {
        "name": "React",
        "domain": "FRONTEND",
        "questions": [
            Q(
                "What does calling a state setter from useState do?",
                [
                    "Mutates the state variable immediately",
                    "Schedules a re-render with the new state",
                    "Reloads the page",
                    "Resets every other piece of state",
                ],
                1,
                1,
            ),
            Q(
                "Why does React need a `key` prop on list items?",
                [
                    "To style each item",
                    "To identify items between renders so it can match and reorder them",
                    "To make items focusable",
                    "To sort the list alphabetically",
                ],
                1,
                1,
            ),
            Q(
                "When does an effect with an empty dependency array (`useEffect(fn, [])`) run?",
                [
                    "On every render",
                    "Only after the first render (and cleanup on unmount)",
                    "Never",
                    "Only when props change",
                ],
                1,
                1,
            ),
            Q(
                "What should a useEffect cleanup function typically do?",
                [
                    "Return JSX",
                    "Undo subscriptions, timers or listeners the effect created",
                    "Set state for the next render",
                    "Call the effect again",
                ],
                1,
                2,
            ),
            Q(
                "Which hook memoizes a computed value between renders?",
                ["useRef", "useMemo", "useState", "useId"],
                1,
                1,
            ),
            Q(
                "What is the main purpose of useCallback?",
                [
                    "To run code after paint",
                    "To keep the same function identity between renders unless its dependencies change",
                    "To fetch data",
                    "To create a ref",
                ],
                1,
                2,
            ),
            Q(
                "Changing the `.current` value of a ref created with useRef will…",
                [
                    "Trigger a re-render",
                    "Not trigger a re-render",
                    "Throw an error",
                    "Reset the component",
                ],
                1,
                1,
            ),
            Q(
                "What is a 'controlled' input in React?",
                [
                    "An input whose value is driven by React state",
                    "An input with validation",
                    "An input inside a form tag",
                    "An input rendered by a server",
                ],
                0,
                1,
            ),
            Q(
                "Why is mutating state directly (e.g. pushing into an array held in state) a problem?",
                [
                    "It is slower",
                    "React may not detect the change because the reference is the same",
                    "It is a syntax error",
                    "It deletes the state",
                ],
                1,
                2,
            ),
            Q(
                "What does React.lazy combined with Suspense provide?",
                [
                    "Server-side rendering",
                    "Code-splitting: loading a component's code only when it is first rendered",
                    "Global state",
                    "Automatic memoization",
                ],
                1,
                2,
            ),
            Q(
                "Which statement about the Rules of Hooks is correct?",
                [
                    "Hooks may be called inside loops",
                    "Hooks must be called in the same order on every render, at the top level of components or custom hooks",
                    "Hooks can be called from class components",
                    "Hooks must be called inside conditions",
                ],
                1,
                2,
            ),
            Q(
                "What is 'lifting state up'?",
                [
                    "Moving state to the closest common parent of components that need it",
                    "Storing state in localStorage",
                    "Using a global variable",
                    "Putting state in a ref",
                ],
                0,
                1,
            ),
            Q(
                "What is the purpose of React Context?",
                [
                    "To pass values through the tree without passing props at every level",
                    "To speed up rendering",
                    "To call APIs",
                    "To replace all component state",
                ],
                0,
                1,
            ),
            Q(
                "In React 18, what does automatic batching do?",
                [
                    "Combines several state updates into one re-render, even inside timeouts and promises",
                    "Sends network requests together",
                    "Merges components",
                    "Delays effects by one second",
                ],
                0,
                3,
            ),
            Q(
                "Which is the safest way to render user-supplied text in React?",
                [
                    "dangerouslySetInnerHTML",
                    "Rendering it as a child expression like {text}",
                    "Building an HTML string",
                    "Using eval",
                ],
                1,
                1,
            ),
            Q(
                "What does a component's return value of `null` mean?",
                [
                    "Render nothing",
                    "Throw an error",
                    "Render the previous output",
                    "Unmount the parent",
                ],
                0,
                1,
            ),
        ],
    },
    {
        "name": "Node.js",
        "domain": "BACKEND",
        "questions": [
            Q(
                "What makes Node.js well suited to I/O-heavy servers?",
                [
                    "It is multi-threaded for JavaScript code",
                    "Its non-blocking, event-driven I/O model",
                    "It compiles to native code",
                    "It runs only on Linux",
                ],
                1,
                1,
            ),
            Q(
                "What happens if you run a long CPU-bound loop on Node's main thread?",
                [
                    "Other requests keep being served normally",
                    "The event loop is blocked and other requests wait",
                    "Node moves it to a GPU",
                    "It runs in parallel automatically",
                ],
                1,
                2,
            ),
            Q(
                "Which runs first after the current operation completes?",
                [
                    "setTimeout(fn, 0)",
                    "A resolved promise's .then callback (microtask)",
                    "setImmediate",
                    "An I/O callback",
                ],
                1,
                3,
            ),
            Q(
                "What does `await` do inside an async function?",
                [
                    "Blocks the whole process",
                    "Pauses that function until the promise settles, without blocking the event loop",
                    "Creates a new thread",
                    "Converts a callback to sync code",
                ],
                1,
                1,
            ),
            Q(
                "How should errors from an awaited promise be handled?",
                [
                    "They can't be caught",
                    "With try/catch around the await",
                    "With process.exit",
                    "Only with .finally",
                ],
                1,
                1,
            ),
            Q(
                "What is the purpose of package-lock.json?",
                [
                    "To list scripts",
                    "To record exact dependency versions so installs are reproducible",
                    "To lock the source code",
                    "To store environment variables",
                ],
                1,
                1,
            ),
            Q(
                "Which module is built in for working with file paths in a cross-platform way?",
                ["fs", "path", "url", "os"],
                1,
                1,
            ),
            Q(
                "Why use streams for large files?",
                [
                    "They encrypt data",
                    "They process data in chunks instead of loading it all into memory",
                    "They are required for HTTP",
                    "They compress automatically",
                ],
                1,
                2,
            ),
            Q(
                "What is the `worker_threads` module for?",
                [
                    "Running CPU-heavy JavaScript in parallel threads",
                    "Managing HTTP workers",
                    "Scheduling cron jobs",
                    "Connecting to databases",
                ],
                0,
                2,
            ),
            Q(
                "What does `process.env` contain?",
                [
                    "The process's environment variables",
                    "The installed packages",
                    "Command history",
                    "Open files",
                ],
                0,
                1,
            ),
            Q(
                "Which is the safest way to build a SQL query with user input?",
                [
                    "String concatenation",
                    "Template literals",
                    "Parameterized queries / placeholders",
                    "Escaping quotes manually",
                ],
                2,
                1,
            ),
            Q(
                "What does middleware mean in Express?",
                [
                    "A database layer",
                    "Functions that run in order on a request and can modify it or end the response",
                    "A template engine",
                    "A load balancer",
                ],
                1,
                1,
            ),
            Q(
                "What is an unhandled promise rejection in recent Node versions by default?",
                [
                    "Ignored silently",
                    "It crashes the process",
                    "Retried automatically",
                    "Logged only in debug mode",
                ],
                1,
                3,
            ),
            Q(
                "What does `npm ci` do differently from `npm install`?",
                [
                    "Installs exactly from the lock file and fails if it doesn't match package.json",
                    "Updates every dependency",
                    "Only installs dev dependencies",
                    "Publishes the package",
                ],
                0,
                2,
            ),
            Q(
                "Which format do ES modules use for imports?",
                ["require()", "import / export", "include", "using"],
                1,
                1,
            ),
            Q(
                "What is the main risk of storing secrets directly in source code?",
                [
                    "Slower startup",
                    "They leak to anyone who can read the repository or its history",
                    "Syntax errors",
                    "They expire",
                ],
                1,
                1,
            ),
        ],
    },
    {
        "name": "FastAPI",
        "domain": "BACKEND",
        "questions": [
            Q(
                "What does FastAPI use Pydantic models for?",
                [
                    "Templating HTML",
                    "Validating and serializing request and response data",
                    "Database migrations",
                    "Scheduling jobs",
                ],
                1,
                1,
            ),
            Q(
                "How does FastAPI generate interactive API documentation?",
                [
                    "From docstrings only",
                    "From the OpenAPI schema it builds from routes and type hints",
                    "From a YAML file you write",
                    "It cannot",
                ],
                1,
                1,
            ),
            Q(
                "What is FastAPI's Depends() used for?",
                [
                    "Declaring dependencies (e.g. DB sessions, auth) that are resolved per request",
                    "Importing modules",
                    "Defining database columns",
                    "Running background tasks",
                ],
                0,
                1,
            ),
            Q(
                "What status code does FastAPI return by default for a request body that fails validation?",
                ["400", "422", "500", "404"],
                1,
                2,
            ),
            Q(
                "How do you declare a path parameter?",
                [
                    "@app.get('/items/{item_id}') with an item_id argument",
                    "Using Query()",
                    "Using a global variable",
                    "Using Body()",
                ],
                0,
                1,
            ),
            Q(
                "What is the effect of declaring a route with `async def`?",
                [
                    "It runs in a new process",
                    "It runs on the event loop, so it should not call blocking code directly",
                    "It is cached",
                    "It becomes a background task",
                ],
                1,
                2,
            ),
            Q(
                "Where does FastAPI run a plain `def` (non-async) endpoint?",
                [
                    "On the event loop",
                    "In a thread pool",
                    "In a new process",
                    "It refuses to run it",
                ],
                1,
                3,
            ),
            Q(
                "What does `response_model` on a route do?",
                [
                    "Validates and filters the response to the declared schema",
                    "Sets the HTTP method",
                    "Caches the response",
                    "Adds authentication",
                ],
                0,
                2,
            ),
            Q(
                "How do you raise a 404 from inside an endpoint?",
                [
                    "return 404",
                    "raise HTTPException(status_code=404)",
                    "sys.exit(404)",
                    "print(404)",
                ],
                1,
                1,
            ),
            Q(
                "Which ASGI server is commonly used to run FastAPI?",
                ["Gunicorn sync workers only", "Uvicorn", "Apache mod_php", "Tomcat"],
                1,
                1,
            ),
            Q(
                "What does `model_config = ConfigDict(extra='forbid')` do on a Pydantic v2 model?",
                [
                    "Allows any extra fields",
                    "Rejects input that contains fields not declared on the model",
                    "Makes all fields optional",
                    "Ignores type errors",
                ],
                1,
                2,
            ),
            Q(
                "What is a common use of FastAPI middleware?",
                [
                    "Adding headers, timing or request ids to every request",
                    "Defining models",
                    "Writing migrations",
                    "Rendering React",
                ],
                0,
                1,
            ),
            Q(
                "Which is the right way to read an optional query parameter `q`?",
                [
                    "def f(q: str | None = None)",
                    "def f(*, body)",
                    "request.json()['q'] only",
                    "It's not possible",
                ],
                0,
                1,
            ),
            Q(
                "What is TestClient (from fastapi.testclient) for?",
                [
                    "Load testing",
                    "Calling the app in tests without running a server",
                    "Deploying",
                    "Generating clients",
                ],
                1,
                1,
            ),
            Q(
                "What does a dependency with `yield` let you do?",
                [
                    "Return multiple values",
                    "Run cleanup code after the response (e.g. close a DB session)",
                    "Stream files",
                    "Retry requests",
                ],
                1,
                2,
            ),
            Q(
                "Why should passwords never be returned in a response model?",
                [
                    "They are too long",
                    "Response models define exactly what leaves the API; secrets must never be exposed",
                    "JSON can't encode them",
                    "FastAPI hashes them",
                ],
                1,
                1,
            ),
        ],
    },
    {
        "name": "PostgreSQL",
        "domain": "DATABASE",
        "questions": [
            Q(
                "What does a PRIMARY KEY guarantee?",
                [
                    "Values are unique and not null",
                    "Values are sorted",
                    "The column is indexed for full-text search",
                    "Values are encrypted",
                ],
                0,
                1,
            ),
            Q(
                "What does a FOREIGN KEY constraint enforce?",
                [
                    "Unique values",
                    "That a value exists in the referenced table",
                    "A default value",
                    "Faster queries",
                ],
                1,
                1,
            ),
            Q(
                "Which isolation level is PostgreSQL's default?",
                ["Read uncommitted", "Read committed", "Repeatable read", "Serializable"],
                1,
                2,
            ),
            Q(
                "What does EXPLAIN ANALYZE show?",
                [
                    "The table's data",
                    "The executed query plan with actual timings and row counts",
                    "Permissions",
                    "Index definitions only",
                ],
                1,
                2,
            ),
            Q(
                "What kind of index is the default in PostgreSQL?",
                ["Hash", "B-tree", "GIN", "BRIN"],
                1,
                1,
            ),
            Q(
                "Which index type is typically used for full-text search vectors (tsvector)?",
                ["B-tree", "GIN", "Hash", "None is possible"],
                1,
                2,
            ),
            Q(
                "What does SELECT … FOR UPDATE do?",
                [
                    "Locks the selected rows until the transaction ends",
                    "Updates the rows",
                    "Creates a backup",
                    "Disables triggers",
                ],
                0,
                2,
            ),
            Q(
                "What is the difference between INNER JOIN and LEFT JOIN?",
                [
                    "None",
                    "LEFT JOIN keeps rows from the left table even without a match",
                    "INNER JOIN is faster always",
                    "LEFT JOIN removes duplicates",
                ],
                1,
                1,
            ),
            Q(
                "What does row-level security (RLS) do?",
                [
                    "Encrypts rows",
                    "Restricts which rows a role can see or change using policies",
                    "Compresses tables",
                    "Logs every query",
                ],
                1,
                2,
            ),
            Q(
                "What is the safest way to pass user input into a query?",
                ["String formatting", "Bound parameters", "Escaping by hand", "Using LIKE"],
                1,
                1,
            ),
            Q(
                "What does a transaction's ROLLBACK do?",
                [
                    "Commits changes",
                    "Undoes all changes made in the transaction",
                    "Restarts the server",
                    "Vacuums the table",
                ],
                1,
                1,
            ),
            Q(
                "What is VACUUM used for?",
                [
                    "Deleting tables",
                    "Reclaiming space from dead row versions and updating visibility information",
                    "Creating indexes",
                    "Backing up",
                ],
                1,
                2,
            ),
            Q(
                "Which type should store money exactly in PostgreSQL?",
                ["real", "double precision", "numeric or integer minor units (e.g. paisa)", "text"],
                2,
                1,
            ),
            Q(
                "What does `timestamptz` store?",
                [
                    "A timestamp with an absolute point in time (converted to UTC internally)",
                    "A string",
                    "Only the date",
                    "Local time without zone",
                ],
                0,
                2,
            ),
            Q(
                "What does a CHECK constraint do?",
                [
                    "Validates that column values satisfy a condition",
                    "Creates a foreign key",
                    "Adds an index",
                    "Encrypts the column",
                ],
                0,
                1,
            ),
            Q(
                "What is a CTE (WITH query)?",
                [
                    "A temporary named result set used within a single query",
                    "A stored procedure",
                    "A table index",
                    "A trigger",
                ],
                0,
                2,
            ),
        ],
    },
    {
        "name": "UI/UX",
        "domain": "DESIGN",
        "questions": [
            Q(
                "What minimum contrast ratio does WCAG 2.1 AA require for normal body text?",
                ["2:1", "3:1", "4.5:1", "7:1"],
                2,
                2,
            ),
            Q(
                "What is the recommended minimum touch target size on mobile (WCAG and platform guidance)?",
                ["About 24×24 px", "About 44×44 px", "About 12×12 px", "There is no guidance"],
                1,
                2,
            ),
            Q(
                "What is the purpose of a visible focus indicator?",
                [
                    "Decoration",
                    "Showing keyboard users where they are on the page",
                    "Indicating errors",
                    "Loading feedback",
                ],
                1,
                1,
            ),
            Q(
                "Why should status never be shown by colour alone?",
                [
                    "Colours are slow to render",
                    "People with colour-vision deficiencies may not perceive it; add text or icons",
                    "Colours are not allowed in forms",
                    "It is a performance issue",
                ],
                1,
                1,
            ),
            Q(
                "What is a primary benefit of a design system?",
                [
                    "Consistent, reusable components and patterns across the product",
                    "Faster servers",
                    "Better SEO only",
                    "Fewer users",
                ],
                0,
                1,
            ),
            Q(
                "What does progressive disclosure mean?",
                [
                    "Showing all options at once",
                    "Showing advanced options only when they are needed",
                    "Loading images progressively",
                    "Revealing passwords",
                ],
                1,
                2,
            ),
            Q(
                "A good error message should…",
                [
                    "Blame the user",
                    "Say what went wrong and how to fix it",
                    "Only show an error code",
                    "Disappear after one second",
                ],
                1,
                1,
            ),
            Q(
                "What is the purpose of usability testing?",
                [
                    "To test server load",
                    "To watch real users attempt tasks and find problems in the design",
                    "To check spelling",
                    "To measure colour contrast",
                ],
                1,
                1,
            ),
            Q(
                "What is a skeleton screen?",
                [
                    "A wireframe",
                    "A placeholder layout shown while content loads",
                    "An error page",
                    "A print stylesheet",
                ],
                1,
                1,
            ),
            Q(
                "Which is an example of Hick's law in practice?",
                [
                    "Bigger buttons are easier to hit",
                    "More choices increase the time to decide",
                    "Users read in an F pattern",
                    "Dark mode saves battery",
                ],
                1,
                3,
            ),
            Q(
                "What does Fitts's law describe?",
                [
                    "Colour perception",
                    "Time to reach a target depends on its distance and size",
                    "Reading speed",
                    "Memory limits",
                ],
                1,
                2,
            ),
            Q(
                "Why respect the 'prefers-reduced-motion' setting?",
                [
                    "It saves bandwidth",
                    "Some users get dizzy or distracted by motion",
                    "It is required by browsers",
                    "It improves SEO",
                ],
                1,
                1,
            ),
            Q(
                "What is the main goal of a primary button style?",
                [
                    "To show the single most important action on the screen",
                    "To decorate",
                    "To show errors",
                    "To link to help",
                ],
                0,
                1,
            ),
            Q(
                "What is information architecture?",
                [
                    "Server layout",
                    "How content is organised, labelled and navigated",
                    "Database design",
                    "Typography",
                ],
                1,
                2,
            ),
            Q(
                "Why use sentence case and clear verbs on buttons (e.g. 'Save changes')?",
                [
                    "Shorter code",
                    "They say exactly what will happen when pressed",
                    "They load faster",
                    "Browsers require it",
                ],
                1,
                1,
            ),
            Q(
                "What should an empty state include?",
                [
                    "Nothing",
                    "A short explanation and the next action to take",
                    "A random image only",
                    "An error code",
                ],
                1,
                1,
            ),
        ],
    },
    {
        "name": "Testing",
        "domain": "TESTING",
        "questions": [
            Q(
                "What does a unit test check?",
                [
                    "The whole system end to end",
                    "A small unit of code in isolation",
                    "Server load",
                    "Visual layout",
                ],
                1,
                1,
            ),
            Q(
                "What is the testing pyramid's main idea?",
                [
                    "Write mostly end-to-end tests",
                    "Have many fast unit tests, fewer integration tests and few end-to-end tests",
                    "Test only in production",
                    "Avoid unit tests",
                ],
                1,
                1,
            ),
            Q(
                "What is a test double such as a mock or stub used for?",
                [
                    "Running tests twice",
                    "Replacing a real dependency to isolate the code under test",
                    "Doubling coverage",
                    "Load testing",
                ],
                1,
                1,
            ),
            Q(
                "What is regression testing?",
                [
                    "Testing new features only",
                    "Re-running tests to make sure existing behaviour still works after changes",
                    "Testing performance",
                    "Testing security",
                ],
                1,
                1,
            ),
            Q(
                "What does boundary value analysis focus on?",
                [
                    "Values at and just around the edges of valid ranges",
                    "Random values",
                    "Only valid values",
                    "UI colours",
                ],
                0,
                2,
            ),
            Q(
                "What is a flaky test?",
                [
                    "A test that is slow",
                    "A test that sometimes passes and sometimes fails without code changes",
                    "A test with no assertions",
                    "A skipped test",
                ],
                1,
                1,
            ),
            Q(
                "What does code coverage measure?",
                [
                    "How many bugs exist",
                    "How much code is executed by the tests",
                    "Test speed",
                    "Number of test files",
                ],
                1,
                1,
            ),
            Q(
                "Which statement about 100% code coverage is true?",
                [
                    "It proves the code has no bugs",
                    "It shows every line ran, but not that behaviour is correct",
                    "It is impossible",
                    "It makes tests faster",
                ],
                1,
                2,
            ),
            Q(
                "What is property-based testing?",
                [
                    "Testing CSS properties",
                    "Generating many inputs to check that a stated property always holds",
                    "Testing object properties only",
                    "Manual testing",
                ],
                1,
                3,
            ),
            Q(
                "What is an end-to-end (E2E) test?",
                [
                    "A test of one function",
                    "A test that drives the full system the way a user would",
                    "A database test",
                    "A lint check",
                ],
                1,
                1,
            ),
            Q(
                "What is the purpose of a test fixture?",
                [
                    "Fixing bugs",
                    "Setting up a known state or data for tests",
                    "Deploying",
                    "Formatting code",
                ],
                1,
                1,
            ),
            Q(
                "In test-driven development (TDD), what comes first?",
                [
                    "Writing the implementation",
                    "Writing a failing test",
                    "Refactoring",
                    "Deployment",
                ],
                1,
                2,
            ),
            Q(
                "What is equivalence partitioning?",
                [
                    "Splitting inputs into groups expected to behave the same and testing one from each",
                    "Splitting servers",
                    "Parallel testing",
                    "Comparing outputs",
                ],
                0,
                2,
            ),
            Q(
                "What is fuzz testing?",
                [
                    "Testing fonts",
                    "Feeding unexpected or random inputs to find crashes and errors",
                    "Testing animations",
                    "Testing documentation",
                ],
                1,
                2,
            ),
            Q(
                "What should a good bug report include?",
                [
                    "Only 'it doesn't work'",
                    "Steps to reproduce, expected result and actual result",
                    "The tester's opinion",
                    "A fix",
                ],
                1,
                1,
            ),
            Q(
                "What is a security test for IDOR checking?",
                [
                    "That one user cannot access another user's resource by changing an id",
                    "Password strength",
                    "Page speed",
                    "Spelling",
                ],
                0,
                2,
            ),
        ],
    },
    {
        "name": "Flutter",
        "domain": "MOBILE",
        "questions": [
            Q(
                "Which language is used to write Flutter apps?",
                ["Kotlin", "Swift", "Dart", "JavaScript"],
                2,
                1,
            ),
            Q(
                "What is the difference between a StatelessWidget and a StatefulWidget?",
                [
                    "None",
                    "A StatefulWidget has mutable state that can change over time",
                    "StatelessWidgets are faster to type",
                    "StatefulWidgets can't have children",
                ],
                1,
                1,
            ),
            Q(
                "What does calling setState() do?",
                [
                    "Saves to disk",
                    "Marks the widget as dirty so it rebuilds with the new state",
                    "Navigates to a new page",
                    "Restarts the app",
                ],
                1,
                1,
            ),
            Q(
                "What does 'hot reload' do?",
                [
                    "Restarts the device",
                    "Injects updated code into the running app, keeping state where possible",
                    "Clears the cache",
                    "Builds a release APK",
                ],
                1,
                1,
            ),
            Q(
                "Which widget arranges children vertically?",
                ["Row", "Column", "Stack", "Wrap only"],
                1,
                1,
            ),
            Q(
                "Which widget lets children overlap one another?",
                ["Column", "Row", "Stack", "ListView"],
                2,
                1,
            ),
            Q(
                "What is the purpose of a Key in Flutter?",
                [
                    "Encryption",
                    "Preserving widget identity and state when widgets move in the tree",
                    "Keyboard shortcuts",
                    "Database ids",
                ],
                1,
                2,
            ),
            Q(
                "Which widget is best for a long, scrollable list built lazily?",
                ["Column", "ListView.builder", "Row", "Stack"],
                1,
                1,
            ),
            Q(
                "What is a Future in Dart?",
                [
                    "A UI widget",
                    "A value or error that will be available later",
                    "A database",
                    "A route",
                ],
                1,
                1,
            ),
            Q(
                "How do you wait for a Future inside an async function?",
                ["await", "yield", "sleep", "join"],
                0,
                1,
            ),
            Q(
                "What is a Stream in Dart?",
                [
                    "A single future value",
                    "A sequence of asynchronous events",
                    "A file",
                    "A layout widget",
                ],
                1,
                2,
            ),
            Q(
                "Which widget rebuilds when a Future completes?",
                ["FutureBuilder", "ListView", "Container", "Padding"],
                0,
                1,
            ),
            Q(
                "What does `const` before a widget constructor help with?",
                [
                    "Makes it mutable",
                    "Lets Flutter reuse the instance and skip unnecessary rebuilds",
                    "Adds animation",
                    "Makes it async",
                ],
                1,
                2,
            ),
            Q(
                "What is BuildContext?",
                [
                    "A handle to the widget's location in the tree",
                    "A database connection",
                    "A theme file",
                    "A test runner",
                ],
                0,
                2,
            ),
            Q(
                "How do you navigate to a new screen with the basic Navigator?",
                ["Navigator.push(...)", "window.location", "setState(newPage)", "runApp(newPage)"],
                0,
                1,
            ),
            Q(
                "What does the pubspec.yaml file declare?",
                [
                    "Only the app icon",
                    "Package metadata, dependencies and assets",
                    "Database schema",
                    "Server routes",
                ],
                1,
                1,
            ),
        ],
    },
    {
        "name": "DevOps",
        "domain": "DEVOPS",
        "questions": [
            Q(
                "What is the main benefit of containerising an application with Docker?",
                [
                    "It makes code faster",
                    "It packages the app with its dependencies so it runs the same everywhere",
                    "It replaces version control",
                    "It removes the need for tests",
                ],
                1,
                1,
            ),
            Q(
                "What is the difference between a Docker image and a container?",
                [
                    "None",
                    "An image is a template; a container is a running instance of it",
                    "Containers are stored on Docker Hub",
                    "Images run processes",
                ],
                1,
                1,
            ),
            Q(
                "What is continuous integration (CI)?",
                [
                    "Deploying once a year",
                    "Automatically building and testing every change merged into the shared branch",
                    "Manual testing",
                    "Writing documentation",
                ],
                1,
                1,
            ),
            Q(
                "Why run containers as a non-root user?",
                [
                    "It is faster",
                    "It limits the damage if the container is compromised",
                    "Docker requires it",
                    "It saves disk",
                ],
                1,
                2,
            ),
            Q(
                "What does a health check in a container orchestrator do?",
                [
                    "Monitors CPU only",
                    "Reports whether the service is working so it can be restarted or taken out of rotation",
                    "Updates the image",
                    "Backs up data",
                ],
                1,
                1,
            ),
            Q(
                "What is infrastructure as code?",
                [
                    "Writing code on servers",
                    "Managing infrastructure through versioned configuration files",
                    "Hard-coding IP addresses",
                    "A programming language",
                ],
                1,
                2,
            ),
            Q(
                "What is a reverse proxy such as Nginx commonly used for?",
                [
                    "Compiling code",
                    "Terminating TLS, routing and load-balancing requests to backends",
                    "Running databases",
                    "Writing logs only",
                ],
                1,
                1,
            ),
            Q(
                "What is a blue-green deployment?",
                [
                    "Deploying only on weekdays",
                    "Running two environments and switching traffic to the new one when it is ready",
                    "Using two colour themes",
                    "A rollback tool for databases",
                ],
                1,
                3,
            ),
            Q(
                "Where should secrets such as database passwords live?",
                [
                    "In the Git repository",
                    "In environment variables or a secrets manager, never in code",
                    "In a public bucket",
                    "In the Docker image",
                ],
                1,
                1,
            ),
            Q(
                "What does a lock file (e.g. requirements.lock) help with?",
                [
                    "Security only",
                    "Reproducible builds with exact dependency versions",
                    "Encryption",
                    "Faster networking",
                ],
                1,
                1,
            ),
            Q(
                "What is the purpose of log aggregation?",
                [
                    "Deleting logs",
                    "Collecting logs from many services in one place to search and alert",
                    "Compressing code",
                    "Testing",
                ],
                1,
                2,
            ),
            Q(
                "What does 'least privilege' mean?",
                [
                    "Giving everyone admin rights",
                    "Giving each user or service only the permissions it needs",
                    "Using the cheapest server",
                    "Running fewer services",
                ],
                1,
                1,
            ),
            Q(
                "What is a rollback?",
                [
                    "Reverting to the previous working version after a bad release",
                    "Scaling up",
                    "Rotating logs",
                    "Clearing caches",
                ],
                0,
                1,
            ),
            Q(
                "What is the role of a Dockerfile?",
                [
                    "Running containers",
                    "Describing step by step how to build an image",
                    "Storing logs",
                    "Monitoring",
                ],
                1,
                1,
            ),
            Q(
                "What does horizontal scaling mean?",
                [
                    "Adding more machines or instances",
                    "Upgrading one machine's CPU",
                    "Rotating the screen",
                    "Reducing traffic",
                ],
                0,
                2,
            ),
            Q(
                "What is the purpose of a staging environment?",
                [
                    "Production traffic",
                    "Testing a release in a production-like setting before it goes live",
                    "Local development only",
                    "Storing backups",
                ],
                1,
                1,
            ),
        ],
    },
]

# Spread correct answers evenly across A–D: shuffle each question's options with a seed derived
# from its text (reproducible), and balance positions per skill.
for s in skills:
    for i, q in enumerate(s["questions"]):
        target = i % 4  # 4 positions used equally often within each skill
        correct = q["options"][q["answer"]]
        others = [o for j, o in enumerate(q["options"]) if j != q["answer"]]
        random.Random(hashlib.sha256(q["text"].encode()).hexdigest()).shuffle(others)
        others.insert(target, correct)
        q["options"], q["answer"] = others, target
    random.Random(s["name"]).shuffle(s["questions"])
for s in skills:
    assert len(s["questions"]) >= 15, s["name"]
    for q in s["questions"]:
        assert len(q["options"]) == 4 and 0 <= q["answer"] <= 3 and len(set(q["options"])) == 4, q
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump({"version": 1, "skills": skills}, out, indent=1, ensure_ascii=False)
print(sum(len(s["questions"]) for s in skills), "questions")
