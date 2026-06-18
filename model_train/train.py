import sys
import os
from pathlib import Path
import numpy as np
import cv2

# Increased resolution to 20x20 (400 features) for better letter/number distinction
FEATURE_DIM = 400 
samples = np.empty((0, FEATURE_DIM), dtype=np.float32)
responses = []

# --- 1. THE LABEL MAP ---
# Explicitly map complex filenames to their EXACT visual sequence left-to-right.
# We will use 'c' to represent the coin stack icon so we can detect it, but explicitly ignore training it.
# The coin stack icon is made of 3 disconnected shapes, so it requires 'ccc'.
LABEL_MAP = {
    "0": "0",
    "600": "+ccc600",
    "800": "+ccc800",
    "900": "+ccc900",
    "1200": "+ccc1,200", # Assumes comma formatting, remove if it's just "+ccc1200"
    "2700": "+ccc2,700", # Assumes comma formatting, remove if it's just "+ccc2700"
    "20000": "+ccc20,000",
    "30000": "+ccc30,000",
    "40000": "+ccc40,000",
    "50000": "+ccc50,000",
    "2": "2/1",
    "3": "3/1",
    "4": "4/1",
    "5": "5/1",
    "6": "6/1",
    "7": "7/1",
    "8": "8/1",
    "9": "9/1",
    "10": "10/1",
    "25": "25/1",
    "evens": "EVENS", # Added for evens.jpg
    "debug_chips_1781799926": "ccc8411770",
    "debug_chips_1781804490": "ccc8461770",
    "debug_chips_1781804531": "ccc8451770",
    "debug_chips_1781804568": "ccc8461770" # Add this new thick-font edge case!
    
}

def resize_and_pad(img, size=(20, 20)):
    """
    Resizes the character while preserving its aspect ratio, 
    then pads the remaining space with black pixels to perfectly fit the target size.
    """
    h, w = img.shape
    scale = min(size[0] / w, size[1] / h)
    new_w, new_h = max(1, int(w * scale)), max(1, int(h * scale))
    
    # Resize preserving aspect ratio
    resized = cv2.resize(img, (new_w, new_h), interpolation=cv2.INTER_AREA)
    
    # Calculate padding to center the character
    top = (size[1] - new_h) // 2
    bottom = size[1] - new_h - top
    left = (size[0] - new_w) // 2
    right = size[0] - new_w - left
    
    # Add black borders
    padded = cv2.copyMakeBorder(resized, top, bottom, left, right, cv2.BORDER_CONSTANT, value=0)
    return padded

def train_file(path):
    global samples, responses
    print("\nProcessing:", path)
    filename = os.path.basename(path)
    base_name = os.path.splitext(filename)[0]
    
    # Determine expected string sequence
    if base_name in LABEL_MAP:
        expect = LABEL_MAP[base_name]
    elif "_" in base_name:
        expect = base_name.split("_")[0]
    else:
        expect = base_name
        # Apply the /1 rule for standard numbers, but not for "0"
        if (len(expect) == 1 or len(expect) == 2) and expect != "0" and expect.isdigit():
             expect += "/1"

    print("Expecting sequence:", expect)
    im = cv2.imread(path)
    
    if im is None:
        print(f"--> [ERROR] Could not read image: {path}")
        return

    # Reproduce main preprocessing
    upscale_factor = 5
    img_upscaled = cv2.resize(im, (0, 0), fx=upscale_factor, fy=upscale_factor, interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img_upscaled, cv2.COLOR_BGR2GRAY)
    high_contrast = cv2.convertScaleAbs(gray, alpha=2.0, beta=-50)
    _, thresh = cv2.threshold(high_contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Sort contours strictly from left to right
    contours = sorted(contours, key=lambda ctr: cv2.boundingRect(ctr)[0])

    detected_chars = []
    min_contour_area = 5 * (upscale_factor * upscale_factor)

    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        
        # Keep area filtering, but remove the height filter 
        # so we don't accidentally delete commas and periods.
        if w * h < min_contour_area:
            continue

        roi = thresh[y:y+h, x:x+w]
        roi_inverted = cv2.bitwise_not(roi)
        
        # Use our new padding function with 20x20
        roismall = resize_and_pad(roi_inverted, size=(20, 20))
        
        detected_chars.append({'roi': roismall, 'x': x})

    if len(detected_chars) != len(expect):
        print(f"--> [ERROR] Mismatch in '{path}'. Detected {len(detected_chars)} contours, expected {len(expect)} for sequence '{expect}'. Skipping.")
        return 

    # Add to training data, but skip the 'c' (coin icon)
    for i, char_data in enumerate(detected_chars):
        e = expect[i]
        
        if e == 'c':
            print("    Skipping coin icon contour.")
            continue
            
        print(f"    Training character: {e}")
        responses.append(ord(e))
        sample = char_data['roi'].reshape((1, FEATURE_DIM))
        samples = np.append(samples, sample, 0)

# --- EXECUTION ---
# Make sure your files are in the 'img' directory
img_dir = 'img'
if not os.path.exists(img_dir):
    print(f"Error: The directory '{img_dir}' was not found. Please create it and add your images.")
    sys.exit(1)

for f in os.listdir(img_dir):
    if f.endswith((".jpg", ".png")):
        train_file(os.path.join(img_dir, f))

# Check if we have data to train
if len(responses) == 0:
    print("\n[ERROR] No valid training data found. Ensure your images match the label expectations.")
    sys.exit(1)

# Format arrays for OpenCV SVM
samples = np.array(samples, np.float32)
# SVM in OpenCV requires labels to be strictly int32 format
responses = np.array(responses, np.int32) 
responses = responses.reshape((responses.size, 1))

print("\nTraining complete. Total samples:", len(samples))

# --- SVM SETUP AND TRAINING ---
print("Configuring and training SVM model...")
svm = cv2.ml.SVM_create()

# SVM_C_SVC is the standard N-class classification algorithm
svm.setType(cv2.ml.SVM_C_SVC) 

# LINEAR kernel is very fast and works beautifully for padded pixel classification
svm.setKernel(cv2.ml.SVM_LINEAR) 

# Configure training criteria (max iterations and tolerance)
svm.setTermCriteria((cv2.TERM_CRITERIA_MAX_ITER, int(1e7), 1e-6))

# Train the model
svm.train(samples, cv2.ml.ROW_SAMPLE, responses)

# Save model to resources/data directory
script_dir = Path(__file__).resolve().parent
model_dir = script_dir.parent / "resources" / "data"
model_dir.mkdir(parents=True, exist_ok=True)
model_path = model_dir / "svm_model.yml"
svm.save(str(model_path))
print(f"Model successfully saved to: {model_path}")