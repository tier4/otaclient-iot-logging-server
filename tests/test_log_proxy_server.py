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


from __future__ import annotations

import logging
import os
import random
from dataclasses import dataclass
from queue import Queue
from typing import NamedTuple
from urllib.parse import urljoin

import aiohttp
import pytest
from aiohttp import web

import otaclient_iot_logging_server.log_proxy_server as log_server_module
from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server.log_proxy_server import LoggingPostHandler

logger = logging.getLogger(__name__)

MODULE = log_server_module.__name__


@dataclass
class _ServerConfig:
    """Minimum set of server_config needed for this test."""

    LISTEN_ADDRESS: str = "127.0.0.1"
    LISTEN_PORT: int = 8083


_test_server_cfg = _ServerConfig()


class MessageEntry(NamedTuple):
    ecu_id: str
    message: str


class TestLogProxyServer:

    SERVER_URL = (
        f"http://{_test_server_cfg.LISTEN_ADDRESS}:{_test_server_cfg.LISTEN_PORT}/"
    )
    ECUS = ("main_ecu", "sub_ecu0", "sub_ecu1", "sub_ecu2")
    MSG_LEN = 16
    TOTAL_MSG_NUM = 4096

    @classmethod
    def _generate_random_msg(cls) -> MessageEntry:
        _ecu, *_ = random.sample(cls.ECUS, 1)
        _msg = os.urandom(cls.MSG_LEN).hex()
        return MessageEntry(_ecu, _msg)

    @pytest.fixture(autouse=True)
    async def launch_server(self):
        """
        See https://docs.aiohttp.org/en/stable/web_advanced.html#custom-resource-implementation
            for more details.
        """
        queue: LogsQueue = Queue()
        self._queue = queue

        handler = LoggingPostHandler(queue)
        app = web.Application()
        # mute the aiohttp server logging
        aiohttp_server_logger = logging.getLogger("aiohttp")
        aiohttp_server_logger.setLevel("ERROR")

        # add handler to the server
        app.add_routes([web.post(r"/{ecu_id}", handler.logging_post_handler)])

        # star the server
        runner = web.AppRunner(app)
        try:
            await runner.setup()
            site = web.TCPSite(
                runner, _test_server_cfg.LISTEN_ADDRESS, _test_server_cfg.LISTEN_PORT
            )
            await site.start()
            logger.info(f"test log_proxy_server started at {self.SERVER_URL}")
            yield
        finally:
            await runner.cleanup()

    @pytest.fixture(autouse=True)
    async def client_sesion(self):
        client_session = aiohttp.ClientSession(
            raise_for_status=True,
            timeout=aiohttp.ClientTimeout(total=0.2),  # for speedup testing
        )
        try:
            yield client_session
        finally:
            await client_session.close()

    @pytest.fixture(autouse=True)
    def prepare_test_data(self):
        self._msgs: list[MessageEntry] = []
        for _ in range(self.TOTAL_MSG_NUM):
            self._msgs.append(self._generate_random_msg())

    async def test_server(self, client_sesion: aiohttp.ClientSession):
        # ------ execution ------ #
        logger.info(f"sending {self.TOTAL_MSG_NUM} msgs to {self.SERVER_URL}...")
        for item in self._msgs:
            _ecu_id, _msg = item.ecu_id, item.message
            _log_upload_endpoint_url = urljoin(self.SERVER_URL, _ecu_id)
            async with client_sesion.post(_log_upload_endpoint_url, data=_msg):
                pass  # raise_for_status is set on session

        # ------ check result ------ #
        # ensure the all msgs are sent in order to the queue by the server.
        logger.info("checking all the received messages...")
        for item in self._msgs:
            _ecu_id, _log_msg = self._queue.get_nowait()
            assert _ecu_id == item.ecu_id
            assert _log_msg["message"] == item.message
        assert self._queue.empty()
