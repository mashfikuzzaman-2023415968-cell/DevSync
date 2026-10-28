# React questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/react.md`.

## react-legacy-02

State and hooks · difficulty 2 · independent solve passed

Why is mutating state directly (e.g. pushing into an array held in state) a problem?

- A. React may not detect the change because the reference is the same ✔
- B. It is a syntax error
- C. It is slower
- D. It deletes the state

Explanation: React decides whether to re-render by comparing the new state with the old using Object.is. Pushing into the existing array keeps the same reference, so the change may not be detected. Create a new array (e.g. [...items, item]).

Approved by: ______

Correction: ______

## react-legacy-03

Performance · difficulty 2 · independent solve passed

What does React.lazy combined with Suspense provide?

- A. Server-side rendering
- B. Code-splitting: loading a component's code only when it is first rendered ✔
- C. Global state
- D. Automatic memoization

Explanation: React.lazy loads a component through a dynamic import() the first time it renders, and Suspense shows a fallback while the chunk loads. This splits the bundle so users download less code up front. It is not SSR, state or memoisation.

Approved by: ______

Correction: ______

## react-legacy-04

Effects and data fetching · difficulty 1 · independent solve passed

When does an effect with an empty dependency array (`useEffect(fn, [])`) run?

- A. Only when props change
- B. On every render
- C. Only after the first render (and cleanup on unmount) ✔
- D. Never

Explanation: With an empty dependency array the effect runs after the first render and its cleanup runs on unmount, since it has no values to react to. (In development StrictMode adds one extra mount/unmount cycle.)

Approved by: ______

Correction: ______

## react-legacy-05

State and hooks · difficulty 1 · independent solve passed

What does calling a state setter from useState do?

- A. Schedules a re-render with the new state ✔
- B. Mutates the state variable immediately
- C. Reloads the page
- D. Resets every other piece of state

Explanation: A state setter queues an update and schedules a re-render with the new value. The variable in the current render keeps its old value, and other state is untouched.

Approved by: ______

Correction: ______

## react-legacy-06

State and hooks · difficulty 1 · independent solve passed

What is the purpose of React Context?

- A. To pass values through the tree without passing props at every level ✔
- B. To replace all component state
- C. To call APIs
- D. To speed up rendering

Explanation: Context lets a provider make a value available to any descendant through useContext, avoiding prop drilling through intermediate components. It is a delivery mechanism, not a replacement for state, a data-fetching tool or a speed-up.

Approved by: ______

Correction: ______

## react-legacy-07

Components and props · difficulty 1 · independent solve passed

What does a component's return value of `null` mean?

- A. Throw an error
- B. Unmount the parent
- C. Render the previous output
- D. Render nothing ✔

Explanation: A component that returns null renders nothing in its place, which is the standard way to hide a component conditionally. It does not throw, unmount the parent or keep earlier output.

Approved by: ______

Correction: ______

## react-legacy-08

State and hooks · difficulty 1 · independent solve passed

Changing the `.current` value of a ref created with useRef will…

- A. Throw an error
- B. Reset the component
- C. Not trigger a re-render ✔
- D. Trigger a re-render

Explanation: A ref is a mutable box that persists across renders. Writing to ref.current does not notify React, so no re-render happens. Use state when the UI must update.

Approved by: ______

Correction: ______

## react-legacy-09

Performance · difficulty 2 · independent solve passed

What is the main purpose of useCallback?

- A. To run code after paint
- B. To keep the same function identity between renders unless its dependencies change ✔
- C. To create a ref
- D. To fetch data

Explanation: useCallback returns the same function instance between renders until its dependencies change. This matters for referential equality, e.g. when passing callbacks to React.memo children or listing them in effect dependencies.

Approved by: ______

Correction: ______

## react-legacy-10

Components and props · difficulty 1 · independent solve passed

Why does React need a `key` prop on list items?

- A. To sort the list alphabetically
- B. To identify items between renders so it can match and reorder them ✔
- C. To style each item
- D. To make items focusable

Explanation: Keys give list items a stable identity so React can match items between renders, reorder DOM nodes and preserve each item's state. They are not passed as props and do not affect sorting, styling or focus.

Approved by: ______

Correction: ______

## react-legacy-11

State and hooks · difficulty 1 · independent solve passed

What is 'lifting state up'?

- A. Putting state in a ref
- B. Storing state in localStorage
- C. Using a global variable
- D. Moving state to the closest common parent of components that need it ✔

Explanation: Lifting state up means moving shared state to the closest common ancestor and passing it down as props (with callbacks to change it), so sibling components stay in sync.

Approved by: ______

Correction: ______

## react-legacy-12

Performance · difficulty 1 · independent solve passed

Which hook memoizes a computed value between renders?

- A. useMemo ✔
- B. useRef
- C. useId
- D. useState

Explanation: useMemo caches the result of a computation between renders and recomputes it only when its dependencies change. useRef holds a mutable box, useId generates ids and useState holds state.

