import pytest

from pipeline import ocr, quotes


def test_normalize_keeps_compound_hyphen():
    assert ocr.normalize("медико-\nсанитарную  помощь ") == "медико-санитарную помощь"


def test_cut_between_markers():
    text = "1. Первый пункт.\n2. Второй пункт\nпродолжается здесь.\n3. Третий."
    assert quotes.cut(text, "2. Второй", "здесь.") == "2. Второй пункт продолжается здесь."
    with pytest.raises(LookupError):
        quotes.cut(text, "4.", "конец")


def test_structure_splits_list_items():
    assert quotes.structure("в том числе: первое; второе.") == "в том числе:\nпервое;\nвторое."


def test_diff_counts_changed_words():
    d = ocr.diff_words("а б в", "а б г")
    assert ocr.changed(d) == 2
