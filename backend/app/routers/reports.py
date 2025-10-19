# backend/app/routers/reports.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timedelta, date

from ..core.db import get_db
from ..models.dispense import Dispense
from ..models.medicine import Medicine

router = APIRouter(prefix="/reports", tags=["Reports"])

@router.get("/summary")
def summary(range: str = "daily", db: Session = Depends(get_db)):
    if range == "monthly":
        since = datetime.utcnow() - timedelta(days=30)
    else:
        since = datetime.combine(date.today(), datetime.min.time())

    totals = db.query(
        func.coalesce(func.sum(Dispense.total_amount), 0.0),
        func.coalesce(func.sum(Dispense.qty), 0),
    ).filter(Dispense.created_at >= since).one()

    top = (
        db.query(Medicine.name, func.sum(Dispense.qty).label("q"))
        .join(Medicine, Medicine.id == Dispense.medicine_id)
        .filter(Dispense.created_at >= since)
        .group_by(Medicine.name)
        .order_by(func.sum(Dispense.qty).desc())
        .limit(10)
        .all()
    )
    return {
        "since": since.isoformat(),
        "sales_total": float(totals[0] or 0.0),
        "units_total": int(totals[1] or 0),
        "top_medicines": [{"name": r[0], "qty": int(r[1] or 0)} for r in top],
    }