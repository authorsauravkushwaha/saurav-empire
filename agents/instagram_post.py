#!/usr/bin/env python3
"""
Instagram Poster - Actually posts to Instagram via Graph API
Requires: IG_APP_ID, IG_APP_SECRET, IG_USER_ID, IG_LONG_LIVED_TOKEN, FB_PAGE_ID in GitHub Secrets
"""
import os
import json
import requests
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

# Instagram Graph API endpoints
GRAPH_API = "https://graph.facebook.com/v20.0"

def get_access_token():
    """Get long-lived access token"""
    token = os.getenv('IG_LONG_LIVED_TOKEN')
    if not token:
        raise ValueError("IG_LONG_LIVED_TOKEN not set in environment")
    return token

def get_instagram_user_id():
    """Get Instagram Business Account ID"""
    return os.getenv('IG_USER_ID')

def get_facebook_page_id():
    """Get Facebook Page ID"""
    return os.getenv('FB_PAGE_ID')

def upload_media(image_path, caption, media_type='IMAGE'):
    """Upload media to Instagram via Graph API"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    if not ig_user_id:
        raise ValueError("IG_USER_ID not set")
    
    url = f"{GRAPH_API}/{ig_user_id}/media"
    
    # For local files, we need to upload to a publicly accessible URL first
    # For GitHub Actions, we'd need to upload to a hosting service or use a different approach
    # For now, we'll use the image URL approach
    
    # This is a simplified version - in production you'd upload to a CDN first
    # For GitHub Actions, you can use the GitHub repo as temporary hosting
    
    payload = {
        'media_type': media_type,
        'caption': caption,
        'access_token': access_token
    }
    
    # If you have a public URL for the image:
    # payload['image_url'] = image_url
    
    # For carousel:
    if isinstance(image_path, list):
        payload['media_type'] = 'CAROUSEL'
        # Would need children media IDs
    
    response = requests.post(url, data=payload)
    return response.json()

def publish_media(creation_id):
    """Publish uploaded media"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    url = f"{GRAPH_API}/{ig_user_id}/media_publish"
    payload = {
        'creation_id': creation_id,
        'access_token': access_token
    }
    
    response = requests.post(url, data=payload)
    return response.json()

def post_reel(video_path, caption):
    """Post a Reel (video)"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    # Upload video first
    url = f"{GRAPH_API}/{ig_user_id}/media"
    payload = {
        'media_type': 'REELS',
        'video_url': video_path,  # Must be public URL
        'caption': caption,
        'access_token': access_token
    }
    
    response = requests.post(url, data=payload)
    result = response.json()
    
    if 'id' in result:
        # Publish
        publish_result = publish_media(result['id'])
        return publish_result
    return result

def post_image(image_path, caption):
    """Post a single image"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    url = f"{GRAPH_API}/{ig_user_id}/media"
    payload = {
        'media_type': 'IMAGE',
        'image_url': image_path,  # Must be public URL
        'caption': caption,
        'access_token': access_token
    }
    
    response = requests.post(url, data=payload)
    result = response.json()
    
    if 'id' in result:
        publish_result = publish_media(result['id'])
        return publish_result
    return result

def post_carousel(images, caption):
    """Post carousel (multiple images)"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    # Create child media for each image
    children = []
    for img_path in images:
        url = f"{GRAPH_API}/{ig_user_id}/media"
        payload = {
            'media_type': 'IMAGE',
            'image_url': img_path,
            'is_carousel_item': 'true',
            'access_token': access_token
        }
        resp = requests.post(url, data=payload)
        child = resp.json()
        if 'id' in child:
            children.append(child['id'])
    
    # Create carousel parent
    url = f"{GRAPH_API}/{ig_user_id}/media"
    payload = {
        'media_type': 'CAROUSEL',
        'children': ','.join(children),
        'caption': caption,
        'access_token': access_token
    }
    
    response = requests.post(url, data=payload)
    result = response.json()
    
    if 'id' in result:
        publish_result = publish_media(result['id'])
        return publish_result
    return result

def get_media_insights(media_id):
    """Get insights for a media"""
    access_token = get_access_token()
    url = f"{GRAPH_API}/{media_id}/insights"
    params = {
        'metric': 'impressions,reach,likes,comments,shares,saves',
        'access_token': access_token
    }
    response = requests.get(url, params=params)
    return response.json()

def get_user_profile():
    """Get Instagram Business Account info"""
    ig_user_id = get_instagram_user_id()
    access_token = get_access_token()
    
    url = f"{GRAPH_API}/{ig_user_id}"
    params = {
        'fields': 'id,username,media_count,account_type',
        'access_token': access_token
    }
    response = requests.get(url, params=params)
    return response.json()

def main():
    import argparse
    parser = argparse.ArgumentParser(description='Post to Instagram via Graph API')
    parser.add_argument('--type', choices=['image', 'carousel', 'reel'], default='image')
    parser.add_argument('--image', help='Path to image (public URL)')
    parser.add_argument('--images', nargs='+', help='Paths to images for carousel')
    parser.add_argument('--video', help='Path to video (public URL)')
    parser.add_argument('--caption', help='Caption for post')
    parser.add_argument('--test', action='store_true', help='Test connection only')
    
    args = parser.parse_args()
    
    if args.test:
        print("Testing Instagram connection...")
        profile = get_user_profile()
        print(f"Connected to: @{profile.get('username', 'unknown')}")
        print(f"Media count: {profile.get('media_count', 0)}")
        print(f"Account type: {profile.get('account_type', 'unknown')}")
        return
    
    if not args.caption:
        print("Error: --caption required")
        return
    
    if args.type == 'carousel' and args.images:
        result = post_carousel(args.images, args.caption)
    elif args.type == 'reel' and args.video:
        result = post_reel(args.video, args.caption)
    elif args.image:
        result = post_image(args.image, args.caption)
    else:
        print("Error: --image, --images, or --video required")
        return
    
    print(json.dumps(result, indent=2))

if __name__ == '__main__':
    main()