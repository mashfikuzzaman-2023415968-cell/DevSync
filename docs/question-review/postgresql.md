# PostgreSQL questions — team review

For each question: check the marked answer and the explanation. If it is right, write your name after **Approved by**. If something is wrong, write the fix after **Correction** instead (the question is retired and replaced). Then run `make question-approve FILE=docs/question-review/postgresql.md`.

## postgresql-legacy-01

Transactions and concurrency · difficulty 2 · independent solve passed

Which isolation level is PostgreSQL's default?

- A. Repeatable read
- B. Serializable
- C. Read committed ✔
- D. Read uncommitted

Explanation: PostgreSQL's default isolation level is READ COMMITTED: each statement sees the data committed before that statement started. REPEATABLE READ and SERIALIZABLE must be requested explicitly, and READ UNCOMMITTED is accepted but behaves like READ COMMITTED.

Approved by: ______

Correction: ______

## postgresql-legacy-02

Indexes and performance · difficulty 2 · independent solve passed

What is VACUUM used for?

- A. Creating indexes
- B. Backing up
- C. Deleting tables
- D. Reclaiming space from dead row versions and updating visibility information ✔

Explanation: UPDATE and DELETE leave dead row versions behind (MVCC). VACUUM makes that space reusable and updates the visibility map and statistics; autovacuum normally runs it. It does not create indexes, back up data or drop tables.

Approved by: ______

Correction: ______

## postgresql-legacy-03

Roles and row-level security · difficulty 2 · independent solve passed

What does row-level security (RLS) do?

- A. Restricts which rows a role can see or change using policies ✔
- B. Encrypts rows
- C. Compresses tables
- D. Logs every query

Explanation: With row-level security enabled, policies decide which rows a role may see (USING) or write (WITH CHECK). It restricts access; it does not encrypt, compress or log anything.

Approved by: ______

Correction: ______

## postgresql-legacy-04

Indexes and performance · difficulty 1 · independent solve passed

What kind of index is the default in PostgreSQL?

- A. B-tree ✔
- B. BRIN
- C. Hash
- D. GIN

Explanation: CREATE INDEX without USING builds a B-tree, which suits equality and range lookups and ordering. Hash, GIN and BRIN are chosen explicitly for special cases.

Approved by: ______

Correction: ______

## postgresql-legacy-05

Indexes and performance · difficulty 2 · independent solve passed

What does EXPLAIN ANALYZE show?

- A. The table's data
- B. Permissions
- C. Index definitions only
- D. The executed query plan with actual timings and row counts ✔

Explanation: EXPLAIN ANALYZE actually runs the statement and shows the chosen plan with real timings and row counts next to the estimates. Plain EXPLAIN shows only the plan and estimates.

Approved by: ______

Correction: ______

## postgresql-legacy-06

Transactions and concurrency · difficulty 1 · independent solve passed

What does a transaction's ROLLBACK do?

- A. Restarts the server
- B. Vacuums the table
- C. Undoes all changes made in the transaction ✔
- D. Commits changes

Explanation: ROLLBACK ends the transaction and discards every change it made; COMMIT is the opposite. It does not restart the server or vacuum anything.

Approved by: ______

Correction: ______

## postgresql-legacy-07

Data modelling · difficulty 2 · independent solve passed

What does `timestamptz` store?

- A. A string
- B. A timestamp with an absolute point in time (converted to UTC internally) ✔
- C. Local time without zone
- D. Only the date

Explanation: timestamptz stores an absolute instant (internally UTC) and converts to and from the session time zone on input and output. It does not store the zone itself. timestamp (without zone) stores a wall-clock value.

Approved by: ______

Correction: ______

## postgresql-legacy-08

SQL queries and joins · difficulty 2 · independent solve passed

What is a CTE (WITH query)?

- A. A table index
- B. A trigger
- C. A stored procedure
- D. A temporary named result set used within a single query ✔

Explanation: A common table expression (WITH name AS (...)) defines a named result set that exists only for the one statement it belongs to, which makes complex queries easier to read and allows recursion.

Approved by: ______

Correction: ______

## postgresql-legacy-09

Constraints and integrity · difficulty 1 · independent solve passed

What does a PRIMARY KEY guarantee?

- A. Values are unique and not null ✔
- B. The column is indexed for full-text search
- C. Values are sorted
- D. Values are encrypted

