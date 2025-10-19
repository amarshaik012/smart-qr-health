"""
Seed ~100 medicines into the DB.

Usage:
  uvicorn app.main:app --reload  # (ensure DB is up)
  python -m app.scripts.load_medicines

or inside container:
  docker exec -it deploy-api python -m app.scripts.load_medicines
"""
import random
from pathlib import Path
from app.core.db import SessionLocal, Base, engine
from app.models.medicine import Medicine

CATEGORIES = [
    ("Paracetamol", ["500 mg","650 mg"], "tablet"),
    ("Ibuprofen", ["200 mg","400 mg"], "tablet"),
    ("Azithromycin", ["250 mg","500 mg"], "tablet"),
    ("Amoxicillin", ["250 mg","500 mg"], "capsule"),
    ("Pantoprazole", ["40 mg"], "tablet"),
    ("Metformin", ["500 mg","1000 mg"], "tablet"),
    ("Cetrizine", ["10 mg"], "tablet"),
    ("Cough Syrup", ["100 ml","200 ml"], "syrup"),
    ("ORS", ["21 g sachet"], "sachet"),
    ("Calcium", ["500 mg"], "tablet"),
]

def main():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    # If we already have items, skip
    count = db.query(Medicine).count()
    if count >= 50:
        print(f"Inventory already has {count} items. Skipping seed.")
        db.close()
        return

    items = []
    for i in range(100):
        base = random.choice(CATEGORIES)
        name = base[0]
        strength = random.choice(base[1])
        form = base[2]
        mrp = round(random.uniform(8, 280), 2)
        tax = random.choice([0, 5, 12])
        stock = random.randint(0, 400)
        reorder = random.choice([10, 20, 30, 50])

        items.append(Medicine(
            name=name,
            strength=strength,
            form=form,
            mrp=mrp,
            tax_pct=float(tax),
            stock_qty=stock,
            reorder_level=reorder,
        ))

    db.add_all(items)
    db.commit()
    print(f"Seeded {len(items)} medicines.")
    db.close()

if __name__ == "__main__":
    main()