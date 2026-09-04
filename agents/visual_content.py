#!/usr/bin/env python3
"""
Visual Content Generator - Creates quote images, carousel slides, story templates
Zero API dependencies - uses local PIL only
"""
import os
import json
import random
from datetime import datetime, timezone, timedelta
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.github_io import load_json, save_json, today_str, load_books, load_heroes

IST = timezone(timedelta(hours=5, minutes=30))

# Color palettes for different vibes
PALETTES = {
    'motivation': {
        'bg': [(25, 25, 35), (45, 45, 65)],  # Dark blue gradient
        'text': (255, 255, 255),
        'accent': (255, 215, 0),  # Gold
        'secondary': (200, 200, 220)
    },
    'education': {
        'bg': [(15, 35, 55), (35, 65, 95)],  # Blue gradient
        'text': (255, 255, 255),
        'accent': (0, 200, 255),  # Cyan
        'secondary': (180, 210, 240)
    },
    'personal': {
        'bg': [(55, 25, 45), (85, 45, 75)],  # Purple-pink gradient
        'text': (255, 255, 255),
        'accent': (255, 100, 200),  # Pink
        'secondary': (230, 180, 220)
    },
    'business': {
        'bg': [(20, 50, 30), (40, 80, 55)],  # Green gradient
        'text': (255, 255, 255),
        'accent': (50, 255, 150),  # Mint
        'secondary': (180, 230, 200)
    }
}

# Instagram dimensions
DIMENSIONS = {
    'reel_cover': (1080, 1920),      # 9:16
    'post_square': (1080, 1080),     # 1:1
    'post_portrait': (1080, 1350),   # 4:5
    'story': (1080, 1920),           # 9:16
    'carousel': (1080, 1080),        # 1:1 per slide
}

def get_font(size, bold=False):
    """Get system font with fallback"""
    font_paths = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Helvetica.ttc",
        "C:/Windows/Fonts/arialbd.ttf",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for path in font_paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except:
                continue
    return ImageFont.load_default()

def create_gradient_bg(width, height, colors):
    """Create gradient background"""
    img = Image.new('RGB', (width, height), colors[0])
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = int(colors[0][0] * (1 - ratio) + colors[1][0] * ratio)
        g = int(colors[0][1] * (1 - ratio) + colors[1][1] * ratio)
        b = int(colors[0][2] * (1 - ratio) + colors[1][2] * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    return img

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

def create_quote_image(quote, author, category, output_path, dim='post_square'):
    """Create a quote image"""
    width, height = DIMENSIONS[dim]
    palette = PALETTES.get(category, PALETTES['motivation'])
    
    # Create gradient background
    img = create_gradient_bg(width, height, palette['bg'])
    
    # Add subtle texture/noise
    noise = Image.effect_noise((width, height), 100).convert('L')
    noise = noise.point(lambda x: x * 0.03)
    img = Image.composite(img, Image.new('RGB', (width, height), (0,0,0)), noise)
    
    draw = ImageDraw.Draw(img)
    
    # Fonts
    quote_font = get_font(56, bold=True)
    author_font = get_font(32, bold=False)
    
    # Wrap quote text
    max_width = width - 160  # 80px padding each side
    lines = wrap_text(quote, quote_font, max_width, draw)
    
    # Calculate text block height
    line_height = 70
    text_block_height = len(lines) * line_height
    
    # Center vertically
    start_y = (height - text_block_height) // 2
    
    # Draw quote lines
    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=quote_font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        y = start_y + i * line_height
        
        # Text shadow
        draw.text((x+2, y+2), line, font=quote_font, fill=(0, 0, 0, 100))
        # Main text
        draw.text((x, y), line, font=quote_font, fill=palette['text'])
    
    # Draw author
    author_text = f"— {author}"
    bbox = draw.textbbox((0, 0), author_text, font=author_font)
    author_width = bbox[2] - bbox[0]
    author_x = (width - author_width) // 2
    author_y = start_y + text_block_height + 40
    
    draw.text((author_x+1, author_y+1), author_text, font=author_font, fill=(0, 0, 0, 100))
    draw.text((author_x, author_y), author_text, font=author_font, fill=palette['accent'])
    
    # Save
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, quality=95)
    return output_path

