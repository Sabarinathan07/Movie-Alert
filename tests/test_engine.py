import json
import tempfile
import unittest
from pathlib import Path

from moviealert.config import ConfigError, Source, TheatreGroup, Watch, load
from moviealert.engine import evaluate
from moviealert.models import Show


def watch(**kw):
    base = dict(
        id="w", users=["u"], movie="M", date="2026-12-17",
        sources=[Source("district", "x"), Source("bms", "y")],
        groups=[
            TheatreGroup("GK", r"\bgk\b.*porur"),
            TheatreGroup("IV", ".", format_match="infinity vision", sources=["district"]),
        ],
        language="English", formats=["3D"], min_seats=1,
    )
    base.update(kw)
    return Watch(**base)


def d(cinema, cid, sid, avail, fmt="MS INFINITY VISION 3D", time="13:00", lang="English"):
    return Show("district", cid, cinema, sid=sid, time=time, time_text=time, fmt=fmt,
                lang=lang, avail=avail, total=100)


class EngineTest(unittest.TestCase):
    def test_first_run_is_silent_baseline(self):
        ev, snap, ws = evaluate(watch(), {"district": [d("PVR X", "1", "a", 0)], "bms": []}, {})
        self.assertEqual(ev, [])
        self.assertTrue(ws["initialized"])
        self.assertIn("district:1", ws["open"])

    def test_open_and_seats_back(self):
        w = watch()
        _, _, ws = evaluate(w, {"district": [d("PVR X", "1", "a", 0)]}, {})
        shows = [d("PVR X", "1", "a", 2), d("GK Cinemas 4K 3D Porur", "9", "z", 50, fmt="3D")]
        ev, _, ws = evaluate(w, {"district": shows}, ws)
        texts = [e.text for e in ev]
        self.assertTrue(texts[0].startswith("OPENED on District: GK Cinemas"))
        self.assertTrue(any(t.startswith("SEATS BACK") and "PVR X" in t for t in texts))
        # no change -> no events
        ev, _, _ = evaluate(w, {"district": shows}, ws)
        self.assertEqual(ev, [])

    def test_filters_language_format_and_window(self):
        w = watch(show_to="12:00")
        _, _, ws = evaluate(w, {"district": [d("PVR X", "1", "a", 0)]}, {})
        ev, _, _ = evaluate(w, {"district": [d("PVR X", "1", "a", 5)]}, ws)  # 13:00 > 12:00
        self.assertEqual(ev, [])
        ev, _, _ = evaluate(watch(), {"district": [d("Other", "2", "b", 9, fmt="2D")]}, ws)
        self.assertEqual(ev, [])

    def test_bms_only_uses_groups_enabled_for_bms(self):
        w = watch()
        _, _, ws = evaluate(w, {"bms": []}, {})
        bms = [Show("bms", "GKPR", "gk cinemas 4k 3d porur", detail=False),
               Show("bms", "RAND", "random cinema", detail=False)]
        ev, _, _ = evaluate(w, {"bms": bms}, ws)
        self.assertEqual(len(ev), 1)
        self.assertIn("GKPR", ev[0].text)

    def test_failed_provider_keeps_previous_seat_counts(self):
        w = watch()
        _, _, ws = evaluate(w, {"district": [d("PVR X", "1", "a", 0)]}, {})
        _, _, ws2 = evaluate(w, {"district": None}, ws)
        self.assertEqual(ws2["avail"], ws["avail"])


class ConfigTest(unittest.TestCase):
    def _write(self, obj):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
        json.dump(obj, f)
        f.close()
        return Path(f.name)

    def test_example_config_loads(self):
        cfg = load(Path(__file__).parent.parent / "watches.example.json")
        self.assertEqual(len(cfg.watches), 2)

    def test_env_refs_resolve(self):
        import os
        os.environ["T_CHAT"] = "123"
        p = self._write({"users": {"a": {"telegram_chat_id": "env:T_CHAT"}}, "watches": []})
        self.assertEqual(load(p).users["a"].telegram_chat_id, "123")

    def test_validation_errors(self):
        p = self._write({"users": {}, "watches": [{"id": "x", "users": ["nobody"], "movie": "M",
                                                   "date": "17-12-2026", "sources": {}, "theatres": []}]})
        with self.assertRaises(ConfigError) as cm:
            load(p)
        msg = str(cm.exception)
        for part in ("unknown user", "YYYY-MM-DD", "at least one source", "theatre group"):
            self.assertIn(part, msg)


if __name__ == "__main__":
    unittest.main()
