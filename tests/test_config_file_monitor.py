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

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from otaclient_iot_logging_server import config_file_monitor


class _SuccessExit(Exception):
    """config file monitor successfully kills the server."""


class TestConfigFileMonitor:
    @pytest.fixture(autouse=True)
    def setup_set(self, tmp_path: Path, mocker: MockerFixture):
        self.config_file = config_file = tmp_path / "config_file"
        config_file.write_text("config_file")
        config_file_monitor.monitored_config_files.add(str(config_file))

        # hack time.sleep to modify the config_file
        def _modify_config_file(*args, **kwargs):
            config_file.write_text("another config_file")

        mocker.patch.object(
            config_file_monitor.time,
            "sleep",
            mocker.MagicMock(wraps=_modify_config_file),
        )

        # mock os.kill to raise SuccessExit exception
        mocker.patch("os.kill", mocker.MagicMock(side_effect=_SuccessExit))

    def test_config_file_monitor(self):
        with pytest.raises(_SuccessExit):
            config_file_monitor._config_file_monitor()
