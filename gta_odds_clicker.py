import ctypes
import os
import random
import re
import sys
import time
from pathlib import Path

try:
    import cv2
    import numpy as np
except ImportError:
    raise ImportError("Please install opencv-python and numpy: pip install opencv-python numpy")

try:
    from PIL import ImageGrab
except ImportError:
    raise ImportError("Please install Pillow: pip install pillow")

try:
    import psutil
except ImportError:
    psutil = None

try:
    import pytesseract
except ImportError:
    pytesseract = None


USER32 = ctypes.windll.user32
KERNEL32 = ctypes.windll.kernel32

WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_int, ctypes.c_int)

PROCESS_QUERY_LIMITED_INFORMATION = 0x1000


def find_gta_window(exe_name="GTA_Enhanced.exe"):
    found = []

    def enum_proc(hwnd, lParam):
        if not USER32.IsWindowVisible(hwnd):
            return True

        pid = ctypes.c_ulong()
        USER32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if pid.value == 0:
            return True

        exe_path = get_process_executable(pid.value)
        if not exe_path:
            return True

        if exe_path.lower().endswith(exe_name.lower()):
            found.append(hwnd)
            return False
        return True

    USER32.EnumWindows(WNDENUMPROC(enum_proc), 0)
    return found[0] if found else None


def get_process_executable(pid):
    if psutil:
        try:
            proc = psutil.Process(pid)
            return proc.exe()
        except Exception:
            return None

    PROCESS_QUERY_INFORMATION = 0x0400
    PROCESS_VM_READ = 0x0010
    handle = KERNEL32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION | PROCESS_VM_READ, False, pid)
    if not handle:
        return None

    buffer_len = ctypes.wintypes.DWORD(260)
    buffer = ctypes.create_unicode_buffer(buffer_len.value)
    if ctypes.windll.kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_len)):
        exe_path = buffer.value
    else:
        exe_path = None

    KERNEL32.CloseHandle(handle)
    return exe_path


def get_window_rect(hwnd):
    rect = ctypes.wintypes.RECT()
    if USER32.GetWindowRect(hwnd, ctypes.byref(rect)) == 0:
        raise RuntimeError(f"Failed to get window rect for hwnd {hwnd}")
    return rect.left, rect.top, rect.right, rect.bottom


def capture_window(hwnd):
    left, top, right, bottom = get_window_rect(hwnd)
    if right <= left or bottom <= top:
        raise ValueError("Invalid window rectangle")

    return ImageGrab.grab(bbox=(left, top, right, bottom))


def load_knn_from_model(model_path):
    fs = cv2.FileStorage(str(model_path), cv2.FILE_STORAGE_READ)
    if not fs.isOpened():
        raise FileNotFoundError(f"Could not open model file: {model_path}")

    samples_node = fs.getNode("samples")
    responses_node = fs.getNode("responses")
    samples = samples_node.mat()
    responses = responses_node.mat()
    fs.release()

    knn = cv2.ml.KNearest_create()
    knn.train(samples.astype(np.float32), cv2.ml.ROW_SAMPLE, responses.astype(np.float32))
    return knn


def preprocess_image(pil_image):
    np_img = np.array(pil_image)
    if np_img.ndim == 2:
        gray = np_img
    else:
        gray = cv2.cvtColor(np_img, cv2.COLOR_BGR2GRAY)

    # High contrast binarization tailored for white/bright odds against darker backgrounds.
    _, thresh = cv2.threshold(gray, 170, 255, cv2.THRESH_BINARY_INV)
    thresh = cv2.medianBlur(thresh, 3)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
    return np_img, thresh