Explanation: A PRIMARY KEY is UNIQUE plus NOT NULL, and PostgreSQL builds a unique B-tree index to enforce it. It does not sort the table, encrypt values or create a full-text index.

Approved by: ______

Correction: ______

## postgresql-legacy-10

Transactions and concurrency · difficulty 2 · independent solve passed

What does SELECT … FOR UPDATE do?

- A. Updates the rows
- B. Disables triggers
- C. Locks the selected rows until the transaction ends ✔
- D. Creates a backup

Explanation: SELECT ... FOR UPDATE takes row-level locks on the returned rows until the transaction ends, so other writers (or other FOR UPDATE readers) wait. It does not modify rows itself.

Approved by: ______

Correction: ______

## postgresql-legacy-12

Data modelling · difficulty 1 · independent solve passed

Which type should store money exactly in PostgreSQL?

- A. numeric or integer minor units (e.g. paisa) ✔
- B. text
- C. double precision
- D. real

Explanation: Money must be exact. numeric(p,s) or integer minor units (paisa) are exact; real and double precision are binary floating point and give rounding errors; text cannot be summed safely.

Approved by: ______

Correction: ______

## postgresql-legacy-13

Constraints and integrity · difficulty 1 · independent solve passed

What does a CHECK constraint do?

- A. Adds an index
- B. Encrypts the column
- C. Validates that column values satisfy a condition ✔
- D. Creates a foreign key

Explanation: A CHECK constraint rejects any row whose values make the condition false (NULL results pass). It is not an index, encryption or a foreign key.

Approved by: ______

Correction: ______

## postgresql-legacy-14

SQL queries and joins · difficulty 1 · independent solve passed

What is the safest way to pass user input into a query?

- A. String formatting
- B. Bound parameters ✔
- C. Using LIKE
- D. Escaping by hand

Explanation: Bound (parameterised) queries send the SQL text and the values separately, so input can never change the statement's structure. String formatting and hand escaping are error-prone and the classic cause of SQL injection.

Approved by: ______

Correction: ______

## postgresql-legacy-15

Indexes and performance · difficulty 2 · independent solve passed

Which index type is typically used for full-text search vectors (tsvector)?

- A. None is possible
- B. GIN ✔
- C. B-tree
- D. Hash

Explanation: GIN (an inverted index) is the usual choice for tsvector columns because it maps each lexeme to the rows containing it. B-tree and hash indexes cannot answer full-text match queries; GiST is a less common alternative.

Approved by: ______

Correction: ______

## postgresql-legacy-16

Constraints and integrity · difficulty 1 · independent solve passed

What does a FOREIGN KEY constraint enforce?

- A. Unique values
- B. That a value exists in the referenced table ✔
- C. A default value
- D. Faster queries

Explanation: A FOREIGN KEY requires each value in the referencing column to exist in the referenced table's key (or be NULL). It does not make values unique, set a default or speed up queries.

Approved by: ______

Correction: ______

## postgresql-data-modelling-01

Data modelling · difficulty 1 · independent solve passed

In an online shop every order has many line items, and each line item belongs to exactly one order. How is this one-to-many relationship modelled in PostgreSQL?

- A. Give orders an item_id column that references line_items(id)
- B. Store the line item ids in a comma-separated text column on orders
- C. Copy all the order columns into every line_items row
- D. Give line_items an order_id column that references orders(id) ✔

Explanation: The foreign key goes on the 'many' side: each line item row points at its one order. A key on orders would allow only one item per order; comma-separated lists and copied columns break integrity and normalisation.

Approved by: ______

Correction: ______

## postgresql-data-modelling-02

Data modelling · difficulty 1 · independent solve passed

Students can enrol in many courses, and every course has many students. What is the standard way to model this many-to-many relationship?

- A. A junction table with a foreign key to each of the two tables ✔
- B. A foreign key column on the students table only
- C. An array of course names stored in a text column on students
- D. Two tables that share the same primary key values

Explanation: A many-to-many relationship needs a third (junction) table with one row per pair, holding foreign keys to both sides, usually with a composite primary key. A single foreign key can express only one-to-many.

Approved by: ______

Correction: ______

## postgresql-data-modelling-03

Data modelling · difficulty 2 · execution check passed

A column is declared numeric(6,2) and the value 1234.567 is inserted. What does the SELECT on line 3 return?

```
1  CREATE TABLE price (amount numeric(6,2));
2  INSERT INTO price VALUES (1234.567);
3  SELECT amount FROM price;
```

