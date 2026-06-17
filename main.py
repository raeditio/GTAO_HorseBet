"""This script detects the GTA5_Enhanced.exe window and captures the screen.
Using the pretrained model, it reads odds text from the game screen, selects the most probable choice,
and clicks that choice. It then simulates a "Tab" keypress after a short delay and clicks the center of the screen.
"""
import argparse
import re
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import win32gui
from PIL import ImageGrab

MODEL_PATH = Path(__file__).resolve().parent / "resources" / "data" / "model.yml"


def find_gta_window():
    candidates = [
        'gta5_enhanced.exe',
        'gta_enhanced.exe',
        'grand theft auto v enhanced',
        'grand theft auto v',
    ]

    def enum_windows_callback(hwnd, windows):
        if not win32gui.IsWindowVisible(hwnd):
            return
        title = win32gui.GetWindowText(hwnd).lower()
        for cand in candidates:
            if cand in title:
                windows.append(hwnd)
                return

    windows = []
    win32gui.EnumWindows(enum_windows_callback, windows)
    return windows[0] if windows else None


def capture_gta_window(hwnd):
    left, top, right, bottom = win32gui.GetWindowRect(hwnd)
    return ImageGrab.grab(bbox=(left, top, right, bottom)), (left, top), (right - left, bottom - top)


def preprocess_image(image):
    gray = cv2.cvtColor(np.array(image), cv2.COLOR_BGR2GRAY)
    blurred = cv2.GaussianBlur(gray, (3, 3), 0)
    thresh = cv2.adaptiveThreshold(
        blurred,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY_INV,
        11,
        2,
    )
    return thresh


def load_model():
    if not MODEL_PATH.exists():
        raise FileNotFoundError(f"Pretrained model not found at {MODEL_PATH}")
    return cv2.ml.KNearest_load(str(MODEL_PATH))


def predict_character(model, roi):
    if roi.size == 0:
        return '?'
    try:
        resized = cv2.resize(roi, (10, 10))
    except cv2.error:
        return '?'
    sample = resized.reshape((1, 100)).astype(np.float32)
    _, results, _, _ = model.findNearest(sample, k=10)
    val = int(results[0][0])
    try:
        return chr(val)
    except ValueError:
        return '?'


def parse_odds_text(text):
    if not text:
        return None
    normalized = text.lower().strip()
    if '?' in normalized:
        return None

    if normalized in ('evens', 'even'):
        return 1.0

    if normalized == '0':
        return None

    m = re.match(r'^(\d+)\s*[/: -]\s*(\d+)$', normalized)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        if a + b == 0:
            return None
        return float(b) / float(a + b)

    m = re.match(r'^\+?(\d+)$', normalized)
    if m:
        a = int(m.group(1))
        if a + 1 == 0:
            return None
        return 1.0 / float(a + 1)

    m = re.search(r'(\d+)', normalized)
    if m:
        a = int(m.group(1))
        if a + 1 == 0:
            return None
        return 1.0 / float(a + 1)

    return None


def get_reference_odds_regions(window_size):
    multiplierW = window_size[0] / 2560.0
    multiplierH = window_size[1] / 1440.0

    x2 = int(round(220 * multiplierW))
    x1 = int(round(965 * multiplierW))
    x3 = int(round(1755 * multiplierW))
    y1 = int(round(1040 * multiplierH))
    y2 = int(round(1070 * multiplierH))
    h = int(round(75 * multiplierH))
    w = int(round(160 * multiplierW))

    return [
        {'name': 'second', 'rect': (x2, y1, w, h)},
        {'name': 'first', 'rect': (x1, y2, w, h)},
        {'name': 'third', 'rect': (x3, y1, w, h)},
    ]


def odd_to_short(odd_text):
    if not odd_text:
        return -1
    s = odd_text.strip().lower()
    if 'even' in s:
        return 1

    m = re.match(r'^(\d+)\s*[/: -]\s*(\d+)$', s)
    if m:
        a = int(m.group(1))
        b = int(m.group(2))
        if b == 0:
            return -1
        val = a // b if a % b == 0 else a
        if val <= 0:
            return -1
        return min(val, 10)

    m = re.match(r'^\+?(\d+)$', s)
    if m:
        val = int(m.group(1))
        return min(val, 10) if val > 0 else -1

    return -1


def get_basic_betting_position(odds_texts):
    if len(odds_texts) != 6:
        return -1

    res = [-1] * 6
    for i in range(6):
        b_res = odd_to_short(odds_texts[i])
        if b_res <= 5 and b_res in res:
            return -1
        res[i] = b_res

    if 1 in res:
        lowest = -1
        for r in res:
            if (lowest == -1 or r < lowest) and r != 1:
                lowest = r
        if lowest != -1 and lowest < 4:
            return -1

    lowest_pos = 0
    lowest_val = res[0]
    for i in range(1, 6):
        if res[i] == -1:
            continue
        if lowest_val == -1 or res[i] < lowest_val:
            lowest_val = res[i]
            lowest_pos = i

    return lowest_pos if lowest_val != -1 else -1


def group_contours(contours):
    regions = []
    for cnt in contours:
        x, y, w, h = cv2.boundingRect(cnt)
        if cv2.contourArea(cnt) < 50:
            continue
        if h <= 28 or w < 9 or w > 28:
            continue
        regions.append((x, y, w, h))

    regions.sort(key=lambda item: (item[1], item[0]))
    groups = []
    for x, y, w, h in regions:
        matched = False
        for group in groups:
            gx, gy, gw, gh, items = group
            if abs(y - gy) < 20:
                group[0] = min(gx, x)
                group[1] = min(gy, y)
                group[2] = max(gw, x + w - gx)
                group[3] = max(gh, y + h - gy)
                items.append((x, y, w, h))
                matched = True
                break
        if not matched:
            groups.append([x, y, w, h, [(x, y, w, h)]])
    return groups