def group_contours_by_line(contours):
    boxes = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if w < 6 or h < 8 or w * h < 80:
            continue
        if h > 100 and w > 100:
            continue
        boxes.append((x, y, w, h))

    if not boxes:
        return []

    boxes.sort(key=lambda b: (b[1], b[0]))
    lines = []
    for box in boxes:
        x, y, w, h = box
        matched = False
        for line in lines:
            if abs(line[0] - y) < max(12, h // 2):
                line[1].append(box)
                matched = True
                break
        if not matched:
            lines.append([y, [box]])

    normalized = []
    for y, line_boxes in sorted(lines, key=lambda t: t[0]):
        normalized.append(sorted(line_boxes, key=lambda b: b[0]))
    return normalized


def recognize_char(knn, char_image):
    resized = cv2.resize(char_image, (10, 10), interpolation=cv2.INTER_AREA)
    sample = resized.reshape(1, -1).astype(np.float32)
    ret, result, _, _ = knn.findNearest(sample, k=3)
    code = int(result[0, 0])
    if 32 <= code <= 126:
        return chr(code)
    return "?"


def try_tesseract(pil_image):
    if not pytesseract:
        return []
    text = pytesseract.image_to_string(pil_image, config="--psm 6")
    if not text:
        return []
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines


def extract_text_lines(knn, image, thresh):
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines = group_contours_by_line(contours)
    results = []

    for line in lines:
        text = []
        boxes = []
        for x, y, w, h in line:
            char_roi = thresh[y:y + h, x:x + w]
            char = recognize_char(knn, char_roi)
            text.append(char)
            boxes.append((x, y, w, h))

        if text:
            line_text = "".join(text).replace(" ", "")
            normalized = re.sub(r"[^\d/\\+\.a-zA-Z]", "", line_text)
            if normalized:
                results.append((normalized, boxes))
    return results


def parse_odds(text):
    text = text.strip().lower().replace("\\", "/")
    if text == "even":
        return ("even", 0.5)

    fraction_match = re.match(r"^(\d+)\s*/\s*(\d+)$", text)
    if fraction_match:
        num = int(fraction_match.group(1))
        den = int(fraction_match.group(2))
        if num + den > 0:
            probability = den / (num + den)
            return (f"{num}/{den}", probability)

    decimal_match = re.match(r"^0?\.\d+$", text)
    if decimal_match:
        probability = float(text)
        return (text, probability)

    if text.isdigit():
        value = int(text)
        probability = 1 / (1 + value)
        return (text, probability)

    return None


def choose_best_odds(lines, use_tesseract=False, pil_image=None):
    candidates = []
    for text, boxes in lines:
        parsed = parse_odds(text)
        if parsed:
            candidates.append((parsed[1], text, boxes))

    if use_tesseract and pil_image is not None:
        tesseract_lines = try_tesseract(pil_image)
        for raw in tesseract_lines:
            for token in re.findall(r"\d+\s*/\s*\d+|even|0?\.\d+|\d+", raw.lower()):
                parsed = parse_odds(token)
                if parsed:
                    candidates.append((parsed[1], token, None))

    if not candidates:
        return None

    best_probability = max(item[0] for item in candidates)
    best_candidates = [item for item in candidates if item[0] == best_probability]
    chosen = random.choice(best_candidates)
    return chosen


def make_window_foreground(hwnd):
    USER32.SetForegroundWindow(hwnd)
    time.sleep(0.1)


def mouse_click(x, y):
    USER32.SetCursorPos(int(x), int(y))
    USER32.mouse_event(0x0002, 0, 0, 0, 0)
    USER32.mouse_event(0x0004, 0, 0, 0, 0)


def send_tab_key():
    VK_TAB = 0x09
    KEYEVENTF_KEYUP = 0x0002
    USER32.keybd_event(VK_TAB, 0, 0, 0)
    time.sleep(0.05)
    USER32.keybd_event(VK_TAB, 0, KEYEVENTF_KEYUP, 0)


def click_window_center(window_rect):
    left, top, right, bottom = window_rect
    center_x = left + (right - left) // 2
    center_y = top + (bottom - top) // 2
    print(f"Clicking window center at ({center_x}, {center_y})")
    mouse_click(center_x, center_y)


def click_best_candidate(window_rect, candidate):
    if candidate is None:
        print("No odds candidate found to click.")
        return False

    _, text, boxes = candidate
    if boxes:
        x, y, w, h = boxes[len(boxes) // 2]
        center_x = window_rect[0] + x + w // 2
        center_y = window_rect[1] + y + h // 2
    else:
        center_x = window_rect[0] + (window_rect[2] - window_rect[0]) // 2
        center_y = window_rect[1] + (window_rect[3] - window_rect[1]) // 2

    print(f"Clicking best odds '{text}' at screen coordinates ({center_x}, {center_y})")
    mouse_click(center_x, center_y)
    return True


def main():
    script_dir = Path(__file__).resolve().parent
    model_path = script_dir / "resources" / "data" / "model.yml"
    if not model_path.exists():
        print(f"Model file not found: {model_path}")
        sys.exit(1)

    print(f"Loading kNN model from {model_path}")
    knn = load_knn_from_model(model_path)
    hwnd = find_gta_window()
    if hwnd is None:
        print("Could not find a visible window for GTA_Enhanced.exe")
        sys.exit(1)

    left, top, right, bottom = get_window_rect(hwnd)
    print(f"Found GTA_Enhanced.exe window at {left},{top} - {right},{bottom}")

    pil_image = capture_window(hwnd)
    np_img, thresh = preprocess_image(pil_image)
    lines = extract_text_lines(knn, np_img, thresh)

    if lines:
        print("Detected text lines:")
        for text, boxes in lines:
            print(f"  {text}")
    else:
        print("No character lines detected from kNN model.")

    candidate = choose_best_odds(lines, use_tesseract=True, pil_image=pil_image)
    if not candidate:
        print("No valid odds found.")
        if pytesseract is None:
            print("Install pytesseract for fallback OCR support: pip install pytesseract")
        sys.exit(1)

    best_probability, best_text, _ = candidate
    print(f"Best odds found: {best_text} with implied probability {best_probability:.3f}")

    make_window_foreground(hwnd)
    click_best_candidate((left, top, right, bottom), candidate)
    time.sleep(0.1)
    send_tab_key()
    time.sleep(0.1)
    click_window_center((left, top, right, bottom))


if __name__ == "__main__":
    main()