- A. 1234.56
- B. 1234.567
- C. 1234.57 ✔
- D. An error: numeric field overflow

Explanation: numeric(6,2) allows 6 digits in total with 2 after the point, so up to 9999.99. The input 1234.567 fits and is rounded (not truncated) to scale 2, giving 1234.57. An overflow error would need 5 digits before the point.

Approved by: ______

Correction: ______

## postgresql-data-modelling-04

Data modelling · difficulty 2 · independent solve passed

A shop prints invoices for orders placed months ago, and product prices change from time to time. Which design keeps old invoices correct?

- A. Join order_items to products.price whenever an invoice is printed
- B. Update every existing order_items row whenever products.price changes
- C. Keep one price on products and add a printed_at column to invoices
- D. Copy the unit price into each order_items row when the order is placed ✔

Explanation: An order must record the price that was agreed at purchase time, so the price is copied (snapshotted) into the order row. Joining to the live price, or rewriting old rows, changes history; a printed_at timestamp does not preserve the price.

Approved by: ______

Correction: ______

## postgresql-data-modelling-05

Data modelling · difficulty 3 · independent solve passed

A customers table has the columns customer_id (primary key), name, postal_code and delivery_zone. delivery_zone is always determined by postal_code, and many customers share a postal code. What is the problem and the usual fix?

- A. It breaks third normal form; move delivery_zone into a table keyed by postal_code ✔
- B. It breaks first normal form; split name into first and last name
- C. It breaks second normal form; give the table a composite primary key
- D. There is no problem; every non-key column belongs to the customer row

Explanation: delivery_zone depends on postal_code, which is not the key: a transitive dependency, so third normal form is violated and the zone is repeated for every customer in a postal code. Second normal form concerns partial dependencies on composite keys.

Approved by: ______

Correction: ______

## postgresql-data-modelling-06

Data modelling · difficulty 3 · execution check passed

A tickets table uses a GENERATED ALWAYS identity column. What happens when line 5 runs?

```
1  CREATE TABLE tickets (
2    id int GENERATED ALWAYS AS IDENTITY,
3    title text
4  );
5  INSERT INTO tickets (id, title) VALUES (10, 'a');
```

- A. It succeeds and stores id 10
- B. It succeeds, ignores the 10 and stores id 1
- C. It succeeds and the next generated id becomes 11
- D. It fails because a non-DEFAULT value cannot be inserted into an identity column ✔

Explanation: GENERATED ALWAYS AS IDENTITY rejects explicit values unless OVERRIDING SYSTEM VALUE is given (error 428C9). Only GENERATED BY DEFAULT accepts an explicit id, and even then the sequence is not advanced by it.

Approved by: ______

Correction: ______

## postgresql-data-modelling-07

Data modelling · difficulty 3 · execution check passed

After an insert that was skipped by ON CONFLICT DO NOTHING, which id does the statement on line 4 return?

```
1  CREATE TABLE tags (id serial PRIMARY KEY, name text UNIQUE);
2  INSERT INTO tags (name) VALUES ('sql');
3  INSERT INTO tags (name) VALUES ('sql') ON CONFLICT DO NOTHING;
4  INSERT INTO tags (name) VALUES ('db') RETURNING id;
```

- A. 1
- B. 2
- C. 3 ✔
- D. 4

Explanation: The default nextval('tags_id_seq') is evaluated before the conflict check, so the ignored insert on line 3 still consumes id 2. Sequences are not gapless and are never rolled back, so 'db' gets 3.

Approved by: ______

Correction: ______

## postgresql-data-modelling-08

Data modelling · difficulty 2 · independent solve passed

A catalogue has products with common columns (name, price), but each category has different optional attributes such as screen size or fabric. Which feature suits the varying attributes best, without changing the schema for each new attribute?

- A. A text column holding a JSON string, searched with LIKE
- B. A jsonb column, with a GIN index if you filter inside it ✔
- C. One extra nullable column for every attribute of every category
- D. A new table per product whose columns are that product's attributes

Explanation: jsonb stores flexible, structured attributes next to the relational columns and can be indexed (GIN) and queried with operators. Extra columns or tables need a schema change per attribute, and LIKE over a text string cannot use an index well.

Approved by: ______

Correction: ______

## postgresql-sql-queries-01

SQL queries and joins · difficulty 1 · execution check passed

