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
from pathlib import Path
import random
from dataclasses import dataclass
from http import HTTPStatus
from queue import Queue
from urllib.parse import urljoin

import aiohttp
import aiohttp.client_exceptions
import pytest
from pytest_mock import MockerFixture
from aiohttp import web

import otaclient_iot_logging_server.log_proxy_server as log_server_module
from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server.log_proxy_server import LoggingPostHandler

logger = logging.getLogger(__name__)

MODULE = log_server_module.__name__
TEST_DIR = Path(__file__).parent / "data"


@dataclass
class _ServerConfig:
    """Minimum set of server_config needed for this test."""

    LISTEN_ADDRESS: str = "127.0.0.1"
    LISTEN_PORT: int = 8083
    ECU_INFO_YAML: Path = TEST_DIR / "ecu_info.yaml"


_test_server_cfg = _ServerConfig()


@dataclass
class MessageEntry:
    ecu_id: str
    message: str


# see data/ecu_info.yaml
mocked_ECUs_list = ("main", "sub1", "sub2", "sub3")


def generate_random_msgs(
    ecus_list: tuple[str, ...] = mocked_ECUs_list,
    msg_len: int = 16,
    msg_num: int = 4096,
) -> list[MessageEntry]:
    _res: list[MessageEntry] = []
    for _ in range(msg_num):
        _ecu, *_ = random.sample(ecus_list, 1)
        _msg = os.urandom(msg_len).hex()
        _res.append(MessageEntry(_ecu, _msg))
    return _res


class TestLogProxyServer:

    SERVER_URL = (
        f"http://{_test_server_cfg.LISTEN_ADDRESS}:{_test_server_cfg.LISTEN_PORT}/"
    )
    TOTAL_MSG_NUM = 4096

    @pytest.fixture(autouse=True)
    async def launch_server(self, mocker: MockerFixture):
        """
        See https://docs.aiohttp.org/en/stable/web_advanced.html#custom-resource-implementation
            for more details.
        """
        mocker.patch(f"{MODULE}.server_cfg", _test_server_cfg)

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
        self._msgs = generate_random_msgs(msg_num=self.TOTAL_MSG_NUM)

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

    @pytest.mark.parametrize(
        "_ecu_id, _data",
        [
            # unknowned ECU's request will be dropped
            ("bad_ecu_id", "valid_msg"),
            # empty message will be dropped
            ("main", ""),
        ],
    )
    async def test_reject_invalid_request(
        self, _ecu_id: str, _data: str, client_sesion: aiohttp.ClientSession
    ):
        with pytest.raises(aiohttp.client_exceptions.ClientResponseError) as exc_info:
            _log_upload_endpoint_url = urljoin(self.SERVER_URL, _ecu_id)
            async with client_sesion.post(_log_upload_endpoint_url, data=_data):
                pass  # raise_for_status is set on session
        assert exc_info.value.status == HTTPStatus.BAD_REQUEST
