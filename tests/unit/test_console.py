import io
import sys

from robi.console import use_utf8_streams


def test_cp1252_stream_accepts_ukrainian_after_switch(monkeypatch):
    # Саме так виглядав stdout служби на планшеті: файл у cp1252.
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    use_utf8_streams()
    print("[settings] застосовую версію 2", flush=True)

    assert raw.getvalue().decode("utf-8").strip() == "[settings] застосовую версію 2"


def test_streams_without_reconfigure_are_left_alone(monkeypatch):
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)
    use_utf8_streams()  # не кидає
    print("ок")
    assert stream.getvalue() == "ок\n"
