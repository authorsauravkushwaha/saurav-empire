#!/usr/bin/env python3
"""
Instagram Poster Generator - Creates branded posts with your photo
Uses your professional headshot as the base for all content
"""
import os
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_heroes

# Configuration
PHOTO_PATH = "assets/your_photo.jpg"  # Place your photo here
OUTPUT_DIR = Path("content/daily") / today_str() / "branded"
BRAND_COLOR = (255, 215, 0)  # Gold accent
BRAND_FONT_BOLD = "assets/fonts/Montserrat-Bold.ttf"
BRAND_FONT_REGULAR = "assets/fonts/Montserrat-Regular.ttf"

# Instagram dimensions
DIMS = {
    'reel_cover': (1080, 1920),      # 9:16
    'post_square': (1080, 1080),     # 1:1
    'post_portrait': (1080, 1350),   # 4:5
    'story': (1080, 1920),           # 9:16
    'carousel': (1080, 1080),        # 1:1
}

def get_font(size, bold=False):
    """Get font with fallbacks"""
    paths = [
        BRAND_FONT_BOLD if bold else BRAND_FONT_REGULAR,
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "C:/Windows/Fonts/montserb.ttf" if bold else "C:/Windows/Fonts/montserr.ttf",
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
    ]
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

def load_your_photo():
    """Load and prepare your photo"""
    if not os.path.exists(PHOTO_PATH):
        # Create placeholder if photo not found
        img = Image.new('RGB', (800, 1000), (30, 30, 40))
        draw = ImageDraw.Draw(img)
        font = get_font(48, bold=True)
        draw.text((400, 500), "PLACE YOUR\nPHOTO HERE", fill=(255, 215, 0), font=font, anchor="mm")
        return img
    
    img = Image.open(PHOTO_PATH).convert('RGB')
    return img

def remove_background_simple(img):
    """Simple background removal using color thresholding"""
    # For professional headshots with solid background, we can mask
    # This is a simplified version - for production use rembg library
    img_rgba = img.convert('RGBA')
    data = img_rgba.getdata()
    
    new_data = []
    for item in data:
        # Detect dark background (charcoal/grey/black)
        r, g, b, a = item
        if r < 50 and g < 50 and b < 50:  # Dark background
            new_data.append((r, g, b, 0))  # Make transparent
        else:
            new_data.append(item)
    
    img_rgba.putdata(new_data)
    return img_rgba

