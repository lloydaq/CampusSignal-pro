"""Notice previews (`excerpt`): the list shows plain text, so Markdown markup goes and list items
stay apart from each other and from the paragraph after them."""

import pytest

from app.schemas.notices import EXCERPT_LENGTH, excerpt


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        ("Plain text.", "Plain text."),
        ("**Bold** and _italic_ and `code`.", "Bold and italic and code."),
        ("See the [exam page](https://example.org/exams).", "See the exam page."),
        (
            "Mid-terms run **3 to 7 November**.\n\n"
            "- Bring your ID card\n- Arrive 15 minutes early\n\n"
            "See the [exam cell page](https://northfield.example/exams).",
            "Mid-terms run 3 to 7 November. Bring your ID card · Arrive 15 minutes early · "
            "See the exam cell page.",
        ),
        ("Steps:\n1. Sign in\n2. Open Results", "Steps: Sign in · Open Results"),
        ("* One\n+ Two", "One · Two"),
        ("- Done.\n- Next", "Done. Next"),  # a sentence already ends: no extra separator
        ("A paragraph wrapped\nacross two lines.", "A paragraph wrapped across two lines."),
    ],
)
def test_previews_drop_markup_and_keep_list_items_apart(body: str, expected: str) -> None:
    assert excerpt(body) == expected


def test_long_previews_are_cut_with_an_ellipsis() -> None:
    preview = excerpt("word " * 100)
    assert len(preview) == EXCERPT_LENGTH
    assert preview.endswith("…")
