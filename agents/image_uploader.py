#!/usr/bin/env python3
"""
Image Uploader - Uploads images to GitHub repo (via API) or Imgur for public URLs
Instagram Graph API requires public image URLs
"""
import os
import json
import base64
import requests
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

GITHUB_REPO = "authorsauravkushwaha/saurav-empire"
GITHUB_BRANCH = "main"

def upload_to_github(images_dir, github_token):
    """Upload images to GitHub repo and return public URLs"""
    if not github_token:
        print("GITHUB_TOKEN not set, skipping GitHub upload")
        return {}
    
    headers = {
        'Authorization': f'token {github_token}',
        'Accept': 'application/vnd.github.v3+json'
    }
    
    urls = {}
    images_path = Path(images_dir).resolve()
    repo_root = Path(__file__).parent.parent.resolve()
    
    for img_file in images_path.rglob('*.png'):
        try:
            # Get relative path from repo root
            rel_path = img_file.relative_to(repo_root)
            github_path = str(rel_path).replace('\\', '/')
            
            # Read file
            with open(img_file, 'rb') as f:
                content = base64.b64encode(f.read()).decode()
            
            # Check if file exists
            check_url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
            check_resp = requests.get(check_url, headers=headers)
            
            sha = None
            if check_resp.status_code == 200:
                sha = check_resp.json().get('sha')
            
            # Upload/update
            url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
            payload = {
                'message': f'Upload branded image: {img_file.name}',
                'content': content,
                'branch': GITHUB_BRANCH
            }
            if sha:
                payload['sha'] = sha
            
            resp = requests.put(url, headers=headers, json=payload)
            if resp.status_code in (200, 201):
                # Get raw URL
                raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{github_path}"
                rel_key = str(img_file.relative_to(images_path))
                urls[rel_key] = raw_url
                print(f"Uploaded: {rel_key} -> {raw_url}")
            else:
                print(f"Failed to upload {img_file.name}: {resp.status_code} {resp.text}")
        except ValueError as e:
            print(f"Path error for {img_file}: {e}")
            # Try alternative - use just the filename
            try:
                github_path = f"content/daily/{img_file.name}"
                with open(img_file, 'rb') as f:
                    content = base64.b64encode(f.read()).decode()
                url = f"https://api.github.com/repos/{GITHUB_REPO}/contents/{github_path}"
                payload = {
                    'message': f'Upload branded image: {img_file.name}',
                    'content': content,
                    'branch': GITHUB_BRANCH
                }
                resp = requests.put(url, headers=headers, json=payload)
                if resp.status_code in (200, 201):
                    raw_url = f"https://raw.githubusercontent.com/{GITHUB_REPO}/{GITHUB_BRANCH}/{github_path}"
                    urls[img_file.name] = raw_url
                    print(f"Uploaded (fallback): {img_file.name} -> {raw_url}")
            except Exception as e2:
                print(f"Failed to upload {img_file.name}: {e2}")
        except Exception as e:
            print(f"Error processing {img_file}: {e}")
    
    return urls

def upload_to_imgur(image_path, client_id):
    """Upload to Imgur (alternative)"""
    if not client_id:
        return None
    
    headers = {'Authorization': f'Client-ID {client_id}'}
    with open(image_path, 'rb') as f:
        files = {'image': f}
        resp = requests.post('https://api.imgur.com/3/image', headers=headers, files=files)
        if resp.status_code == 200:
            return resp.json()['data']['link']
    return None

def get_public_urls(images_dir, method='github'):
    """Get public URLs for all images in directory"""
    images_dir = Path(images_dir)
    if not images_dir.exists():
        return {}
    
    if method == 'github':
        token = os.getenv('GITHUB_TOKEN')
        return upload_to_github(images_dir, token)
    elif method == 'imgur':
        client_id = os.getenv('IMGUR_CLIENT_ID')
        urls = {}
        for img in images_dir.rglob('*.png'):
            url = upload_to_imgur(img, os.getenv('IMGUR_CLIENT_ID'))
            if url:
                urls[str(img.relative_to(images_dir))] = url
        return urls
    
    return {}

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--dir', required=True, help='Images directory')
    parser.add_argument('--method', choices=['github', 'imgur'], default='github')
    parser.add_argument('--output', help='Output JSON file for URLs')
    args = parser.parse_args()
    
    urls = get_public_urls(args.dir, args.method)
    
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(urls, f, indent=2)
        print(f"Saved {len(urls)} URLs to {args.output}")
    else:
        print(json.dumps(urls, indent=2))

if __name__ == '__main__':
    main()