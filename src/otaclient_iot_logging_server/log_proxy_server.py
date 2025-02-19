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

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

import grpc.aio
from aiohttp import web

from otaclient_iot_logging_server._common import LogsQueue
from otaclient_iot_logging_server._sd_notify import (
    READY_MSG,
    sd_notify,
    sd_notify_enabled,
)
from otaclient_iot_logging_server.configs import server_cfg
from otaclient_iot_logging_server.ecu_info import ecu_info
from otaclient_iot_logging_server.servicer import OTAClientIoTLoggingServerServicer
from otaclient_iot_logging_server.v1 import (
    otaclient_iot_logging_server_v1_pb2_grpc as v1_grpc,
)
from otaclient_iot_logging_server.v1.api_stub import OTAClientIoTLoggingServiceV1

logger = logging.getLogger(__name__)


WAIT_BEFORE_SEND_READY_MSG = 2  # seconds

async def _start_http_server(queue: LogsQueue):
    handler = OTAClientIoTLoggingServerServicer(ecu_info=ecu_info, queue=queue)
    app = web.Application()
    app.add_routes([web.post(r"/{ecu_id}", handler.http_put_log)])

    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host=server_cfg.LISTEN_ADDRESS, port=server_cfg.LISTEN_PORT)
    try:
        await site.start()
        logger.info(f"HTTP server started at {server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT}")
    except Exception as e:
        logger.error(f"Failed to start HTTP server: {e}")

async def _start_grpc_server(queue: LogsQueue):
    thread_pool = ThreadPoolExecutor(
        thread_name_prefix="otaclient_iot_logging_server",
    )
    servicer = OTAClientIoTLoggingServerServicer(
        ecu_info=ecu_info,
        queue=queue,
    )
    otaclient_iot_logging_service_v1 = OTAClientIoTLoggingServiceV1(servicer)

    server = grpc.aio.server(migration_thread_pool=thread_pool)
    v1_grpc.add_OTAClientIoTLoggingServiceServicer_to_server(
        server=server, servicer=otaclient_iot_logging_service_v1
    )
    server.add_insecure_port(
        f"{server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT_GRPC}"
    )
    logger.info(
        f"launch grpc server at {server_cfg.LISTEN_ADDRESS}:{server_cfg.LISTEN_PORT_GRPC}"
    )

    await server.start()
    try:
        await server.wait_for_termination()
    finally:
        await server.stop(1)
        thread_pool.shutdown(wait=True)

async def _start_server(queue: LogsQueue):
    await asyncio.gather(
        _start_http_server(queue),
        _start_grpc_server(queue),
    )

def launch_server(queue: LogsQueue) -> None:
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    if sd_notify_enabled():
        logger.info(
            "otaclient-logger service is configured to send ready msg to systemd, "
            f"wait for {WAIT_BEFORE_SEND_READY_MSG} seconds for the server starting up ..."
        )

        loop.call_later(
            WAIT_BEFORE_SEND_READY_MSG,
            sd_notify,
            READY_MSG,
        )

    loop.run_until_complete(_start_server(queue))
