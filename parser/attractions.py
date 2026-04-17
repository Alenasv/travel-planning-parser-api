import requests
from bs4 import BeautifulSoup
import re
import uuid
import time
from urllib.parse import urljoin
from parser.utils import create_directories, clean_text, download_image, save_to_json, map_category

class PeterburgCenterParser:
    def __init__(self, images_dir='places_images'):
        self.images_dir = images_dir
        self.base_url = "https://peterburg.center"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        create_directories(images_dir)

    def fetch_html(self, url):
        try:
            full_url = urljoin(self.base_url, url)
            response = self.session.get(full_url, timeout=15)
            response.raise_for_status()
            response.encoding = 'utf-8'
            return response.text
        except Exception as e:
            print(f"Ошибка загрузки {url}: {e}")
            return None

    def extract_image_url(self, soup):
        fotorama = soup.find('div', class_='fotorama')
        if fotorama:
            for img in fotorama.find_all('img'):
                src = img.get('src')
                if src and 'peterburg.center' in src:
                    return src
                data_src = img.get('data-src')
                if data_src and 'peterburg.center' in data_src:
                    return data_src
        
        content_selectors = [
            '.main-content img',
            'article img',
            '.content img',
            'img.field-name-field-image',
            'img[alt]'
        ]
        
        for selector in content_selectors:
            images = soup.select(selector)
            for img in images:
                src = img.get('src')
                if src and 'peterburg.center' in src:
                    return src
                data_src = img.get('data-src')
                if data_src and 'peterburg.center' in data_src:
                    return data_src
        
        meta_selectors = [
            'meta[property="og:image"]',
            'meta[name="og:image"]',
            'meta[property="twitter:image"]'
        ]
        
        for selector in meta_selectors:
            meta = soup.select_one(selector)
            if meta:
                src = meta.get('content')
                if src:
                    return src
        
        return None

    def get_address(self, soup):
        address_selectors = [
            '.field-name-field-address .field-item',
            '.field-name-field-address',
            'div.field-label:contains("Адрес") + div.field-items',
            '.field-label-inline:contains("Адрес")'
        ]
        
        for selector in address_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                text = re.sub(r'^Адрес:\s*', '', text, flags=re.IGNORECASE).strip()
                if text and len(text) > 5:
                    return clean_text(text)
        
        for element in soup.find_all(string=re.compile("Адрес:")):
            parent = element.parent
            if parent:
                text = parent.get_text(strip=True)
                parts = text.split("Адрес:")
                if len(parts) > 1:
                    address_part = parts[1].strip().split('\n')[0].strip()
                    if address_part and len(address_part) > 5:
                        return clean_text(address_part)
        
        for item in soup.select('.field-item'):
            text = item.get_text(strip=True)
            if (len(text) > 10 and 
                any(keyword in text.lower() for keyword in ['санкт-петербург', 'спб', 'ленинградская', 'ул.', 'улица', 'проспект', 'площадь', 'набережная', 'г. павловск']) and
                not any(exclude in text.lower() for exclude in ['режим работы', 'телефон', 'сайт', 'email'])):
                return clean_text(text)
        
        return "—"

    def get_work_time(self, soup):
        work_time_info = []
        
        for header in soup.find_all(['h2', 'h3', 'h4']):
            header_text = header.get_text()
            if any(word in header_text.lower() for word in ['режим работы', 'время работы', 'часы работы']):
                current = header.find_next()
                collected = []
                while current and len(collected) < 15:  
                    if current.name in ['h2', 'h3', 'h4'] and current != header:
                        break
                    if current.name in ['p', 'ul', 'li', 'div']:
                        text = current.get_text(strip=True)
                        if text and len(text) > 3:
                            collected.append(text)
                    current = current.find_next()
                
                if collected:
                    work_time_info.extend(collected[:8])
                    break
        
        if not work_time_info:
            for li in soup.find_all('li'):
                text = li.get_text(strip=True)
                if (any(keyword in text.lower() for keyword in ['работает', 'касса', 'выходной', 'бесплатный', 'вход']) or
                    any(day in text.lower() for day in ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'])):
                    if any(time_indicator in text for time_indicator in [':', '—', '00', 'часов', 'время']):
                        work_time_info.append(text)
        
        if work_time_info:
            result = '\n'.join(work_time_info[:8])
            if len(result) > 400:
                result = result[:400] + "..."
            return clean_text(result)
        
        return "—"

    def get_description(self, soup):
        description = "—"
        
        body_element = soup.find('div', class_='field-name-body')
        if body_element:
            paragraphs = body_element.find_all('p')
            desc_texts = []
            for p in paragraphs:
                text = p.get_text(strip=True)
                if len(text) > 50 and not any(exclude in text.lower() for exclude in [
                    'режим работы', 'время работы', 'расписание', 'цена',
                    'билет', 'стоимость', 'руб.', 'заказ экскурсий',
                    'адрес', 'телефон', 'сайт', 'email', '@'
                ]):
                    desc_texts.append(text)
            
            if desc_texts:
                description = ' '.join(desc_texts[:3])
        
        if description == "—":
            content_selectors = [
                '.content',
                '.description',
                'article',
                'main',
                '.text-content',
                '.entry-content'
            ]
            
            for selector in content_selectors:
                elements = soup.select(selector)
                for element in elements:
                    paragraphs = element.find_all('p')
                    desc_texts = []
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 50 and not any(exclude in text.lower() for exclude in [
                            'режим работы', 'время работы', 'расписание',
                            'телефон', 'сайт', 'цена', 'билет', 'руб.',
                            'стоимость', 'адрес:', 'контакты', 'касса'
                        ]):
                            desc_texts.append(text)
                    
                    if desc_texts:
                        description = ' '.join(desc_texts[:3])
                        break
                
                if description != "—":
                    break
        
        return clean_text(description)

    def get_category_urls(self):
        html = self.fetch_html("/dostoprimechatelnocti")
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        
        category_urls = []
        
        for a in soup.find_all('a', href=True):
            href = a['href']
            if 'category' in href and not any(exclude in href for exclude in ['javascript', '#']):
                full_url = urljoin(self.base_url, href)
                if full_url not in category_urls:
                    category_urls.append(full_url)
        
        return category_urls[:10] 

    def get_place_urls_from_category(self, category_url, limit=7):
        html = self.fetch_html(category_url)
        if not html:
            return []
        
        soup = BeautifulSoup(html, 'html.parser')
        place_urls = []
        
        cards = soup.find_all('div', class_=re.compile(r'card'))
        for card in cards[:limit]:
            a_tag = card.find('a', href=re.compile(r'/maps/'))
            if a_tag and a_tag.get('href'):
                full_url = urljoin(self.base_url, a_tag['href'])
                place_urls.append(full_url)
        
        if not place_urls:
            for a in soup.find_all('a', href=re.compile(r'/maps/')):
                href = a['href']
                full_url = urljoin(self.base_url, href)
                if full_url not in place_urls:
                    place_urls.append(full_url)
                    if len(place_urls) >= limit:
                        break
        
        return place_urls

    def parse_place(self, url, category_name):
        html = self.fetch_html(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        h1 = soup.find('h1', class_='page-title')
        if not h1:
            h1 = soup.find('h1')
        name = h1.get_text(strip=True) if h1 else "—"
        
        address = self.get_address(soup)
        work_time = self.get_work_time(soup)
        description = self.get_description(soup)
        image_url = self.extract_image_url(soup)
        
        image_filename = None
        if image_url and name != "—":
            clean_name = re.sub(r'[^\w\s-]', '', name).strip()
            image_filename = download_image(image_url, clean_name, self.images_dir)

        mapped_category = map_category(category_name)
        return {
            "id": f"peterburg_{url.split('/')[-1]}",
            "category": mapped_category,
            "name": name,
            "address": address,
            "work_time": work_time,
            "description": description,
            "image_filename": image_filename if image_filename else "default_place.jpg",
            "source": "peterburg.center",
            "url": url
        }

    def parse(self):
        all_data = []
        
        category_urls = self.get_category_urls()
        
        for i, category_url in enumerate(category_urls, 1):
            try:
                
                html_cat = self.fetch_html(category_url)
                if not html_cat:
                    continue
                
                soup_cat = BeautifulSoup(html_cat, 'html.parser')
                h1 = soup_cat.find('h1')
                category_name = h1.get_text(strip=True) if h1 else "Достопримечательности"
                
                place_urls = self.get_place_urls_from_category(category_url, limit=1)
                
                for j, place_url in enumerate(place_urls, 1):
                    try:
                        
                        place_data = self.parse_place(place_url, category_name)
                        if place_data:
                            all_data.append(place_data)
                        
                        time.sleep(1)
                        
                    except Exception as e:
                        print(f" Ошибка: {e}")
                        continue
                time.sleep(2)
                
            except Exception as e:
                print(f"Ошибка {category_url}: {e}")
                continue
        return all_data

if __name__ == "__main__":
    parser = PeterburgCenterParser()
    results = parser.parse()
    
    if results:
        save_to_json(results, 'data/places.json')
    else:
        print("Не удалось собрать")