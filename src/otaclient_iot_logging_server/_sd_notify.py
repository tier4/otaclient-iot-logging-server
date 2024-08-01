# Copyright 2022 TIER IV, INC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""A simple implementation of systemd sd_nofity protocol."""


from __future__ import annotations

import logging
import os
import socket

logger = logging.getLogger(__name__)

READY_MSG = "READY=1"
SD_NOTIFY_SOCKET_ENV = "NOTIFY_SOCKET"


def sd_notify_enabled() -> bool:
    return bool(os.getenv(SD_NOTIFY_SOCKET_ENV))


def get_notify_socket() -> str | None:
    """Get the notify socket provided by systemd if set.

    If the provided socket_path is an abstract socket which starts
        with a "@" char, regulate the socket_path by replacing the
        "@" char with NULL char and then return the regulated one.
    """
    socket_path = os.getenv(SD_NOTIFY_SOCKET_ENV)
    if not socket_path:
        return

    # systemd provide abstract socket to us
    if socket_path.startswith("@"):
        socket_path = "\0" + socket_path[1:]
    return socket_path


def sd_notify(msg: str) -> bool | None:
    if not (notify_socket := get_notify_socket()):
        return

    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as socket_conn:
        try:
            socket_conn.connect(notify_socket)
        except Exception as e:
            logger.warning(f"failed to connect to {notify_socket=}: {e!r}")
            return False

        try:
            socket_conn.sendall(msg.encode())
            logger.info(f"sent ready message to {notify_socket=}")
            return True
        except Exception as e:
            logger.warning(f"failed to send ready message to {notify_socket=}: {e!r}")
            return False
