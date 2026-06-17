import os
import sys
import math

def crop_to_rounded_square(img):
    """
    Detects if the input image is a landscape dashboard screenshot (like edited-image.jpg)
    and crops it precisely around the central glowing rounded square to produce a clean icon.
    """
    w, h = img.size
    if w > h:
        # The icon is in the center of the landscape image.
        # In the uploaded 'edited-image.jpg', the rounded square with its purple glow
        # occupies approximately 82% of the vertical height.
        cx, cy = w // 2, h // 2
        side = int(h * 0.82)
        
        left = max(0, cx - (side // 2))
        top = max(0, cy - (side // 2))
        right = min(w, cx + (side // 2))
        bottom = min(h, cy + (side // 2))
        
        print(f"[AUTO-CROP] Landscape image detected ({w}x{h}).")
        print(f"[AUTO-CROP] Cropping around the central rounded square: ({left}, {top}) to ({right}, {bottom})")
        return img.crop((left, top, right, bottom))
    return img

def build_vector_design(size=512):
    """
    Programmatically renders a high-fidelity white-on-black vector horse 
    icon from scratch to match the binary theme of the vision system.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter
    except ImportError:
        print("Pillow is required. Please install it using: pip install pillow")
        sys.exit(1)

    # Base canvas with transparency channel
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    cx, cy = size // 2, size // 2

    # 1. Base Dark Slate Container (Chiseled App Frame)
    padding = 20
    rect_coords = [padding, padding, size - padding, size - padding]
    
    # Soft back-glow to lift the icon off the desktop background
    glow = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    glow_draw = ImageDraw.Draw(glow)
    glow_draw.rounded_rectangle(rect_coords, radius=110, fill=(16, 185, 129, 45))
    glow = glow.filter(ImageFilter.GaussianBlur(16))
    img = Image.alpha_composite(img, glow)
    draw = ImageDraw.Draw(img)

    # Main structural backing plate (Deep Black/Slate)
    draw.rounded_rectangle(rect_coords, radius=110, fill=(10, 15, 26, 255), outline=(255, 255, 255, 15), width=3)

    # 2. Tech Calibration Wheel Rings (Vision System Theme)
    outer_r = 175
    draw.ellipse([cx - outer_r, cy - outer_r, cx + outer_r, cy + outer_r], outline=(16, 185, 129, 180), width=5)
    draw.ellipse([cx - 145, cy - 145, cx + 145, cy + 145], outline=(255, 255, 255, 40), width=2)
    draw.ellipse([cx - 115, cy - 115, cx + 115, cy + 115], outline=(16, 185, 129, 60), width=1)

    # Angular calibration ticks 
    for angle in range(0, 360, 15):
        rad = math.radians(angle)
        x1 = cx + int((outer_r - 10) * math.cos(rad))
        y1 = cy + int((outer_r - 10) * math.sin(rad))
        x2 = cx + int((outer_r + 10) * math.cos(rad))
        y2 = cy + int((outer_r + 10) * math.sin(rad))
        draw.line([x1, y1, x2, y2], fill=(16, 185, 129, 140), width=2)

    # 3. Stylized High-Contrast White Racing Horse (Clean contours)
    horse_color = (255, 255, 255, 255)
    border_color = (240, 243, 248, 255)
    
    # Polygon point layout for geometric horse bust profile
    horse_pts = [
        (215, 365), # Base of neck
        (195, 305), # Chest curve
        (205, 245), # Neck front
        (235, 215), # Jaw curve start
        (265, 175), # Snout top bridge
        (325, 195), # Nose tip
        (345, 230), # Muzzle lower curve
        (305, 250), # Mouth gap indentation
        (285, 240), # Jaw curve back base
        (275, 290), # Mane structural curve mid
        (295, 335), # Mane lower segment
        (255, 375), # Shoulder terminal edge
    ]
    draw.polygon(horse_pts, fill=horse_color, outline=border_color, width=3)
    
    # Matching crisp geometric ear
    ear_pts = [(235, 215), (215, 155), (245, 180)]
    draw.polygon(ear_pts, fill=horse_color, outline=border_color, width=2)

    # 4. Binary Betting Target Token (Bottom Right Highlight)
    token_x, token_y, token_r = 335, 315, 52
    draw.ellipse([token_x - token_r, token_y - token_r, token_x + token_r, token_y + token_r], 
                 fill=(16, 185, 129, 255), outline=(255, 255, 255, 220), width=4)
    
    # Invariant split lines inside the green token
    for angle in range(0, 360, 45):
        rad = math.radians(angle)
        x1 = token_x + int((token_r - 12) * math.cos(rad))
        y1 = token_y + int((token_r - 12) * math.sin(rad))
        x2 = token_x + int(token_r * math.cos(rad))
        y2 = token_y + int(token_r * math.sin(rad))
        draw.line([x1, y1, x2, y2], fill=(255, 255, 255, 255), width=4)

    draw.ellipse([token_x - 32, token_y - 32, token_x + 32, token_y + 32], outline=(255, 255, 255, 130), width=2)

    # Centered procedural white cash symbol line 
    draw.ellipse([token_x - 12, token_y - 12, token_x + 12, token_y + 12], outline=(255, 255, 255, 240), width=3)
    draw.line([token_x, token_y - 20, token_x, token_y + 20], fill=(255, 255, 255, 255), width=4)
    
    # Sharp upward-slanted execution indicator arrow
    arrow_pts = [
        (335, 165), # Arrow tip
        (315, 195), # Left point
        (328, 195), # Joint
        (328, 235), # Base left
        (342, 235), # Base right
        (342, 195), # Joint right
        (355, 195)  # Right point
    ]
    draw.polygon(arrow_pts, fill=(16, 185, 129, 250), outline=(255, 255, 255, 100), width=1)

    return img

def compile_ico():
    try:
        from PIL import Image
    except ImportError:
        print("[ERROR] Pillow library not found.")
        return

    output_ico_path = "icon.ico"
    
    # Check for custom image files (supports both standard 'icon.png' and 'edited-image.jpg')
    possible_inputs = ["icon.png", "edited-image.jpg", "edited-image.png"]
    source_image = None

    for path in possible_inputs:
        if os.path.exists(path):
            print(f"[FOUND] Asset '{path}' detected. Processing...")
            source_image = Image.open(path)
            break

    if source_image is not None:
        # Automatically crop around the rounded square in case it's a landscape dashboard screenshot
        source_image = crop_to_rounded_square(source_image)
    else:
        print(f"[NOT FOUND] Looked for local inputs {possible_inputs}. Generating layout...")
        source_image = build_vector_design(512)
        # Keep a master flat image copy handy
        source_image.save("master_preview.png")
        print("[SAVED] Master flat configuration image written to 'master_preview.png'")

    # Ensure alpha trans-channel is active and combine sizes into Windows ICO format
    ico_dimensions = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    rgba_canvas = source_image.convert("RGBA")
    rgba_canvas.save(output_ico_path, format="ICO", sizes=ico_dimensions)
    print(f"[SUCCESS] Multi-resolution icon stack cleanly embedded to '{output_ico_path}'!")

if __name__ == "__main__":
    compile_ico()