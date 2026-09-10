"""Immutable web snapshots and bounded input handoff to the device loop."""

from concurrent.futures import Future, TimeoutError
from queue import Empty, Full, Queue
from uuid import uuid4


class WebBridge:
    def __init__(self, clock):
        self.clock = clock
        self.epoch = uuid4().hex
        self.revision = 0
        self.activation = None
        self.state = {}
        self.expires = None
        self.inputs = Queue(maxsize=32)

    def publish(self, state, activation):
        if activation is not self.activation:
            self.revision += 1
            self.activation = activation
        state["display"]["token"] = f"{self.epoch}:{self.revision}"
        # One assignment publishes a complete frame, never a mixture of modes.
        self.state = (state, activation.expires_at)

    def read(self):
        if not self.state:
            return {}
        state, expires = self.state
        remaining = None if expires is None else max(0, expires - self.clock())
        display = dict(state["display"], remaining_s=remaining)
        if remaining == 0:
            display.update(mode="home", qr=None, node="")
        return dict(state, display=display)

    def submit(self, payload):
        future = Future()
        try:
            self.inputs.put_nowait((payload, future))
            return future.result(timeout=2)
        except (Full, TimeoutError):
            future.cancel()
            return {"ok": False, "reason": "busy"}
        except Exception:
            return {"ok": False, "reason": "failed"}

    def drain(self, handler):
        for _ in range(32):
            try:
                payload, future = self.inputs.get_nowait()
            except Empty:
                break
            if future.set_running_or_notify_cancel():
                try:
                    future.set_result(handler(payload))
                except Exception as exc:
                    future.set_exception(exc)
