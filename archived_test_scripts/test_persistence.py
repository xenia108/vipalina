#!/usr/bin/env python3
"""
Test script for VipalinaPersistence functionality
"""

import asyncio
import logging
from vipalina_persistence import get_persistence

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

async def test_persistence():
    """Test the VipalinaPersistence functionality"""
    try:
        logger.info("Testing VipalinaPersistence...")
        
        # Get the persistence instance
        persistence = get_persistence()
        if not persistence or not persistence.is_initialized():
            logger.error("Failed to initialize persistence")
            return
            
        logger.info("✅ VipalinaPersistence initialized successfully")
        
        # Test saving a chat-to-student mapping
        logger.info("Testing chat-to-student mapping...")
        result = persistence.save_chat_to_student_mapping(
            chat_id=123456789,
            getcourse_id="test_student_001",
            student_name="Test Student",
            invite_link="https://t.me/test_invite_link"
        )
        logger.info(f"Save chat-to-student result: {result}")
        
        # Test saving student data
        logger.info("Testing student data saving...")
        student_data = {
            'name': 'Test Student',
            'email': 'test@example.com',
            'phone': '+1234567890',
            'course': 'python-ai-2.0',
            'telegram_username': '@testuser',
            'telegram_id': 123456789,
            'getcourse_url': 'https://getcourse.ru/test_student_001',
            'is_test_student': True
        }
        result = persistence.save_student_data("test_student_001", student_data)
        logger.info(f"Save student data result: {result}")
        
        # Test saving manager assignment
        logger.info("Testing manager assignment saving...")
        assignment_data = {
            'manager_id': 987654321,
            'manager_name': 'Test Manager',
            'course_tag': 'python-ai-2.0',
            'status': 'assigned',
            'student_name': 'Test Student',
            'student_telegram': '@testuser',
            'student_telegram_id': 123456789
        }
        result = persistence.save_manager_assignment("test_student_001", assignment_data)
        logger.info(f"Save manager assignment result: {result}")
        
        # Test loading data back
        logger.info("Testing data loading...")
        chat_to_student = persistence.load_all_chat_to_student()
        logger.info(f"Loaded {len(chat_to_student)} chat-to-student mappings")
        
        students_data = persistence.load_all_students_data()
        logger.info(f"Loaded {len(students_data)} students")
        
        manager_assignments = persistence.load_all_manager_assignments()
        logger.info(f"Loaded {len(manager_assignments)} manager assignments")
        
        logger.info("✅ VipalinaPersistence test completed successfully")
        
    except Exception as e:
        logger.error(f"Error during test: {e}", exc_info=True)

if __name__ == "__main__":
    asyncio.run(test_persistence())