A score column holds 10, NULL and 30. What does the SELECT on line 3 return?

```
1  CREATE TABLE results (score int);
2  INSERT INTO results VALUES (10), (NULL), (30);
3  SELECT count(*), count(score) FROM results;
```

- A. 2, 2
- B. 2, 3
- C. 3, 2 ✔
- D. 3, 3

Explanation: count(*) counts rows (3) while count(score) counts only non-NULL values (2), so the result is the single row 3, 2.

Approved by: ______

Correction: ______

## postgresql-sql-queries-02

SQL queries and joins · difficulty 1 · independent solve passed

You want only the departments that have more than five employees. Which clause filters on the result of count(*) after grouping?

- A. HAVING ✔
- B. WHERE
- C. ORDER BY
- D. QUALIFY

Explanation: HAVING filters groups after aggregation. WHERE runs before grouping and cannot contain aggregates; ORDER BY only sorts; QUALIFY exists in some other databases but not in PostgreSQL.

Approved by: ______

Correction: ______

## postgresql-sql-queries-04

SQL queries and joins · difficulty 2 · execution check passed

Which approach correctly lists the customers who have never placed an order?

- A. INNER JOIN orders on customer_id, then keep rows WHERE orders.id IS NULL
- B. LEFT JOIN orders on customer_id, then keep rows WHERE orders.id IS NULL ✔
- C. LEFT JOIN orders on customer_id, then keep rows WHERE orders.id = NULL
- D. LEFT JOIN orders on customer_id, then GROUP BY customers.id HAVING count(*) = 0

Explanation: Unmatched customers get NULLs from the LEFT JOIN, and IS NULL finds them. An INNER JOIN drops them first, '= NULL' is never true, and count(*) counts the NULL-extended row as 1, so a group can never have 0.

Approved by: ______

Correction: ______

## postgresql-sql-queries-05

SQL queries and joins · difficulty 3 · execution check passed

The subquery on line 5 yields a NULL among its values. What does the NOT IN query return?

```
1  CREATE TABLE a (id int);
2  CREATE TABLE b (id int);
3  INSERT INTO a VALUES (1), (2), (3);
4  INSERT INTO b VALUES (2), (NULL);
5  SELECT count(*) FROM a WHERE id NOT IN (SELECT id FROM b);
```

- A. 0 ✔
- B. 1
- C. 2
- D. 3

Explanation: id NOT IN (2, NULL) is NULL for ids 1 and 3 (the comparison with NULL is unknown) and false for 2, so no row qualifies and the count is 0. NOT EXISTS or filtering NULLs out of the subquery avoids this trap.

Approved by: ______

Correction: ______

## postgresql-sql-queries-06

SQL queries and joins · difficulty 1 · execution check passed

Two students tie for the highest score. In which sequence does the rank() query return the values of r?

```
1  CREATE TABLE scores (name text, score int);
2  INSERT INTO scores VALUES ('ann', 90), ('bob', 90), ('cy', 80), ('dee', 70);
3  SELECT rank() OVER (ORDER BY score DESC) AS r
4  FROM scores
5  ORDER BY score DESC, name;
```

- A. 1, 2, 3, 4
- B. 1, 1, 3, 4 ✔
- C. 1, 1, 2, 3
- D. 1, 1, 2, 2

Explanation: rank() gives tied rows the same rank and then skips: 90, 90, 80, 70 become 1, 1, 3, 4. row_number() would give 1, 2, 3, 4 and dense_rank() would give 1, 1, 2, 3.

Approved by: ______

Correction: ______

## postgresql-sql-queries-07

SQL queries and joins · difficulty 2 · execution check passed

The table payments has no rows for user 999. What does SELECT sum(amount) FROM payments WHERE user_id = 999 return?

- A. One row containing 0
- B. No rows at all
- C. An error about an empty group
- D. One row containing NULL ✔

Explanation: An aggregate without GROUP BY always returns exactly one row. sum() over zero rows is NULL (only count() returns 0), so use COALESCE(sum(amount), 0) when a zero is wanted.

Approved by: ______

Correction: ______

## postgresql-sql-queries-08

SQL queries and joins · difficulty 3 · execution check passed

Which rows does the DISTINCT ON query return as (customer_id, total)?

