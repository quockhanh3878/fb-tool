import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from shooter_worker import ShooterWorker


class FakeFileInput:
    def __init__(self):
        self.file_count = 0

    async def set_input_files(self, paths):
        self.file_count = len(paths)

    async def evaluate(self, _script):
        return self.file_count


class FakePage:
    def __init__(self, file_input=None):
        self.file_input = file_input

    async def query_selector(self, selector):
        if self.file_input is not None and 'input[type="file"]' in selector:
            return self.file_input
        return None

    def locator(self, _selector):
        return FakeLocator()


class FakeLocator:
    last = None

    async def count(self):
        return 0

    async def text_content(self):
        return ""


def test_attach_media_waits_for_all_files():
    worker = object.__new__(ShooterWorker)
    file_input = FakeFileInput()
    ok = asyncio.run(worker._attach_media(FakePage(file_input), ["a.png", "b.png"]))
    assert ok is True
    assert file_input.file_count == 2


def test_attach_media_fails_closed_when_input_is_missing():
    worker = object.__new__(ShooterWorker)
    ok = asyncio.run(worker._attach_media(FakePage(), ["a.png"]))
    assert ok is False


def test_clean_comment_permalink_keeps_comment_id_only():
    assert ShooterWorker._clean_comment_permalink(
        "https://www.facebook.com/groups/1042987808508567/posts/1053142604159754/"
        "?comment_id=1053144087492939&tracking=1#fragment"
    ) == (
        "https://www.facebook.com/groups/1042987808508567/posts/1053142604159754/"
        "?comment_id=1053144087492939"
    )
    assert ShooterWorker._clean_comment_permalink(
        "https://www.facebook.com/groups/1042987808508567/posts/1053142604159754/"
    ) is None


def test_extract_comments_js_returns_comment_identity_and_links():
    from constants import EXTRACT_COMMENTS_JS

    async def run():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            page = await browser.new_page()
            await page.goto("http://example.com")
            await page.set_content(
                '<div class="comment">'
                '<a href="/profile.php?id=123"><span dir="auto">Nguoi Viet</span></a>'
                '<div dir="auto">Can tim writer nhan long fic</div>'
                '<a href="/groups/1/posts/2?comment_id=77"><span dir="auto">1 gio</span></a>'
                '</div>'
            )
            result = await page.evaluate(
                EXTRACT_COMMENTS_JS,
                ["https://www.facebook.com/groups/1/posts/2/", 10],
            )
            await browser.close()
            return result

    result = asyncio.run(run())
    assert result == [
        {
            "id": "77",
            "text": "Can tim writer nhan long fic",
            "author": "Nguoi Viet",
            "authorId": "123",
            "url": "https://www.facebook.com/groups/1/posts/2/",
            "commentUrl": "https://www.facebook.com/groups/1/posts/2/?comment_id=77",
            "commentedAt": "",
        }
    ]
