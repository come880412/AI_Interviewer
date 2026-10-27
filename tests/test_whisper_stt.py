"""Hallucination filters of InterviewWhisperSTT, exercised without loading a Whisper model."""

from types import SimpleNamespace

import pytest

import whisper_stt
from whisper_stt import SUBTITLE_CREDITS, WORD, InterviewWhisperSTT

HOTWORDS = "QNX TensorRT ONNX INT8 QNN HTP"


def make_stt(hotwords: str = HOTWORDS, context: str = "", min_avg_logprob: float = -1.0) -> InterviewWhisperSTT:
    stt = object.__new__(InterviewWhisperSTT)
    stt._hotword_seq = WORD.findall(hotwords.lower())
    stt._context = context
    stt._min_avg_logprob = min_avg_logprob
    return stt


def seg(text, no_speech_prob=0.1, avg_logprob=-0.3):
    return SimpleNamespace(text=text, no_speech_prob=no_speech_prob, avg_logprob=avg_logprob)


# --- hotword echo ---------------------------------------------------------------------------------

def test_echoes_three_hotwords_in_list_order():
    stt = make_stt()
    assert stt._echoes_hotwords("QNX TensorRT ONNX INT8s")  # the transcript that prompted the filter
    assert stt._echoes_hotwords("we then tensorrt onnx int8 it")


def test_real_sentence_with_hotwords_is_kept():
    stt = make_stt()
    assert not stt._echoes_hotwords("I used QNN INT8 on the HTP")
    assert not stt._echoes_hotwords("ONNX TensorRT QNX")  # out of list order
    assert not stt._echoes_hotwords("TensorRT ONNX")  # only two in a row


def test_echo_with_short_or_empty_hotword_list():
    assert not make_stt("")._echoes_hotwords("QNX TensorRT ONNX")
    assert not make_stt("QNX TensorRT")._echoes_hotwords("QNX TensorRT ONNX")
    assert not make_stt()._echoes_hotwords("")


# --- context copying ------------------------------------------------------------------------------

def test_copies_context():
    stt = make_stt(context="Can you walk me through how you quantized the detection model for the edge device?")
    assert stt._copies_context("how you quantized the detection model for the edge device")
    assert not stt._copies_context("I used post-training quantization with a calibration set of images")


def test_copies_context_needs_minimum_words():
    stt = make_stt(context="the model for the edge")
    assert not stt._copies_context("the model for the edge")  # five words: too short to judge
    assert not make_stt(context="")._copies_context("one two three four five six seven")


def test_add_context_appends_and_truncates():
    stt = make_stt()
    stt.add_context("  Hello   there \n")
    stt.add_context("")
    stt.add_context(None)
    assert stt._context == "Hello there"
    stt.add_context("General Kenobi.")
    assert stt._context == "Hello there General Kenobi."

    stt.add_context("x" * 1000)
    assert len(stt._context) == whisper_stt.CONTEXT_CHARS
    assert stt._context == "x" * whisper_stt.CONTEXT_CHARS

    stt._context = ""
    stt.add_context("a" * (whisper_stt.CONTEXT_CHARS - 1))
    stt.add_context("b")
    assert stt._context.endswith(" b") and len(stt._context) == whisper_stt.CONTEXT_CHARS


# --- reject reasons -------------------------------------------------------------------------------

def test_reject_reason_order_and_values():
    stt = make_stt(context="")
    assert stt._reject_reason(seg("I trained it on eight GPUs."), 0.6) is None
    assert stt._reject_reason(seg("speech", no_speech_prob=0.7), 0.6) == "no speech 0.70"
    assert stt._reject_reason(seg("speech", no_speech_prob=0.99), None) is None  # no threshold configured
    assert stt._reject_reason(seg("speech", avg_logprob=-1.25), 0.6) == "low confidence -1.25"
    assert stt._reject_reason(seg(" QNX TensorRT ONNX"), 0.6) == "repeats the hotword list"
    assert stt._reject_reason(seg("Thank you for watching!"), 0.6) == "subtitle credit"


def test_reject_reason_copies_context():
    stt = make_stt(context="Tell me about a time you disagreed with your manager about a deadline.")
    assert stt._reject_reason(seg("a time you disagreed with your manager about a deadline"), 0.6) == \
        "copies the context prompt"


def test_reject_reason_threshold_is_configurable():
    lenient = make_stt(min_avg_logprob=-1.5)
    assert lenient._reject_reason(seg("fine", avg_logprob=-1.25), None) is None


# --- subtitle credits -----------------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    "Subtitles by the Amara.org community",
    "subtitle by someone",
    "Transcription by CastingWords",
    "Captions by GetSubs",
    "Thank you for watching.",
    "Thanks for watching!",
    "thank for watching",
    "Please subscribe to my channel",
    "amara.org",
])
def test_subtitle_credits_match(text):
    assert SUBTITLE_CREDITS.search(text)


@pytest.mark.parametrize("text", [
    "I wrote the subtitles module myself",
    "We did the translation layer in C++",
    "Thanks for asking about watching metrics",
    "I subscribe to the event bus",
])
def test_subtitle_credits_do_not_match_normal_speech(text):
    assert not SUBTITLE_CREDITS.search(text)


@pytest.mark.parametrize("text", [
    "字幕由Amara.org社区提供",
    "请不吝点赞 订阅 转发 打赏支持明镜与点点栏目",
    "謝謝觀看",
    "感谢观看",
    "优优独播剧场",
])
def test_chinese_subtitle_credits_match(text):
    assert SUBTITLE_CREDITS.search(text)


@pytest.mark.parametrize("text", [
    "我們把 GRU 換成 MLP，因為 QNN 不支援",
    "我負責影片字幕的偵測模型",
    "謝謝你的問題",
])
def test_chinese_subtitle_credits_do_not_match_normal_speech(text):
    assert not SUBTITLE_CREDITS.search(text)


def test_copies_context_counts_chinese_characters():
    stt = make_stt(context="你可以說明一下你當初是怎麼把模型量化到 INT8 的嗎？")
    assert stt._copies_context("你當初是怎麼把模型量化到 INT8 的")
    assert not stt._copies_context("我先用校正資料集做 post-training quantization")
