#!/usr/bin/env python3
import os
import sys
sys.path.insert(0, ".")
import haseosconfig

print("✅ HASEOS config loaded.")
print("Ethics First. Always. is active.")

hrm_path = os.path.join(os.getcwd(), "hrm")
print("HRM path:", hrm_path)
print("HRM folder contents:", os.listdir(hrm_path))

print("\n✅ Bridge ready for next step.")
