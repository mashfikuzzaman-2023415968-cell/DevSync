# Flutter questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/flutter.md`.

## flutter-legacy-01

Widgets and layout · difficulty 1 · independent solve passed

Which widget is best for a long, scrollable list built lazily?

- A. Stack
- B. Column
- C. Row
- D. ListView.builder ✔

Explanation: ListView.builder creates children lazily, only for items that scroll into view, so long lists stay fast and memory-efficient.

Approved by: ______

Correction: ______

## flutter-legacy-02

Data and APIs · difficulty 2 · independent solve passed

What is a Stream in Dart?

- A. A single future value
- B. A file
- C. A sequence of asynchronous events ✔
- D. A layout widget

Explanation: A Stream delivers a sequence of asynchronous events, such as websocket messages, whereas a Future delivers a single value.

Approved by: ______

Correction: ______

## flutter-legacy-03

Data and APIs · difficulty 1 · independent solve passed

Which widget rebuilds when a Future completes?

- A. Padding
- B. Container
- C. ListView
- D. FutureBuilder ✔

Explanation: FutureBuilder rebuilds its subtree when its Future completes, giving the snapshot's data or error.

Approved by: ______

Correction: ______

## flutter-legacy-04

Widgets and layout · difficulty 2 · independent solve passed

What is BuildContext?

- A. A test runner
- B. A handle to the widget's location in the tree ✔
- C. A database connection
- D. A theme file

Explanation: BuildContext is a handle to the widget's position in the widget tree. It is used to look up ancestors such as Theme, MediaQuery or Navigator.

Approved by: ______

Correction: ______

## flutter-legacy-05

Data and APIs · difficulty 1 · independent solve passed

How do you wait for a Future inside an async function?

- A. join
- B. await ✔
- C. yield
- D. sleep

Explanation: await suspends an async function until the Future completes and yields its value or throws its error.

Approved by: ______

Correction: ______

## flutter-legacy-06

State management · difficulty 1 · independent solve passed

What does calling setState() do?

- A. Saves to disk
- B. Navigates to a new page
- C. Marks the widget as dirty so it rebuilds with the new state ✔
- D. Restarts the app

Explanation: setState tells the framework that the State has changed, which schedules a rebuild so the UI shows the new values.

Approved by: ______

Correction: ______

## flutter-legacy-07

Widgets and layout · difficulty 1 · independent solve passed

Which widget arranges children vertically?

- A. Column ✔
- B. Row
- C. Wrap only
- D. Stack

Explanation: Column lays its children out along the vertical axis; Row lays them out horizontally.

Approved by: ______

Correction: ______

## flutter-legacy-08

State management · difficulty 1 · independent solve passed

What is the difference between a StatelessWidget and a StatefulWidget?

- A. StatelessWidgets are faster to type
- B. A StatefulWidget has mutable state that can change over time ✔
- C. None
- D. StatefulWidgets can't have children

Explanation: A StatelessWidget is immutable and depends only on its configuration. A StatefulWidget has an associated State object that persists and can call setState to rebuild.

Approved by: ______

Correction: ______

## flutter-legacy-09

Widgets and layout · difficulty 2 · independent solve passed

What does `const` before a widget constructor help with?

- A. Lets Flutter reuse the instance and skip unnecessary rebuilds ✔
- B. Adds animation
- C. Makes it mutable
- D. Makes it async

Explanation: A const widget is created once at compile time and can be reused, so Flutter can skip rebuilding that subtree when the parent rebuilds.

Approved by: ______

Correction: ______

## flutter-legacy-10

Data and APIs · difficulty 1 · independent solve passed

What is a Future in Dart?

- A. A value or error that will be available later ✔
- B. A database
- C. A route
- D. A UI widget

Explanation: A Future represents a computation whose result, a value or an error, will be available later.

Approved by: ______

Correction: ______

## flutter-legacy-11

State management · difficulty 2 · independent solve passed

What is the purpose of a Key in Flutter?

- A. Database ids
- B. Encryption
- C. Preserving widget identity and state when widgets move in the tree ✔
- D. Keyboard shortcuts

Explanation: Keys let Flutter match widgets to State objects across rebuilds, so state follows an item when a list is reordered, inserted or removed.

Approved by: ______

Correction: ______

## flutter-legacy-13

Widgets and layout · difficulty 1 · independent solve passed

Which widget lets children overlap one another?

- A. Row
- B. Stack ✔
- C. Column
- D. ListView

Explanation: Stack paints its children on top of each other; Positioned places children inside it.

Approved by: ______

Correction: ______

## flutter-legacy-15

Navigation · difficulty 1 · independent solve passed

How do you navigate to a new screen with the basic Navigator?

- A. setState(newPage)
- B. runApp(newPage)
- C. Navigator.push(...) ✔
- D. window.location

Explanation: Navigator.push adds a new route on top of the navigator's stack, for example `Navigator.push(context, MaterialPageRoute(builder: (_) => Page()))`.

Approved by: ______

Correction: ______

## flutter-widgets-layout-01

Widgets and layout · difficulty 3 · independent solve passed

