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
import time
from datetime import datetime
from queue import Empty, Queue
from threading import Thread

from typing_extensions import NoReturn

from otaclient_iot_logging_server._common import LogMessage
from otaclient_iot_logging_server._utils import chain_query, retry
from otaclient_iot_logging_server.boto3_session import Boto3Session
from otaclient_iot_logging_server.greengrass_config import IoTSessionConfig

logger = logging.getLogger(__name__)


def get_log_stream_name(thing_name: str, log_stream_sufix: str) -> str:
    """Compose LogStream name.

    Schema: YYYY/MM/DD/<thing_name>
    """
    fmt = "{strftime:%Y/%m/%d}".format(strftime=datetime.utcnow())
    return f"{fmt}/{thing_name}/{log_stream_sufix}"


class AWSIoTLogger:
    """

    Ref: https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/logs.html
    """

    # this upper bound is defined by boto3, check doc for more details.
    MAX_LOGS_PER_PUT = 10_000

    def __init__(
        self,
        session_config: IoTSessionConfig,
        queue: Queue[tuple[str, LogMessage]],
        max_logs_per_merge: int,
        interval: int,
    ):
        _boto3_session = Boto3Session(session_config)
        self._client = _client = _boto3_session.get_session().client(
            service_name="logs"
        )
        self._session_config = session_config
        self._exception = _client.exceptions
        self._sequence_tokens = {}
        self._interval = interval
        self._queue: Queue[tuple[str, LogMessage]] = queue
        self._max_logs_per_merge = max_logs_per_merge
        # unconditionally create log_group and log_stream, do nothing if existed.
        self._create_log_group(log_group_name=session_config.aws_cloudwatch_log_group)

    @retry(max_retry=16, backoff_factor=2, backoff_max=32)
    def _create_log_group(self, log_group_name: str):
        try:
            self._client.create_log_group(logGroupName=log_group_name)
            logger.info(f"{log_group_name=} has been created")
        except self._exception.ResourceAlreadyExistsException as e:
            logger.debug(
                f"{log_group_name=} already existed, skip creating: {e.response}"
            )
        except Exception as e:
            logger.error(f"failed to create {log_group_name=}: {e!r}")
            raise

    @retry(max_retry=16, backoff_factor=2, backoff_max=32)
    def _create_log_stream(self, log_group_name: str, log_stream_name: str):
        try:
            self._client.create_log_stream(
                logGroupName=log_group_name,
                logStreamName=log_stream_name,
            )
            logger.info(f"{log_stream_name=}@{log_group_name} has been created")
            self._sequence_tokens = {}  # clear sequence token on new stream created
        except self._exception.ResourceAlreadyExistsException:
            logger.debug(
                f"{log_stream_name=}@{log_group_name} already existed, skip creating"
            )
        except Exception as e:
            logger.error(f"failed to create {log_stream_name=}@{log_group_name}: {e!r}")
            raise

    @retry(backoff_factor=2)
    def send_messages(self, log_stream_suffix: str, message_list: list[LogMessage]):
        """
        Ref:
        https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/logs/client/put_log_events.html
        """
        session_config, client = self._session_config, self._client
        exceptions = client.exceptions
        log_stream_name = get_log_stream_name(
            session_config.thing_name, log_stream_suffix
        )
        log_group_name = session_config.aws_cloudwatch_log_group

        request = {
            "logGroupName": log_group_name,
            "logStreamName": log_stream_name,
            "logEvents": message_list,
        }
        if _seq_token := self._sequence_tokens.get(log_stream_name):
            request["sequenceToken"] = _seq_token
        # check message_list length
        if len(message_list) > self.MAX_LOGS_PER_PUT:
            logger.warning(
                f"too much logs in a single put, ignore exceeded logs: {self.MAX_LOGS_PER_PUT=}"
            )
            message_list = message_list[: self.MAX_LOGS_PER_PUT]

        try:
            response = client.put_log_events(**request)
            # NOTE: the sequenceToken is deprecated, put_log_events will always
            #       be accepted with/without a sequenceToken.
            #       see docs for more details.
            if _sequence_token := response.get("nextSequenceToken"):
                self._sequence_tokens[log_stream_name] = _sequence_token
        except exceptions.DataAlreadyAcceptedException:
            pass
        except exceptions.InvalidSequenceTokenException as e:
            response = e.response
            logger.debug(f"{response}: {e!r}")

            _resp_err_msg: str = chain_query(e.response, "Error", "Message", default="")
            # null as the next sequenceToken means don't include any
            # sequenceToken at all, not that the token should be set to "null"
            next_expected_token = _resp_err_msg.rsplit(" ", 1)[-1]
            if next_expected_token == "null":
                self._sequence_tokens.pop(log_stream_name, None)
            else:
                self._sequence_tokens[log_stream_name] = next_expected_token
            raise  # let the retry do the logging upload again
        except client.exceptions.ResourceNotFoundException as e:
            response = e.response
            logger.info(f"{log_stream_name=} not found: {e!r}")
            self._create_log_stream(
                log_group_name=log_group_name, log_stream_name=log_stream_name
            )
            raise
        except Exception as e:
            logger.error(
                f"put_log_events failure: {e!r}\n"
                f"log_group_name={session_config.aws_cloudwatch_log_group}, \n"
                f"log_stream_name={log_stream_name}"
            )
            raise

    def thread_main(self) -> NoReturn:
        """Main entry for running this iot_logger in a thread."""
        while True:
            # merge message
            message_dict: dict[str, list[LogMessage]] = {}

            _merge_count = 0
            while _merge_count < self._max_logs_per_merge:
                _queue = self._queue
                try:
                    log_stream_suffix, message = _queue.get_nowait()
                    _merge_count += 1

                    if log_stream_suffix not in message_dict:
                        message_dict[log_stream_suffix] = []
                    message_dict[log_stream_suffix].append(message)
                except Empty:
                    break

            for log_stream_suffix, logs in message_dict.items():
                self.send_messages(log_stream_suffix, logs)

            time.sleep(self._interval)


def start_sending_msg_thread(iot_logger: AWSIoTLogger) -> Thread:
    _thread = Thread(target=iot_logger.thread_main, daemon=True)
    _thread.start()
    logger.debug("iot logger started")
    return _thread