Approved by: ______

Correction: ______

## react-legacy-13

Forms and validation · difficulty 1 · independent solve passed

What is a 'controlled' input in React?

- A. An input inside a form tag
- B. An input with validation
- C. An input rendered by a server
- D. An input whose value is driven by React state ✔

Explanation: A controlled input gets its value from React state through the value prop and reports changes through onChange, so React is the single source of truth. An uncontrolled input keeps its value in the DOM.

Approved by: ______

Correction: ______

## react-legacy-14

State and hooks · difficulty 2 · independent solve passed

Which statement about the Rules of Hooks is correct?

- A. Hooks can be called from class components
- B. Hooks must be called inside conditions
- C. Hooks must be called in the same order on every render, at the top level of components or custom hooks ✔
- D. Hooks may be called inside loops

Explanation: React identifies hooks by call order, so hooks must be called unconditionally at the top level of function components or custom hooks, in the same order every render. Not inside conditions, loops, nested functions or classes.

Approved by: ______

Correction: ______

## react-legacy-15

Components and props · difficulty 1 · independent solve passed

Which is the safest way to render user-supplied text in React?

- A. dangerouslySetInnerHTML
- B. Building an HTML string
- C. Rendering it as a child expression like {text} ✔
- D. Using eval

Explanation: React escapes strings rendered as children ({text}), so user input is shown as text and cannot inject markup. dangerouslySetInnerHTML, HTML strings and eval can all execute attacker-controlled content.

Approved by: ______

Correction: ______

## react-legacy-16

Effects and data fetching · difficulty 2 · independent solve passed

What should a useEffect cleanup function typically do?

- A. Set state for the next render
- B. Call the effect again
- C. Return JSX
- D. Undo subscriptions, timers or listeners the effect created ✔

Explanation: The cleanup function runs before the effect re-runs and when the component unmounts. It should release what the effect set up (subscriptions, timers, listeners, requests) to avoid leaks and stale callbacks.

Approved by: ______

Correction: ______

## react-components-props-01

Components and props · difficulty 1 · independent solve passed

Which prop holds the elements written between a component's opening and closing tags, as in `<Card>...</Card>`?

- A. props.children ✔
- B. props.content
- C. props.slot
- D. props.inner

Explanation: React passes whatever is nested between the tags as the special `children` prop. There is no built-in `content`, `slot` or `inner` prop; those names only work if the parent passes them explicitly.

Approved by: ______

Correction: ______

## react-components-props-02

Components and props · difficulty 2 · independent solve passed

A child component must change a number that its parent owns and passes down as a prop. What is the idiomatic way?

- A. The child assigns a new value to props.count, which makes React re-render the parent component
- B. The parent also passes a callback prop; the child calls it and the parent updates its state ✔
- C. The child keeps the number in a module-level variable that the parent component reads on render
- D. The child calls ReactDOM.render again with a different count prop for the same parent

Explanation: Props are read-only (frozen in development). Data flows down and changes flow up: the owner of the state exposes a setter or handler via props, the child calls it, and the owner re-renders with the new value.

Approved by: ______

Correction: ______

## react-components-props-03

Components and props · difficulty 2 · execution check passed

What HTML does `Inbox` produce when `messages` is an empty array?

```
1  function Inbox({ messages }) {
2    return <div>{messages.length && <p>You have mail</p>}</div>;
3  }
4  // rendered with messages = []
```

- A. <div></div>
- B. <div><p>You have mail</p></div>
- C. <div>false</div>
- D. <div>0</div> ✔

Explanation: `messages.length && ...` evaluates to 0 when the array is empty, and React renders the number 0 as text (unlike false, null or undefined, which render nothing). Use `messages.length > 0 &&` or a ternary.

Approved by: ______

Correction: ______

## react-components-props-04

Components and props · difficulty 2 · execution check passed

What does `<Badge color={null} />` render?

```
1  function Badge({ color = 'gray' }) {
2    return <span className={'badge-' + color} />;
3  }
```

- A. <span class="badge-null"></span> ✔
- B. <span class="badge-gray"></span>
- C. <span class="badge-"></span>
- D. <span class="badge-undefined"></span>

Explanation: Destructuring defaults apply only when the value is undefined, not when it is null. With color={null} the default 'gray' is not used and string concatenation turns null into 'null'.

Approved by: ______

Correction: ______

## react-components-props-05

Components and props · difficulty 3 · execution check passed

After the button is clicked once, what text do the list items show, in order?

```
1  function Row({ name }) {
2    const [label] = useState(name);
3    return <li>{label}</li>;
4  }
5  function List() {
6    const [names, setNames] = useState(['A', 'B', 'C']);
7    return (
8      <>
9        <button onClick={() => setNames(names.slice(1))}>Remove first</button>
10       <ul>{names.map((n, i) => <Row key={i} name={n} />)}</ul>
11     </>
12   );
13 }
```

