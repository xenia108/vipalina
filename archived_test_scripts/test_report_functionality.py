#!/usr/bin/env python3
"""
Test script to verify report generator functionality after fix
"""

import asyncio
import sys
import os

# Add the current directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

async def test_report_generation():
    """Test report generation functionality"""
    try:
        print("🔍 Testing report generator initialization...")
        
        # Import and initialize report generator
        from report_generator import get_report_generator
        report_gen = get_report_generator()
        print("✅ Report generator initialized successfully")
        print(f"📊 Spreadsheet ID: {report_gen.spreadsheet_id}")
        
        # Test getting KPI data
        print("\n🔍 Testing KPI data retrieval...")
        kpi_data = await report_gen.get_kpi_data()
        print(f"✅ Retrieved {len(kpi_data)} student records from KPI sheet")
        
        # Test getting VIPalina data
        print("\n🔍 Testing VIPalina data retrieval...")
        vipalina_data = await report_gen.get_vipalina_data()
        print(f"✅ Retrieved {len(vipalina_data)} student records from VIPalina sheet")
        
        # Test manager list
        print("\n🔍 Testing manager list retrieval...")
        managers = report_gen.get_manager_list()
        print(f"✅ Found {len(managers)} managers: {', '.join(managers[:3])}...")
        
        print("\n🎉 ALL TESTS PASSED! Report generation functionality is working correctly.")
        return True
        
    except Exception as e:
        print(f"❌ Error during testing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    result = asyncio.run(test_report_generation())
    sys.exit(0 if result else 1)