def create_branded_background(width, height, style='gradient'):
    """Create branded background"""
    if style == 'gradient':
        img = Image.new('RGB', (width, height), (15, 15, 25))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            ratio = y / height
            r = int(15 * (1 - ratio) + 45 * ratio)
            g = int(15 * (1 - ratio) + 45 * ratio)
            b = int(25 * (1 - ratio) + 65 * ratio)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        return img
    elif style == 'solid_dark':
        return Image.new('RGB', (width, height), (20, 20, 30))
    elif style == 'brand_gold':
        img = Image.new('RGB', (width, height), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            ratio = y / height
            r = int(255 * ratio)
            g = int(215 * ratio)
            b = int(0)
            draw.line([(0, y), (width, y)], fill=(r, g, b))
        return img
    return Image.new('RGB', (width, height), (20, 20, 30))

def add_gold_accent_line(draw, x1, y1, x2, y2, width=4):
    """Add gold accent line"""
    draw.line([(x1, y1), (x2, y2)], fill=(255, 215, 0), width=width)

def add_gold_rect(draw, x, y, w, h, radius=20):
    """Add gold rounded rectangle"""
    draw.rounded_rectangle([x, y, x+w, y+h], radius=radius, outline=(255, 215, 0), width=3)

def place_photo_on_canvas(canvas, photo, position='center', max_width=None, max_height=None):
    """Place photo on canvas with smart positioning"""
    canvas_w, canvas_h = canvas.size
    photo_w, photo_h = photo.size
    
    if max_width and photo_w > max_width:
        ratio = max_width / photo_w
        photo = photo.resize((max_width, int(photo_h * ratio)), Image.LANCZOS)
    if max_height and photo.height > max_height:
        ratio = max_height / photo.height
        photo = photo.resize((int(photo.width * ratio), max_height), Image.LANCZOS)
    
    photo_w, photo_h = photo.size
    
    if position == 'center':
        x = (canvas_w - photo_w) // 2
        y = (canvas_h - photo_h) // 2
    elif position == 'top':
        x = (canvas_w - photo_w) // 2
        y = 100
    elif position == 'bottom':
        x = (canvas_w - photo_w) // 2
        y = canvas_h - photo_h - 100
    elif position == 'left':
        x = 100
        y = (canvas_h - photo_h) // 2
    elif position == 'right':
        x = canvas_w - photo_w - 100
        y = (canvas_h - photo_h) // 2
    else:
        x, y = position
    
    # Add subtle shadow
    shadow = Image.new('RGBA', photo.size, (0, 0, 0, 0))
    shadow_draw = ImageDraw.Draw(shadow)
    shadow_draw.rounded_rectangle([10, 10, photo.width-10, photo.height-10], 
                                   radius=20, fill=(0, 0, 0, 100))
    
    if photo.mode == 'RGBA':
        canvas.paste(shadow, (x+5, y+5), shadow)
        canvas.paste(photo, (x, y), photo)
    else:
        canvas.paste(shadow, (x+5, y+5), shadow)
        canvas.paste(photo, (x, y))
    
    return canvas

def create_reel_cover_with_photo(photo, output_path, book_data=None):
    """Create Instagram Reel cover (9:16) with your photo"""
    width, height = DIMS['reel_cover']
    
    # Create gradient background
    canvas = create_branded_background(width, height, 'gradient')
    draw = ImageDraw.Draw(canvas)
    
    # Place your photo (upper portion)
    photo_resized = photo.copy()
    photo.thumbnail((700, 900), Image.LANCZOS)
    
    # Position photo in upper third
    x = (width - photo.width) // 2
    y = 150
    
    # Add gold frame around photo
    frame_padding = 8
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle(
        [x-frame_padding, y-frame_padding, x+photo.width+frame_padding, y+photo.height+frame_padding],
        radius=25, outline=(255, 215, 0), width=4
    )
    
    # Paste photo
    canvas.paste(photo, (x, y))
    
    # Add text below photo
    hook_font = get_font(72, bold=True)
    cta_font = get_font(40, bold=True)
    
    hook_text = "Stop writing books nobody reads.\nHere's the 30-day system."
    
    # Wrap text
    lines = wrap_text(hook_text, get_font(72, bold=True), width - 120, draw)
    line_height = 90
    start_y = y + photo.height + 80
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=get_font(72, bold=True))
        text_width = bbox[2] - bbox[0]
        x_text = (width - text_width) // 2
        y_text = start_y + i * line_height
        
        # Shadow
        draw.text((x_text+3, y_text+3), line, font=get_font(72, bold=True), fill=(0, 0, 0, 100))
        draw.text((x_text, y_text), line, font=get_font(72, bold=True), fill=(255, 255, 255))
    
    # CTA button
    cta_y = start_y + len(lines) * 90 + 60
    cta_text = "Free lesson: Link in bio 👆"
    cta_font = get_font(40, bold=True)
    cta_bbox = draw.textbbox((0, 0), cta_text, font=get_font(40, bold=True))
    cta_w = cta_bbox[2] - cta_bbox[0]
    cta_x = (width - cta_w) // 2
    
    # CTA background
    pad = 30
    draw.rounded_rectangle(
        [cta_x - pad, cta_y - pad, cta_x + cta_w + pad, cta_y + 50 + pad],
        radius=25, fill=(255, 215, 0)
    )
    draw.text((cta_x, cta_y), "Free lesson: Link in bio 👆", font=get_font(40, bold=True), fill=(0, 0, 0))
    
    # Hashtags at bottom
    hashtags = "#writerlife #selfpublishing #authorlife #bookmarketing #30daybook"
    tag_font = get_font(28)
    tag_bbox = draw.textbbox((0, 0), hashtags, font=tag_font)
    tag_x = (width - (tag_bbox[2] - tag_bbox[0])) // 2
    tag_y = height - 150
    draw.text((tag_x, tag_y), hashtags, font=tag_font, fill=(200, 200, 220))
    
    canvas.save(output_path, quality=95)
    return output_path

