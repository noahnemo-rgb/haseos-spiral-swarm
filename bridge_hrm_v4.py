import os, sys
sys.path.insert(0, ".")
import haseosconfig
print("✅ Config loaded")
hrm_path = os.path.join(os.getcwd(), "hrm")
print("HRM path:", hrm_path)

models_path = os.path.join(hrm_path, "models")
print("Models exists:", os.path.exists(models_path))
if os.path.exists(models_path):
    print("Models contents:", os.listdir(models_path))
else:
    print("Models folder not found")
print("\nBridge ready for HRM integration.")
