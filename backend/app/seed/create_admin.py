"""Create or promote a production admin account from environment variables.

Never hard-code production admin credentials. Set ADMIN_EMAIL and ADMIN_PASSWORD
in .env (or the environment) and run:

    PYTHONPATH=backend:. .venv/bin/python -m app.seed.create_admin

- If no user with ADMIN_EMAIL exists, one is created with role=ADMIN and added
  to the first workspace (or a new one, if none exists) as OWNER.
- If a user with that email already exists, they are promoted to role=ADMIN
  (their password is left untouched unless --reset-password is passed).

This is separate from `app.seed.run`, which seeds a fixed-password demo admin
(admin@ipsakti.demo) for local/demo use only — never point that at production.
"""
import argparse
import sys

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password, password_problems
from app.db import SessionLocal
from app.models.orm import Organization, User, UserRole, Workspace, WorkspaceMember, WorkspaceRole


def main(argv=None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset-password", action="store_true", help="Also (re)set the password if the account already exists")
    args = ap.parse_args(argv)

    email = settings.ADMIN_EMAIL.strip().lower()
    password = settings.ADMIN_PASSWORD
    if not email or not password:
        print("Set ADMIN_EMAIL and ADMIN_PASSWORD in .env before running this script.", file=sys.stderr)
        return 1
    problems = password_problems(password)
    if problems:
        print("ADMIN_PASSWORD is too weak: needs " + ", ".join(problems) + ".", file=sys.stderr)
        return 1

    db = SessionLocal()
    try:
        user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
        if user:
            user.role = UserRole.ADMIN
            user.is_active = True
            if args.reset_password:
                user.password_hash = hash_password(password)
            db.commit()
            print(f"Promoted existing account {email} to ADMIN" + (" and reset its password." if args.reset_password else "."))
            return 0

        user = User(name="Administrator", email=email, password_hash=hash_password(password), role=UserRole.ADMIN)
        db.add(user)
        db.flush()
        ws = db.execute(select(Workspace)).scalars().first()
        if not ws:
            org = Organization(name="Administration")
            db.add(org)
            db.flush()
            ws = Workspace(organization_id=org.id, name="Admin Workspace")
            db.add(ws)
            db.flush()
        db.add(WorkspaceMember(workspace_id=ws.id, user_id=user.id, role=WorkspaceRole.OWNER))
        db.commit()
        print(f"Created ADMIN account {email} (workspace: {ws.name}).")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
