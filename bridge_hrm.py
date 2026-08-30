

import os
import sys
sys.path.insert(0, ".")
import haseosconfig

print("=" * 70)
print("HASEOS SPIRAL SWARM - BRIDGE")
print("=" * 70)
print("Ethics First. Always. is active.")

hrm_path = os.path.join(os.getcwd(), "hrm")
models_path = os.path.join(hrm_path, "models")

print("HRM path:", hrm_path)
print("Models folder exists:", os.path.exists(models_path))

if os.path.exists(models_path):
    print("Models contents:", os.listdir(models_path))
else:
    print("Models folder not found")

print("\nBridge ready for HRM integration.")
print("=" * 70)

