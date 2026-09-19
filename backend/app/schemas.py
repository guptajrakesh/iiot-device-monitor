from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel


class TemplateTagIn(BaseModel):
    tag_key: str
    display_name: str
    data_type: str = "float"
    unit: Optional[str] = None
    scale: float = 1.0
    protocol_config: dict


class TemplateTagOut(TemplateTagIn):
    id: str
    model_config = {"from_attributes": True}


class DeviceTemplateIn(BaseModel):
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    protocol: str
    description: Optional[str] = None
    tags: list[TemplateTagIn] = []


class DeviceTemplateOut(BaseModel):
    id: str
    name: str
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    category: Optional[str] = None
    protocol: str
    description: Optional[str] = None
    tags: list[TemplateTagOut] = []
    model_config = {"from_attributes": True}


class DeviceInstanceIn(BaseModel):
    org_id: str
    site_id: str
    gateway_id: str
    template_id: Optional[str] = None
    name: str
    protocol: str
    connection_config: dict
    poll_interval_seconds: float = 1.0
    tag_overrides: list[TemplateTagIn] = []


class DeviceInstanceOut(BaseModel):
    id: str
    name: str
    protocol: str
    connection_config: dict
    status: str
    template_id: Optional[str] = None
    model_config = {"from_attributes": True}


class DeviceInstanceTagOut(TemplateTagIn):
    id: str
    enabled: bool = True
    model_config = {"from_attributes": True}


class DeviceInstanceDetailOut(DeviceInstanceOut):
    org_id: str
    site_id: str
    gateway_id: str
    poll_interval_seconds: float
    tags: list[DeviceInstanceTagOut] = []


class TestConnectionRequest(BaseModel):
    gateway_id: str
    protocol: str
    connection_config: dict
    tags: list[TemplateTagIn]


class AlertRuleIn(BaseModel):
    device_instance_id: str
    tag_key: str
    condition: Literal["gt", "gte", "lt", "lte"]
    threshold: float
    severity: Literal["warning", "critical"] = "warning"
    enabled: bool = True


class AlertRuleOut(AlertRuleIn):
    id: str
    model_config = {"from_attributes": True}


class AlertEventOut(BaseModel):
    id: str
    rule_id: Optional[str] = None
    device_instance_id: str
    tag_key: str
    condition: str
    threshold: float
    value: float
    severity: str
    status: str
    acknowledged: bool
    triggered_at: datetime
    resolved_at: Optional[datetime] = None
    model_config = {"from_attributes": True}