- A. B, C
- B. A, B ✔
- C. A, B, C
- D. C, B

Explanation: With key={i} the rows are matched by position, not by item. After removing the first name, row 0 and row 1 keep their existing instances, whose `label` state was initialised once from the old props, so they still show A and B and the last row is unmounted. Use a stable id as the key.

Approved by: ______

Correction: ______

## react-components-props-06

Components and props · difficulty 3 · execution check passed

Typing in this input loses focus after every keystroke. What is the cause?

```
1  function SignupForm() {
2    const [email, setEmail] = useState('');
3    function EmailField() {
4      return <input value={email} onChange={(e) => setEmail(e.target.value)} />;
5    }
6    return <EmailField />;
7  }
```

- A. The onChange handler is an inline arrow function, which is recreated on every render and so resets the focus
- B. The input is controlled, and React drops the focus from controlled inputs after each state update it applies
- C. EmailField is declared inside SignupForm, so each render creates a new component type and remounts the input ✔
- D. useState is called before EmailField is defined, so the state update is lost and the input is re-created

Explanation: A component defined inside another component is a new function on every render, so React sees a different type, unmounts the old input and mounts a new one (losing focus). Declare EmailField outside SignupForm, or call it as a plain function. Inline handlers and controlled inputs do not cause this.

Approved by: ______

Correction: ______

## react-components-props-07

Components and props · difficulty 3 · execution check passed

The button is clicked twice while `first` is true, then `first` becomes false. What does the button show?

```
1  function Counter({ label }) {
2    const [n, setN] = useState(0);
3    return <button onClick={() => setN(n + 1)}>{label}: {n}</button>;
4  }
5  function App({ first }) {
6    return first ? <Counter label="A" /> : <Counter label="B" />;
7  }
```

- A. B: 0
- B. A: 2
- C. A: 0
- D. B: 2 ✔

Explanation: Both branches render a Counter at the same position with the same type, so React keeps the existing instance and its state (n = 2) and only updates the label prop. Give the two a different key (or render them in different positions) to reset the state.

Approved by: ______

Correction: ______

## react-state-hooks-01

State and hooks · difficulty 2 · execution check passed

`count` is 0. After one click on a button that runs `handleClick`, what is `count` on the next render?

```
1  const [count, setCount] = useState(0);
2  function handleClick() {
3    setCount(count + 1);
4    setCount(count + 1);
5    setCount(c => c + 1);
6  }
```

- A. 0
- B. 1
- C. 2 ✔
- D. 3

Explanation: Both `setCount(count + 1)` calls use the same snapshot (count = 0), so each queues 'set to 1'. The updater `c => c + 1` then runs on the queued value 1 and gives 2. Use updater functions when the next state depends on the previous one.

Approved by: ______

Correction: ______

## react-state-hooks-02

State and hooks · difficulty 3 · execution check passed

After clicking Add, the list on screen stays empty. Why?

```
1  function reducer(state, action) {
2    if (action.type === 'add') {
3      state.items.push(action.item);
4      return state;
5    }
6    return state;
7  }
8  // const [state, dispatch] = useReducer(reducer, { items: [] });
9  // clicking Add calls dispatch({ type: 'add', item: 'x' });
10 // the screen renders state.items
```

- A. The reducer returns the same state object it mutated, so React sees no change and skips the render ✔
- B. dispatch only schedules the update, so the list becomes visible after a second click on the button
- C. useReducer cannot hold an array inside its state object, so the pushed item is silently discarded
- D. The reducer must be wrapped in useCallback before dispatch will call it with the action object

Explanation: React compares the new state with the old using Object.is. A reducer that mutates `state` and returns it yields the same reference, so React bails out. Return a new object, e.g. { ...state, items: [...state.items, action.item] }.

Approved by: ______

Correction: ______

## react-state-hooks-03

State and hooks · difficulty 3 · execution check passed

On the first click, which value does the timeout callback push onto `log`?

```
1  const log = [];
2  function Counter() {
3    const [count, setCount] = useState(0);
4    function handleClick() {
5      setCount(count + 5);
6      setTimeout(() => log.push(count), 0);
7    }
8    return <button onClick={handleClick}>{count}</button>;
9  }
```

- A. 0 ✔
- B. 1
- C. 5
- D. 10

Explanation: Each render has its own snapshot of state. The handler created during the render where count is 0 closes over that 0, so the callback pushes 0 even though count becomes 5 on the next render.

Approved by: ______

Correction: ______

## react-state-hooks-04

State and hooks · difficulty 2 · independent solve passed

Two components each call the same custom hook `useCounter()`, which uses `useState` inside. How are their counters related?

- A. They share one value, because the hook function is defined only once in the codebase
- B. Each call gets its own independent state; the hook shares logic, not state ✔
- C. They share one value only if the two components are rendered as siblings in the tree
- D. React throws an error when two different components call the same custom hook

