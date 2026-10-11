import socket

import pytest


def test_outside_host_raises_runtime_error() -> None:
    blocked = False
    try:
        with socket.socket() as sock:
            sock.settimeout(1)
            sock.connect(("1.1.1.1", 80))
    except* RuntimeError:
        # except* also matches a bare RuntimeError, so no manual unwrapping.
        blocked = True
    if not blocked:
        pytest.fail("connection to 1.1.1.1 was not blocked")
