#!/usr/bin/env python
"""Quick test to check if posh_act_page_corp view can be imported and run"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'OHS.settings')
django.setup()

try:
    from home.views import posh_act_page_corp
    print("✓ Successfully imported posh_act_page_corp")
    print(f"✓ Function name: {posh_act_page_corp.__name__}")
    print(f"✓ Function location: {posh_act_page_corp.__module__}")
except Exception as e:
    print(f"✗ Error importing: {e}")
    import traceback
    traceback.print_exc()
