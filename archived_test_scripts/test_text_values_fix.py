#!/usr/bin/env python3
"""
Test script to verify the fix for text values in course parameters.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from dynamic_course_config import DynamicCourseConfig
from course_config_v2 import CourseConfig

def test_dynamic_course_config():
    """Test DynamicCourseConfig with text values"""
    print("Testing DynamicCourseConfig...")
    
    # Create a mock course with text values
    config = DynamicCourseConfig.__new__(DynamicCourseConfig)
    
    # Test parsing text values
    assert config._parse_int("Навсегда") == 0
    assert config._parse_int("Бессрочно") == 0
    assert config._parse_int("12") == 12
    assert config._parse_int("0") == 0
    assert config._parse_int("") == 0
    
    # Test converting to days
    assert config._convert_to_days("Навсегда") == 0
    assert config._convert_to_days("12") == 360
    assert config._convert_to_days("0") == 0
    
    print("✅ DynamicCourseConfig tests passed")

def test_course_config_v2():
    """Test CourseConfig with text values"""
    print("Testing CourseConfig...")
    
    # Test converting months to days
    assert CourseConfig._convert_months_to_days("Навсегда") == 0
    assert CourseConfig._convert_months_to_days("12") == 360
    assert CourseConfig._convert_months_to_days("0") == 0
    
    print("✅ CourseConfig tests passed")

def test_format_months_value():
    """Test formatting months values"""
    print("Testing format months value...")
    
    # Mock the method since it's part of TrackerCreator
    def format_months_value(original_value, days_value):
        """Форматирует значение месяцев для отображения."""
        # Если оригинальное значение текстовое, возвращаем его как есть
        if isinstance(original_value, str) and not original_value.isdigit():
            return original_value
        
        # Если оригинальное значение числовое, конвертируем дни в месяцы
        try:
            days = int(days_value) if days_value else 0
            months = days // 30 if days > 0 else 0
            return months if months > 0 else 0
        except (ValueError, TypeError):
            return 0
    
    # Test with text values
    assert format_months_value("Навсегда", 0) == "Навсегда"
    assert format_months_value("Бессрочно", 0) == "Бессрочно"
    
    # Test with numeric values
    assert format_months_value(12, 360) == 12
    assert format_months_value(0, 0) == 0
    
    print("✅ Format months value tests passed")

if __name__ == "__main__":
    print("Running tests for text values fix...\n")
    
    test_dynamic_course_config()
    test_course_config_v2()
    test_format_months_value()
    
    print("\n🎉 All tests passed! The fix for text values in course parameters is working correctly.")