```
1  CREATE TABLE orders (customer_id int, total int, created_on date);
2  INSERT INTO orders VALUES
3    (1, 10, '2024-01-01'), (1, 20, '2024-01-03'),
4    (2, 7, '2024-01-01'), (2, 5, '2024-01-02');
5  SELECT DISTINCT ON (customer_id) customer_id, total
6  FROM orders
7  ORDER BY customer_id, created_on DESC;
```

- A. (1, 10), (2, 7)
- B. (1, 20), (2, 7)
- C. (1, 10), (2, 5)
- D. (1, 20), (2, 5) ✔

Explanation: DISTINCT ON (customer_id) keeps the first row of each customer in the ORDER BY order, here the newest created_on: (1, 20) from 2024-01-03 and (2, 5) from 2024-01-02. It does not pick the largest total.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-01

Constraints and integrity · difficulty 2 · execution check passed

A UNIQUE column receives two NULL values on line 2. What is the outcome of the three statements?

```
1  CREATE TABLE users (email text UNIQUE);
2  INSERT INTO users VALUES (NULL), (NULL), ('a@x.com');
3  SELECT count(*) FROM users;
```

- A. Line 2 fails with a unique violation because of the two NULLs
- B. Line 2 succeeds and the SELECT returns 2, because duplicate NULLs are merged
- C. Line 2 succeeds and the SELECT returns 1, because only non-NULL values are stored
- D. Line 2 succeeds and the SELECT returns 3 ✔

Explanation: NULL is never equal to NULL, so a UNIQUE constraint allows any number of NULLs (unless NULLS NOT DISTINCT is specified, PostgreSQL 15+). All three rows are stored.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-02

Constraints and integrity · difficulty 2 · execution check passed

After the DELETE on line 8 removes a parent that has two child rows, what does the SELECT on line 9 return?

```
1  CREATE TABLE parent (id int PRIMARY KEY);
2  CREATE TABLE child (
3    id int PRIMARY KEY,
4    parent_id int REFERENCES parent (id) ON DELETE CASCADE
5  );
6  INSERT INTO parent VALUES (1), (2);
7  INSERT INTO child VALUES (10, 1), (11, 1), (12, 2);
8  DELETE FROM parent WHERE id = 1;
9  SELECT count(*) FROM child;
```

- A. 0
- B. 1 ✔
- C. 2
- D. 3

Explanation: ON DELETE CASCADE deletes the child rows that reference the deleted parent: rows 10 and 11 go with parent 1, leaving only row 12.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-03

Constraints and integrity · difficulty 2 · execution check passed

A CHECK (price > 0) column receives NULL. What happens when line 2 runs?

```
1  CREATE TABLE items (price int CHECK (price > 0));
2  INSERT INTO items VALUES (NULL);
```

- A. It fails with a check constraint violation
- B. It succeeds and stores a NULL price ✔
- C. It fails with a not-null violation
- D. It succeeds and stores 0 instead

Explanation: A CHECK constraint rejects a row only when the condition is false. NULL > 0 evaluates to NULL (unknown), which passes. Add NOT NULL as well if a price must always be present.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-04

Constraints and integrity · difficulty 3 · execution check passed

A foreign key is DEFERRABLE INITIALLY DEFERRED and the child row is inserted before its parent. Which statement fails, if any?

```
1  CREATE TABLE parent (id int PRIMARY KEY);
2  CREATE TABLE child (
3    id int PRIMARY KEY,
4    parent_id int REFERENCES parent (id) DEFERRABLE INITIALLY DEFERRED
5  );
6  BEGIN;
7  INSERT INTO child VALUES (1, 5);
8  INSERT INTO parent VALUES (5);
9  COMMIT;
```

- A. Line 7, because parent 5 does not exist yet
- B. Line 8, because the child row already exists
- C. Line 9, because the commit is rejected
- D. None; the foreign key is checked at COMMIT and then passes ✔

Explanation: A DEFERRABLE INITIALLY DEFERRED constraint is checked at COMMIT, not per statement. By then parent 5 exists, so every statement succeeds. Without DEFERRABLE, line 7 would fail immediately.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-05

Constraints and integrity · difficulty 3 · execution check passed

Each user may have at most one subscription with status 'active', but any number of 'cancelled' or 'expired' ones. Which approach enforces this in the database?

- A. A table constraint UNIQUE (user_id, status)
- B. A CHECK constraint that counts the user's other active rows in a subquery
- C. A foreign key from subscriptions.status to a statuses lookup table
- D. A partial unique index on (user_id) with WHERE status = 'active' ✔