On a narrow phone this screen shows the error 'A RenderFlex overflowed by 84 pixels on the right'. Which change fixes it?

```
Row(
  children: [
    Text('A very long title that does not fit on one line on small screens'),
    Icon(Icons.star),
  ],
)
```

- A. Wrap the Text in an Expanded widget ✔
- B. Add overflow: TextOverflow.ellipsis to the Text only
- C. Wrap the Row in a Container
- D. Put the Row inside a Column

Explanation: A Row gives its non-flex children unbounded width, so a long Text just keeps growing. Expanded (or Flexible) gives the Text the remaining width, which lets it wrap or ellipsize. The overflow property alone does not constrain the width, and Container or Column do not change the Row's behaviour.

Approved by: ______

Correction: ______

## flutter-widgets-layout-02

Widgets and layout · difficulty 3 · independent solve passed

This screen throws 'Vertical viewport was given unbounded height'. What is the right fix?

```
Column(
  children: [
    Text('Messages'),
    ListView(children: messageTiles),
  ],
)
```

- A. Replace the Column with a Row
- B. Set mainAxisSize: MainAxisSize.max on the Column
- C. Set scrollDirection: Axis.horizontal on the ListView
- D. Wrap the ListView in an Expanded widget ✔

Explanation: A Column passes unbounded height to its children, but a scrollable ListView needs a bounded height. Expanded gives it the remaining space. A horizontal list hits the same problem in the other axis, and mainAxisSize.max is already the default.

Approved by: ______

Correction: ______

## flutter-state-management-01

State management · difficulty 2 · independent solve passed

The button is tapped many times, but the label always shows 0. Why?

```
class _CounterState extends State<Counter> {
  int count = 0;

  @override
  Widget build(BuildContext context) {
    return ElevatedButton(
      onPressed: () {
        count++;
      },
      child: Text('$count'),
    );
  }
}
```

- A. The count variable must be declared final
- B. A Text widget cannot display an int
- C. The onPressed callback must be async
- D. The change is not wrapped in setState, so Flutter is never told to rebuild ✔

Explanation: The variable does change, but Flutter only rebuilds a StatefulWidget when setState is called. Writing `setState(() { count++; });` marks the widget dirty and shows the new value.

Approved by: ______

Correction: ______

## flutter-state-management-02

State management · difficulty 2 · independent solve passed

A State object creates a TextEditingController in initState. Where should the controller be disposed?

- A. At the end of the build() method
- B. In a second call to initState
- C. Nowhere; the garbage collector always handles it
- D. In the State's dispose() method ✔

Explanation: Controllers hold listeners and other resources, so the State that creates one must release it in dispose(), which runs once when the State is removed from the tree. Disposing in build would break the next rebuild.

Approved by: ______

Correction: ______

## flutter-state-management-03

State management · difficulty 3 · independent solve passed

After `add()` runs, the ValueListenableBuilder listening to `items` does not rebuild. Why?

```
final items = ValueNotifier<List<int>>([1, 2, 3]);

void add() {
  items.value.add(4);
}
```

- A. A ValueNotifier only notifies when a different value is assigned; mutating the same list does not ✔
- B. ValueNotifier supports only int and String values
- C. add() must be called inside setState to notify listeners
- D. ValueListenableBuilder needs a Key to rebuild

Explanation: ValueNotifier compares the new value with the old one in its value setter and notifies only if they differ. add() mutates the existing list object, so nothing is notified. Assign a new list, for example `items.value = [...items.value, 4];`.

Approved by: ______

Correction: ______

## flutter-state-management-04

State management · difficulty 3 · independent solve passed

TodoTile is a StatefulWidget that keeps its own checkbox state. After the first todo is removed from the list, the checked state appears on the wrong rows. What is the fix?

```
ListView(
  children: todos.map((t) => TodoTile(todo: t)).toList(),
)
```

- A. Call setState when a todo is removed
- B. Give each tile a stable key, such as key: ValueKey(t.id) ✔
- C. Declare the TodoTile constructor as const
- D. Switch to ListView.builder without adding keys

Explanation: Without keys Flutter matches widgets to existing State objects by position, so after a removal the remaining tiles inherit the State of the tile that was in that position. A ValueKey based on the item's id ties each State to its own todo.

Approved by: ______

Correction: ______

## flutter-navigation-01

Navigation · difficulty 1 · independent solve passed

Which call closes the current screen and returns to the previous one?

- A. Navigator.back(context)
- B. Navigator.close(context)
- C. Navigator.pop(context) ✔
- D. Navigator.exit(context)

Explanation: Navigator.pop removes the top route from the stack. Navigator has no back, close or exit methods.

Approved by: ______

Correction: ______

## flutter-navigation-02

Navigation · difficulty 2 · independent solve passed

A screen is opened with `Navigator.pushNamed(context, '/details', arguments: 42)`. How does the '/details' screen read the 42?

- A. Navigator.of(context).arguments
- B. context.widget.arguments
- C. Route.current.arguments
- D. ModalRoute.of(context)!.settings.arguments ✔

