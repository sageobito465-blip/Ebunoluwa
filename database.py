import os
import psycopg
from dotenv import load_dotenv

load_dotenv()


# Connect to PostgreSQL
def get_connection():
    connection = psycopg.connect(
        os.getenv("DATABASE_URL")
    )

    return connection