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

from otaclient_iot_logging_server.ecu_info import parse_ecu_info

TESTS_DIR = Path(__file__).parent / "data"


@pytest.mark.parametrize(
    ["ecu_info_fname", "expected_ecu_id_set"],
    (
        (
            "ecu_info.yaml",
            set(["sub1", "sub2", "sub3", "main"]),
        ),
    ),
)
def test_ecu_info(ecu_info_fname: str, expected_ecu_id_set: set[str]):
    ecu_info_fpath = TESTS_DIR / ecu_info_fname
    assert (ecu_info_cfg := parse_ecu_info(ecu_info_fpath))
    assert ecu_info_cfg.ecu_id_set == expected_ecu_id_set
