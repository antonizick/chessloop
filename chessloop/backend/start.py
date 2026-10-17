"""Container entry point: refuse to run with an unsafe JWT secret, then start the API.

Lives outside main.py so tests and local `uvicorn main:app` runs keep the dev default.
"""
import os
import sys

from config import jwt_secret_problem, settings


def main() -> None:
    problem = jwt_secret_problem(settings.jwt_secret)
    if problem:
        print(
            f"ChessLoop will not start: {problem}\n"
            "Anyone who knows the secret could sign in as any user.\n"
            "Fix: run  openssl rand -base64 32  and put the output in the .env file\n"
            "next to docker-compose.prod.yml as  JWT_SECRET=<output>  then run\n"
            "  docker compose -f docker-compose.prod.yml up -d\n"
            "Everyone is signed out once, because old sessions used the old secret.",
            file=sys.stderr,
            flush=True,
        )
        sys.exit(1)
    os.execvp("uvicorn", ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"])


if __name__ == "__main__":
    main()