def create_carousel_slides(topic, slides_data, category, output_dir, dim='carousel'):
    """Create carousel slides (multiple images)"""
    width, height = DIMENSIONS[dim]
    palette = PALETTES.get(category, PALETTES['education'])
    paths = []
    
    for i, slide in enumerate(slides_data):
        img = create_gradient_bg(width, height, palette['bg'])
        draw = ImageDraw.Draw(img)
        
        # Title
        title_font = get_font(64, bold=True)
        body_font = get_font(40, bold=False)
        
        title = slide.get('title', f'Slide {i+1}')
        body = slide.get('body', '')
        
        # Title at top
        title_bbox = draw.textbbox((0, 0), title, font=title_font)
        title_width = title_bbox[2] - title_bbox[0]
        title_x = (width - title_width) // 2
        title_y = 150
        
        draw.text((title_x+2, title_y+2), title, font=title_font, fill=(0, 0, 0, 100))
        draw.text((title_x, title_y), title, font=title_font, fill=palette['text'])
        
        # Body text (wrapped)
        if body:
            lines = wrap_text(body, body_font, width - 200, draw)
            line_height = 55
            start_y = 300
            
            for j, line in enumerate(lines):
                bbox = draw.textbbox((0, 0), line, font=body_font)
                line_width = bbox[2] - bbox[0]
                x = (width - line_width) // 2
                y = start_y + j * line_height
                draw.text((x+1, y+1), line, font=body_font, fill=(0, 0, 0, 100))
                draw.text((x, y), line, font=body_font, fill=palette['secondary'])
        
        # Slide number
        num_font = get_font(28, bold=True)
        num_text = f"{i+1} / {len(slides_data)}"
        bbox = draw.textbbox((0, 0), num_text, font=num_font)
        num_x = width - bbox[2] - 50
        num_y = height - 80
        draw.text((num_x, num_y), num_text, font=num_font, fill=palette['accent'])
        
        # Save
        slide_path = os.path.join(output_dir, f'carousel_{i+1}.png')
        os.makedirs(output_dir, exist_ok=True)
        img.save(slide_path, quality=95)
        paths.append(slide_path)
    
    return paths

def create_story_template(hook, cta, category, output_path):
    """Create Instagram Story template (9:16)"""
    width, height = DIMENSIONS['story']
    palette = PALETTES.get(category, PALETTES['motivation'])
    
    img = create_gradient_bg(width, height, palette['bg'])
    draw = ImageDraw.Draw(img)
    
    # Hook text (large, centered)
    hook_font = get_font(72, bold=True)
    cta_font = get_font(40, bold=True)
    
    # Hook text
    hook_lines = wrap_text(hook, hook_font, width - 120, draw)
    line_height = 90
    start_y = (height - len(hook_lines) * line_height) // 2 - 100
    
    for i, line in enumerate(hook_lines):
        bbox = draw.textbbox((0, 0), line, font=hook_font)
        text_width = bbox[2] - bbox[0]
        x = (width - text_width) // 2
        y = start_y + i * line_height
        draw.text((x+3, y+3), line, font=hook_font, fill=(0, 0, 0, 100))
        draw.text((x, y), line, font=hook_font, fill=palette['text'])
    
    # CTA at bottom
    cta_y = height - 250
    cta_bbox = draw.textbbox((0, 0), cta, font=cta_font)
    cta_width = cta_bbox[2] - cta_bbox[0]
    cta_x = (width - cta_width) // 2
    
    # CTA background
    pad = 30
    draw.rounded_rectangle(
        [cta_x - pad, cta_y - pad, cta_x + cta_width + pad, cta_y + 50 + pad],
        radius=25, fill=palette['accent']
    )
    draw.text((cta_x, cta_y), cta, font=cta_font, fill=(0, 0, 0))
    
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img.save(output_path, quality=95)
    return output_path

