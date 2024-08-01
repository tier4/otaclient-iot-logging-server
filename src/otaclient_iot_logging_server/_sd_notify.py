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

import asyncio
import logging
import os

logger = logging.getLogger(__name__)

READY_MSG = "READY=1"
SD_NOTIFY_SOCKET_ENV = "NOTIFY_SOCKET"


def get_notify_socket() -> str | None:
    return os.getenv(SD_NOTIFY_SOCKET_ENV)


async def send_msg() -> bool | None:
    if not (notify_socket := get_notify_socket()):
        return
    logger.info("otaclient-logger service is configured to send ready msg to systemd")

    try:
        _, writer = await asyncio.open_unix_connection(notify_socket)
    except Exception as e:
        logger.warning(f"failed to connect to {notify_socket=}: {e!r}")
        return False

    try:
        writer.write(READY_MSG.encode())
        await writer.drain()
        logger.info("sent ready message to systemd")
        return True
    except Exception as e:
        logger.warning(f"failed to send ready message to notify socket: {e!r}")
        return False
    finally:
        writer.close()
        await writer.wait_closed()
