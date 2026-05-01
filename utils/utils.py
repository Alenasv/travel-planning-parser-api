import os
import re
import uuid
import requests
from urllib.parse import urlparse
import json
import html
from transliterate import translit
from utils.geo_utils import geo_key,distance
from difflib import SequenceMatcher

def normalize_name(name):
    if not name:
        return ""

    name = name.lower()

    name = re.sub(r"(музей|памятник|театр)", "", name)

    name = re.sub(r'[^a-zа-я0-9 ]', '', name)
    name = re.sub(r'\s+', ' ', name).strip()

    return name

def clean_text(text):
    if not text or text == "—":
        return text

    text = html.unescape(text)

    text = re.sub(r"<[^>]+>", "", text)

    lines = text.split('\n')
    cleaned_lines = [re.sub(r'[ \t]+', ' ', line).strip() for line in lines]
    cleaned_lines = [line for line in cleaned_lines if line]

    return '\n'.join(cleaned_lines)

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
        
        safe_name = translit(place_name, 'ru', reversed=True)  
        safe_name = re.sub(r'[^\w\s-]', '', safe_name)
        safe_name = re.sub(r'[-\s]+', '_', safe_name)
        safe_name = re.sub(r'_+', '_', safe_name).strip('_')
        
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
                    return f"{images_dir}/{filename}"
                else:
                    os.remove(filepath)
                    return None

            elif response.status_code == 404:
                print(f"Картинка не найдена (404): {clean_url}")
                return None
            else:
                print(f"Ошибка загрузки {clean_url}: {response.status_code}")
                return None
                
        except requests.exceptions.Timeout:
            return None
        except requests.exceptions.ConnectionError:
            print(f"Ошибка соединения при загрузке: {clean_url}")
            return None
            
    except Exception as e:
        print(f"Ошибка при загрузке изображения {image_url}: {e}")
        return None


def save_to_json(results, filename):
    try:
        os.makedirs(os.path.dirname(filename), exist_ok=True)

        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка при сохранении в JSON: {e}")
        return False


CATEGORY_GROUPS = {
    "Еда и напитки": ["бар", "паб", "ресторан", "кафе", "пивовар"],
    "Развлечения": ["клуб", "театр", "кино", "концерт", "антикафе", "развлеч"],
    "Культура": ["музей", "галере", "выстав", "искусств"],
    "Природа": ["парк", "река", "канал", "сад"],
    "История": ["памятник", "дворец", "мост", "фонтан", "усадьба", "архитект"],
    "Религия": ["храм", "церковь", "собор", "монастыр"],
}

def map_category(category_name: str) -> str:
    if not category_name:
        return "Другое"

    cat = category_name.lower()

    for group, keywords in CATEGORY_GROUPS.items():
        if any(k in cat for k in keywords):
            return group

    return "Другое"

def make_key(item):
    name = normalize_name(item.get("name"))

    coords = item.get("coords")

    geo = None
    if coords and isinstance(coords, dict):
        lat = coords.get("lat")
        lon = coords.get("lon")

        if lat is not None and lon is not None:
            geo = geo_key(coords)

    return f"{name}_{geo}" if geo else name

def similar(a, b):
    return SequenceMatcher(None, a, b).ratio()


def is_same_place(a, b):
    name_a = normalize_name(a.get("name"))
    name_b = normalize_name(b.get("name"))

    name_score = similar(name_a, name_b)

    coords_a = a.get("coords") or {}
    coords_b = b.get("coords") or {}

    lat1 = coords_a.get("lat")
    lon1 = coords_a.get("lon")
    lat2 = coords_b.get("lat")
    lon2 = coords_b.get("lon")

    dist = None

    if all(v is not None for v in [lat1, lon1, lat2, lon2]):
        dist = distance(lat1, lon1, lat2, lon2)

    if name_score > 0.75:
        return True

    if dist is not None and dist < 0.2:
        return True

    if name_score > 0.6 and dist is not None and dist < 0.5:
        return True

    return False


def deduplicate(data):
    unique = []

    for item in data:
        duplicate_found = False

        for i, existing in enumerate(unique):
            if is_same_place(item, existing):

                if len(item.get("description", "")) > len(existing.get("description", "")):
                    unique[i] = item

                duplicate_found = True
                break

        if not duplicate_found:
            unique.append(item)

    return unique