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
