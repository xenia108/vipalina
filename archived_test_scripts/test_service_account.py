#!/usr/bin/env python3
"""
Test script to verify service account credentials loading
"""

import json
from google.oauth2.service_account import Credentials

# Test loading the service account file
try:
    # Load the service account file
    with open('vipalina_google_service_account.json', 'r') as f:
        service_account_info = json.load(f)
    
    print("Service account file loaded successfully")
    print(f"Client email: {service_account_info.get('client_email')}")
    print(f"Token URI: {service_account_info.get('token_uri')}")
    
    # Test creating credentials
    scopes = ['https://www.googleapis.com/auth/spreadsheets']
    credentials = Credentials.from_service_account_info(service_account_info, scopes=scopes)
    print("Credentials created successfully")
    
except Exception as e:
    print(f"Error: {e}")
    import traceback
    traceback.print_exc()