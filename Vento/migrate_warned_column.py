"""
Migration script to change 'warned' column from boolean to integer
This fixes the datatype mismatch issue in PostgreSQL
"""
import asyncio
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def migrate_warned_column():
    """Migrate warned column from boolean to integer"""
    try:
        from database import get_db_connection
        
        logger.info("Starting migration: warned column boolean -> integer")
        
        async with get_db_connection() as db:
            # Check current column type
            logger.info("Checking current column type...")
            async with db.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'warned'") as cursor:
                result = await cursor.fetchone()
                if result:
                    logger.info(f"Current 'warned' column type: {result[0]}")
                else:
                    logger.warning("Could not determine current column type")
            
            # Alter column type from boolean to integer
            logger.info("Altering column type from boolean to integer...")
            await db.execute("ALTER TABLE users ALTER COLUMN warned TYPE INTEGER USING CASE WHEN warned THEN 1 ELSE 0 END")
            await db.commit()
            
            logger.info("Migration completed successfully!")
            
            # Verify the change
            async with db.execute("SELECT data_type FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'warned'") as cursor:
                result = await cursor.fetchone()
                if result:
                    logger.info(f"New 'warned' column type: {result[0]}")
                    
            return True
            
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return False

if __name__ == "__main__":
    asyncio.run(migrate_warned_column())