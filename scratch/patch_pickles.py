import joblib
import os
import torch

def patch_file(path):
    if not os.path.exists(path):
        print(f"File not found: {path}")
        return

    print(f"Patching {path}...")
    data = joblib.load(path)
    
    modified = False
    
    if isinstance(data, dict):
        for key in data:
            if isinstance(data[key], list):
                new_list = []
                for item in data[key]:
                    if isinstance(item, str):
                        new_item = item.replace("OHS", "OHPL")
                        if new_item != item:
                            modified = True
                        new_list.append(new_item)
                    else:
                        new_list.append(item)
                data[key] = new_list
            elif isinstance(data[key], str):
                new_val = data[key].replace("OHS", "OHPL")
                if new_val != data[key]:
                    modified = True
                data[key] = new_val
    elif isinstance(data, list):
        new_list = []
        for item in data:
            if isinstance(item, str):
                new_item = item.replace("OHS", "OHPL")
                if new_item != item:
                    modified = True
                new_list.append(new_item)
            else:
                new_list.append(item)
        data = new_list
    else:
        # For LabelEncoder or other objects
        if hasattr(data, 'classes_'):
            new_classes = []
            for item in data.classes_:
                if isinstance(item, str):
                    new_item = item.replace("OHS", "OHPL")
                    if new_item != item:
                        modified = True
                    new_classes.append(new_item)
                else:
                    new_classes.append(item)
            data.classes_ = np.array(new_classes)

    if modified:
        joblib.dump(data, path)
        print(f"Successfully patched {path}")
    else:
        print(f"No changes needed for {path}")

import numpy as np
patch_file("home/semantic_data.pkl")
patch_file("home/label_encoder.pkl")
# chatbot_model.pkl might have labels in the estimator, but usually label_encoder handles it.
