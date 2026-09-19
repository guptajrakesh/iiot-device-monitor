from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..db import get_session
from ..models import DeviceTemplate, TemplateTag
from ..schemas import DeviceTemplateIn, DeviceTemplateOut

router = APIRouter(prefix="/api/templates", tags=["templates"])


@router.get("", response_model=list[DeviceTemplateOut])
def list_templates(session: Session = Depends(get_session)):
    return session.query(DeviceTemplate).all()


@router.post("", response_model=DeviceTemplateOut)
def create_template(payload: DeviceTemplateIn, session: Session = Depends(get_session)):
    template = DeviceTemplate(
        name=payload.name, manufacturer=payload.manufacturer, model=payload.model,
        category=payload.category, protocol=payload.protocol, description=payload.description,
    )
    session.add(template)
    session.flush()
    for tag in payload.tags:
        session.add(TemplateTag(template_id=template.id, **tag.model_dump()))
    session.commit()
    session.refresh(template)
    return template


@router.get("/{template_id}", response_model=DeviceTemplateOut)
def get_template(template_id: str, session: Session = Depends(get_session)):
    template = session.get(DeviceTemplate, template_id)
    if not template:
        raise HTTPException(404, "Template not found")
    return template