Explanation: The arguments are stored in the route's RouteSettings. The destination widget reads them with ModalRoute.of(context)!.settings.arguments (or via onGenerateRoute). The other expressions do not exist.

Approved by: ______

Correction: ______

## flutter-navigation-03

Navigation · difficulty 2 · independent solve passed

After a successful login the app should show HomePage, and pressing Back on HomePage must not return to the login screen. Which call does this?

- A. Navigator.pushReplacement(context, MaterialPageRoute(builder: (_) => HomePage())) ✔
- B. Navigator.push(context, MaterialPageRoute(builder: (_) => HomePage()))
- C. Navigator.pop(context)
- D. Navigator.pushNamed(context, '/home')

Explanation: pushReplacement swaps the current route for the new one, so the login screen leaves the stack. A plain push or pushNamed keeps the login screen underneath, and pop would just close the login screen.

Approved by: ______

Correction: ______

## flutter-navigation-04

Navigation · difficulty 2 · independent solve passed

Why do many Flutter apps use a declarative router such as go_router instead of only calling Navigator.push?

- A. Navigator.push is not available on Android
- B. Routes map to URLs, so deep links and browser URLs work and navigation can follow app state ✔
- C. Declarative routers make screens load faster
- D. Navigator.push cannot pass data to the next screen

Explanation: Declarative routers describe the navigation stack from route paths and state, giving deep linking, web URLs and redirects (for example to a login page). Navigator.push works on every platform and can pass data, so the other reasons are wrong.

Approved by: ______

Correction: ______

## flutter-navigation-05

Navigation · difficulty 3 · independent solve passed

A user opens a picker screen and then presses the system Back button without choosing anything. What does this code print?

```
final choice = await Navigator.push<String>(
  context,
  MaterialPageRoute(builder: (_) => const PickerPage()),
);
print(choice);
```

- A. An empty string
- B. Nothing, because the await never completes
- C. null ✔
- D. It throws an exception

Explanation: The Future returned by push completes with the value passed to Navigator.pop(context, value). When a route is removed without a value, for example by the Back button, it completes with null, so the type is effectively String?.

Approved by: ______

Correction: ______

## flutter-navigation-06

Navigation · difficulty 3 · independent solve passed

In current Flutter (3.7 or later), the analyzer warns about using the BuildContext after an await in this handler. What is the risk and the fix?

```
onPressed: () async {
  await saveProfile();
  Navigator.of(context).pop();
}
```

- A. The await blocks the UI thread; remove it
- B. pop cannot be called after an async call; use push instead
- C. The context becomes null; assign it to a variable first
- D. The widget may be unmounted during the await; check context.mounted before using the context ✔

Explanation: While saveProfile runs the user may leave the screen, so the widget can be disposed and its context is no longer valid. After an await, check `if (!context.mounted) return;` (or State.mounted) before using the context.

Approved by: ______

Correction: ______

## flutter-data-apis-01

Data and APIs · difficulty 2 · independent solve passed

`response.body` is the String '{"id": 1}' returned by an http call. Which code turns it into a Map?

- A. jsonDecode(response.body) ✔
- B. response.body.toMap()
- C. Map.from(response.body)
- D. json.parse(response.body)

Explanation: jsonDecode from dart:convert parses a JSON string into Dart objects (Map, List, num, String, bool, null). String has no toMap, Map.from needs a Map, and json.parse is JavaScript.

Approved by: ______

Correction: ______

## flutter-data-apis-02

Data and APIs · difficulty 3 · independent solve passed

This screen sends a new network request every time the widget rebuilds, for example on every keystroke elsewhere. What is the fix?

```
@override
Widget build(BuildContext context) {
  return FutureBuilder<List<User>>(
    future: fetchUsers(),
    builder: (context, snapshot) {
      ...
    },
  );
}
```

- A. Replace FutureBuilder with a StreamBuilder
- B. Create the Future once, such as in initState, and pass the stored Future to FutureBuilder ✔
- C. Add a Key to the FutureBuilder
- D. Call fetchUsers() twice so the result is cached

Explanation: build can run many times, and each run calls fetchUsers() again, creating a new Future. Store the Future in a State field (initState or didUpdateWidget) and pass that same Future to FutureBuilder so the request happens once.

Approved by: ______

Correction: ______

## flutter-data-apis-03

Data and APIs · difficulty 3 · independent solve passed

The API omits `nickname` for some users. For those users, constructing the model fails at runtime. What is the cause and fix?

```
class User {
  final String nickname;
  User.fromJson(Map<String, dynamic> json)
      : nickname = json['nickname'];
}
```

- A. Map keys that are missing throw a KeyError; check containsKey in a try block
- B. fromJson constructors must be async to read optional fields
- C. json['nickname'] is null, which cannot be a non-nullable String; declare the field as String? ✔
- D. Dart converts missing values to an empty string automatically

Explanation: Reading a missing key from a Map returns null. Assigning that dynamic null to a non-nullable String throws a TypeError at runtime ('Null is not a subtype of String'). Declare the field nullable (String?) or supply a default such as `json['nickname'] as String? ?? ''`.

Approved by: ______

Correction: ______
