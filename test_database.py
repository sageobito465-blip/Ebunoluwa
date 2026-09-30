from database import get_connection


connection = get_connection()

print("Database connected successfully!")

connection.close()