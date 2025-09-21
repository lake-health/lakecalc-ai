import json
from unittest.mock import MagicMock, patch

import pytest

from app.utils import llm_extract_missing_fields


def make_fake_resp(content: str):
    fake = MagicMock()
    fake.choices = [MagicMock()]
    fake.choices[0].message.content = content
    return fake


def test_llm_extract_parses_json_direct():
    # simple JSON (no code fences)
    fake_content = '{"od": {"axis": "100"}, "os": {"axis": ""}}'
    fake_resp = make_fake_resp(fake_content)
    with patch("app.utils.openai.chat.completions.create", return_value=fake_resp):
        out = llm_extract_missing_fields("text", {"od": ["axis"], "os": ["axis"]})
    assert out.get("od", {}).get("axis") == "100"


def test_llm_extract_parses_codeblock_json():
    # JSON wrapped in triple backticks
    content = "```json\n{\n  \"od\": { \"k1\": { \"value\": \"40.95\", \"axis\": \"100\" } },\n  \"os\": {}\n}\n```"
    fake_resp = make_fake_resp(content)
    with patch("app.utils.openai.chat.completions.create", return_value=fake_resp):
        out = llm_extract_missing_fields("text", {"od": ["k1"], "os": []})
    assert isinstance(out, dict)
    assert out.get("od", {}).get("k1", {}).get("value") == "40.95"
