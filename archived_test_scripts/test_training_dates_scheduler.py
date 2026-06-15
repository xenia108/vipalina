#!/usr/bin/env python3
"""
Test script for TrainingDatesScheduler
"""

import asyncio
import logging
from datetime import datetime, timedelta
import pytz
from training_dates_scheduler import TrainingDatesScheduler
from vipalina_sheets import VipalinaSheetIntegration

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_scheduler():
    """Test the TrainingDatesScheduler functionality"""
    try:
        logger.info("Testing TrainingDatesScheduler...")
        
        # Initialize the sheets integration
        sheets_integration = VipalinaSheetIntegration()
        logger.info("✅ VipalinaSheetIntegration initialized")
        
        # Initialize the scheduler
        scheduler = TrainingDatesScheduler(sheets_integration)
        logger.info("✅ TrainingDatesScheduler initialized")
        
        # Test getting students with trackers
        logger.info("Getting students with trackers...")
        students = await sheets_integration.get_all_students_with_trackers()
        logger.info(f"Found {len(students)} students with trackers")
        
        # Test the _should_update_dates method
        moscow_tz = pytz.timezone('Europe/Moscow')
        now = datetime.now(moscow_tz)
        
        # Test with a date from 2 hours ago (should trigger hour update)
        two_hours_ago = now - timedelta(hours=2)
        should_update = await scheduler._should_update_dates("test_student_001", two_hours_ago, now)
        logger.info(f"Should update (2 hours ago): {should_update}")
        
        # Test with a date from 2 days ago (should trigger day update)
        two_days_ago = now - timedelta(days=2)
        should_update = await scheduler._should_update_dates("test_student_002", two_days_ago, now)
        logger.info(f"Should update (2 days ago): {should_update}")
        
        # Test with a date from 2 months ago (should trigger month update)
        two_months_ago = now - timedelta(days=60)
        should_update = await scheduler._should_update_dates("test_student_003", two_months_ago, now)
        logger.info(f"Should update (2 months ago): {should_update}")
        
        logger.info("✅ TrainingDatesScheduler test completed successfully")
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_scheduler())