def wrap_text(text, font, max_width, draw):
    """Wrap text to fit within max_width"""
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    return lines

def create_quote_post_with_photo(photo, output_path, quote_data=None):
    """Create square quote post (1:1) with your photo"""
    width, height = DIMS['post_square']
    
    canvas = create_branded_background(width, height, 'solid_dark')
    draw = ImageDraw.Draw(canvas)
    
    # Place photo on left side
    photo_resized = photo.copy()
    photo.thumbnail((400, 500), Image.LANCZOS)
    
    x = 80
    y = (height - photo.height) // 2
    
    # Gold frame
    draw.rounded_rectangle(
        [x-5, y-5, x+photo.width+5, y+photo.height+5],
        radius=20, outline=(255, 215, 0), width=3
    )
    canvas.paste(photo, (x, y))
    
    # Quote text on right
    quote = "Stop writing books nobody reads.\nHere's the 30-day system."
    author = "Saurav Kushwaha"
    
    quote_font = get_font(48, bold=True)
    author_font = get_font(32)
    
    # Right side text area
    text_x = x + photo.width + 60
    text_max_width = width - text_x - 80
    
    lines = wrap_text("Stop writing books nobody reads.\nHere's the 30-day system.", 
                      get_font(48, bold=True), text_max_width, draw)
    
    line_height = 65
    start_y = (height - len(lines) * 65) // 2
    
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=get_font(48, bold=True))
        text_width = bbox[2] - bbox[0]
        # Right align
        x_text = width - text_width - 80
        y_text = start_y + i * line_height
        
        draw.text((x_text+2, y_text+2), line, font=get_font(48, bold=True), fill=(0, 0, 0, 100))
        draw.text((x_text, y_text), line, font=get_font(48, bold=True), fill=(255, 255, 255))
    
    # Author
    author_y = start_y + len(lines) * 65 + 30
    author_text = f"— Saurav Kushwaha"
    bbox = draw.textbbox((0, 0), author_text, font=get_font(32))
    author_x = width - (bbox[2] - bbox[0]) - 80
    draw.text((author_x+1, author_y+1), author_text, font=get_font(32), fill=(0, 0, 0, 100))
    draw.text((author_x, author_y), author_text, font=get_font(32), fill=(255, 215, 0))
    
    # CTA
    cta = "Free lesson: Link in bio 👆"
    cta_font = get_font(28, bold=True)
    cta_bbox = draw.textbbox((0, 0), cta, font=cta_font)
    cta_x = (width - (cta_bbox[2] - cta_bbox[0])) // 2
    cta_y = height - 120
    
    pad = 20
    draw.rounded_rectangle(
        [cta_x - 20, cta_y - 10, cta_x + (cta_bbox[2] - cta_bbox[0]) + 20, cta_y + 40],
        radius=20, fill=(255, 215, 0)
    )
    draw.text((cta_x, cta_y), cta, font=cta_font, fill=(0, 0, 0))
    
    # Hashtags
    hashtags = "#writerlife #selfpublishing #authorlife #bookmarketing #30daybook"
    tag_font = get_font(24)
    tag_bbox = draw.textbbox((0, 0), hashtags, font=tag_font)
    tag_x = (width - (tag_bbox[2] - tag_bbox[0])) // 2
    tag_y = height - 80
    draw.text((tag_x, tag_y), hashtags, font=tag_font, fill=(180, 180, 200))
    
    canvas.save(output_path, quality=95)
    return output_path

