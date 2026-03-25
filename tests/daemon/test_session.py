import time
from phone_cli.daemon.session import Session, SessionManager

class TestSessionCreate:
    def test_create_active_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A", timeout=300)
        assert session.status == "active"
        assert session.device_type == "ios"
        assert session.device_id == "iPhone-A"
        assert session.session_id

    def test_create_queued_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id=None, timeout=300, status="queued")
        assert session.status == "queued"
        assert session.device_id is None

class TestSessionRelease:
    def test_release_active_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        mgr.release(session.session_id)
        assert mgr.get(session.session_id).status == "released"

    def test_release_unknown_session_returns_none(self):
        mgr = SessionManager()
        result = mgr.release("nonexistent-id")
        assert result is None

class TestSessionExpire:
    def test_expire_session(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        mgr.expire(session.session_id)
        assert mgr.get(session.session_id).status == "expired"

class TestSessionActivity:
    def test_touch_updates_last_active(self):
        mgr = SessionManager()
        session = mgr.create("ios", device_id="iPhone-A")
        old_ts = session.last_active_at
        time.sleep(0.01)
        mgr.touch(session.session_id)
        assert mgr.get(session.session_id).last_active_at > old_ts

class TestSessionQuery:
    def test_active_sessions(self):
        mgr = SessionManager()
        s1 = mgr.create("ios", device_id="iPhone-A")
        s2 = mgr.create("adb", device_id="emu-5554")
        mgr.release(s1.session_id)
        active = mgr.active_sessions()
        assert len(active) == 1
        assert active[0].session_id == s2.session_id

    def test_expired_sessions_for_timeout(self):
        mgr = SessionManager()
        s1 = mgr.create("ios", device_id="iPhone-A", timeout=0.01)
        time.sleep(0.02)
        expired = mgr.find_expired()
        assert len(expired) == 1
        assert expired[0].session_id == s1.session_id