Explanation: State created by useState inside a custom hook belongs to the component that calls it. Calling the hook twice gives two separate states. To share state, lift it up or put it in context.

Approved by: ______

Correction: ______

## react-effects-data-01

Effects and data fetching · difficulty 1 · independent solve passed

In a function component, where should a request that loads data when the component first appears normally be started?

- A. Directly in the component body, before the return
- B. Inside the JSX that the component returns
- C. Inside a useEffect callback ✔
- D. In the initial value, as useState(fetch(url))

Explanation: Rendering must be pure, so network requests belong in effects (or event handlers). Starting a request in the body would repeat it on every render, and useState(fetch(url)) would store a Promise.

Approved by: ______

Correction: ______

## react-effects-data-02

Effects and data fetching · difficulty 1 · independent solve passed

What does the dependency array in `useEffect(fn, [userId])` control?

- A. The effect runs once for every item in the array, in the order that the items appear
- B. userId is passed to fn as its first argument every time that the effect is run
- C. React re-renders the component whenever userId changes, even when nothing else did
- D. The effect runs again after a render only if userId changed since the previous render ✔

Explanation: The array lists the reactive values the effect reads. After each render React compares them with the previous ones (Object.is) and re-runs the effect only if one differs. It does not pass arguments or trigger renders.

Approved by: ______

Correction: ______

## react-effects-data-03

Effects and data fetching · difficulty 2 · execution check passed

The network tab shows this request being sent over and over. Which change stops the repeated requests while still loading the right user?

```
1  function Profile({ id }) {
2    const [user, setUser] = useState(null);
3    useEffect(() => {
4      fetch('/api/users/' + id).then((r) => r.json()).then(setUser);
5    });
6    return <h1>{user ? user.name : 'Loading'}</h1>;
7  }
```

- A. Pass [id] as the second argument to useEffect ✔
- B. Wrap the fetch call in a useCallback hook
- C. Call setUser inside a setTimeout callback
- D. Move the fetch call into the component body

Explanation: Without a dependency array the effect runs after every render; setUser with a new object triggers a render, which re-runs the effect, forever. [id] makes it run only when id changes. The other changes still fetch on every render.

Approved by: ______

Correction: ______

## react-effects-data-04

Effects and data fetching · difficulty 2 · execution check passed

After the component has been on screen for about five seconds, what does it show?

```
1  function Ticker() {
2    const [count, setCount] = useState(0);
3    useEffect(() => {
4      const t = setInterval(() => setCount(count + 1), 1000);
5      return () => clearInterval(t);
6    }, []);
7    return <p>{count}</p>;
8  }
```

- A. 0
- B. 1 ✔
- C. 4
- D. 5

Explanation: The effect runs once with an empty dependency array, so its callback closes over count = 0 forever. Every tick calls setCount(0 + 1), so the value becomes 1 and then stays 1. Use setCount(c => c + 1) or list count in the dependencies.

Approved by: ______

Correction: ______

## react-effects-data-05

Effects and data fetching · difficulty 2 · execution check passed

A component mounts with id = 1 and is later re-rendered with id = 2 (no StrictMode). What does `log` contain afterwards?

```
1  useEffect(() => {
2    log.push('start ' + id);
3    return () => { log.push('stop ' + id); };
4  }, [id]);
```

- A. start 1, start 2, stop 1
- B. start 1, stop 1, start 2 ✔
- C. start 1, stop 2, start 2
- D. start 1, start 2

Explanation: When the dependencies change, React first runs the cleanup of the previous effect (which closed over id 1), then runs the new effect with id 2. The cleanup therefore logs 'stop 1' before 'start 2'.

Approved by: ______

Correction: ______

## react-effects-data-06

Effects and data fetching · difficulty 3 · execution check passed

`id` changes from 1 to 2 while the first request is pending, and the response for 1 arrives after the response for 2, so the screen shows user 1 under id 2. Which change fixes it?

```
1  function User({ id }) {
2    const [user, setUser] = useState(null);
3    useEffect(() => {
4      fetch('/api/users/' + id)
5        .then((r) => r.json())
6        .then(setUser);
7    }, [id]);
8    return <p>{user ? user.name : '...'}</p>;
9  }
```

- A. Remove id from the dependency array so that only a single request is ever made
- B. Wrap setUser in useCallback so that late responses are dropped before they apply
- C. Set a local ignore flag in the effect's cleanup and skip setUser when it is set ✔
- D. Make the effect callback async and await the fetch call inside of that callback

Explanation: Responses can arrive out of order. A cleanup that sets `ignore = true` marks the earlier effect as stale, so its late response is discarded (AbortController works too). The other options either stop refetching, do nothing about ordering, or break the effect's return value.

Approved by: ______

Correction: ______

## react-effects-data-07

Effects and data fetching · difficulty 3 · execution check passed

The component mounts (no StrictMode) and the button is then clicked twice. How many times is 'load' pushed onto `log`?

