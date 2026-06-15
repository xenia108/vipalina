# Fix for Text Values in Course Parameters

## Problem
When courses have text values like "Навсегда" or "Бессрочно" instead of numeric values for access/support periods, the formulas in tracker sheets break because:
1. The system tries to convert text values to days by multiplying by 30
2. Formulas attempt to perform calculations with text values
3. This causes errors in the monthly progress tracking and other calculations

## Solution
We implemented a comprehensive fix that handles text values properly throughout the system:

### 1. Dynamic Course Configuration ([dynamic_course_config.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/dynamic_course_config.py))
- Added `_parse_int()` method to handle text values like "Навсегда" by returning 0
- Added `_convert_to_days()` method that preserves text values and only converts numeric values
- Modified `get_course_params()` to store both original text values and converted numeric values

### 2. Course Configuration V2 ([course_config_v2.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/course_config_v2.py))
- Added `_convert_months_to_days()` method to handle text values
- Modified `get_course_params()` to properly convert months to days while preserving text values

### 3. Tracker Creator ([tracker_creator.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/tracker_creator.py))
- Modified `_copy_course_data_to_config()` to preserve text values in the configuration sheet
- Added `_format_months_value()` method to format values for display
- Updated `_update_monthly_progress_formulas()` to handle text values:
  - When a text value like "Навсегда" is detected, creates a single row displaying the text
  - For numeric values, creates the normal monthly progress rows

### 4. Tariff Tracker Manager ([tariff_tracker_manager.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/tariff_tracker_manager.py))
- Updated `_update_progress_formulas()` to use ISNUMBER/ISTEXT checks in formulas:
  - H column (lessons done): Uses ISNUMBER to check if values are numeric
  - I column (total lessons): Uses ISNUMBER to check if values are numeric
  - J column (percentage): Handles both numeric and text values appropriately

## Key Changes

### Formula Updates
The formulas now use ISNUMBER checks to determine if values are numeric before performing calculations:

```excel
=IF(G5<>"";IF(ISNUMBER(INDIRECT("'📚 "&G5&"'!A2"));COUNTIF(INDIRECT("'📚 "&G5&"'!D:D");TRUE);"-");"-")
```

### Text Value Handling
When text values like "Навсегда" are encountered:
1. They are preserved as-is in the configuration sheets
2. Monthly progress tracking displays the text value instead of creating multiple rows
3. Formulas check for text values and handle them appropriately

## Testing
Created test script [test_text_values_fix.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/test_text_values_fix.py) that verifies:
- Text values are properly parsed and converted
- Numeric values are properly converted to days
- Formatting functions work correctly for both text and numeric values

## Benefits
1. **No more formula errors** when text values are used
2. **Preserves original text values** for display purposes
3. **Maintains compatibility** with existing numeric values
4. **Automatic handling** of common text values like "Навсегда", "Бессрочно"
5. **Improved user experience** with clear display of text values

## Files Modified
1. [dynamic_course_config.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/dynamic_course_config.py) - Core parsing and conversion logic
2. [course_config_v2.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/course_config_v2.py) - Configuration handling
3. [tracker_creator.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/tracker_creator.py) - Tracker creation and formula handling
4. [tariff_tracker_manager.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/tariff_tracker_manager.py) - Tariff tracker management
5. [test_text_values_fix.py](file:///Users/macbook/Desktop/telegram_bot/Alina/VipAlina/vipalina/test_text_values_fix.py) - Test script