def extract_odds_choices(model, thresh_image, debug=False):
    contours, _ = cv2.findContours(thresh_image, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    groups = group_contours(contours)
    choices = []
    vis = cv2.cvtColor(thresh_image, cv2.COLOR_GRAY2BGR)
    for gx, gy, gw, gh, items in groups:
        items.sort(key=lambda item: item[0])
        text = ''
        for x, y, w, h in items:
            roi = thresh_image[y:y + h, x:x + w]
            char = predict_character(model, roi)
            text += char
            if debug:
                cv2.rectangle(vis, (x, y), (x + w, y + h), (0, 255, 0), 1)
                cv2.putText(vis, char, (x, y - 2), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)
        odds_value = parse_odds_text(text)
        if odds_value is not None:
            choices.append({'text': text, 'value': odds_value, 'rect': (gx, gy, gw, gh)})
            if debug:
                cv2.rectangle(vis, (gx, gy), (gx + gw, gy + gh), (255, 0, 0), 2)
                cv2.putText(vis, text, (gx, gy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 0, 0), 2)
    return choices, vis


def annotate_odds_snapshot(image, choices, reference_regions=None):
    annotated = cv2.cvtColor(np.array(image), cv2.COLOR_RGB2BGR)
    if reference_regions:
        for ref in reference_regions:
            gx, gy, gw, gh = ref['rect']
            label = f"ref:{ref['name']}"
            cv2.rectangle(annotated, (gx, gy), (gx + gw, gy + gh), (255, 255, 0), 2)
            cv2.putText(annotated, label, (gx, max(gy - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)

    for choice in choices:
        gx, gy, gw, gh = choice['rect']
        label = choice['text']
        cv2.rectangle(annotated, (gx, gy), (gx + gw, gy + gh), (0, 255, 0), 2)
        cv2.putText(annotated, label, (gx, max(gy - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    return annotated


def choose_best_choice(choices):
    if not choices:
        return None
    return max(choices, key=lambda c: c['value'])


def run_click_sequence(window_offset, window_size, best_choice):
    if best_choice:
        gx, gy, gw, gh = best_choice['rect']
        left, top = window_offset
        click_x = left + gx + gw // 2
        click_y = top + gy + gh // 2
        pyautogui.click(x=click_x, y=click_y)
        print(f"Clicked choice '{best_choice['text']}' at screen position ({click_x}, {click_y})")
    else:
        print("No valid odds choice detected; skipping choice click.")

    time.sleep(0.5)
    pyautogui.press('tab')
    left, top = window_offset
    window_width, window_height = window_size
    pyautogui.click(x=left + window_width // 2, y=top + window_height // 2)
    print("Pressed Tab and clicked center of the detected GTA window.")


def main():
    parser = argparse.ArgumentParser(description='GTA odds clicker')
    parser.add_argument('--debug', action='store_true', help='Show debug visuals for detection')
    args = parser.parse_args()

    gta_window = find_gta_window()
    if not gta_window:
        print("GTA window not found.")
        return

    window_text = win32gui.GetWindowText(gta_window)
    left, top, right, bottom = win32gui.GetWindowRect(gta_window)
    print(f"Detected GTA window: '{window_text}' at ({left}, {top}, {right}, {bottom})")

    try:
        model = load_model()
    except FileNotFoundError as exc:
        print(exc)
        return

    while True:
        screenshot, window_offset, window_size = capture_gta_window(gta_window)
        reference_regions = get_reference_odds_regions(window_size)
        processed_image = preprocess_image(screenshot)
        choices, vis = extract_odds_choices(model, processed_image, debug=args.debug)
        best_choice = choose_best_choice(choices)

        if len(choices) == 6:
            odds_texts = [c['text'] for c in choices]
            bet_pos = get_basic_betting_position(odds_texts)
            if 0 <= bet_pos < 6:
                print(f"Betting algorithm selected position: {bet_pos} (odd={odds_texts[bet_pos]})")
                best_choice = choices[bet_pos]

        if choices:
            print("Detected choices:")
            for c in choices:
                print(f" - {c['text']} => {c['value']} at {c['rect']}")
            if best_choice:
                print(f"Best odds detected: {best_choice['text']} (value={best_choice['value']})")
        else:
            print("No odds detected in the current frame.")

        if args.debug:
            snapshot = annotate_odds_snapshot(screenshot, choices, reference_regions)
            snapshot_path = Path.cwd() / 'debug_snapshot.png'
            cv2.imwrite(str(snapshot_path), snapshot)
            print(f"Saved debug snapshot with labeled odds to {snapshot_path}")
            for ref in reference_regions:
                gx, gy, gw, gh = ref['rect']
                cv2.rectangle(vis, (gx, gy), (gx + gw, gy + gh), (255, 255, 0), 2)
                cv2.putText(vis, f"ref:{ref['name']}", (gx, max(gy - 10, 0)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            cv2.imshow('thresh', processed_image)
            cv2.imshow('detection', vis)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                print('Debug exit')
                break

        run_click_sequence(window_offset, window_size, best_choice)
        time.sleep(30)

    if args.debug:
        cv2.destroyAllWindows()


if __name__ == '__main__':
    main()