def generate_visual_content(date_str=None):
    """Main function to generate all visual content for a day"""
    if date_str is None:
        date_str = today_str()
    
    date_obj = datetime.strptime(date_str, '%Y-%m-%d')
    day_name = date_obj.strftime('%A')
    
    # Load heroes for book-specific content
    heroes = load_heroes()
    books = load_books()
    
    # Content themes by day
    themes = {
        'Monday': ('motivation', 'Start the week right'),
        'Tuesday': ('education', 'Learn something new'),
        'Wednesday': ('business', 'Midweek business insights'),
        'Thursday': ('education', 'Writing/publishing tips'),
        'Friday': ('motivation', 'Weekend writing goals'),
        'Saturday': ('personal', 'Personal growth'),
        'Sunday': ('business', 'Plan next week'),
    }
    
    category, theme = themes.get(day_name, ('motivation', 'Daily inspiration'))
    
    # Quotes for the day
    quotes = [
        ("Write the book you want to read.", "Saurav Kushwaha"),
        ("50 books published. The secret? Systems, not motivation.", "Saurav Kushwaha"),
        ("Your first draft is just you telling yourself the story.", "Terry Pratchett"),
        ("Write & Publish in 30 Days. System beats talent every time.", "Saurav Kushwaha"),
        ("Don't wait for inspiration. Build a system that writes for you.", "Saurav Kushwaha"),
    ]
    quote, author = random.choice(quotes)
    
    # Carousel slides
    carousel_slides = [
        {"title": "The 30-Day Book System", "body": "Phase 1: Research (Days 1-7)\nPhase 2: Outline (Days 8-14)\nPhase 3: Draft (Days 15-21)\nPhase 4: Edit (Days 22-26)\nPhase 5: Publish (Days 27-30)"},
        {"title": "Why Most Authors Fail", "body": "1. No market research\n2. Writing for themselves\n3. No launch plan\n4. Inconsistent marketing\n5. Giving up too early"},
        {"title": "My 50-Book Proof", "body": "Every book started with:\n✓ Keyword research\n✓ Competitor analysis\n✓ Outline first\n✓ Daily word count\n✓ Professional cover"},
        {"title": "Ready to Start?", "body": "Join 1000+ authors in\n\"Write & Publish in 30 Days\"\nCourse: ₹2,999\nLink in bio 👆"},
    ]
    
    # Output directory
    base_dir = Path(__file__).parent.parent
    day_dir = base_dir / 'content' / 'daily' / date_str
    images_dir = day_dir / 'images'
    os.makedirs(images_dir, exist_ok=True)
    
    generated = {}
    
    # 1. Quote Image (Square post)
    quote, author = random.choice(quotes)
    quote_path = images_dir / 'quote_square.png'
    create_quote_image(quote, author, category, str(quote_path), 'post_square')
    generated['quote_square'] = str(quote_path.relative_to(base_dir))
    
    # 2. Quote Image (Reel cover - 9:16)
    reel_cover_path = images_dir / 'reel_cover.png'
    create_quote_image(quote, author, category, str(reel_cover_path), 'reel_cover')
    generated['reel_cover'] = str(reel_cover_path.relative_to(base_dir))
    
    # 3. Carousel slides
    carousel_dir = images_dir / 'carousel'
    carousel_paths = create_carousel_slides(theme, carousel_slides, category, str(carousel_dir), 'carousel')
    generated['carousel'] = [str(Path(p).relative_to(base_dir)) for p in carousel_paths]
    
    # 4. Story template
    story_path = images_dir / 'story.png'
    create_story_template(
        "Stop writing books nobody reads.\nHere's the 30-day system.",
        "Link in bio for free course",
        category,
        str(story_path)
    )
    generated['story'] = str(story_path.relative_to(base_dir))
    
    # 5. Portrait post (4:5)
    portrait_path = images_dir / 'post_portrait.png'
    create_quote_image(
        "Your book won't write itself.\nBut a system will write it for you.",
        "Saurav Kushwaha",
        category,
        str(portrait_path),
        'post_portrait'
    )
    generated['post_portrait'] = str(portrait_path.relative_to(base_dir))
    
    # Save metadata
    metadata = {
        'date': date_str,
        'day': day_name,
        'category': category,
        'theme': theme,
        'quote': quote,
        'author': author,
        'generated_images': generated,
        'carousel_slides': len(carousel_paths)
    }
    
    save_json(f'content/daily/{date_str}/visuals.json', metadata)
    
    print(f"[{datetime.now(IST)}] Visual content generated for {date_str} → {len(generated)} images")
    return metadata

def main():
    generate_visual_content()
    print("Visual content generation complete!")

if __name__ == '__main__':
    main()