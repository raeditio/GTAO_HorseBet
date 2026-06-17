import cv2
import numpy as np
import pyautogui
import pydirectinput
import time
import os
import win32gui
import argparse
import socket
import webbrowser
import sys
import threading
from dashboard import start_dashboard

try:
    import webview
    USE_WEBVIEW = True
except ImportError:
    USE_WEBVIEW = False

def get_base_path():
    """Get the absolute path to the executable or script location."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

AUTOBET_DIR = os.path.join(os.path.expanduser('~'), 'Documents', 'autobet')
if not os.path.exists(AUTOBET_DIR):
    os.makedirs(AUTOBET_DIR)
    
DEBUG_DIR = os.path.join(AUTOBET_DIR, 'debug')

if not os.path.exists(DEBUG_DIR):
    os.makedirs(DEBUG_DIR)
    
SSL_DIR = os.path.join(AUTOBET_DIR, 'ssl')
if not os.path.exists(SSL_DIR):
    os.makedirs(SSL_DIR)

# --- Argument Parsing ---
arg_parser = argparse.ArgumentParser(description="GTA V Horse Betting Automation")
arg_parser.add_argument('--debug', action='store_true', help="Enable debug mode to save intermediate images.")
args = arg_parser.parse_args()

# --- Global Stats Tracking ---
class BettingStats:
    def __init__(self):
        self.races_won = 0
        self.races_lost = 0
        self.winnings = 0
        self.total_time_running = 0
        self.session_start_time = None
        
    def start_session(self):
        if self.session_start_time is None:
            self.session_start_time = time.time()
            
    def stop_session(self):
        if self.session_start_time is not None:
            self.total_time_running += time.time() - self.session_start_time
            self.session_start_time = None
            
    def get_elapsed_time(self):
        if self.session_start_time:
            return self.total_time_running + (time.time() - self.session_start_time)
        return self.total_time_running
        
    def print_stats(self):
        elapsed = int(self.get_elapsed_time())
        print(f"\n--- SESSION STATS ---")
        print(f"Races Won:  {self.races_won}")
        print(f"Races Lost: {self.races_lost}")
        print(f"Winnings:   {self.winnings}")
        print(f"Time Ran:   {elapsed // 60}m {elapsed % 60}s")
        print(f"---------------------\n")

def get_available_ips():
    try:
        return ["0.0.0.0", "127.0.0.1"] + socket.gethostbyname_ex(socket.gethostname())[2]
    except Exception:
        return ["0.0.0.0", "127.0.0.1"]

class BotState:
    def __init__(self):
        self.running = False
        self.status = "Waiting for start..."
        self.stats = BettingStats()
        self.debug = False
        self.web_hosting = True
        self.game_running = False
        self.host_ip = "0.0.0.0"
        self.available_ips = get_available_ips()
        
    def set_running(self, is_running):
        if is_running and not self.running:
            self.stats.start_session()
        elif not is_running and self.running:
            self.stats.stop_session()
        self.running = is_running

bot_state = BotState()
bot_state.debug = args.debug

if bot_state.debug:
    # Empty directory
    for f in os.listdir(DEBUG_DIR):
        try: os.remove(os.path.join(DEBUG_DIR, f))
        except: pass

def load_knn_model():
    """Loads and verifies the KNN model handling both native and manual YAML formats."""
    filepath = os.path.join(get_base_path(), 'resources', 'data', 'model.yml')
    
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
    """Translates the OCR string prediction into a mathematical odds numerator."""
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

def parse_winnings(pred_str):
    """Translates the OCR string prediction into a winnings integer."""
    pred = pred_str.strip().lower()
    
    # Common OCR mistakes compensation for numbers
    pred = pred.replace('o', '0').replace('l', '1').replace('i', '1').replace('s', '5')
    
    # Extract only digits (removes slashes, spaces, commas, letters, etc)
    digits = ''.join(filter(str.isdigit, pred))
    if digits:
        return int(digits)
    return -1

def read_ocr_string(model, img, debug_prefix):
    """Reads the raw text from an image by parsing individual upscaled character contours."""
    
    # --- UPSCALE PRE-PROCESSING ---
    # Upscale the raw crop by 5x using Cubic interpolation. 
    # This heavily improves edge smoothing and helps Otsu's thresholding isolate characters better.
    upscale_factor = 5
    img = cv2.resize(img, (0, 0), fx=upscale_factor, fy=upscale_factor, interpolation=cv2.INTER_CUBIC)
    
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 1. Increase contrast significantly
    high_contrast = cv2.convertScaleAbs(gray, alpha=2.0, beta=-50)
    
    # 2. Use Otsu's Thresholding (Creates White text on Black background)
    _, thresh = cv2.threshold(high_contrast, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    if bot_state.debug:
        timestamp = int(time.time())
        filename = os.path.join(DEBUG_DIR, f"debug_{debug_prefix}_{timestamp}.png")
        cv2.imwrite(filename, thresh)
        
    # findContours NEEDS White text on a Black background to work
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    detected_chars = []
    
    # Because we upscaled the image, the minimum contour area (noise filter) needs to scale accordingly
    min_contour_area = 5 * (upscale_factor * upscale_factor)
    
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        if w * h < min_contour_area:  
            continue
            
        # Crop the White-on-Black character
        roi = thresh[y:y+h, x:x+w]
        
        # 3. INVERT the character to Black-on-White!
        # The KNN model was trained on Black text on a White background.
        roi_inverted = cv2.bitwise_not(roi)
        
        # Resize to 10x10 to match the 100 columns expected by model.yml (THIS MUST STAY 10x10)
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
    
    return pred_str

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
    
    if model is None:
        print("Exiting due to model load failure.")
        bot_state.status = "Failed to load model"
        return
        
    consecutive_read_failures = 0
    was_running = False

    while True:
        hwnd, win_x, win_y, win_w, win_h = get_gta_window_info()
        bot_state.game_running = bool(hwnd)
        
        if not bot_state.running:
            if bot_state.status not in ["Stopped (GTA lost focus)", "Failed to load model"]:
                bot_state.status = "Paused - Ready to Start"
            was_running = False
            time.sleep(1)
            continue

        if not was_running:
            bot_state.status = "Starting in 5s... Switch to GTA!"
            print("Starting in 5 seconds... Switch to GTA V!")
            time.sleep(5)
            was_running = True
        
        if not hwnd or win32gui.GetForegroundWindow() != hwnd:
            print("GTA V lost focus. Stopping automation.")
            bot_state.set_running(False)
            bot_state.status = "Stopped (GTA lost focus)"
            was_running = False
            
            time.sleep(1)
            continue

        bot_state.status = "Reading Odds"
        print(f"\nTaking screenshot of game window... ({win_w}x{win_h})")
        screenshot = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
        frame = cv2.cvtColor(np.array(screenshot), cv2.COLOR_RGB2BGR)

        dynamic_boxes = get_dynamic_boxes(win_w, win_h)

        odds_list = []
        raw_list = []
        for i, (x, y, w, h) in enumerate(dynamic_boxes):
            crop = frame[y:y+h, x:x+w]
            raw_str = read_ocr_string(model, crop, f"horse{i+1}")
            odds = parse_odds(raw_str)
            
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
            consecutive_read_failures = 0
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
                print("Bet Maxed")
                
                # Click "Place Bet" button (Converted to 1024x768 baseline)
                button_x = win_x + (656 / 1024.0) * win_w
                button_y = win_y + (562 / 768.0) * win_h
                pydirectinput.moveTo(int(button_x), int(button_y))
                pydirectinput.mouseDown()
                pydirectinput.mouseUp()
                
                print("Bet placed. Waiting for race to finish (~34s)...")
                bot_state.status = "Waiting for race to finish (~34s)"
                
                interrupted = False
                for _ in range(34):
                    if not bot_state.running or win32gui.GetForegroundWindow() != hwnd:
                        bot_state.set_running(False)
                        bot_state.status = "Stopped (GTA lost focus)"
                        interrupted = True
                        break
                    time.sleep(1)
                    
                if interrupted:
                    was_running = False
                    continue

                # Get the winnings using the 1024x768 baseline modifiers
                mult_w = win_w / 1024.0
                mult_h = win_h / 768.0
                
                y_coord = int(500 * mult_h)
                h_coord = int(57 * mult_h)
                x_coord = int(510 * mult_w)
                w_coord = int(150 * mult_w)
                
                print("Checking for winnings...")
                winnings_img = pyautogui.screenshot(region=(win_x + x_coord, win_y + y_coord, w_coord, h_coord))
                winnings_crop = cv2.cvtColor(np.array(winnings_img), cv2.COLOR_RGB2BGR)

                if bot_state.debug:
                    cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_winnings_{int(time.time())}.png"), winnings_crop)
                
                # Coordinates for top 3 horses (1024x768 scale)
                x2, x1, x3 = int(15 * mult_w), int(365 * mult_w), int(735 * mult_w)
                y1, y2 = int(500 * mult_h), int(485 * mult_h)
                h, w = int(53 * mult_h), int(85 * mult_w)
                
                def is_valid_odds(val, text):
                    return val > 0 and ('/' in text or 'even' in text.lower() or 'evn' in text.lower() or 'eve' in text.lower())

                for attempt in range(3):
                    print(f"Checking for winnings... (Attempt {attempt + 1})")
                    winnings_img = pyautogui.screenshot(region=(win_x + x_coord, win_y + y_coord, w_coord, h_coord))
                    winnings_crop = cv2.cvtColor(np.array(winnings_img), cv2.COLOR_RGB2BGR)

                    if bot_state.debug:
                        cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_winnings_{int(time.time())}.png"), winnings_crop)
                    
                    finish_img = pyautogui.screenshot(region=(win_x, win_y, win_w, win_h))
                    finish_src = cv2.cvtColor(np.array(finish_img), cv2.COLOR_RGB2BGR)
                    
                    first_crop = finish_src[y1:y1+h, x1:x1+w]
                    second_crop = finish_src[y2:y2+h, x2:x2+w]
                    third_crop = finish_src[y2:y2+h, x3:x3+w]
                    
                    if bot_state.debug:
                        timestamp = int(time.time())
                        cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_finish_screen_{timestamp}.png"), finish_src)
                        cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_first_place_{timestamp}.png"), first_crop)
                        cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_second_place_{timestamp}.png"), second_crop)
                        cv2.imwrite(os.path.join(DEBUG_DIR, f"debug_third_place_{timestamp}.png"), third_crop)
                    
                    o1_str = read_ocr_string(model, first_crop, "first_place")
                    o1_val = parse_odds(o1_str)
                    
                    o2_str = read_ocr_string(model, second_crop, "second_place")
                    o2_val = parse_odds(o2_str)
                    
                    o3_str = read_ocr_string(model, third_crop, "third_place")
                    o3_val = parse_odds(o3_str)

                    print("Getting the odds of the first three horses:")
                    print(f"First place: {o1_str}")
                    print(f"Second place: {o2_str}")
                    print(f"Third place: {o3_str}")
                    
                    if is_valid_odds(o1_val, o1_str) and is_valid_odds(o2_val, o2_str) and is_valid_odds(o3_val, o3_str):
                        break
                        
                    if attempt < 2:
                        print("Finish screen odds are unreadable or not fractions/evens. Retrying in 2 seconds...")
                        time.sleep(2)
                
                # Reading and parsing winnings accurately
                pred_str = read_ocr_string(model, winnings_crop, "winnings")
                res = parse_winnings(pred_str)
                
                if res > 0 or '+' in pred_str:
                    expected_winnings = 10000 * (odds_list[best_horse_idx] + 1)
                    if res != expected_winnings:
                        print(f"Winnings prediction misread as {res}. Overriding to expected math: {expected_winnings} [Raw OCR: '{pred_str}']")
                        res = expected_winnings
                    else:
                        print(f"Winnings prediction: {res} [Raw OCR: '{pred_str}']")
                        
                    bot_state.stats.winnings += res
                    bot_state.stats.races_won += 1
                else:
                    print(f"No winnings detected. Raw OCR: '{pred_str}'")
                    bot_state.stats.races_lost += 1

                bot_state.stats.print_stats()
                
                if win32gui.GetForegroundWindow() != hwnd:
                    bot_state.set_running(False)
                    bot_state.status = "Stopped (GTA lost focus)"
                    was_running = False
                    continue
                
                # Click "Place Bet" button (Converted to 1024x768 baseline)
                button2_x = win_x + win_w // 2
                button2_y = win_y + int(705 * mult_h)
                pydirectinput.moveTo(int(button2_x), int(button2_y))
                pydirectinput.mouseDown()
                pydirectinput.mouseUp()
                button3_x = win_x + win_w * 3 // 4
                button3_y = win_y + int(605 * mult_h)
                pydirectinput.moveTo(int(button3_x), int(button3_y))
                pydirectinput.mouseDown()
                pydirectinput.mouseUp()
                time.sleep(2)
                
            except Exception as e:
                print(f"Error during clicking phase: {e}")
        else:
            consecutive_read_failures += 1
            print(f"No valid odds could be read. Refreshing... (Attempt {consecutive_read_failures}/5)")
            
            if consecutive_read_failures >= 5:
                print("Failsafe triggered: Attempting to clear stuck screen...")
                bot_state.status = "Running Failsafe..."
                
                if win32gui.GetForegroundWindow() != hwnd:
                    bot_state.set_running(False)
                    bot_state.status = "Stopped (GTA lost focus)"
                    was_running = False
                    continue
                    
                try:
                    mult_w = win_w / 1024.0
                    mult_h = win_h / 768.0
                    
                    button2_x = win_x + win_w // 2
                    button2_y = win_y + int(705 * mult_h)
                    pydirectinput.moveTo(int(button2_x), int(button2_y))
                    pydirectinput.mouseDown()
                    pydirectinput.mouseUp()
                    time.sleep(1)
                    
                    button3_x = win_x + win_w * 3 // 4
                    button3_y = win_y + int(605 * mult_h)
                    pydirectinput.moveTo(int(button3_x), int(button3_y))
                    pydirectinput.mouseDown()
                    pydirectinput.mouseUp()
                except Exception as e:
                    print(f"Error during failsafe phase: {e}")
                    
                consecutive_read_failures = 0
                
            time.sleep(2)

        time.sleep(1)

if __name__ == "__main__":
    host_ip = "0.0.0.0"
    
    cert_path = None
    key_path = None
    
    if os.path.exists(SSL_DIR):
        for f in os.listdir(SSL_DIR):
            if f.endswith('.key') or (f.endswith('.pem') and 'key' in f.lower()):
                key_path = os.path.join(SSL_DIR, f)
            elif f.endswith(('.crt', '.cer')) or (f.endswith('.pem') and 'key' not in f.lower()):
                cert_path = os.path.join(SSL_DIR, f)
                
    if cert_path and key_path:
        protocol = "https"
    else:
        protocol = "http"
        
    browse_url = f"{protocol}://127.0.0.1:8027"
    
    if USE_WEBVIEW:
        print(f"Opening Dashboard in App Window: {browse_url}")
        start_dashboard(bot_state, host_ip)
        
        # Move the bot loop to a background thread so the GUI can run on the main thread
        bot_thread = threading.Thread(target=main_loop, daemon=True)
        bot_thread.start()
        
        # Set custom window icon if provided
        icon_path = os.path.join(get_base_path(), 'resources', 'icon.ico')
        icon_path = icon_path if os.path.exists(icon_path) else None
        
        window = webview.create_window('GTAO HorseBet', browse_url, width=750, height=900, background_color='#11111b')
        webview.start(icon=icon_path)
    else:
        print(f"Opening Dashboard in browser: {browse_url}")
        print("[INFO] Install 'pywebview' (pip install pywebview) to open the dashboard as a standalone application.")
        webbrowser.open(browse_url)
        
        start_dashboard(bot_state, host_ip)
        main_loop()