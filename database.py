"""Database setup entry point. Keeps the original setup command working."""
from services.database_service import init_database

if __name__ == "__main__":
    init_database()
