import json
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).parents[2] / "src/scripts/courses"))
import courses


TZ = ZoneInfo("Asia/Jerusalem")


def registry(tmp_path):
    directory = tmp_path / "term"
    directory.mkdir()
    term = {
        "timezone": "Asia/Jerusalem",
        "semesters": {
            "A": {"start": "2026-10-11", "end": "2027-01-29"},
            "B": {"start": "2027-03-07", "end": "2027-06-25"},
        },
    }
    (directory / "term.json").write_text(json.dumps(term), encoding="utf-8")
    data = [
        {"slug": "machshava", "slots": [{"day": "Sun", "start": "12:00", "end": "14:00", "semester": "A"}]},
        {"slug": "migdar", "slots": [{"day": "Sun", "start": "12:00", "end": "14:00", "semester": "B"}]},
        {"slug": "regashot", "slots": [{"day": "Mon", "start": "12:00", "end": "14:00", "semester": "yearly"}]},
        {"slug": "friday", "slots": [{"day": "Fri", "start": "12:00", "end": "14:00", "semester": "yearly"}]},
    ]
    for item in data:
        (directory / f"{item['slug']}.json").write_text(json.dumps(item), encoding="utf-8")
    return courses.Registry(directory)


def local(value):
    return datetime.fromisoformat(value).replace(tzinfo=TZ)


def test_maps_monday_yearly_course_with_window(tmp_path):
    assert courses.map_recording(registry(tmp_path), local("2026-10-12T12:04:00")) == ("regashot", None)


def test_sunday_slot_resolves_to_semester_a_or_b(tmp_path):
    reg = registry(tmp_path)
    assert courses.map_recording(reg, local("2026-10-11T12:10:00")) == ("machshava", None)
    assert courses.map_recording(reg, local("2027-03-07T12:10:00")) == ("migdar", None)


def test_outside_slot_is_unmatched(tmp_path):
    slug, reason = courses.map_recording(registry(tmp_path), local("2026-10-12T19:00:00"))
    assert slug is None
    assert "slot" in reason


def test_utc_birth_time_maps_after_dst_change(tmp_path):
    # 10:04 UTC is 12:04 local after Israel returns to UTC+2.
    when = datetime.fromisoformat("2026-10-26T10:04:00+00:00")
    assert courses.map_recording(registry(tmp_path), when) == ("regashot", None)


def test_between_semesters_is_unmatched(tmp_path):
    slug, reason = courses.map_recording(registry(tmp_path), local("2027-02-01T12:10:00"))
    assert slug is None
    assert "semester" in reason


def test_voice_memo_filename_is_local_wall_time(tmp_path):
    path = tmp_path / "20261012 120422.m4a"
    assert courses.recording_time(path, birth_time=0) == local("2026-10-12T12:04:22")
