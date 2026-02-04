# test_db.py
from database import engine

try:
    connection = engine.connect()
    print("Database connected successfully!")
    connection.close()
except Exception as e:
    print("Failed to connect to the database.")
    print(e)