Explanation: A partial unique index applies uniqueness only to the rows matching its WHERE clause. UNIQUE (user_id, status) would also limit each user to one cancelled row, CHECK constraints cannot contain subqueries, and a lookup foreign key only validates the status value.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-06

Constraints and integrity · difficulty 3 · execution check passed

A CHECK constraint is added with NOT VALID to a table whose data already violates it. Which statement is the first to fail?

```
1  CREATE TABLE t (a int);
2  INSERT INTO t VALUES (1), (-1);
3  ALTER TABLE t ADD CONSTRAINT a_pos CHECK (a > 0) NOT VALID;
4  INSERT INTO t VALUES (-2);
```

- A. Line 2
- B. Line 3
- C. Line 4 ✔
- D. None; all four statements succeed

Explanation: NOT VALID adds the constraint without checking existing rows, so line 3 succeeds even though -1 violates it; the constraint is enforced for new rows, so line 4 fails. Without NOT VALID, line 3 would fail.

Approved by: ______

Correction: ______

## postgresql-constraints-integrity-07

Constraints and integrity · difficulty 1 · execution check passed

orders.customer_id references customers(id) with the default foreign key behaviour (no ON DELETE clause). What happens when you DELETE a customer who still has orders?

- A. The DELETE fails with a foreign key violation ✔
- B. The DELETE succeeds and the orders keep the old customer_id
- C. The DELETE succeeds and the orders are deleted too
- D. The DELETE succeeds and customer_id becomes NULL on the orders

Explanation: The default action is NO ACTION: the delete is rejected (error 23503) so no orphaned orders can exist. Cascading, nulling or defaulting happens only when ON DELETE CASCADE, SET NULL or SET DEFAULT is declared.

Approved by: ______

Correction: ______

## postgresql-indexes-performance-01

Indexes and performance · difficulty 1 · independent solve passed

The query SELECT * FROM users WHERE email = 'ann@example.com' is slow on a table with ten million rows and no index on email. Which change is the most direct fix?

- A. Create an index on users (name)
- B. Run VACUUM FULL users before each query
- C. Create a B-tree index on users (email) ✔
- D. Change the test to LIKE '%ann@example.com%'

Explanation: An equality lookup on an unindexed column forces a sequential scan; a B-tree index on that column lets PostgreSQL find the row directly. An index on another column, VACUUM FULL or a leading-wildcard LIKE does not help.

Approved by: ______

Correction: ______

## postgresql-indexes-performance-02

Indexes and performance · difficulty 3 · execution check passed

On a large table EXPLAIN shows a sequential scan for the query on line 2, even though users_email_idx exists. Which change lets PostgreSQL use an index for this query?

```
1  CREATE INDEX users_email_idx ON users (email);
2  SELECT * FROM users WHERE lower(email) = 'ann@example.com';
```

- A. CREATE INDEX ON users (email DESC)
- B. Run ANALYZE users
- C. Recreate users_email_idx with USING hash
- D. CREATE INDEX ON users (lower(email)) ✔

Explanation: The index stores email, but the query filters on lower(email); a plain index cannot answer a condition on an expression. An expression index on lower(email) can. Sort direction, fresh statistics or the hash method on email do not change that.

Approved by: ______

Correction: ______

## postgresql-indexes-performance-03

Indexes and performance · difficulty 3 · execution check passed

An orders table has 20 million rows; 99% have status 'shipped' and the app constantly reads the few rows with status 'pending'. Which index best serves WHERE status = 'pending' with the least storage and write overhead?

- A. A full B-tree index on status
- B. A hash index on status
- C. A partial index on status with WHERE status = 'pending' ✔
- D. A composite B-tree index on (status, created_at, total)

Explanation: A partial index contains only the rows matching its predicate, so it is tiny and is updated only when a pending row changes, yet it fully serves the pending lookups. The other indexes cover all 20 million rows.

Approved by: ______

Correction: ______

## postgresql-indexes-performance-04

Indexes and performance · difficulty 2 · independent solve passed

After ten more indexes were added to a busy events table, INSERT and UPDATE statements became slower while some SELECTs got faster. What is the most likely reason?

- A. PostgreSQL re-sorts the whole table on every insert
- B. Every write must also update each index on the table ✔
- C. Each index takes an exclusive table lock for the length of any query
- D. PostgreSQL turns autovacuum off for tables with many indexes

