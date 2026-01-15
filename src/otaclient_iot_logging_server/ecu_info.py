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
"""ECU metadatas definition and parsing logic.

Basically the one copied from otaclient, with only parsing fields we care about.
"""

from __future__ import annotations

import logging
from functools import cached_property
from pathlib import Path
from typing import List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, IPvAnyAddress

logger = logging.getLogger(__name__)


class BaseFixedConfig(BaseModel):
    model_config = ConfigDict(frozen=True)


class ECUContact(BaseFixedConfig):
    ecu_id: str
    ip_addr: IPvAnyAddress
    port: int = 50051


class ECUInfo(BaseFixedConfig):
    """ECU info configuration.

    We only need to parse ecu_id and secondaries fields.
    """

    format_version: int = 1
    ecu_id: str
    secondaries: List[ECUContact] = Field(default_factory=list)

    @cached_property
    def ecu_id_set(self) -> set[str]:
        res = [ecu_contact.ecu_id for ecu_contact in self.secondaries]
        res.append(self.ecu_id)
        return set(res)


def parse_ecu_info(ecu_info_file: Path | str) -> Optional[ECUInfo]:
    try:
        _raw_yaml_str = Path(ecu_info_file).read_text()
        loaded_ecu_info = yaml.safe_load(_raw_yaml_str)
        assert isinstance(loaded_ecu_info, dict), "not a valid yaml file"
        return ECUInfo.model_validate(loaded_ecu_info, strict=True)
    except Exception as e:
        logger.info(f"{ecu_info_file=} is invalid or missing: {e!r}")


# NOTE(20241113): since ecu_info.yaml file will still be modified regularly,
#   temporary disable the logging filter with ecu_info.yaml.
# ecu_info = parse_ecu_info(server_cfg.ECU_INFO_YAML)
# if ecu_info:
#     monitored_config_files.add(server_cfg.ECU_INFO_YAML)
logger.warning("disable logging filtering for now")
ecu_info = None
