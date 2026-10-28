"""Check for fastapi-databases-orm-04: count the SELECTs the loop sends (SQLite, 3 authors)."""

CODE = r'''
import warnings
warnings.filterwarnings("ignore")
from sqlalchemy import ForeignKey, create_engine, event, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, selectinload

class Base(DeclarativeBase):
    pass

class Author(Base):
    __tablename__ = "author"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str]
    books: Mapped[list["Book"]] = relationship()

class Book(Base):
    __tablename__ = "book"
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str]
    author_id: Mapped[int] = mapped_column(ForeignKey("author.id"))

engine = create_engine("sqlite://")
Base.metadata.create_all(engine)
with Session(engine) as s:
    for n in range(3):
        s.add(Author(name=f"a{n}", books=[Book(title=f"b{n}{k}") for k in range(2)]))
    s.commit()

selects = []
event.listen(engine, "before_cursor_execute",
             lambda conn, cur, stmt, *a: selects.append(stmt) if stmt.lstrip().upper().startswith("SELECT") else None)

with Session(engine) as db:
    authors = db.scalars(select(Author)).all()
    titles = []
    for author in authors:
        titles += [b.title for b in author.books]
print(len(selects))

selects.clear()
with Session(engine) as db:
    for author in db.scalars(select(Author).options(selectinload(Author.books))):
        [b.title for b in author.books]
print(len(selects))
'''


def check(ctx, q):
    lazy, eager = ctx.python(CODE).split()
    ctx.expect_only(q, lazy)
    assert eager == "2"  # eager loading is the fix, not 3 or 1
