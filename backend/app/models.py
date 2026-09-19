import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()


def gen_id() -> str:
    return str(uuid.uuid4())


class Organization(Base):
    __tablename__ = "organizations"
    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)


class Site(Base):
    __tablename__ = "sites"
    id = Column(String, primary_key=True, default=gen_id)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    name = Column(String, nullable=False)


class Gateway(Base):
    __tablename__ = "gateways"
    id = Column(String, primary_key=True, default=gen_id)
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    name = Column(String, nullable=False)


class DeviceTemplate(Base):
    """A reusable device *type*: protocol + full tag/register map, defined once."""

    __tablename__ = "device_templates"
    id = Column(String, primary_key=True, default=gen_id)
    name = Column(String, nullable=False)
    manufacturer = Column(String, nullable=True)
    model = Column(String, nullable=True)
    category = Column(String, nullable=True)
    protocol = Column(String, nullable=False)  # "modbus" | "opcua"
    description = Column(Text, nullable=True)
    tags = relationship("TemplateTag", backref="template", cascade="all, delete-orphan")


class TemplateTag(Base):
    __tablename__ = "template_tags"
    id = Column(String, primary_key=True, default=gen_id)
    template_id = Column(String, ForeignKey("device_templates.id"), nullable=False)
    tag_key = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    data_type = Column(String, default="float")
    unit = Column(String, nullable=True)
    scale = Column(Float, default=1.0)
    protocol_config = Column(JSON, nullable=False)


class DeviceInstance(Base):
    """One physical device on site, optionally created from a DeviceTemplate."""

    __tablename__ = "device_instances"
    id = Column(String, primary_key=True, default=gen_id)
    org_id = Column(String, ForeignKey("organizations.id"), nullable=False)
    site_id = Column(String, ForeignKey("sites.id"), nullable=False)
    gateway_id = Column(String, ForeignKey("gateways.id"), nullable=False)
    template_id = Column(String, ForeignKey("device_templates.id"), nullable=True)
    name = Column(String, nullable=False)
    protocol = Column(String, nullable=False)
    connection_config = Column(JSON, nullable=False)
    poll_interval_seconds = Column(Float, default=1.0)
    status = Column(String, default="active")  # active | disabled | error
    tags = relationship("DeviceInstanceTag", backref="device", cascade="all, delete-orphan")


class DeviceInstanceTag(Base):
    __tablename__ = "device_instance_tags"
    id = Column(String, primary_key=True, default=gen_id)
    device_instance_id = Column(String, ForeignKey("device_instances.id"), nullable=False)
    tag_key = Column(String, nullable=False)
    display_name = Column(String, nullable=False)
    data_type = Column(String, default="float")
    unit = Column(String, nullable=True)
    scale = Column(Float, default=1.0)
    protocol_config = Column(JSON, nullable=False)
    enabled = Column(Boolean, default=True)


class Reading(Base):
    __tablename__ = "readings"
    time = Column(DateTime(timezone=True), primary_key=True)
    device_instance_id = Column(String, primary_key=True)
    tag_key = Column(String, primary_key=True)
    value = Column(Float, nullable=True)
    quality = Column(String, default="good")


class AlertRule(Base):
    """A threshold on one device's tag: fire when value <condition> threshold."""

    __tablename__ = "alert_rules"
    id = Column(String, primary_key=True, default=gen_id)
    device_instance_id = Column(String, ForeignKey("device_instances.id"), nullable=False)
    tag_key = Column(String, nullable=False)
    condition = Column(String, nullable=False)  # gt | gte | lt | lte
    threshold = Column(Float, nullable=False)
    severity = Column(String, default="warning")  # warning | critical
    enabled = Column(Boolean, default=True)


class AlertEvent(Base):
    """One breach lifecycle: created when a rule transitions to breached,
    marked resolved when it transitions back - not one row per reading."""

    __tablename__ = "alert_events"
    id = Column(String, primary_key=True, default=gen_id)
    rule_id = Column(String, ForeignKey("alert_rules.id"), nullable=True)
    device_instance_id = Column(String, nullable=False)
    tag_key = Column(String, nullable=False)
    condition = Column(String, nullable=False)
    threshold = Column(Float, nullable=False)
    value = Column(Float, nullable=False)
    severity = Column(String, default="warning")
    status = Column(String, default="active")  # active | resolved
    acknowledged = Column(Boolean, default=False)
    triggered_at = Column(DateTime(timezone=True), nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
