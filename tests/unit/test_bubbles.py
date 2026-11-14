from app.domain.bubbles import split_into_bubbles


def test_a_short_reply_stays_one_message() -> None:
    assert split_into_bubbles("Hello! How can I help?", 3) == ["Hello! How can I help?"]


def test_paragraphs_become_separate_bubbles() -> None:
    assert split_into_bubbles("Lovely choice ✨\n\nHere are two options\n\nWhich do you prefer?", 3) == [
        "Lovely choice ✨",
        "Here are two options",
        "Which do you prefer?",
    ]


def test_never_more_than_the_maximum_and_nothing_is_lost() -> None:
    text = "\n\n".join(f"part {i}" for i in range(6))

    bubbles = split_into_bubbles(text, 3)

    assert len(bubbles) == 3
    assert bubbles[:2] == ["part 0", "part 1"]
    assert bubbles[2] == "part 2\n\npart 3\n\npart 4\n\npart 5"  # the remainder is kept together


def test_blank_text_gives_no_bubbles() -> None:
    assert split_into_bubbles("  \n\n  ", 3) == []
