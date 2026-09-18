"""A populated category migration rehearsal shared by SQLite and PostgreSQL."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from alembic import command
from sqlalchemy import MetaData, Table, select, text
from sqlalchemy.exc import IntegrityError


def rehearse_categories(engine, config):
    command.upgrade(config, "f55f2e58ba86")
    metadata = MetaData()
    users = Table("users", metadata, autoload_with=engine)
    books = Table("books", metadata, autoload_with=engine)
    transactions = Table("transactions", metadata, autoload_with=engine)
    # Reflected SQLite CHAR UUID columns take strings, PostgreSQL UUID takes
    # UUID objects. Hex strings are accepted by both database drivers.
    user_id = uuid.uuid4().hex
    book_ids = [uuid.uuid4().hex, uuid.uuid4().hex]
    with engine.begin() as connection:
        connection.execute(users.insert().values(id=user_id, display_name="seed", locale="fa",
            timezone="Asia/Tehran", is_active=True))
        for book_id in book_ids:
            connection.execute(books.insert().values(id=book_id, name="book", type="BUSINESS",
                owner_user_id=user_id, base_currency="IRT", timezone="Asia/Tehran", locale="fa",
                calendar="jalali", is_active=True))
        for index, book_id in enumerate([book_ids[0], book_ids[0], book_ids[1]]):
            connection.execute(transactions.insert().values(id=uuid.uuid4().hex, book_id=book_id,
                actor_user_id=user_id, occurred_on=date(2026, 8, 24), flow="INCOME", scope="WORK",
                category="فروش قدیمی", description="historical", original_amount=Decimal("10.15"),
                original_currency="USD", base_currency="IRT", conversion_rate=Decimal("12.3456"),
                converted_amount=Decimal("125.3078"), rate_mode="MANUAL", receipt_file_id=f"FILE{index}",
                receipt_provider="telegram", receipt_kind="photo"))
        before = connection.execute(select(transactions).order_by(transactions.c.id)).mappings().all()
    command.upgrade(config, "head")
    current = Table("transactions", MetaData(), autoload_with=engine)
    categories = Table("categories", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        after = connection.execute(select(current).order_by(current.c.id)).mappings().all()
        category_rows = connection.execute(select(categories)).mappings().all()
        assert len(category_rows) == 2
        assert [dict(row) for row in before] == [
            {key: value for key, value in row.items() if key != "category_id"} for row in after]
        for transaction in after:
            category = next(row for row in category_rows if row["id"] == transaction["category_id"])
            assert category["book_id"] == transaction["book_id"]
            assert category["name"] == transaction["category"]
    command.downgrade(config, "f55f2e58ba86")
    restored = Table("transactions", MetaData(), autoload_with=engine)
    with engine.connect() as connection:
        assert connection.execute(select(restored).order_by(restored.c.id)).mappings().all() == before
    command.upgrade(config, "head")
    with engine.connect() as connection:
        if engine.dialect.name == "sqlite":
            connection.execute(text("PRAGMA foreign_keys=ON"))
        connection.commit()
        transaction = connection.execute(select(current)).mappings().first()
        category_rows = connection.execute(select(categories)).mappings().all()
        foreign_category = next(row for row in category_rows if row["book_id"] != transaction["book_id"])
        connection.commit()
        with pytest.raises(IntegrityError):
            with connection.begin():
                connection.execute(current.update().where(current.c.id == transaction["id"])
                    .values(category_id=foreign_category["id"]))
        with pytest.raises(IntegrityError):
            with connection.begin():
                connection.execute(categories.delete().where(categories.c.id == transaction["category_id"]))
        # The same deferred FK must allow the supported whole-book cascade.
        with connection.begin():
            connection.execute(books.delete().where(books.c.id == transaction["book_id"]))
        assert connection.execute(select(current).where(current.c.book_id == transaction["book_id"])).first() is None
