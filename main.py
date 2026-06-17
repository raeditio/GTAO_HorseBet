import cv2
import numpy as np
import pyautogui
import time
import os
import win32gui

DEBUG_MODE = True
DEBUG_DIR = "debug"

if DEBUG_MODE and not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)

# --- Global Stats Tracking ---
class BettingStats:
    def __init__(self):
        self.races_won = 0
        self.races_lost = 0
        self.winnings = 0
        self.time_running = time.time()
        
    def print_stats(self):
        elapsed = int(time.time() - self.time_running)
        print(f"\n--- SESSION STATS ---")
        print(f"Races Won:  {self.races_won}")
        print(f"Races Lost: {self.races_lost}")
        print(f"Time Ran:   {elapsed // 60}m {elapsed % 60}s")
        print(f"---------------------\n")

def load_knn_model():
    """Loads and verifies the KNN model handling both native and manual YAML formats."""
    filepath = 'resources/data/model.yml'
    
    if not os.path.exists(filepath):
        print(f"Error: Model file not found at '{filepath}'")
        return None
        
    # METHOD 1: Try OpenCV's native ML loader
    try:
        model = cv2.ml.KNearest_load(filepath)
        if model is not None and model.isTrained():
            print("Model loaded successfully via cv2.ml.KNearest_load().")
            return model
    except Exception:
        pass 

    # METHOD 2: Try manual parsing
    try:
        print("Native ML load failed/unsupported. Attempting manual matrix extraction...")
        fs = cv2.FileStorage(filepath, cv2.FILE_STORAGE_READ)
        if not fs.isOpened():
            print("Error: Could not open model.yml for manual parsing.")
            return None

        root_knn = fs.getNode('opencv_ml_knn')
        parent_node = root_knn if not root_knn.empty() else fs

        def extract_matrix(keys):
            for key in keys:
                node = parent_node.getNode(key)
                if not node.empty():
                    return node.mat()
            return None

        samples = extract_matrix(['samples', 'train_data', 'trainData', 'data'])
        responses = extract_matrix(['responses', 'train_labels', 'labels', 'responsesData'])
        fs.release()

        if samples is None or responses is None:
            print("Error: Model file is missing recognizable matrices.")
            return None

        model = cv2.ml.KNearest_create()
        model.train(np.float32(samples), cv2.ml.ROW_SAMPLE, np.float32(responses))
        print("Model verified and loaded successfully via manual matrix extraction.")
        return model

    except Exception as e:
        print(f"Failed to load model manually: {e}")
        return None

def parse_odds(pred_str):
    """Translates the string prediction to a short/int."""
    pred = pred_str.strip().lower()
    
    # Common OCR mistakes compensation
    pred = pred.replace('\\', '/').replace('|', '/').replace('l', '/').replace('i', '/')
    
    if not pred: return -1
    
    # Fuzzy match for 'evens' in case of a minor 1-letter OCR mistake
    if "even" in pred or "evn" in pred or "eve" in pred: 
        return 1
        
    slash_idx = pred.find('/')
    if slash_idx == -1: return -1
        
    try:
        return int(pred[:slash_idx])
    except ValueError:
        return -1

