"""
Dynamic course configuration that fetches data directly from Google Sheets template.
This ensures the system always uses the latest course data.
"""

import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
from google.oauth2.credentials import Credentials
import logging
import re
import os
from typing import Dict, Any, Optional, List
import asyncio
from auth_error_notifier import notify_oauth_error

logger = logging.getLogger('vipalina_telethon')

class DynamicCourseConfig:
    """
    Dynamic course configuration that fetches data from Google Sheets template.
    """
    
    TEMPLATE_ID = '1gH1Sd7BCeUFBqufXUy63nVjWPcNmGNq312iL8-_Y_rQ'
    
    def __init__(self, credentials_path: str = 'vipalina_google_service_account.json'):
        self.credentials_path = credentials_path
        self.sheets_client = None
        self._authorize()
        self._course_cache = {}
        self._load_courses()
    
    def _authorize(self):
        """Authorize with Google Sheets API using either OAuth token or service account"""
        try:
            scope = [
                'https://www.googleapis.com/auth/drive',
                'https://www.googleapis.com/auth/spreadsheets'
            ]
            
            # Try to use OAuth token first
            token_path = 'token_vipzerocoder.json'
            if os.path.exists(token_path):
                try:
                    creds = Credentials.from_authorized_user_file(token_path, scope)
                    self.sheets_client = gspread.authorize(creds)
                    logger.info("✅ Google Sheets authorization successful (OAuth)")
                    return
                except Exception as e:
                    error_msg = str(e)
                    logger.warning(f"⚠️ OAuth authorization failed: {error_msg}")
                    # Отправляем уведомление руководителю VIP-отдела
                    try:
                        loop = asyncio.get_running_loop()
                        loop.create_task(notify_oauth_error(error_msg))
                    except RuntimeError:
                        asyncio.run(notify_oauth_error(error_msg))
                    except Exception as notification_error:
                        logger.error(f"❌ Ошибка при отправке уведомления: {notification_error}")
            
            # Fallback to service account
            if os.path.exists(self.credentials_path):
                creds = ServiceAccountCredentials.from_service_account_file(
                    self.credentials_path, scopes=scope
                )
                self.sheets_client = gspread.authorize(creds)
                logger.info("✅ Google Sheets authorization successful (Service Account)")
            else:
                raise FileNotFoundError(f"Credentials file not found: {self.credentials_path}")
                
        except Exception as e:
            logger.error(f"❌ Google Sheets authorization failed: {e}")
            # Отправляем уведомление руководителю VIP-отдела
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(notify_oauth_error(str(e)))
            except RuntimeError:
                asyncio.run(notify_oauth_error(str(e)))
            except Exception as notification_error:
                logger.error(f"❌ Ошибка при отправке уведомления: {notification_error}")
            raise
    
    def _load_courses(self):
        """Load courses from the template sheet"""
        try:
            template = self.sheets_client.open_by_key(self.TEMPLATE_ID)
            conditions_sheet = template.worksheet('Условия курсов')
            
            # Get all data from the sheet
            all_data = conditions_sheet.get_all_values()
            
            if len(all_data) < 2:
                logger.warning("⚠️ No course data found in template")
                return
            
            # Headers are in the first row
            headers = all_data[0]
            
            # Process each course row
            for i, row in enumerate(all_data[1:], start=2):  # Start from row 2 (1-indexed)
                if len(row) == 0 or not row[0].strip():  # Skip empty rows
                    continue
                
                # Create course data dictionary
                course_data = {}
                for j, header in enumerate(headers):
                    if j < len(row):
                        course_data[header] = row[j]
                    else:
                        course_data[header] = ""
                
                course_tag = course_data.get('A', '')  # Column A - Course tag
                if course_tag:
                    # Normalize the course tag for comparison
                    normalized_tag = self._normalize_tag(course_tag)
                    self._course_cache[normalized_tag] = {
                        'original_tag': course_tag,
                        'internal_name': course_data.get('B', course_tag),  # Column B - Internal name
                        'tracker_name': course_data.get('B', course_tag),
                        'kpi_name': course_data.get('B', course_tag),
                        'airtable_name': course_data.get('B', course_tag),
                        'gant_sheet': course_data.get('C', ''),  # Column C - GANT sheet
                        'lesson_count': self._parse_int(course_data.get('D', '0')),  # Column D - Lessons
                        'access_months': self._parse_int(course_data.get('E', '0')),  # Column E - Access months
                        'curator_support_months': self._parse_int(course_data.get('F', '0')),  # Column F - Curator support
                        'vip_support_months': self._parse_int(course_data.get('G', '0')),  # Column G - VIP support
                        'program_type': course_data.get('H', 'regular').lower(),  # Column H - Program type
                        'row_index': i
                    }
            
            logger.info(f"✅ Loaded {len(self._course_cache)} courses from template")
            
        except Exception as e:
            logger.error(f"❌ Failed to load courses from template: {e}")
            raise
    
    def _normalize_tag(self, tag: str) -> str:
        """
        Normalize course tag for comparison.
        Removes case sensitivity, punctuation, and internal additions.
        """
        if not tag:
            return ""
        
        # Convert to lowercase
        normalized = tag.lower().strip()
        
        # Remove common punctuation and special characters
        normalized = re.sub(r'[.,;"\'\[\]]', '', normalized)
        
        # Remove internal additions (case insensitive)
        internal_additions = [
            'первый платеж',
            'вн. рассрочка',
            'внутренняя рассрочка',
            'рассрочка',
            'навсегда'
        ]
        
        for addition in internal_additions:
            normalized = re.sub(r'\b' + re.escape(addition) + r'\b', '', normalized, flags=re.IGNORECASE)
        
        # Clean up extra spaces
        normalized = re.sub(r'\s+', ' ', normalized).strip()
        
        return normalized
    
    def _parse_int(self, value: str) -> int:
        """Safely parse string to integer"""
        try:
            # Handle text values like "Навсегда" by returning 0
            if isinstance(value, str) and not value.isdigit():
                # Check for common text values that mean "forever" or "unlimited"
                if value.strip().lower() in ['навсегда', 'бессрочно', 'forever', 'unlimited']:
                    return 0  # Special value to indicate unlimited
                return 0  # Default to 0 for any non-numeric text
            return int(float(value)) if value else 0
        except (ValueError, TypeError):
            return 0
    
    def get_course_by_tag(self, getcourse_tag: str) -> Optional[Dict[str, Any]]:
        """
        Find course by GetCourse tag with fuzzy matching.
        
        Args:
            getcourse_tag: Tag from GetCourse system
            
        Returns:
            Course data dictionary or None if not found
        """
        if not getcourse_tag:
            return None
        
        # Normalize the input tag
        normalized_input = self._normalize_tag(getcourse_tag)
        
        # Direct match first
        if normalized_input in self._course_cache:
            course = self._course_cache[normalized_input].copy()
            course['getcourse_tag'] = getcourse_tag
            logger.info(f"✅ Direct match found: '{getcourse_tag}' -> '{course['original_tag']}'")
            return course
        
        # Fuzzy matching - look for partial matches
        best_matches = []
        input_parts = set(normalized_input.split())
        
        for normalized_tag, course_data in self._course_cache.items():
            tag_parts = set(normalized_tag.split())
            
            # Calculate similarity based on common parts
            if input_parts and tag_parts:
                intersection = input_parts.intersection(tag_parts)
                union = input_parts.union(tag_parts)
                similarity = len(intersection) / len(union) if union else 0
                
                if similarity > 0.5:  # At least 50% similarity
                    best_matches.append((similarity, normalized_tag, course_data))
        
        # Return best match if found
        if best_matches:
            best_matches.sort(key=lambda x: x[0], reverse=True)
            best_similarity, best_tag, best_course = best_matches[0]
            course = best_course.copy()
            course['getcourse_tag'] = getcourse_tag
            logger.info(f"✅ Fuzzy match found ({best_similarity:.2f}): '{getcourse_tag}' -> '{course['original_tag']}'")
            return course
        
        logger.warning(f"❌ No matching course found for: '{getcourse_tag}'")
        return None
    
    def is_tariff_program(self, getcourse_tag: str) -> bool:
        """
        Check if the program is a tariff (bundle, subscription, premium).
        
        Args:
            getcourse_tag: Tag from GetCourse system
            
        Returns:
            True if it's a tariff program
        """
        course = self.get_course_by_tag(getcourse_tag)
        if not course:
            return False
        
        program_type = course.get('program_type', 'regular')
        return program_type.lower() in ['bundle', 'subscription', 'premium', 'бандл', 'абонемент', 'премиум']
    
    def get_tracker_course_name(self, getcourse_tag: str) -> str:
        """Get course name for tracker"""
        course = self.get_course_by_tag(getcourse_tag)
        return course['tracker_name'] if course else getcourse_tag
    
    def get_kpi_course_name(self, getcourse_tag: str) -> str:
        """Get course name for KPI sheets"""
        course = self.get_course_by_tag(getcourse_tag)
        return course['kpi_name'] if course else getcourse_tag
    
    def get_airtable_course_name(self, getcourse_tag: str) -> str:
        """Get course name for Airtable"""
        course = self.get_course_by_tag(getcourse_tag)
        return course['airtable_name'] if course else getcourse_tag
    
    def get_course_params(self, getcourse_tag: str) -> Dict[str, Any]:
        """
        Get course parameters for tracker creation.
        
        Returns:
            Dict with course parameters
        """
        course = self.get_course_by_tag(getcourse_tag)
        if not course:
            # Default values if course not found
            logger.warning(f"⚠️ Using default parameters for course: {getcourse_tag}")
            return {
                'lesson_count': 50,
                'access_days': 360,
                'curator_support_days': 180,
                'vip_support_days': 360,
                'monthly_target': 7,
                'monthly_minimum': 7,
                'gant_sheet': '',
                'program_type': 'regular'
            }
        
        # Convert months to days, preserving text values
        # For text values like "Навсегда", we store the original text
        original_access = course.get('access_months', 0)
        original_curator = course.get('curator_support_months', 0)
        original_vip = course.get('vip_support_months', 0)
        
        # Convert to days only if they are numeric values
        access_days = self._convert_to_days(original_access)
        curator_support_days = self._convert_to_days(original_curator)
        vip_support_days = self._convert_to_days(original_vip)
        
        return {
            'lesson_count': course['lesson_count'],
            'access_days': access_days,
            'curator_support_days': curator_support_days,
            'vip_support_days': vip_support_days,
            'monthly_target': 7,
            'monthly_minimum': 7,
            'gant_sheet': course['gant_sheet'],
            'program_type': course['program_type'],
            # Store original values for use in formulas
            'original_access_months': original_access,
            'original_curator_months': original_curator,
            'original_vip_months': original_vip
        }
    
    def _convert_to_days(self, value) -> int:
        """Convert months to days, handling text values"""
        # If it's a text value, return 0 to indicate special handling needed
        if isinstance(value, str) and not value.isdigit():
            return 0
        # Convert numeric values to days
        try:
            months = int(float(value)) if value else 0
            return months * 30 if months > 0 else 0
        except (ValueError, TypeError):
            return 0
    
    def refresh_courses(self):
        """Refresh course cache from Google Sheets"""
        logger.info("🔄 Refreshing course data from template...")
        self._course_cache.clear()
        self._load_courses()

# Example usage
if __name__ == "__main__":
    # Test the dynamic course configuration
    try:
        config = DynamicCourseConfig()
        
        # Test cases
        test_tags = [
            "[club] Тариф VIP Навсегда. Первый платеж",
            "[club] Тариф VIP",
            "[python-ai-2.0] Тариф \"VIP\"",
            "Unknown Course"
        ]
        
        for tag in test_tags:
            print(f"\n--- Testing: {tag} ---")
            course = config.get_course_by_tag(tag)
            if course:
                print(f"Found: {course['internal_name']}")
                print(f"Program Type: {course['program_type']}")
                print(f"Is Tariff: {config.is_tariff_program(tag)}")
                params = config.get_course_params(tag)
                print(f"Access Days: {params['access_days']}")
            else:
                print("Not found")
                
    except Exception as e:
        print(f"Error: {e}")