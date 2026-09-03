"""
Prior Initiatives model
=======================
Stores the client's improvement history for each KPI before AI
prescriptions are generated. Imported by app.main so SQLAlchemy
registers the table with Base.metadata.
"""

import uuid
from datetime import datetime
from sqlalchemy import Column, DateTime, ForeignKey, Text, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.database import Base


class PriorInitiative(Base):
    __tablename__ = "prior_initiatives"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    discovery_id = Column(UUID(as_uuid=True), nullable=True)
    kpi_id = Column(UUID(as_uuid=True), ForeignKey("kpis.id"), nullable=False)
    sme_id = Column(UUID(as_uuid=True), ForeignKey("smes.id"), nullable=True)
    outcome_type = Column(String(20), nullable=True)
    description = Column(Text, nullable=False)
    outcome = Column(Text, nullable=True)
    tried_when = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    kpi = relationship("KPI")
    sme = relationship("SME")