Explanation: Indexes are extra structures that must be maintained on every INSERT, DELETE and non-HOT UPDATE, so each one adds write cost and storage. They do not re-sort the table, lock it for reads or disable autovacuum.

Approved by: ______

Correction: ______

## postgresql-transactions-concurrency-01

Transactions and concurrency · difficulty 1 · independent solve passed

A transfer runs UPDATE accounts SET balance = balance - 100 WHERE id = 1 and then UPDATE accounts SET balance = balance + 100 WHERE id = 2. Why should both statements run in one transaction?

- A. So that either both changes are applied or neither is ✔
- B. So that the second statement runs faster
- C. So that other sessions cannot read the accounts table meanwhile
- D. Because a single statement cannot change more than one row

Explanation: A transaction makes the transfer atomic: if the second update fails, the first is rolled back instead of losing 100. Under MVCC readers are not blocked, and each statement is already atomic on its own.

Approved by: ______

Correction: ______

## postgresql-transactions-concurrency-02

Transactions and concurrency · difficulty 3 · execution check passed

Starting balance is 100 and the default isolation level is overridden as shown. What happens at line 5?

```
1  -- accounts: id 1, balance 100
2  A: BEGIN ISOLATION LEVEL REPEATABLE READ;
3  A: SELECT balance FROM accounts WHERE id = 1;
4  B: UPDATE accounts SET balance = 50 WHERE id = 1;  -- autocommits
5  A: UPDATE accounts SET balance = balance - 10 WHERE id = 1;
```

- A. It succeeds and sets the balance to 40
- B. It succeeds and sets the balance to 90
- C. It fails with a serialization failure (could not serialize access due to concurrent update) ✔
- D. It succeeds but changes nothing because A's snapshot is stale

Explanation: Under REPEATABLE READ, A works from the snapshot taken at its first query. Updating a row that another transaction changed and committed since then raises SQLSTATE 40001, and the application must retry. READ COMMITTED would instead re-read the row and give 40.

Approved by: ______

Correction: ______

## postgresql-transactions-concurrency-03

Transactions and concurrency · difficulty 3 · execution check passed

Both sessions use the default isolation level and the balance starts at 100. B's UPDATE on line 5 has to wait. What is the balance after line 7?

```
1  -- accounts: id 1, balance 100
2  A: BEGIN;
3  A: UPDATE accounts SET balance = balance - 30 WHERE id = 1;
4  B: BEGIN;
5  B: UPDATE accounts SET balance = balance - 20 WHERE id = 1;
6  A: COMMIT;
7  B: COMMIT;
```

- A. 50 ✔
- B. 70
- C. 80
- D. 100

Explanation: B blocks on A's row lock. When A commits, B re-evaluates its UPDATE on the newly committed row (100 - 30 = 70), so balance - 20 gives 50. Under READ COMMITTED no update is lost.

Approved by: ______

Correction: ______

## postgresql-transactions-concurrency-04

Transactions and concurrency · difficulty 2 · execution check passed

Rows 1 and 2 exist. Each session already holds a row lock from its first UPDATE and now reaches line 4 and line 5. What does PostgreSQL do?

```
1  -- accounts has rows with id 1 and 2
2  A: BEGIN; UPDATE accounts SET balance = balance + 1 WHERE id = 1;
3  B: BEGIN; UPDATE accounts SET balance = balance + 1 WHERE id = 2;
4  A: UPDATE accounts SET balance = balance + 1 WHERE id = 2;  -- waits
5  B: UPDATE accounts SET balance = balance + 1 WHERE id = 1;
```

- A. It detects the deadlock and aborts one transaction with an error ✔
- B. It aborts both transactions with an error
- C. Both sessions wait forever until an administrator cancels one
- D. Both updates succeed because each session sees its own row version

Explanation: Each session waits for a lock the other holds. PostgreSQL's deadlock detector notices the cycle (after deadlock_timeout, 1 s by default), aborts one transaction with SQLSTATE 40P01 and lets the other continue. The application should retry.

Approved by: ______

Correction: ______

## postgresql-roles-rls-01

Roles and row-level security · difficulty 1 · independent solve passed

A web API connects to PostgreSQL. To follow the principle of least privilege, which database role should it use?

- A. The postgres superuser, so that migrations never fail
- B. The owner of every table, so that any query can run
- C. A dedicated role granted only the privileges it needs on the tables it uses ✔
- D. A role with CREATEROLE, so it can add users when needed