```
1  function Results() {
2    const [n, setN] = useState(0);
3    const options = { limit: 10 };
4    useEffect(() => { log.push('load'); }, [options]);
5    return <button onClick={() => setN(n + 1)}>{n}</button>;
6  }
```

- A. 0
- B. 1
- C. 2
- D. 3 ✔

Explanation: `options` is a new object on every render, and dependencies are compared with Object.is, so the effect sees a changed dependency after each of the three renders (mount plus two clicks). Move the object outside the component or memoise it.

Approved by: ______

Correction: ______

## react-effects-data-08

Effects and data fetching · difficulty 3 · independent solve passed

In development with StrictMode on, an effect that sends an analytics request on mount fires twice. What is the correct reading?

- A. A mistake in the dependency array causes a second run of the effect in production builds too, not only in development
- B. StrictMode doubles every state update, so production builds also render each component twice on mount
- C. The browser fires the effect again whenever the tab regains focus after the user switches windows
- D. React deliberately mounts, unmounts and remounts the component once in development to expose missing cleanup ✔

Explanation: In React 18 development, StrictMode simulates unmount and remount once to check that effects are resilient (cleanup/idempotent). It does not happen in production builds. Fix by adding cleanup or making the effect safe to run twice, not by removing StrictMode.

Approved by: ______

Correction: ______

## react-forms-validation-01

Forms and validation · difficulty 1 · independent solve passed

An input has `value={name}` but no `onChange` handler. What happens when the user types in it?

- A. The text does not change, and React warns that the field is read-only ✔
- B. The text changes and name updates automatically as the user types in the field
- C. The input is treated as uncontrolled and works normally without any warning
- D. React throws an error and unmounts the whole form from the page

Explanation: Passing `value` makes the input controlled, so only state can change what it shows. Without onChange (or readOnly) the field is frozen and React logs a warning. Use defaultValue for an uncontrolled input.

Approved by: ______

Correction: ______

## react-forms-validation-02

Forms and validation · difficulty 1 · independent solve passed

A `<form onSubmit={handleSubmit}>` handler does not call `event.preventDefault()`. What happens on submit?

- A. React blocks the submit by itself and logs a warning to the console
- B. The browser also submits the form normally, which reloads the page ✔
- C. Nothing extra happens, because React always cancels the default submission
- D. The handler runs only after the browser has cleared the form fields

Explanation: React does not cancel the browser default for you. Unless the handler calls event.preventDefault(), the browser performs a normal form submission and reloads the page, losing client-side state.

Approved by: ______

Correction: ______

## react-forms-validation-03

Forms and validation · difficulty 2 · independent solve passed

A sign-up form must show 'Email is invalid' only after the user has left the field, not while they are still typing. What is a good approach?

- A. Disable the input until the user clicks Submit, then validate it and re-enable it for the next try
- B. Store the error in a ref and read it during render so that the message appears a little later
- C. Keep a touched flag per field, set it in onBlur, and show the error only if the field is touched and invalid ✔
- D. Throw an error from onChange and catch it in the parent component to display the message

Explanation: Validation logic can run on every change, but when to show the message is separate UI state. A per-field touched flag set on blur is the standard pattern. The other options block input, rely on refs that do not re-render, or misuse exceptions.

Approved by: ______

Correction: ______

## react-forms-validation-04

Forms and validation · difficulty 2 · execution check passed

The user changes the field to 2. What does the `<p>` show?

```
1  function Total() {
2    const [qty, setQty] = useState('1');
3    return (
4      <div>
5        <input type="number" value={qty} onChange={(e) => setQty(e.target.value)} />
6        <p>{qty + 1}</p>
7      </div>
8    );
9  }
```

- A. 2
- B. 3
- C. 21 ✔
- D. NaN

Explanation: e.target.value is always a string, even for type="number". The state is the string '2', so qty + 1 concatenates to '21'. Convert with Number(e.target.value) before doing arithmetic.

Approved by: ______

Correction: ______

## react-forms-validation-05

Forms and validation · difficulty 3 · execution check passed

Users cannot type a space between their first and last name. What is the cause?

```
1  function NameField() {
2    const [name, setName] = useState('');
3    return (
4      <input
5        value={name}
6        onChange={(e) => setName(e.target.value.trim())}
7      />
8    );
9  }
```

- A. A controlled input with value={name} ignores whitespace characters that the user types into it
- B. useState('') should start as null before the controlled input is able to accept spaces at all
- C. onChange only fires on blur in React, so the typed space is dropped before the handler runs
- D. trim() in onChange strips the space before it is stored, so the controlled value never contains it ✔

Explanation: After typing 'John' and a space, the handler stores 'John ' trimmed to 'John', and React sets the input back to 'John', so the space disappears. Trim when submitting, not on each change.

Approved by: ______

Correction: ______

## react-forms-validation-06

Forms and validation · difficulty 3 · execution check passed

