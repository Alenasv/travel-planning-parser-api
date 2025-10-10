import os
import re
import uuid
import requests
import shutil
from urllib.parse import urlparse
import json

def create_directories(images_dir):
    if not os.path.exists(images_dir):
        os.makedirs(images_dir)

def clean_text(text):
    if text and text != "—":
        return re.sub(r'\s+', ' ', text).strip()
    return text

def download_image(image_url, place_name, images_dir):
    if not image_url:
        return None
        
    try:
        parsed_url = urlparse(image_url)
        clean_url = f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}"
        
        if '/xl/' in clean_url and 'media.kudago.com' in clean_url:
            clean_url = clean_url.replace('/xl/', '/large/') 
        
        file_extension = os.path.splitext(parsed_url.path)[1]
        if not file_extension or len(file_extension) > 5:
            file_extension = '.jpg'
        
        safe_name = re.sub(r'[^\w\s-]', '', place_name)
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        filename = f"{safe_name}_{uuid.uuid4().hex[:8]}{file_extension}"
        filepath = os.path.join(images_dir, filename)
        
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Accept-Encoding': 'gzip, deflate, br',
            'DNT': '1',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'image',
            'Sec-Fetch-Mode': 'no-cors',
            'Sec-Fetch-Site': 'cross-site',
            'Cache-Control': 'max-age=0',
            'Referer': 'https://kudago.com/', 
        }
        
        cookies = {
            'device_type': 'desktop',
            'city': 'spb'
        }
        
        session = requests.Session()
        session.headers.update(headers)
        
        try:
            response = session.get(
                clean_url, 
                cookies=cookies,
                timeout=30,  
                stream=True,
                allow_redirects=True
            )
            
            if response.status_code == 200:
                with open(filepath, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                file_size = os.path.getsize(filepath)
                if file_size > 1000:  
                    return filename
                else:
                    os.remove(filepath)
                    return None
            else:
                print(f"Ошибка загрузки {clean_url}: {response.status_code}")
                
                if '/xl/' in image_url:
                    medium_url = image_url.replace('/xl/', '/large/')
                    return download_image(medium_url, place_name, images_dir)
                
                return None
                
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.ConnectionError:
            print(f" Ошибка соединения при загрузке: {clean_url}")
            return None
            
            
    except Exception as e:
        print(f" Ошибка при загрузке изображения {image_url}: {e}")
        return None

def is_valid_address(text):
    if not text or len(text) < 10:
        return False
    
    indicators = [
        'ул.', 'улица', 'пр.', 'проспект', 'наб.', 'набережная',
        'Санкт-Петербург', 'спб', 'д.', 'дом', 'площадь', 'аллея', 'бульвар'
    ]
    text_lower = text.lower()
    return any(indicator in text_lower for indicator in indicators)

def save_to_json(results, filename):
    try:
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении в JSON: {e}")
        return False

def merge_json_files(files, output_file='all_places.json'):
    all_data = []
    
    for file in files:
        try:
            with open(file, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_data.extend(data)
        except Exception as e:
            print(f"Ошибка при загрузке {file}: {e}")
    
    if save_to_json(all_data, output_file):
        return True
    return False

def cleanup_previous_data():
    json_files = ['all_places.json', 'restaurants.json', 'places.json']
    image_dirs = ['kudago_images', 'places_images']

    deleted_files = 0
    for json_file in json_files:
        if os.path.exists(json_file):
            try:
                os.remove(json_file)
                deleted_files += 1
            except Exception as e:
                print(f"Не удалось удалить {json_file}: {e}")
    
    deleted_dirs = 0
    for image_dir in image_dirs:
        if os.path.exists(image_dir):
            try:
                shutil.rmtree(image_dir)
                deleted_dirs += 1
            except Exception as e:
                print(f"Не удалось удалить {image_dir}: {e}")