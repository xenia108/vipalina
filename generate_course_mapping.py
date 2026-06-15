"""
Script to generate course mapping from Google Sheets template.
This ensures all required fields including program_type are included.
"""

import gspread
from google.oauth2.service_account import Credentials as ServiceAccountCredentials
import json
import logging

logger = logging.getLogger('vipalina_telethon')

def generate_course_mapping(
    template_id: str = '1gH1Sd7BCeUFBqufXUy63nVjWPcNmGNq312iL8-_Y_rQ',
    credentials_path: str = 'vipalina_google_credentials.json',
    output_file: str = 'course_mapping_generated.py'
):
    """
    Generate course mapping from Google Sheets template.
    
    Args:
        template_id: ID of the template spreadsheet
        credentials_path: Path to credentials file
        output_file: Output Python file path
    """
    try:
        # Authorize with Google Sheets API
        scope = [
            'https://www.googleapis.com/auth/drive',
            'https://www.googleapis.com/auth/spreadsheets'
        ]
        creds = ServiceAccountCredentials.from_service_account_file(
            credentials_path, scopes=scope
        )
        sheets_client = gspread.authorize(creds)
        
        # Open template
        template = sheets_client.open_by_key(template_id)
        conditions_sheet = template.worksheet('Условия курсов')
        
        # Get all data
        all_data = conditions_sheet.get_all_values()
        
        if len(all_data) < 2:
            raise Exception("No course data found in template")
        
        # Headers are in the first row
        headers = [h.strip() for h in all_data[0]] if all_data else []
        logger.info(f"Headers: {headers}")
        
        # Create column index mapping
        col_indices = {}
        for i, header in enumerate(headers):
            col_indices[header] = i
        
        # Generate Python code
        python_code = '''"""
Automatically generated course mapping from Google Sheets template.
Source: Template tracker, "Условия курсов" sheet

DO NOT EDIT MANUALLY!
To update, run: python3 generate_course_mapping.py
"""

COURSE_MAPPING = {
'''
        
        # Process each course row
        course_count = 0
        for i, row in enumerate(all_data[1:], start=2):  # Start from row 2 (1-indexed)
            if len(row) == 0 or not row[0].strip():  # Skip empty rows
                continue
            
            course_tag = row[0].strip() if len(row) > 0 else ""
            if not course_tag:
                continue
            
            # Extract data by column index
            def get_cell(col_name, default=""):
                idx = col_indices.get(col_name, -1)
                if idx >= 0 and idx < len(row):
                    return row[idx].strip()
                return default
            
            internal_name = get_cell('Название для AT, KPI Ultra, трекера и группы в телеграм', course_tag)
            gant_sheet = get_cell('Название листа в таблице ГАНТ', '')
            lesson_count = get_cell('Количество уроков', '0')
            access_months = get_cell('Доступ к платформе (мес)', '0')
            curator_support_months = get_cell('Поддержка куратора (мес)', '0')
            vip_support_months = get_cell('Поддержка VIP, обучение+окупаемость (мес)', '0')
            program_type = get_cell('Тип программы', 'regular')
            
            # Generate Python dictionary entry
            # Escape quotes in course tag and other strings
            escaped_course_tag = course_tag.replace('"', '\\"')
            escaped_internal_name = internal_name.replace('"', '\\"')
            escaped_gant_sheet = gant_sheet.replace('"', '\\"')
            
            python_code += f'    "{escaped_course_tag}": {{\n'
            python_code += f'        "internal_name": "{escaped_internal_name}",\n'
            python_code += f'        "tracker_name": "{escaped_internal_name}",\n'
            python_code += f'        "kpi_name": "{escaped_internal_name}",\n'
            python_code += f'        "airtable_name": "{escaped_internal_name}",\n'
            python_code += f'        "gant_sheet": "{escaped_gant_sheet}",\n'
            
            # Parse numeric values safely
            def safe_int(value):
                # Handle empty values
                if not value or value == '':
                    return 0
                
                # Handle special cases like "навсегда", "бессрочно", etc.
                if isinstance(value, str):
                    # Check for common text values that mean "forever" or "unlimited"
                    lower_value = value.lower().strip()
                    if any(text in lower_value for text in ['навсегда', 'бессрочно', 'forever', 'unlimited', 'бесконечно']):
                        return '"Навсегда"'  # Return as string literal for Python
                # For other text values, return as quoted string
                if isinstance(value, str) and not value.isdigit():
                    # Escape quotes in the string
                    escaped_value = value.replace('"', '\\"')
                    return f'"{escaped_value}"'
                # For numeric values, return as number
                return int(float(value)) if value else 0
            
            python_code += f'        "lesson_count": {safe_int(lesson_count)},\n'
            python_code += f'        "access_months": {safe_int(access_months)},\n'
            python_code += f'        "curator_support_months": {safe_int(curator_support_months)},\n'
            python_code += f'        "vip_support_months": {safe_int(vip_support_months)},\n'
            python_code += f'        "program_type": "{program_type.lower()}"\n'
            python_code += '    },\n'
            
            course_count += 1
        
        python_code += '}\n'
        
        # Add helper functions
        python_code += '''
def get_total_courses():
    """Get total number of courses in mapping"""
    return len(COURSE_MAPPING)

def list_all_courses():
    """List all course tags"""
    return list(COURSE_MAPPING.keys())

def search_courses(search_term):
    """Search courses by term"""
    search_term = search_term.lower()
    results = []
    for tag, data in COURSE_MAPPING.items():
        if (search_term in tag.lower() or 
            search_term in data["internal_name"].lower() or
            search_term in data["tracker_name"].lower()):
            results.append({"tag": tag, "name": data["internal_name"]})
    return results
'''
        
        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write(python_code)
        
        logger.info(f"✅ Generated course mapping with {course_count} courses")
        logger.info(f"📝 Output written to {output_file}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Failed to generate course mapping: {e}")
        raise

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    try:
        generate_course_mapping()
        print("✅ Course mapping generation completed successfully!")
    except Exception as e:
        print(f"❌ Error: {e}")