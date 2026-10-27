import pytest

from chinese import chinese_punctuation, has_chinese, spoken_units, tidy_spaces, to_simplified, to_traditional


def test_has_chinese():
    assert has_chinese("我用了 GRU")
    assert not has_chinese("I used a GRU.")
    assert not has_chinese("")


@pytest.mark.parametrize("text, expected", [
    ("I used a GRU.", 4),
    ("我用了 GRU", 4),  # three characters and one word
    ("誤差從 4.0 降到 0.15。", 7),
    ("it's a trade-off", 3),
    ("", 0),
])
def test_spoken_units(text, expected):
    assert spoken_units(text) == expected


@pytest.mark.parametrize("text, expected", [
    ("我們 用了 GRU 。", "我們用了 GRU。"),
    ("好， 那我們 開始。 下一題", "好，那我們開始。下一題"),
    ("I used a GRU.", "I used a GRU."),  # English keeps its spaces
    ("QNN SDK 不支援", "QNN SDK 不支援"),  # and so does the gap between English and Chinese
])
def test_tidy_spaces(text, expected):
    assert tidy_spaces(text) == expected


def test_chinese_punctuation():
    assert chinese_punctuation("你好,我是 Mark。為什麼?") == "你好，我是 Mark。為什麼？"
    assert chinese_punctuation("I see, why?") == "I see, why?"  # English punctuation stays
    assert chinese_punctuation("用了 GRU, 對嗎?") == "用了 GRU, 對嗎？"  # only right after a Chinese character


def test_opencc_conversions():
    assert to_traditional("我们用软件处理视频") == "我們用軟體處理影片"  # Taiwan wording too
    assert to_traditional("GRU 换成 MLP") == "GRU 換成 MLP"
    assert to_simplified("我們用軟體處理影片") == "我们用软件处理视频"
