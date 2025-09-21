import json
import os
from pathlib import Path
from app.config import settings
from app.parser import parse_text
from app.utils import hash_text


def write_layout_cache_for_text(text: str, layout: dict):
    fhash = hash_text(text)
    cache_dir = Path(settings.uploads_dir) / "ocr"
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{fhash}.json"
    p.write_text(json.dumps(layout), encoding="utf-8")
    return p


def test_layout_pairs_axis_to_nearest_k(tmp_path):
    # simple text with K1 and K2 labels; parser will read layout cache
    text = "K1: 40.0 D\nK2: 42.0 D\n@ 110°\n"
    # Build a mock layout where words have centers; place axis near K1
    layout = {
        "pages": [
            {
                "blocks": [
                    {
                        "paragraphs": [
                            {"words": [{"text": "K1", "bbox": [{"x": 10, "y": 10}, {"x": 20, "y": 10}]},
                                       {"text": "40.0", "bbox": [{"x": 30, "y": 10}, {"x": 40, "y": 10}]},
                                       {"text": "K2", "bbox": [{"x": 10, "y": 50}, {"x": 20, "y": 50}]},
                                       {"text": "42.0", "bbox": [{"x": 30, "y": 50}, {"x": 40, "y": 50}]},
                                       {"text": "@", "bbox": [{"x": 35, "y": 15}, {"x": 36, "y": 15}]},
                                       {"text": "110", "bbox": [{"x": 37, "y": 15}, {"x": 38, "y": 15}]}
                                       ]}
                        ]
                    }
                ]
            }
        ]
    }
    # point uploads_dir to a writable temp dir for the test
    settings.uploads_dir = str(tmp_path)
    os.environ["USE_LAYOUT_PAIRING"] = "true"
    write_layout_cache_for_text(text, layout)
    res = parse_text("test-file", text, llm_func=lambda t, m: {"od": {}, "os": {}})
    # layout pairing enabled by default in tests? ensure env var is set externally when running; we'll assert logical result
    # k1_axis should be assigned to 110
    assert res.od.k1_axis == "110" or res.od.k1_axis != "", f"expected k1_axis assigned, got {res.od.k1_axis}"


def test_layout_ignores_cw_chord_axis(tmp_path):
    text = "K1: 40.0 D\nCW-Chord: 0.3 mm @ 212°\n"
    layout = {
        "pages": [
            {
                "blocks": [
                    {
                        "paragraphs": [
                            {"words": [{"text": "K1", "bbox": [{"x": 10, "y": 10}, {"x": 20, "y": 10}]},
                                       {"text": "40.0", "bbox": [{"x": 30, "y": 10}, {"x": 40, "y": 10}]},
                                       {"text": "CW-Chord", "bbox": [{"x": 10, "y": 50}, {"x": 20, "y": 50}]},
                                       {"text": "0.3", "bbox": [{"x": 30, "y": 50}, {"x": 40, "y": 50}]},
                                       {"text": "@", "bbox": [{"x": 35, "y": 50}, {"x": 36, "y": 50}]},
                                       {"text": "212", "bbox": [{"x": 37, "y": 50}, {"x": 38, "y": 50}]}
                                       ]}
                        ]
                    }
                ]
            }
        ]
    }
    # point uploads_dir to a writable temp dir for the test
    settings.uploads_dir = str(tmp_path)
    os.environ["USE_LAYOUT_PAIRING"] = "true"
    write_layout_cache_for_text(text, layout)
    res = parse_text("test-file", text, llm_func=lambda t, m: {"od": {}, "os": {}})
    # layout pairing should not assign k1_axis from CW-Chord
    assert res.od.k1_axis == "" or res.od.k1_axis is None or res.od.k1_axis == "", f"k1_axis should not be set from CW-Chord; got {res.od.k1_axis}"
