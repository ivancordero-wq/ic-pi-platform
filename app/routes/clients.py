"""
IC-pi Platform: Client Routes
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from uuid import UUID

from app.database import get_db
from app import models

router = APIRouter()


class ClientCreate(BaseModel):
    name: str
    industry: Optional[str] = None
    country: Optional[str] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None


class ClientResponse(BaseModel):
    id: UUID
    name: str
    industry: Optional[str]
    country: Optional[str]
    contact_name: Optional[str]
    contact_email: Optional[str]

    class Config:
        from_attributes = True


@router.post("/", response_model=ClientResponse)
def create_client(data: ClientCreate, db: Session = Depends(get_db)):
    client = models.Client(**data.model_dump())
    db.add(client)
    db.commit()
    db.refresh(client)
    return client


@router.get("/", response_model=list[ClientResponse])
def list_clients(db: Session = Depends(get_db)):
    return db.query(models.Client).all()


@router.get("/{client_id}", response_model=ClientResponse)
def get_client(client_id: UUID, db: Session = Depends(get_db)):
    client = db.query(models.Client).filter(models.Client.id == client_id).first()
    if not client:
        raise HTTPException(404, "Client not found")
    return client
