"""Initialize the database tables. Useful for first-run / CI."""
from app.db.session import Base, engine
import app.models  # noqa: F401  — registers model classes


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    print("Database tables created.")


if __name__ == "__main__":
    init_db()
