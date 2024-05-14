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

import logging
import sys
import time
from os import stat_result
from typing import NamedTuple, NoReturn
from pathlib import Path

logger = logging.getLogger(__name__)

_CHECK_INTERVAL = 3  # second

monitored_config_files: set[str] = set()
_monitored_files_stat: dict[str, _MCTime] = {}


class _MCTime(NamedTuple):
    mtime: int
    ctime: int

    def file_changed(self, new_mctime: _MCTime) -> bool:
        # if create time is newer in <new_mctime>, it means the file is recreated.
        # if modified time is newer in <new_mctime>, it means the file is modified.
        return self.ctime < new_mctime.ctime or self.mtime < new_mctime.mtime

    @classmethod
    def from_stat(cls, stat: stat_result) -> _MCTime:
        return cls(int(stat.st_mtime), int(stat.st_ctime))


def config_file_monitor() -> NoReturn:
    # initialize, record the original status
    logger.info(f"start to monitor the changes of {monitored_config_files}")
    while True:
        for entry in monitored_config_files:
            new_f_mctime = _MCTime.from_stat(Path(entry).stat())
            if entry not in _monitored_files_stat:
                _monitored_files_stat[entry] = new_f_mctime
                continue

            f_mctime = _monitored_files_stat[entry]
            if f_mctime.file_changed(new_f_mctime):
                logger.warning(f"detect change on config file {entry}, exit")
                sys.exit()

        time.sleep(_CHECK_INTERVAL)
