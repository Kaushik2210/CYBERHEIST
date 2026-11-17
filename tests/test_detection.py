"""Detection meter: thresholds, failure and gear modifiers."""
from challenges.detection import DetectionMeter
from core.state import load_config

CFG = load_config()["detection"]


def test_status_thresholds():
    m = DetectionMeter(CFG)
    assert m.status == "CLEAR"
    for level, label in [(29, "CLEAR"), (30, "ELEVATED"), (59, "ELEVATED"), (60, "HIGH"),
                         (84, "HIGH"), (85, "CRITICAL"), (99, "CRITICAL")]:
        m.level = level
        assert m.status == label, level


def test_wrong_guess_adds_eight_and_fails_at_100():
    m = DetectionMeter(CFG)
    assert m.wrong_guess() == 8
    for _ in range(20):
        m.wrong_guess()
    assert m.level == 100 and m.failed and m.status == "DETECTED"


def test_ghost_proxy_scales_gains():
    m = DetectionMeter(CFG, ghost_proxy=True)
    assert abs(m.wrong_guess() - 8 * 0.7) < 1e-9


def test_signal_mask_absorbs_one_alarm():
    m = DetectionMeter(CFG, signal_mask=True)
    assert m.alarm() == (0.0, True)
    added, absorbed = m.alarm()
    assert added == 15 and not absorbed


def test_overtime_and_peak():
    m = DetectionMeter(CFG)
    m.overtime(5)
    m.reduce(3)
    assert m.level == 2 and m.peak == 5