The form is submitted once with email 'bad'. What happens?

```
1  function SignupForm({ save }) {
2    const [email] = useState('bad');
3    const [error, setError] = useState('');
4    function handleSubmit(e) {
5      e.preventDefault();
6      setError(email.includes('@') ? '' : 'Invalid email');
7      if (!error) save(email);
8    }
9    return (
10     <form onSubmit={handleSubmit}>
11       <p>{error}</p>
12       <button>Send</button>
13     </form>
14   );
15 }
```

- A. save('bad') is called, and the message 'Invalid email' appears ✔
- B. save is not called, and the message 'Invalid email' appears on the next render
- C. save is not called, and no message appears because the update is still pending
- D. save('bad') is called twice, and the message 'Invalid email' appears as well

Explanation: State updates are applied on the next render, so on line 7 `error` is still the empty string from this render's snapshot. `!error` is true, save runs with the bad email, and then the re-render shows the message. Validate into a local variable and branch on it.

Approved by: ______

Correction: ______

## react-forms-validation-07

Forms and validation · difficulty 2 · independent solve passed

The console warns 'A component is changing an uncontrolled input to be controlled'. The input uses `value={user.name}`, which is undefined until the user loads. What is the best fix?

- A. Add a defaultValue prop in addition to the value prop on the same input
- B. Give the field a defined initial value, such as value={user.name ?? ''} ✔
- C. Remove the onChange handler so that the input is no longer controlled by state
- D. Wrap the input component in React.memo so that its type can never switch

Explanation: An input whose value is undefined is uncontrolled; once the value becomes a string it switches to controlled, which React warns about. Always pass a string (an empty one while loading). Supplying both value and defaultValue also warns.

Approved by: ______

Correction: ______

## react-performance-01

Performance · difficulty 1 · independent solve passed

Which tool shows how long each component takes to render and why it re-rendered?

- A. The Elements panel in the browser's DevTools
- B. The StrictMode wrapper component
- C. The Profiler in React DevTools ✔
- D. The console.table function

Explanation: The React DevTools Profiler records commits, per-component render time and the reason for each render. The Elements panel shows DOM, StrictMode only adds development checks, and console.table prints data.

Approved by: ______

Correction: ______

## react-performance-02

Performance · difficulty 3 · execution check passed

ListView is wrapped in React.memo, yet it renders again on every keystroke. Why?

```
1  const ListView = React.memo(function ListView({ options }) {
2    renders.push('render');
3    return <ul />;
4  });
5  function Page() {
6    const [text, setText] = useState('');
7    return (
8      <>
9        <input value={text} onChange={(e) => setText(e.target.value)} />
10       <ListView options={{ sort: 'asc' }} />
11     </>
12   );
13 }
```

- A. React.memo compares props only on the first mount and ignores them afterwards
- B. React.memo does not work for components that render lists or other collections
- C. A parent state update always forces every child to render, regardless of React.memo
- D. The inline object literal is a new object on each render, so memo sees a changed prop ✔

Explanation: React.memo skips rendering only if all props are Object.is-equal. `{ sort: 'asc' }` is a fresh object each render, so the comparison fails. Hoist it to a constant or memoise it with useMemo.

Approved by: ______

Correction: ______

## react-performance-03

Performance · difficulty 3 · independent solve passed

Typing in a search box feels laggy because each keystroke re-renders a very large filtered list. Which React 18 feature keeps the input responsive by treating the list update as lower priority?

- A. useDeferredValue (or startTransition) for the value that drives the list ✔
- B. flushSync around the state update that drives the list, so that it is applied right away
- C. useLayoutEffect to filter the list before paint, so that the list is up to date at once
- D. useId to give the list a stable identity, so that React can skip re-rendering its rows

Explanation: useDeferredValue and startTransition mark an update as non-urgent so React can interrupt it to handle urgent input first. flushSync does the opposite, useLayoutEffect blocks paint, and useId only generates ids.

Approved by: ______

Correction: ______

## react-performance-04

Performance · difficulty 2 · independent solve passed

A table must show 20,000 rows and scrolling is slow. Which technique helps most?

- A. Use each row's array index as its key, so that React can reuse the row elements
- B. Windowing (virtualisation): render only the rows currently visible ✔
- C. Call forceUpdate on every row after it mounts, so the rows are painted quickly
- D. Move the row data into Context so that each row updates on its own from the provider

Explanation: The cost is the number of DOM nodes and components. Windowing libraries mount only the visible slice plus a small buffer. Index keys, forced updates or context do not reduce the work, and some make it worse.

Approved by: ______

Correction: ______

## react-accessibility-01

Accessibility · difficulty 1 · independent solve passed

A control saves a form and does not navigate anywhere. Which element should you use so that it works with the keyboard and screen readers by default?

- A. <a href="#">
- B. <div role="presentation">
- C. <button> ✔
- D. <span tabIndex={-1}>

