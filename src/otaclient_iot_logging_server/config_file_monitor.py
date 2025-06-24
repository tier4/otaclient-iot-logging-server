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
"""Monitor the used config files.

Monitor the files listed in <monitored_config_files>, kill the server
if any of the files are changed.

This is expected to be used together with systemd.unit Restart policy
to achieve automatically restart on configuration files changed.
"""

from __future__ import annotations

import atexit
import logging
import os
import signal
import threading
import time
from functools import partial

from otaclient_iot_logging_server._utils import cal_file_digest

logger = logging.getLogger(__name__)

_global_shutdown = False


def _python_exit():
    global _global_shutdown
    _global_shutdown = True


atexit.register(_python_exit)

_CHECK_INTERVAL = 3  # second

file_digest_sha256 = partial(cal_file_digest, algorithm="sha256")

monitored_config_files: set[str] = set()
_monitored_files_hash: dict[str, str] = {}


def _config_file_monitor() -> None:
    # initialize, record the original status
    logger.info(f"start to monitor the changes of {monitored_config_files}")
    while not _global_shutdown:
        for entry in monitored_config_files:
            _f_digest = file_digest_sha256(entry)
            _saved_digest = _monitored_files_hash.setdefault(entry, _f_digest)

            if _f_digest != _saved_digest:
                logger.warning(f"detect change on config file {entry}, exit")
                # NOTE: sys.exit is not working in thread
                os.kill(os.getpid(), signal.SIGINT)
        time.sleep(_CHECK_INTERVAL)


def config_file_monitor_thread() -> threading.Thread:
    t = threading.Thread(target=_config_file_monitor, daemon=True)
    t.start()
    return t
