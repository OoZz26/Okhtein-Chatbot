from app.domain.reply_style import humanize_punctuation, remove_arabic_words


def test_arabic_words_are_removed_from_an_english_reply() -> None:
    assert remove_arabic_words("أكيد 🤍 Is it for everyday?") == "🤍 Is it for everyday?"
    assert remove_arabic_words("تمام يا حلوة, tell me the vibe?") == "tell me the vibe?"


def test_an_english_reply_is_untouched() -> None:
    text = "Ooh lovely 🤍\nIs it for everyday or a special occasion?"
    assert remove_arabic_words(text) == text


def test_em_and_en_dashes_become_commas() -> None:
    text = "It's so pretty — and it goes with everything – honestly"
    assert humanize_punctuation(text) == "It's so pretty, and it goes with everything, honestly"


def test_a_dash_at_the_end_of_a_sentence_leaves_no_stray_comma() -> None:
    assert humanize_punctuation("You'll love this one —") == "You'll love this one"
    assert humanize_punctuation("So elegant — . Want to see more?") == "So elegant. Want to see more?"


def test_list_markers_are_dropped_but_the_lines_stay() -> None:
    text = "Two I love:\n• *Mini Lotus Clutch*, 55,000 EGP\n- *Malleable Clutch*, 60,000 EGP\n1. *Charm*"
    assert humanize_punctuation(text) == (
        "Two I love:\n*Mini Lotus Clutch*, 55,000 EGP\n*Malleable Clutch*, 60,000 EGP\n*Charm*"
    )


def test_bold_hyphens_and_prices_are_untouched() -> None:
    text = "*Mini Lotus* is 10,000 EGP, a must-have for evenings"
    assert humanize_punctuation(text) == text
