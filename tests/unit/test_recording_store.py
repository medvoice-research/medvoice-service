import os

import pytest

from app.services.recording_store import RecordingStore


@pytest.fixture()
def store(tmp_path):
    return RecordingStore(storage_dir=str(tmp_path))


def test_save_and_load_recording(store):
    rec_id = store.create_recording(patient_name="Jane Doe", language="en", audio_filename="a.m4a")
    assert rec_id.startswith("rec_")
    audio_path = store.audio_path(rec_id)
    with open(audio_path, "w") as f:
        f.write("fake-audio")
    store.save_transcript(rec_id, {"full_text": "hi", "segments": []})
    store.save_medical(rec_id, {"soap": {}, "entities": [], "phi": {"detected": False, "entities": []}})
    store.finalize(rec_id)

    meta = store.load_meta(rec_id)
    assert meta["status"] == "completed"
    assert store.load_transcript(rec_id)["full_text"] == "hi"
    assert os.path.exists(store.audio_path(rec_id))


def test_list_recordings_newest_first(store):
    a = store.create_recording(patient_name="A", language="en", audio_filename="a.m4a")
    b = store.create_recording(patient_name="B", language="en", audio_filename="b.m4a")
    for rid in (a, b):
        store.finalize(rid)
    items = store.list_recordings()
    assert [i["recording_id"] for i in items] == [b, a]


def test_delete_recording(store):
    rid = store.create_recording(patient_name="A", language="en", audio_filename="a.m4a")
    store.finalize(rid)
    assert store.delete_recording(rid) is True
    assert store.load_meta(rid) is None
    assert store.delete_recording(rid) is False


@pytest.mark.parametrize("bad_id", ["..", "../..", "rec_../../evil", "/etc", "rec_TEST", "", "rec_a/../../b"])
def test_store_rejects_ids_outside_the_allowlist(store, bad_id):
    with pytest.raises(ValueError):
        store.load_meta(bad_id)
    with pytest.raises(ValueError):
        store.delete_recording(bad_id)


def test_audio_filename_is_confined_to_the_recording_dir(store, tmp_path):
    rid = store.create_recording(patient_name="A", language="en", audio_filename="../../../evil.mp4")
    assert store.audio_path(rid).parent == (tmp_path / rid).resolve()
    assert store.audio_path(rid).name == "evil.mp4"


def test_finalize_without_meta_raises_filenotfound(store):
    with pytest.raises(FileNotFoundError):
        store.finalize("rec_20260101_000000_deadbeef")


def test_list_recordings_tolerates_corrupt_metadata(store, tmp_path):
    good = store.create_recording(patient_name="A", language="en", audio_filename="a.m4a")
    (tmp_path / "rec_20260101_000000_00000000").mkdir()
    (tmp_path / "rec_20260101_000000_00000000" / "meta.json").write_text("{}")
    (tmp_path / "not_a_recording").mkdir()
    items = store.list_recordings()
    assert good in [i["recording_id"] for i in items]
    assert "not_a_recording" not in [i.get("recording_id") for i in items]
