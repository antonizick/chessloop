#!/usr/bin/env python3
"""Create the default admin account if it does not already exist.

Called from deploy.sh immediately after containers start:
    docker compose exec -T backend python seeds/create_admin.py
"""
import sys
import os
# Running from /app/seeds — add /app so project modules are importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import models  # noqa: F401 — registers all SQLModel tables
from models.user import User
from auth.password import hash_password
from database import engine
from sqlmodel import Session, select

EMAIL = "admin@example.com"
USERNAME = "admin"
PASSWORD = "admin"

with Session(engine) as db:
    if db.exec(select(User).where(User.username == USERNAME)).first():
        print(f"Admin account already exists ({USERNAME})")
    else:
        db.add(User(
            email=EMAIL,
            username=USERNAME,
            password_hash=hash_password(PASSWORD),
            role="admin",
        ))
        db.commit()
        print(f"Admin account created: {EMAIL} / {PASSWORD}")
