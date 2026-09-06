from .database import SessionLocal
from .seeds import seed

with SessionLocal.begin() as session:
    seed(session)