def create_carousel_slides_with_photo(photo, output_dir, slides_data):
    """Create carousel slides with your photo on first/last slide"""
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    
    for i, slide in enumerate(slides_data):
        width, height = DIMS['carousel']
        canvas = create_branded_background(width, height, 'gradient')
        draw = ImageDraw.Draw(canvas)
        
        if i == 0:
            # First slide: your photo + title
            photo_resized = photo.copy()
            photo.thumbnail((400, 500), Image.LANCZOS)
            x = (width - photo.width) // 2
            y = 150
            
            # Gold frame
            draw.rounded_rectangle(
                [x-8, y-8, x+photo.width+8, y+photo.height+8],
                radius=25, outline=(255, 215, 0), width=4
            )
            canvas.paste(photo, (x, y))
            
            # Title below photo
            title = slide.get('title', 'The 30-Day Book System')
            title_font = get_font(56, bold=True)
            bbox = draw.textbbox((0, 0), title, font=get_font(56, bold=True))
            title_x = (width - (bbox[2] - bbox[0])) // 2
            title_y = y + photo.height + 40
            draw.text((title_x+2, title_y+2), title, font=get_font(56, bold=True), fill=(0, 0, 0, 100))
            draw.text((title_x, title_y), title, font=get_font(56, bold=True), fill=(255, 255, 255))
            
        elif i == len(slides_data) - 1:
            # Last slide: your photo + CTA
            photo_resized = photo.copy()
            photo.thumbnail((350, 450), Image.LANCZOS)
            x = (width - photo.width) // 2
            y = 150
            
            draw.rounded_rectangle(
                [x-8, y-8, x+photo.width+8, y+photo.height+8],
                radius=25, outline=(255, 215, 0), width=4
            )
            canvas.paste(photo, (x, y))
            
            # CTA
            cta_font = get_font(48, bold=True)
            cta = "Free lesson: Link in bio 👆"
            bbox = draw.textbbox((0, 0), cta, font=get_font(48, bold=True))
            cta_x = (width - (bbox[2] - bbox[0])) // 2
            cta_y = y + photo.height + 60
            
            pad = 30
            draw.rounded_rectangle(
                [cta_x - 30, cta_y - 20, cta_x + (bbox[2] - bbox[0]) + 30, cta_y + 70],
                radius=25, fill=(255, 215, 0)
            )
            draw.text((cta_x, cta_y), cta, font=get_font(48, bold=True), fill=(0, 0, 0))
            
        else:
            # Middle slides: content only
            title = slide.get('title', f'Slide {i+1}')
            body = slide.get('body', '')
            
            title_font = get_font(64, bold=True)
            body_font = get_font(40)
            
            bbox = draw.textbbox((0, 0), title, font=get_font(64, bold=True))
            title_x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((title_x+2, 152), title, font=get_font(64, bold=True), fill=(0, 0, 0, 100))
            draw.text((title_x, 150), title, font=get_font(64, bold=True), fill=(255, 255, 255))
            
            if body:
                lines = wrap_text(body, get_font(40), width - 200, draw)
                for j, line in enumerate(lines):
                    bbox = draw.textbbox((0, 0), line, font=get_font(40))
                    x = (width - (bbox[2] - bbox[0])) // 2
                    y = 300 + j * 55
                    draw.text((x+1, y+1), line, font=body_font, fill=(0, 0, 0, 100))
                    draw.text((x, y), line, font=body_font, fill=(200, 200, 220))
        
        # Slide number
        num_font = get_font(28, bold=True)
        num_text = f"{i+1} / {len(slides_data)}"
        bbox = draw.textbbox((0, 0), num_text, font=num_font)
        num_x = width - bbox[2] - 50
        num_y = height - 80
        draw.text((num_x, num_y), num_text, font=num_font, fill=(255, 215, 0))
        
        # Save
        slide_path = os.path.join(output_dir, f'carousel_{i+1}.png')
        os.makedirs(output_dir, exist_ok=True)
        canvas.save(slide_path, quality=95)
        paths.append(slide_path)
    
    return paths

