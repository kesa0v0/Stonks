# create_tables.py
from backend.core.database import engine
from backend.models import Base

def init_db():
    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully! 🎉")

if __name__ == "__main__":
    init_db()