def read_odds(model, img, horse_index):
    """Reads the odds by parsing individual character contours."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Increase contrast significantly
    high_contrast = cv2.convertScaleAbs(gray, alpha=2.0, beta=-50)
    
    # 2. Use Otsu's Thresholding (Creates White text on Black background)
    _, thresh = cv2.threshold(high_contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    if DEBUG_MODE:
        timestamp = int(time.time())
        filename = os.path.join(DEBUG_DIR, f"debug_horse{horse_index}_{timestamp}.png")
        cv2.imwrite(filename, thresh)
        
    # findContours NEEDS White text on a Black background to work
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected_chars = []
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < 5:  
            continue
            
        # Crop the White-on-Black character
        roi = thresh[y:y+h, x:x+w]
        
        # 3. INVERT the character to Black-on-White!
        # The KNN model was trained on Black text on a White background.
        # If we don't flip it, the model gets confused and guesses letters like 'v' or 'e'.
        roi_inverted = cv2.bitwise_not(roi)
        
        # Resize to 10x10 to match the 100 columns expected by model.yml
        resized = cv2.resize(roi_inverted, (10, 10))
        sample = resized.reshape((1, -1)).astype(np.float32)
        
        # Predict
        ret, results, neighbours, dist = model.findNearest(sample, k=1)
        pred_val = int(results[0][0])
        pred_char = chr(pred_val) if 0 <= pred_val <= 255 else str(pred_val)
        
        detected_chars.append((x, pred_char))

    # Sort characters by X-coordinate to read left-to-right
    detected_chars.sort(key=lambda item: item[0])
    pred_str = "".join([char for x, char in detected_chars])
    
    return parse_odds(pred_str), pred_str

def get_gta_window_info():
    """Gets GTA V window bounds for dynamic resolution multiplier logic."""
    try:
        hwnd = win32gui.FindWindow(None, "Grand Theft Auto V")
        if hwnd:
            rect = win32gui.GetWindowRect(hwnd)
            x, y, w, h = rect[0], rect[1], rect[2] - rect[0], rect[3] - rect[1]
            if w > 0 and h > 0:
                return hwnd, x, y, w, h
    except Exception:
        pass
    return None, 0, 0, 0, 0

def get_dynamic_boxes(width, height):
    """Calculates coordinates mathematically based on 1920x1080 baseline."""
    mult_w = width / 1920.0
    mult_h = height / 1080.0

    boxes = []
    base_y_coords = [370, 485, 600, 715, 830, 945]  
    base_x = 240
    base_width = 90
    base_height = 45

    for y in base_y_coords:
        boxes.append((
            int(base_x * mult_w),
            int(y * mult_h),
            int(base_width * mult_w),
            int(base_height * mult_h)
        ))
    return boxes

def main_loop():
    model = load_knn_model()
    stats = BettingStats()
    
    if model is None:
        print("Exiting due to model load failure.")
        return

    while True:
        hwnd, win_x, win_y, win_w, win_h = get_gta_window_info()
        
        if not hwnd or win32gui.GetForegroundWindow() != hwnd:
            print("GTA V is not active or minimized. Waiting...")
            time.sleep(2)
            continue

        print("\nTaking screenshot of game window...")
        screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        dynamic_boxes = get_dynamic_boxes(win_w, win_h)

        odds_list = []
        raw_list = []
        for i, (x, y, w, h) in enumerate(dynamic_boxes):
            crop = frame[y:y+h, x:x+w]
            odds, raw_str = read_odds(model, crop, i + 1)
            odds_list.append(odds)
            raw_list.append(raw_str)
            
        print("\n--- ODDS ANALYSIS ---")
        best_horse_idx = -1
        best_prob = -1.0
        valid_odds_found = False

        for idx, odds in enumerate(odds_list):
            raw_str = raw_list[idx]
            if odds > 0:
                prob = 100.0 / (odds + 1)
                odds_str = "Evens" if odds == 1 else f"{odds}/1"
                print(f"Horse {idx + 1}: {odds_str} ({prob:.1f}% chance) [Raw OCR: '{raw_str}']")
                
                if prob > best_prob:
                    best_prob = prob
                    best_horse_idx = idx
                    valid_odds_found = True
            else:
                print(f"Horse {idx + 1}: Unreadable/Invalid [Raw OCR: '{raw_str}']")
        print("---------------------\n")
        
        if valid_odds_found: 
             print(f"-> Most probable choice: Horse {best_horse_idx + 1} ({best_prob:.1f}% chance)")
             try:
                 target_box = dynamic_boxes[best_horse_idx]
                 click_x = win_x + target_box[0] + (target_box[2] // 2)
                 click_y = win_y + target_box[1] + (target_box[3] // 2)
                 pyautogui.click(click_x, click_y)
                 print(f"Clicked Horse {best_horse_idx + 1} at ({click_x}, {click_y})")
                 time.sleep(0.5)
                 
                 pyautogui.press('tab')
                 print("Pressed Tab")
                 time.sleep(0.5)
                 
                 center_x = win_x + (win_w // 2)
                 center_y = win_y + (win_h // 2)
                 pyautogui.click(center_x, center_y)
                 print(f"Clicked Window Center at ({center_x}, {center_y})")
                 
                 print("Bet placed. Waiting for race to finish (30s)...")
                 time.sleep(30)
                 stats.races_won += 1
                 stats.print_stats()
             except Exception as e:
                 print(f"Error during clicking phase: {e}")
        else:
             print("No valid odds could be read. Refreshing...")
             time.sleep(2)

        time.sleep(1)

if __name__ == "__main__":
    main_loop()