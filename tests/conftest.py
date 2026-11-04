import os
import sys
import tempfile

# Set env SEBELUM aplikasi di-import, supaya tes memakai database sementara
_tmp = tempfile.mkdtemp()
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["CRON_INTERVAL_DETIK"] = "0"
os.environ["DOMISILI_PASAR"] = "Kota Contoh"
os.environ["TIMEOUT_DETIK"] = str(3 * 86400)
os.environ["PREEMPTION_DETIK"] = str(14 * 86400)
os.environ["PERINGATAN_DETIK"] = str(7 * 86400)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest
from fastapi.testclient import TestClient

from database.config import Base, SessionLocal, engine


@pytest.fixture()
def client():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    from main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def db():
    s = SessionLocal()
    yield s
    s.close()


@pytest.fixture()
def admin_headers(client, db):
    from database.models import Admin
    from routers.auth import buat_token
    from seed import hash_password

    db.add(Admin(username="pengelola-uji", password_hash=hash_password("password-uji")))
    db.commit()
    return {"Authorization": f"Bearer {buat_token({'sub': 'pengelola-uji'})}"}
