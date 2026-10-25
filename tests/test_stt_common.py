import wave

from stt_common import TurnAudio, hotword_fixer, save_wav


def test_hotword_fixer_restores_split_and_recased_terms():
    fix = hotword_fixer(["TensorRT", "AcmeVision", "INT8", "ByteTrack"])
    assert fix("We used tensor RT and Tensor-RT.") == "We used TensorRT and TensorRT."
    assert fix("acme vision is hiring") == "AcmeVision is hiring"
    assert fix("int 8 quantization") == "INT8 quantization"
    assert fix("byte track ids") == "ByteTrack ids"


def test_hotword_fixer_leaves_short_hotwords_and_word_parts_alone():
    fix = hotword_fixer(["Go", "QNN", "LoRA"])
    assert fix("I want to go home") == "I want to go home"  # "Go" is too short to restore
    assert fix("flora and lora") == "flora and LoRA"  # only whole words


def test_turn_audio_matches_pieces_to_their_answer_by_text():
    audio = TurnAudio()
    audio.add(b"\x01\x00", "First sentence.")
    # The next piece is already transcribed before the first answer is handed over.
    audio.add(b"\x02\x00", "Second sentence.")
    assert audio.take("First sentence.") == b"\x01\x00"
    assert audio.take("Second sentence.") == b"\x02\x00"
    assert audio.take("Nothing left.") == b""


def test_turn_audio_keeps_untranscribed_segments_with_the_next_piece():
    audio = TurnAudio()
    audio.add(b"\x00\x00", None)  # silent or dropped segment
    audio.add(b"\x03\x00", "Hello  there.")
    assert audio.take("Hello there. And more.") == b"\x00\x00\x03\x00"


def test_turn_audio_answer_with_several_pieces():
    audio = TurnAudio()
    audio.add(b"a", "One.")
    audio.add(b"b", "Two.")
    assert audio.take("One. Two.") == b"ab"


def test_save_wav_writes_16_bit_mono(tmp_path):
    path = tmp_path / "x" / "answer-01.wav"
    save_wav(path, b"\x00\x00" * 160, 16000)
    with wave.open(str(path)) as w:
        assert (w.getnchannels(), w.getsampwidth(), w.getframerate(), w.getnframes()) == (1, 2, 16000, 160)
