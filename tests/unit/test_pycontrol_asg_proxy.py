from __future__ import annotations

from PulseGenerator.asg_process import ASGProxy


def test_proxy_retains_status_returned_by_start_worker(monkeypatch) -> None:
    proxy = ASGProxy()
    calls: list[str] = []

    def call(command: str, *args, **kwargs):
        calls.append(command)
        return {
            "seq": 1,
            "ok": True,
            "result": {"playback_state": 1, "loop": 1},
            "error": "",
        }

    monkeypatch.setattr(proxy, "_call", call)

    assert proxy.start() is True
    assert proxy.last_start_status == {"playback_state": 1, "loop": 1}
    assert calls == ["start"]