Explanation: Least privilege limits the damage of a bug or SQL injection. The application should use its own login role with only the needed grants, never a superuser, owner or role-creating account.

Approved by: ______

Correction: ______

## postgresql-roles-rls-02

Roles and row-level security · difficulty 1 · execution check passed

Which statement takes the SELECT privilege on table orders away from role reporting?

- A. DENY SELECT ON orders TO reporting
- B. REVOKE SELECT ON orders FROM reporting ✔
- C. DROP SELECT ON orders FROM reporting
- D. GRANT NO SELECT ON orders TO reporting

Explanation: PostgreSQL removes privileges with REVOKE. DENY is SQL Server syntax, and the other two are not valid PostgreSQL statements.

Approved by: ______

Correction: ______

## postgresql-roles-rls-03

Roles and row-level security · difficulty 2 · execution check passed

Row-level security is enabled with an owner = current_user policy. Role alice is not the table owner. What does the SELECT on line 7 return for her?

```
1  CREATE TABLE notes (id int, owner text, body text);
2  INSERT INTO notes VALUES (1, 'alice', 'x'), (2, 'alice', 'y'), (3, 'bob', 'z');
3  ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
4  CREATE POLICY own_notes ON notes USING (owner = current_user);
5  GRANT SELECT ON notes TO alice;
6  -- connected as alice (not the owner):
7  SELECT count(*) FROM notes;
```

- A. 0
- B. 1
- C. 2 ✔
- D. 3

Explanation: With RLS enabled, the policy filters the rows alice can see to those where owner = current_user: her two rows. Without the policy she would get the default deny (0 rows), and RLS applies to her because she is not the owner.

Approved by: ______

Correction: ______

## postgresql-roles-rls-04

Roles and row-level security · difficulty 3 · execution check passed

Role bob created notes, so he owns it; he is not a superuser and has no BYPASSRLS. What does the SELECT on line 6 return when bob runs it?

```
1  CREATE TABLE notes (id int, owner text);
2  INSERT INTO notes VALUES (1, 'alice'), (2, 'alice'), (3, 'bob');
3  ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
4  CREATE POLICY own_notes ON notes USING (owner = current_user);
5  -- bob, the table owner, connects and runs:
6  SELECT count(*) FROM notes;
```

- A. 0
- B. 1
- C. 2
- D. 3 ✔

Explanation: Table owners are exempt from row-level security unless the table is set to FORCE ROW LEVEL SECURITY, so bob sees all 3 rows even though the policy would limit him to 1. Applications should connect as a non-owner role.

Approved by: ______

Correction: ______

## postgresql-roles-rls-05

Roles and row-level security · difficulty 3 · execution check passed

The policy has only a USING expression, and alice is not the owner. What happens when she runs the INSERT on line 6?

```
1  CREATE TABLE notes (id int, owner text);
2  ALTER TABLE notes ENABLE ROW LEVEL SECURITY;
3  CREATE POLICY own ON notes USING (owner = current_user);
4  GRANT SELECT, INSERT ON notes TO alice;
5  -- connected as alice (not the owner):
6  INSERT INTO notes VALUES (1, 'bob');
```

- A. It fails: new row violates row-level security policy for table notes ✔
- B. It succeeds, but alice cannot see the new row afterwards
- C. It succeeds and inserts 0 rows with no error
- D. It fails with: permission denied for table notes

Explanation: A policy created without FOR defaults to ALL, and when WITH CHECK is omitted the USING expression is also applied to new rows. The row for 'bob' fails the check and the statement errors out. It is not a table privilege error because alice has INSERT.

Approved by: ______

Correction: ______

## postgresql-roles-rls-06

Roles and row-level security · difficulty 2 · independent solve passed

A SaaS app keeps every customer's rows in shared tables with a tenant_id column. A bug could leave out the WHERE tenant_id = ... filter. Which feature makes the database itself enforce the tenant boundary?

- A. A column-level GRANT on the tenant_id column
- B. Row-level security policies that compare tenant_id with a per-session setting ✔
- C. A CHECK constraint on tenant_id
- D. A unique index on (tenant_id, id)

Explanation: RLS policies filter every query on the table, whatever the application code does, and can read a session setting such as current_setting('app.tenant_id'). Grants, check constraints and unique indexes do not restrict which rows a role reads.

Approved by: ______

Correction: ______
