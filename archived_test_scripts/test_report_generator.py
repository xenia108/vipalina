#!/usr/bin/env python3
"""
Test script to verify report generator initialization
"""

import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from report_generator import get_report_generator
    
    print("Getting report generator...")
    report_gen = get_report_generator()
    print("Report generator initialized successfully!")
    print(f"Spreadsheet ID: {report_gen.spreadsheet_id}")
    
except Exception as e:
    print(f"Error initializing report generator: {e}")
    import traceback
    traceback.print_exc()