Explanation: A native button is focusable, activates with Enter and Space, and is announced as a button. Links are for navigation, role="presentation" removes semantics, and tabIndex -1 removes the element from the tab order.

Approved by: ______

Correction: ______

## react-accessibility-02

Accessibility · difficulty 1 · independent solve passed

In JSX, which attribute connects a `<label>` to the input whose id it names?

- A. labelFor
- B. forId
- C. aria-for
- D. htmlFor ✔

Explanation: `for` is a reserved word in JavaScript, so JSX uses htmlFor, which renders as the HTML `for` attribute. The label then names the input and clicking it focuses the input. The other names do not exist.

Approved by: ______

Correction: ______

## react-accessibility-03

Accessibility · difficulty 2 · execution check passed

Keyboard and screen-reader users cannot use this control. Which single change fixes both problems?

```
1  <div className="save" onClick={handleSave}>
2    Save
3  </div>
```

- A. Use <button type="button" onClick={handleSave}> instead of the div ✔
- B. Add tabIndex={0} to the div
- C. Add aria-label="Save" to the div
- D. Add an onKeyDown handler to the div that calls handleSave on Enter

Explanation: A native button is focusable, responds to Enter and Space, and exposes the button role. tabIndex alone makes it focusable but not operable or announced as a button; aria-label adds a name without role or keyboard support; onKeyDown adds one key but no role.

Approved by: ______

Correction: ______

## react-accessibility-04

Accessibility · difficulty 2 · independent solve passed

After a failed submit, a React form renders an error message below the field. Screen-reader users hear nothing. Which change makes the message be announced?

- A. Make the message red with a 4.5:1 contrast ratio
- B. Render the message in an element with role="alert" ✔
- C. Set aria-hidden="true" on the message so it is not read twice
- D. Give the message tabIndex={-1} and change nothing else

Explanation: Content inserted dynamically is not announced unless it is in a live region. role="alert" (or aria-live) makes assistive technology read it when it appears. Colour and contrast help sighted users, aria-hidden hides it, and tabIndex does not announce anything.

Approved by: ______

Correction: ______

## react-accessibility-05

Accessibility · difficulty 3 · independent solve passed

A modal dialog opens when a button is clicked. Which behaviour gives keyboard users the correct experience?

- A. Leave focus on the opening button and let Tab move through the page behind the dialog box
- B. Move focus into the dialog and take every control out of the tab order so that Tab does nothing
- C. Move focus into the dialog, trap Tab inside it, close on Escape, and restore focus to the trigger ✔
- D. Move focus to the first link of the page so that users can reach the site navigation from the dialog

Explanation: A modal must take focus, keep it inside while open, be dismissible with Escape and return focus to the control that opened it, otherwise keyboard users get lost behind the overlay. The other behaviours leave focus outside the dialog or make it unusable.

Approved by: ______

Correction: ______

## react-accessibility-06

Accessibility · difficulty 2 · execution check passed

Screen readers announce this input with no name. Which change gives it an accessible name?

```
1  <label>Email</label>
2  <input id="email" type="email" name="email" />
```

- A. Change name="email" to name="Email" on the input
- B. Add type="text" as well to the input element
- C. Add role="label" as well to the label element
- D. Change the label to <label htmlFor="email"> ✔

Explanation: A label only names an input when it is associated with it: htmlFor matching the input's id (or wrapping the input). The name attribute is for form data, type does not name anything, and there is no label role.

Approved by: ______

Correction: ______

## react-accessibility-07

Accessibility · difficulty 3 · independent solve passed

In a single-page app, a route change swaps the content without a page load and screen-reader users get no cue. What is the recommended handling?

- A. Move focus to the new page's main heading and update document.title ✔
- B. Call window.location.reload() on every route change to simulate a real page load
- C. Put aria-live="assertive" on the app root so that all of its content is read out
- D. Show a visual toast message for the change and leave the keyboard focus where it was

Explanation: A real navigation resets focus and announces the new title; a client-side route change does neither. Managing focus on the new heading and updating the title restores that. A root live region would read the whole page, and visual-only cues are invisible to screen readers.

Approved by: ______

Correction: ______

## react-testing-ui-01

Testing UI · difficulty 1 · independent solve passed

In React Testing Library, which query is generally preferred to find a button with the visible text 'Save'?

- A. container.querySelector('.save-btn')
- B. screen.getByRole('button', { name: 'Save' }) ✔
- C. screen.getByTestId('save-button-test-id')
- D. wrapper.find('Button').first()

Explanation: Role queries find elements the way users and assistive technology do and also confirm the element is a real button. Class selectors and test ids are implementation details; `wrapper.find` belongs to Enzyme.

Approved by: ______

Correction: ______

## react-testing-ui-02

Testing UI · difficulty 1 · independent solve passed

What is the guiding principle of Testing Library?

