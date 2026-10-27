"""Text helpers for interviews held in Mandarin Chinese (interview_language: zh-TW).

Whisper writes Mandarin in Simplified characters; OpenCC turns it into Taiwan Traditional. Speech recognition
and the aggregator join pieces with spaces, which Chinese does not use. Speaking rate counts Chinese characters
and English words. The interviewer's Chinese voice is in chinese_tts.py.
"""

import re

CJK = r"㐀-鿿豈-﫿"
# Full-width punctuation that sits against Chinese text without spaces.
CJK_PUNCT = r"　-〿＀-￯"
CJK_CHAR = re.compile(f"[{CJK}]")
# A space between two Chinese characters, or next to full-width punctuation, is an artifact of joining pieces.
# Spaces between Chinese and English stay, as Taiwanese writing puts them there ("把 GRU 換成 MLP").
CJK_SPACE = re.compile(f"(?<=[{CJK_PUNCT}]) +| +(?=[{CJK_PUNCT}])|(?<=[{CJK}]) +(?=[{CJK}])")
# Half-width punctuation right after a Chinese character; Whisper writes "你好,我是" instead of "你好，我是".
HALF_WIDTH_PUNCT = re.compile(f"(?<=[{CJK}])[,?!:;]")
FULL_WIDTH = {",": "，", "?": "？", "!": "！", ":": "：", ";": "；"}
SPOKEN_UNIT = re.compile(f"[{CJK}]|[A-Za-z0-9]+(?:['’.-][A-Za-z0-9]+)*")


def has_chinese(text: str) -> bool:
    return bool(CJK_CHAR.search(text or ""))


def spoken_units(text: str) -> int:
    """Words for English, characters for Chinese: each Chinese character and each English word counts once."""
    return len(SPOKEN_UNIT.findall(text or ""))


def tidy_spaces(text: str) -> str:
    """Drops the spaces left between Chinese pieces: "我們 用了 GRU 。" -> "我們用了 GRU。". English is untouched."""
    return CJK_SPACE.sub("", text)


def chinese_punctuation(text: str) -> str:
    """Full-width commas and question marks after Chinese characters: "你好,我是" -> "你好，我是"."""
    return HALF_WIDTH_PUNCT.sub(lambda m: FULL_WIDTH[m.group(0)], text)


_converters = {}


def _convert(text: str, config: str) -> str:
    if config not in _converters:
        import opencc

        _converters[config] = opencc.OpenCC(config)
    return _converters[config].convert(text)


def to_traditional(text: str) -> str:
    """Simplified to Taiwan Traditional, including Taiwan wording (视频 -> 影片, 软件 -> 軟體)."""
    return _convert(text, "s2twp")


def to_simplified(text: str) -> str:
    """Taiwan Traditional to Simplified. The G2P's word segmentation (jieba) is built for Simplified text, and
    the words it finds decide how characters with several readings are pronounced."""
    return _convert(text, "tw2sp")
