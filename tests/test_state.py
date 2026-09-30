from uptime_monitor.models import CheckResult, Monitor
from uptime_monitor.state import DOWN, UNKNOWN, UP, MonitorState, update

M = Monitor("Site", "http", url="https://x.it", fail_threshold=3, recover_threshold=2, remind_every=600)
OK, FAIL = CheckResult(True, 50), CheckResult(False, 0, "HTTP 503")


def feed(results, state=None, start=0.0, step=60.0):
    state = state or MonitorState()
    events = []
    now = start
    for r in results:
        state, event = update(state, r, M, now)
        if event:
            events.append((event.kind, now, event.duration))
        now += step
    return state, events


def test_first_start_goes_up_silently():
    state, events = feed([OK, OK])
    assert state.status == UP and events == []
    assert feed([OK])[0].status == UNKNOWN  # one success is not enough yet


def test_single_failures_are_ignored():
    state, events = feed([OK, OK, FAIL, OK, FAIL, FAIL, OK, OK])
    assert state.status == UP and events == []


def test_down_after_threshold_then_recovery_with_duration():
    state, events = feed([OK, OK, FAIL, FAIL, FAIL, FAIL, OK, OK])
    assert state.status == UP
    assert [(k, t) for k, t, _ in events] == [("down", 240.0), ("up", 420.0)]
    assert events[1][2] == 180.0  # down at 240, recovered at 420


def test_one_success_while_down_is_not_recovery():
    state, events = feed([FAIL, FAIL, FAIL, OK, FAIL])
    assert state.status == DOWN and [e[0] for e in events] == ["down"]


def test_reminders_while_down():
    state, events = feed([FAIL] * 25)  # one check a minute for 25 minutes, remind every 10
    assert [(k, t) for k, t, _ in events] == [("down", 120.0), ("reminder", 720.0), ("reminder", 1320.0)]
    assert events[1][2] == 600.0 and state.last_error == "HTTP 503"


def test_no_reminders_when_disabled():
    quiet = Monitor("Site", "http", url="https://x.it", fail_threshold=1, remind_every=0)
    state = MonitorState()
    kinds = []
    for i in range(50):
        state, event = update(state, FAIL, quiet, i * 3600.0)
        kinds += [event.kind] if event else []
    assert kinds == ["down"]
