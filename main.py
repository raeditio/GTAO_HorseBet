import cv2
import numpy as np
import pyautogui
import pydirectinput
import time
import os
import win32gui
import argparse

DEBUG_MODE = False
DEBUG_DIR = "debug"

# --- Argument Parsing ---
arg_parser = argparse.ArgumentParser(description="GTA V Horse Betting Automation")
arg_parser.add_argument('--debug', action='store_true', help="Enable debug mode to save intermediate images.")
args = arg_parser.parse_args()
DEBUG_MODE = args.debug

if DEBUG_MODE and not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)
elif DEBUG_MODE:
    # Empty directory
    for f in os.listdir(DEBUG_DIR):
        os.remove(os.path.join(DEBUG_DIR, f))

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
        print(f"Winnings:   {self.winnings}")
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
    
    # A valid GTA odd never starts with a 0. If it does, it was misread and is almost certainly an 8.
    if pred.startswith('0'):
        pred = '8' + pred[1:]
    
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
        roi_inverted = cv2.bitwise_not(roi)
        
        # Resize to 10x10 to match the 100 columns expected by model.yml
        resized = cv2.resize(roi_inverted, (10, 10))
        sample = resized.reshape((1, -1)).astype(np.float32)
        
        # Predict
        ret, results, neighbours, dist = model.findNearest(sample, k=1)
        pred_val = int(results[0][0])
        pred_char = chr(pred_val) if 0 <= pred_val <= 255 else str(pred_val)
        
        # --- 0 vs 8 Disambiguation Heuristic ---
        # The KNN often confuses 0 and 8 when downscaled. 
        # We physically inspect the center pixels of the unscaled ROI to verify.
        if pred_char in ['0', '8', 'O', 'o']:
            h_roi, w_roi = roi.shape
            # Extract the center 30% of the character
            cy_start, cy_end = int(h_roi * 0.35), int(h_roi * 0.65)
            cx_start, cx_end = int(w_roi * 0.35), int(w_roi * 0.65)
            
            center_region = roi[cy_start:cy_end, cx_start:cx_end]
            if center_region.size > 0:
                # Calculate how much of the center is filled with white pixels
                fill_ratio = cv2.countNonZero(center_region) / center_region.size
                
                # An '8' has a center crossbar (high fill ratio), a '0' is hollow (low fill ratio)
                if fill_ratio > 0.2:
                    pred_char = '8'
                else:
                    pred_char = '0'
        # ---------------------------------------

        detected_chars.append((x, pred_char))

    # Sort characters by X-coordinate to read left-to-right
    detected_chars.sort(key=lambda item: item[0])
    pred_str = "".join([char for x, char in detected_chars])
    
    return parse_odds(pred_str), pred_str

def get_gta_window_info():
    """Gets GTA V actual rendering bounds, ignoring Windows title bars and borders."""
    try:
        hwnd = win32gui.FindWindow(None, "Grand Theft Auto V")
        if hwnd:
            # Get the exact rendering resolution of the game (excludes title bar)
            client_rect = win32gui.GetClientRect(hwnd)
            win_w = client_rect[2] - client_rect[0]
            win_h = client_rect[3] - client_rect[1]
            
            # Map the inner window coordinate (0,0) to absolute screen coordinates
            top_left = win32gui.ClientToScreen(hwnd, (0, 0))
            win_x, win_y = top_left[0], top_left[1]
            
            if win_w > 0 and win_h > 0:
                return hwnd, win_x, win_y, win_w, win_h
    except Exception:
        pass
    return None, 0, 0, 0, 0

def get_dynamic_boxes(width, height):
    """Calculates coordinates mathematically based on verified 1024x768 baseline."""
    mult_w = width / 1024.0
    mult_h = height / 768.0

    boxes = []
    base_y_coords = [243, 330, 416, 503, 589, 676]  
    base_x = 120
    base_width = 58
    base_height = 32

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

        print(f"\nTaking screenshot of game window... ({win_w}x{win_h})")
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
                
                # Click the center of the horse odds box
                click_x = win_x + target_box[0] + (target_box[2] * 3)  # multiplier takes account of the slower in-game cursor speed
                click_y = win_y + target_box[1] + (target_box[3] // 3)
                
                pydirectinput.moveTo(int(click_x), int(click_y))
                pydirectinput.mouseDown()
                pydirectinput.mouseUp()
                print(f"Clicked Horse {best_horse_idx + 1} at ({click_x}, {click_y})")
                time.sleep(0.5)
                
                pydirectinput.keyDown('tab')
                pydirectinput.keyUp('tab')
                print("Pressed Tab")
                
                # Click "Place Bet" button (Converted to 1024x768 baseline)
                button_x = win_x + (656 / 1024.0) * win_w
                button_y = win_y + (562 / 768.0) * win_h
                pydirectinput.moveTo(int(button_x), int(button_y))
                pydirectinput.mouseDown()
                pydirectinput.mouseUp()
                
                print("Bet placed. Waiting for race to finish (~34s)...")
                time.sleep(34)

                # Get the winnings using the 1024x768 baseline modifiers
                mult_w = win_w / 1024.0
                mult_h = win_h / 768.0
                
                y_coord = int(500 * mult_h)
                h_coord = int(57 * mult_h)
                x_coord = int(500 * mult_w)
                w_coord = int(162 * mult_w)
                
                print("Checking for winnings...")
                winnings_img = pyautogui.screenshot(region=(win_x + x_coord, win_y + y_coord, w_coord, h_coord))
                winnings_crop = cv2.cvtColor(np.array(winnings_img), cv2.COLOR_RGB2BGR)

                if DEBUG_MODE:
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_winnings_{int(time.time())}.png"), winnings_crop)
                
                # Coordinates for top 3 horses (1024x768 scale)
                x2, x1, x3 = int(250 * mult_w), int(400 * mult_w), int(550 * mult_w)
                y1, y2 = int(500 * mult_h), int(480 * mult_h)
                h, w = int(53 * mult_h), int(85 * mult_w)
                
                finish_img = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
                finish_src = cv2.cvtColor(np.array(finish_img), cv2.COLOR_RGB2BGR)
                
                first_crop = finish_src[y2:y2+h, x1:x1+w]
                second_crop = finish_src[y1:y1+h, x2:x2+w]
                third_crop = finish_src[y1:y1+h, x3:x3+w]
                
                if DEBUG_MODE:
                    timestamp = int(time.time())
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_finish_screen_{timestamp}.png"), finish_src)
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_first_place_{timestamp}.png"), first_crop)
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_second_place_{timestamp}.png"), second_crop)
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_third_place_{timestamp}.png"), third_crop)
                
                _, o1_str = read_odds(model, first_crop, 1)
                _, o2_str = read_odds(model, second_crop, 2)
                _, o3_str = read_odds(model, third_crop, 3)

                print("Getting the odds of the first three horses:")
                print(f"First place: {o1_str}")
                print(f"Second place: {o2_str}")
                print(f"Third place: {o3_str}")
                
                res, pred_str = read_odds(model, winnings_crop, 0)
                
                if res > 0:
                    print(f"Winnings prediction: {res}")
                    stats.winnings += res
                    stats.races_won += 1
                else:
                    print(f"No winnings detected. Raw OCR: '{pred_str}'")
                    stats.races_lost += 1

                stats.print_stats()
                exit()
            except Exception as e:
                print(f"Error during clicking phase: {e}")
        else:
            print("No valid odds could be read. Refreshing...")
            time.sleep(2)

        time.sleep(1)

if __name__ == "__main__":
    main_loop()