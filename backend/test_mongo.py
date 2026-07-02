import asyncio
from app.core.database import client, db

async def test_conn():
    try:
        # Ping the database
        await db.command("ping")
        print("SUCCESS! Successfully connected to MongoDB.")
    except Exception as e:
        print(f"FAILED: Could not connect to MongoDB. Error: {e}")
    finally:
        client.close()

if __name__ == "__main__":
    asyncio.run(test_conn())