def generate_all_branded_posts(date_str=None):
    """Generate all branded posts with your photo"""
    if date_str is None:
        date_str = today_str()
    
    # Load your photo
    photo = load_your_photo()
    
    # Output directory
    base = Path(__file__).parent.parent
    day_dir = base / 'content' / 'daily' / date_str / 'branded'
    images_dir = day_dir / 'images'
    os.makedirs(images_dir, exist_ok=True)
    carousel_dir = images_dir / 'carousel'
    os.makedirs(carousel_dir, exist_ok=True)
    
    generated = {}
    
    # 1. Reel cover with photo
    reel_path = images_dir / 'reel_cover_branded.png'
    create_reel_cover_with_photo(photo, str(reel_path))
    generated['reel_cover'] = str(reel_path.relative_to(base))
    
    # 2. Quote post with photo
    quote_path = images_dir / 'quote_branded.png'
    create_quote_post_with_photo(photo, str(quote_path))
    generated['quote_branded'] = str(quote_path.relative_to(base))
    
    # 3. Carousel slides with photo
    slides = [
        {"title": "The 30-Day Book System", "body": "Phase 1: Research (Days 1-7)\nPhase 2: Outline (Days 8-14)\nPhase 3: Draft (Days 15-21)\nPhase 4: Edit (Days 22-26)\nPhase 5: Publish (Days 27-30)"},
        {"title": "Why Most Authors Fail", "body": "1. No market research\n2. Writing for themselves\n3. No launch plan\n4. Inconsistent marketing\n5. Giving up too early"},
        {"title": "My 50-Book Proof", "body": "Every book started with:\n✓ Keyword research\n✓ Competitor analysis\n✓ Outline first\n✓ Daily word count\n✓ Professional cover"},
        {"title": "Ready to Start?", "body": "Join 1000+ authors in\n\"Write & Publish in 30 Days\"\nCourse: ₹2,999\nLink in bio 👆"},
    ]
    carousel_dir = images_dir / 'carousel'
    carousel_paths = create_carousel_slides_with_photo(photo, str(carousel_dir), [
        {"title": "The 30-Day Book System", "body": "Phase 1: Research (Days 1-7)\nPhase 2: Outline (Days 8-14)\nPhase 3: Draft (Days 15-21)\nPhase 4: Edit (Days 22-26)\nPhase 5: Publish (Days 27-30)"},
        {"title": "Why Most Authors Fail", "body": "1. No market research\n2. Writing for themselves\n3. No launch plan\n4. Inconsistent marketing\n5. Giving up too early"},
        {"title": "My 50-Book Proof", "body": "Every book started with:\n✓ Keyword research\n✓ Competitor analysis\n✓ Outline first\n✓ Daily word count\n✓ Professional cover"},
        {"title": "Ready to Start?", "body": "Join 1000+ authors in\n\"Write & Publish in 30 Days\"\nCourse: ₹2,999\nLink in bio 👆"},
    ])
    generated['carousel_branded'] = [str(Path(p).relative_to(Path(__file__).parent.parent)) for p in carousel_paths]
    
    # Save metadata
    metadata = {
        'date': date_str,
        'photo_used': PHOTO_PATH,
        'generated_images': generated
    }
    
    save_json(f'content/daily/{date_str}/branded.json', metadata)
    print(f"[{datetime.now().strftime('%H:%M:%S')}] Branded posts with your photo generated for {date_str}")
    return metadata

# Add datetime import
from datetime import datetime, timezone, timedelta
IST = timezone(timedelta(hours=5, minutes=30))

def main():
    generate_all_branded_posts()
    print("Branded posts with your photo generated!")

if __name__ == '__main__':
    main()