- A. Each component should be tested in isolation with all of its child components mocked out
- B. Tests should assert the values of the internal state of every component that they render
- C. Tests should resemble how users use the software, not test implementation details ✔
- D. Snapshots should replace explicit assertions so that tests never need to be updated by hand

Explanation: Testing Library encourages querying by role/label/text and asserting on what the user sees, so that refactors that keep behaviour do not break tests. Mocking all children, asserting state or relying on snapshots tie tests to implementation.

Approved by: ______

Correction: ______

## react-testing-ui-03

Testing UI · difficulty 2 · independent solve passed

After a click, a success message appears only once a mocked request resolves. Which query waits for the message to appear?

- A. screen.getByText('Saved') right away
- B. screen.queryByText('Saved') right away
- C. screen.getAllByText('Saved') right away
- D. await screen.findByText('Saved') ✔

Explanation: findBy* queries return a promise that retries until the element appears or a timeout passes. getBy* and getAllBy* throw immediately if nothing matches; queryBy* returns null immediately.

Approved by: ______

Correction: ______

## react-testing-ui-04

Testing UI · difficulty 2 · independent solve passed

A component test passes locally but fails now and then in CI because it calls the real API. What is the best fix?

- A. Mock the network layer (for example with MSW or a mocked fetch) so responses are fixed ✔
- B. Raise the timeout of every waitFor call in the test suite until the failures stop appearing
- C. Retry the failed tests automatically in CI until one of the attempts finally passes
- D. Run the affected test only on developer machines and skip it in the CI pipeline

Explanation: Tests that depend on a real network are non-deterministic. Mocking the network boundary gives fixed responses and still exercises the component. Longer timeouts and retries hide the flakiness instead of removing it.

Approved by: ______

Correction: ______

## react-testing-ui-05

Testing UI · difficulty 2 · execution check passed

This test throws before reaching the assertion even though the banner is correctly hidden. What is the fix?

```
1  test('hides the banner', () => {
2    render(<Banner show={false} />);
3    expect(screen.getByText('Welcome')).not.toBeInTheDocument();
4  });
```

- A. Use findByText on line 3, which waits for the banner to disappear from the document
- B. Use queryByText on line 3, which returns null instead of throwing when nothing matches ✔
- C. Wrap line 2 in act, because render is asynchronous and the banner is hidden too late
- D. Replace not.toBeInTheDocument with toBeFalsy and keep getByText as the query

Explanation: getByText throws if no element matches, so it cannot be used to assert absence. queryByText returns null, which not.toBeInTheDocument accepts. findByText also rejects when nothing appears, and wrapping render in act or changing the matcher does not stop getByText throwing.

Approved by: ______

Correction: ______

## react-testing-ui-06

Testing UI · difficulty 3 · execution check passed

With user-event v14 this test fails with 'Unable to find an element with the text: Count: 1'. Which change fixes it?

```
1  test('increments', async () => {
2    render(<Counter />);
3    userEvent.click(screen.getByRole('button'));
4    expect(screen.getByText('Count: 1')).toBeInTheDocument();
5  });
```

- A. Replace getByRole on line 3 with getByText, so that the button is found more reliably
- B. Wrap the expectation on line 4 in act(() => { ... }), so that updates get flushed
- C. Await the call on line 3, because user-event v14 methods return promises ✔
- D. Replace the matcher on line 4 with toBeTruthy, which is less strict about the element

Explanation: In v14 the user-event APIs are asynchronous, so the click has not been applied when line 4 runs. Awaiting it fixes the test. A different query, an act around the check, or a different matcher cannot make the click happen earlier.

Approved by: ______

Correction: ______

## react-testing-ui-07

Testing UI · difficulty 3 · independent solve passed

A test clicks `screen.getByTestId('submit')`. After a refactor the button became `<div data-testid="submit" onClick={...}>`; the test still passes but keyboard users can no longer submit. What does this show?

- A. Tests should never click elements, and should call the component's handlers directly instead
- B. The test needs a longer timeout so that the browser has time to focus the div element
- C. data-testid attributes should be removed from the markup so that such tests fail sooner
- D. Test-id queries can pass when the element is no longer accessible; role-based queries would catch it ✔

Explanation: getByTestId finds the element regardless of its semantics, so it hides accessibility regressions. getByRole('button') would fail once the div lost its role. Calling handlers directly tests even less of what users do.

Approved by: ______

Correction: ______

## react-testing-ui-08

Testing UI · difficulty 2 · independent solve passed

A component debounces its search input by 300 ms. How can a unit test check the debounced call without really waiting 300 ms?

- A. Use fake timers and advance them by 300 ms ✔
- B. Lower the delay to 0 in production code
- C. Call the change handler 300 times
- D. Poll the assertion in a loop for ten seconds

Explanation: Fake timers (jest.useFakeTimers or vi.useFakeTimers) let the test control the clock and advance it instantly, so the test is fast and deterministic. Changing production delay, spamming the handler or long polling do not test the behaviour reliably.

Approved by: ______

Correction: ______
