"""Files attached to a transaction from the web panel.

What has to hold is not that a photo goes in and comes out, but that nothing
else does: a file of another type dressed up with an image's name, a file that
is too big, a stranger reading someone else's paperwork, and a file id opened
under a different book's path.
"""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from kasbbook.api.app import create_app
from kasbbook.api.ratelimit import MemoryRateLimiter
from kasbbook.modules.ledger.attachments import MAX_BYTES, clean_name, sniff
from kasbbook.shared.settings import Settings

pytestmark = pytest.mark.asyncio

SECRET = "a-test-signing-key-that-is-long-enough-to-be-real"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
PDF = b"%PDF-1.4\n" + b"0" * 64


@pytest.fixture
async def api(db):
    settings = Settings(database_url="sqlite+aiosqlite://", api_secret_key=SECRET)
    app = create_app(settings=settings, database=db, limiter=MemoryRateLimiter())
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        async with app.router.lifespan_context(app):
            yield client


async def signed_in(api, email):
    tokens = (await api.post("/api/v1/auth/register", json={
        "display_name": "عماد", "email": email, "password": "a-good-password"})).json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


async def workspace(api, email="o@example.com"):
    headers = await signed_in(api, email)
    book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "کارگاه", "type": "business", "currency": "IRT"})).json()["id"]
    tx = (await api.post(f"/api/v1/books/{book}/transactions", headers=headers, json={
        "flow": "expense", "scope": "work", "category": "اجاره", "amount": "1000"})).json()["id"]
    return headers, book, tx


def url(book, tx, attachment=""):
    return f"/api/v1/books/{book}/transactions/{tx}/attachments" + (f"/{attachment}" if attachment else "")


async def upload(api, headers, book, tx, data, name="receipt.png"):
    return await api.post(url(book, tx), headers=headers, files={"file": (name, data, "application/octet-stream")})


def test_the_type_comes_from_the_bytes():
    assert sniff(PNG) == "image/png" and sniff(PDF) == "application/pdf"
    assert sniff(b"<html><script>alert(1)</script>") is None
    assert sniff(b"MZ\x90\x00") is None


def test_a_name_is_made_safe_and_follows_the_real_type():
    assert clean_name("../../etc/passwd", "image/png") == "passwd.png"
    assert clean_name("receipt.pdf", "image/png") == "receipt.png"
    assert clean_name('a"b<c>.jpg', "image/jpeg") == "abc.jpg"
    assert clean_name("", "application/pdf") == "file.pdf"
    assert len(clean_name("x" * 500 + ".png", "image/png")) <= 105


async def test_a_photo_goes_in_and_comes_back_byte_for_byte(api):
    headers, book, tx = await workspace(api)
    made = await upload(api, headers, book, tx, PNG)
    assert made.status_code == 201, made.text
    body = made.json()
    assert body["content_type"] == "image/png" and body["size"] == len(PNG)

    listed = (await api.get(url(book, tx), headers=headers)).json()
    assert [row["id"] for row in listed] == [body["id"]]

    got = await api.get(url(book, tx, body["id"]), headers=headers)
    assert got.content == PNG
    assert got.headers["content-type"] == "image/png"
    assert got.headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in got.headers["content-security-policy"]

    row = (await api.get(f"/api/v1/books/{book}/transactions/{tx}", headers=headers)).json()
    assert row["attachment_count"] == 1
    page = (await api.get(f"/api/v1/books/{book}/transactions", headers=headers)).json()
    assert page["items"][0]["attachment_count"] == 1


async def test_something_that_is_not_an_image_or_pdf_is_refused_whatever_it_is_called(api):
    headers, book, tx = await workspace(api)
    page = await upload(api, headers, book, tx, b"<html><script>alert(1)</script></html>", "photo.png")
    assert page.status_code == 422
    assert (await upload(api, headers, book, tx, b"", "empty.png")).status_code == 422


async def test_a_file_over_the_limit_and_a_sixth_file_are_refused(api):
    headers, book, tx = await workspace(api)
    big = await upload(api, headers, book, tx, PNG + b"0" * MAX_BYTES)
    assert big.status_code == 422 and "1.5" in big.json()["detail"]
    for _ in range(5):
        assert (await upload(api, headers, book, tx, PNG)).status_code == 201
    assert (await upload(api, headers, book, tx, PNG)).status_code == 422


async def test_deleting_a_file_and_deleting_the_transaction_remove_it(api):
    headers, book, tx = await workspace(api)
    kept = (await upload(api, headers, book, tx, PNG)).json()["id"]
    gone = (await upload(api, headers, book, tx, PDF, "a.pdf")).json()["id"]
    assert (await api.delete(url(book, tx, gone), headers=headers)).status_code == 204
    assert (await api.get(url(book, tx, gone), headers=headers)).status_code == 404
    assert [r["id"] for r in (await api.get(url(book, tx), headers=headers)).json()] == [kept]
    assert (await api.delete(f"/api/v1/books/{book}/transactions/{tx}", headers=headers)).status_code == 204
    assert (await api.get(url(book, tx), headers=headers)).status_code == 404


async def test_a_stranger_cannot_read_add_or_delete(api):
    headers, book, tx = await workspace(api)
    attachment = (await upload(api, headers, book, tx, PNG)).json()["id"]
    stranger = await signed_in(api, "s@example.com")
    assert (await api.get(url(book, tx), headers=stranger)).status_code == 404
    assert (await api.get(url(book, tx, attachment), headers=stranger)).status_code == 404
    assert (await upload(api, stranger, book, tx, PNG)).status_code == 404
    assert (await api.delete(url(book, tx, attachment), headers=stranger)).status_code == 404
    assert (await api.get(url(book, tx, attachment))).status_code == 401


async def test_a_file_does_not_open_under_another_books_path(api):
    headers, book, tx = await workspace(api)
    attachment = (await upload(api, headers, book, tx, PNG)).json()["id"]
    other_book = (await api.post("/api/v1/books", headers=headers, json={
        "name": "دوم", "type": "business", "currency": "IRT"})).json()["id"]
    other_tx = (await api.post(f"/api/v1/books/{other_book}/transactions", headers=headers, json={
        "flow": "expense", "scope": "work", "category": "اجاره", "amount": "5"})).json()["id"]
    assert (await api.get(url(other_book, other_tx, attachment), headers=headers)).status_code == 404
    assert (await api.get(url(book, other_tx, attachment), headers=headers)).status_code == 404
