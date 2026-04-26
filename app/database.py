import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/protectora")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


RAZAS_DEFAULT = [
    "Mestizo", "Labrador Retriever", "Pastor Alemán", "Golden Retriever",
    "Bulldog Francés", "Bulldog Inglés", "Yorkshire Terrier", "Chihuahua",
    "Boxer", "Teckel / Dachshund", "Caniche / Poodle", "Beagle",
    "Cocker Spaniel", "Husky Siberiano", "Border Collie", "Rottweiler",
    "Pitbull", "American Staffordshire", "Galgo Español", "Podenco",
    "Dogo Argentino", "Schnauzer", "Bichón Maltés", "Shih Tzu",
    "Pug / Carlino", "Setter Irlandés", "Dobermann", "Gran Danés",
    "Dálmata", "Shar Pei", "Chow Chow", "Akita Inu", "Samoyedo",
    "Otro",
]


def init_db():
    from app import models
    from app.models import Raza
    Base.metadata.create_all(bind=engine)
    with engine.connect() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS analytics"))
        conn.commit()
    # Poblar razas si la tabla está vacía
    with SessionLocal() as session:
        if session.query(Raza).count() == 0:
            session.add_all([Raza(nombre=r) for r in RAZAS_DEFAULT])
            session.commit()
