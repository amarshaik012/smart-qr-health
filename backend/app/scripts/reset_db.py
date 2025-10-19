from app.core.db import Base, engine
import app.models.dispense, app.models.doctor, app.models.medicine, app.models.otp_log
import app.models.patient, app.models.payment, app.models.prescription, app.models.user

print("⚙️ Dropping and recreating all tables...")
Base.metadata.drop_all(bind=engine)
Base.metadata.create_all(bind=engine)
print("✅ Database schema refreshed successfully.")