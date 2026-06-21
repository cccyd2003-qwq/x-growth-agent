"""Offline smoke tests — no network, no API keys, no live agent.

Covers the pure logic: JSON extraction from messy model output, candidate
parsing, prompt assembly, and the CLI range selector.
"""

from xgrowth.engines.base import Engine
from xgrowth.models import Candidate, Post
from xgrowth.prompts import build_reply_prompt
from xgrowth.util import extract_json


def test_extract_json_plain():
    assert extract_json('{"a": 1}') == {"a": 1}


def test_extract_json_fenced():
    raw = '```json\n{"candidates": [{"style": "x", "text": "hi"}]}\n```'
    data = extract_json(raw)
    assert data["candidates"][0]["text"] == "hi"


def test_extract_json_embedded_in_prose():
    raw = 'Sure! Here you go:\n{"candidates": [{"style": "s", "text": "yo"}]}\nHope that helps.'
    data = extract_json(raw)
    assert data["candidates"][0]["style"] == "s"


def test_parse_candidates_from_dict():
    raw = '{"candidates": [{"style": "神补刀", "text": "plot twist"}, {"style": "反直觉", "text": "nah"}]}'
    cands = Engine._parse(raw, 3)
    assert len(cands) == 2
    assert cands[0].style == "神补刀"
    assert cands[0].text == "plot twist"


def test_parse_candidates_truncates_to_n():
    raw = '[{"text": "a"}, {"text": "b"}, {"text": "c"}]'
    cands = Engine._parse(raw, 2)
    assert len(cands) == 2


def test_post_url():
    p = Post(tweet_id="123", username="naval", author_id="9", text="hi")
    assert p.url == "https://x.com/naval/status/123"


def test_build_prompt_contains_post_and_rules():
    p = Post(tweet_id="1", username="naval", author_id="9", text="learn to learn")
    prompt = build_reply_prompt(p, ["神补刀", "反直觉"], 2)
    assert "learn to learn" in prompt
    assert "@naval" in prompt
    assert "STRICT JSON" in prompt
    assert "神补刀" in prompt


def test_rapidapi_status_parse_and_filters():
    from xgrowth.twitter import RapidApiClient

    original = {"id_str": "111", "full_text": "a real original post", "created_at": "now"}
    reply = {"id_str": "222", "text": "@x replying", "in_reply_to_status_id_str": "999"}
    retweet = {"id_str": "333", "text": "RT @y: something"}

    p = RapidApiClient._post_from_status(original, "naval", "745273", True, True)
    assert p and p.tweet_id == "111" and p.text == "a real original post"

    assert RapidApiClient._post_from_status(reply, "naval", "1", True, True) is None
    assert RapidApiClient._post_from_status(retweet, "naval", "1", True, True) is None
    # when filters are off, reply/retweet come through
    assert RapidApiClient._post_from_status(reply, "naval", "1", False, False) is not None


def test_human_age():
    from datetime import datetime, timezone
    from xgrowth.util import human_age

    now = datetime(2026, 6, 21, 12, 0, 0, tzinfo=timezone.utc)
    assert human_age("Sun Jun 21 11:57:00 +0000 2026", now=now) == "3 分钟前"
    assert human_age("Sun Jun 21 09:00:00 +0000 2026", now=now) == "3 小时前"
    assert human_age("2026-06-21T11:59:30.000Z", now=now) == "刚刚"
    assert human_age("", now=now) == ""


def test_poll_window_wraps_midnight():
    from xgrowth.poller import _in_window

    # window 12:00 -> 02:00 next day
    assert _in_window(12, 12, 2)
    assert _in_window(23, 12, 2)
    assert _in_window(1, 12, 2)
    assert not _in_window(2, 12, 2)
    assert not _in_window(9, 12, 2)


def test_instruction_in_prompt():
    from xgrowth.models import Post
    from xgrowth.prompts import build_reply_prompt

    p = Post(tweet_id="1", username="x", author_id="2", text="hi")
    prompt = build_reply_prompt(p, ["神补刀"], 2, instruction="更毒一点")
    assert "更毒一点" in prompt
    assert "20-word" in prompt or "20 words" in prompt


def test_range_selector():
    from xgrowth.cli import _select

    items = list("abcdefgh")
    assert _select(items, "1,3,5-7") == ["a", "c", "e", "f", "g"]
    assert _select(items, "all") == items
    assert _select(items, "") == []
