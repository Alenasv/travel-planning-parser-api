import requests
import os
from bs4 import BeautifulSoup
import re
import time
from urllib.parse import urljoin
from utils.utils import clean_text, download_image, save_to_json, map_category
from utils.geo_utils import geocode
from utils.normalize import valid_coords

MAX_ADDRESS_LEN = 150
COORDS_PAIR_RE = re.compile(r"(5[89]|6[01])\.(\d{3,})\s*,\s*(2[7-9]|3[0-5])\.(\d{3,})")
COORDS_PAIR_REVERSED_RE = re.compile(r"(2[7-9]|3[0-5])\.(\d{3,})\s*,\s*(5[89]|6[01])\.(\d{3,})")

class PeterburgCenterParser:
    def __init__(self, images_dir='places_images', per_category=2):
        self.images_dir = images_dir
        self.per_category = per_category
        self.base_url = "https://peterburg.center"
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
            'Connection': 'keep-alive',
        }
        self.session = requests.Session()
        self.session.headers.update(self.headers)
        os.makedirs(images_dir, exist_ok=True)

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

    def get_address(self, soup):
        address_selectors = [
            '.field-name-field-address .field-item',
            '.field-name-field-address',
            'div.field-label:-soup-contains("Адрес") + div.field-items',
            '.field-label-inline:-soup-contains("Адрес")'
        ]
        
        for selector in address_selectors:
            elements = soup.select(selector)
            for element in elements:
                text = element.get_text(strip=True)
                text = re.sub(r'^Адрес:\s*', '', text, flags=re.IGNORECASE).strip()
                if text and 5 < len(text) <= MAX_ADDRESS_LEN:
                    return clean_text(text)
        
        for element in soup.find_all(string=re.compile("Адрес:")):
            parent = element.parent
            if parent:
                text = parent.get_text(strip=True)
                parts = text.split("Адрес:")
                if len(parts) > 1:
                    address_part = parts[1].strip().split('\n')[0].strip()
                    if address_part and 5 < len(address_part) <= MAX_ADDRESS_LEN:
                        return clean_text(address_part)

        for item in soup.select('.field-item'):
            text = item.get_text(strip=True)
            if (10 < len(text) <= MAX_ADDRESS_LEN and
                any(keyword in text.lower() for keyword in ['санкт-петербург', 'спб', 'ленинградская', 'ул.', 'улица', 'проспект', 'площадь', 'набережная', 'г. павловск']) and
                not any(exclude in text.lower() for exclude in ['режим работы', 'телефон', 'сайт', 'email'])):
                return clean_text(text)

        return None

    def get_work_time(self, soup):
        work_time_info = []

        for header in soup.find_all(['h2', 'h3', 'h4']):
            header_text = header.get_text()
            if any(word in header_text.lower() for word in ['режим работы', 'время работы', 'часы работы']):
                for el in header.find_all_next(['p', 'li', 'h2', 'h3', 'h4'], limit=15):
                    if el.name in ['h2', 'h3', 'h4']:
                        break
                    for line in el.get_text('\n', strip=True).split('\n'):
                        line = line.strip()
                        if len(line) > 3 and line not in work_time_info:
                            work_time_info.append(line)
                if work_time_info:
                    break

        if not work_time_info:
            for li in soup.find_all('li'):
                text = li.get_text(' ', strip=True)
                if (any(keyword in text.lower() for keyword in ['работает', 'касса', 'выходной', 'вход']) or
                    any(day in text.lower() for day in ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье'])):
                    if re.search(r'\d{1,2}[:.]\d{2}', text):
                        work_time_info.append(text)

        if work_time_info:
            return clean_text('\n'.join(work_time_info))

        return None

    def get_coords(self, soup):
        lat = soup.select_one('meta[property="place:location:latitude"], meta[itemprop="latitude"]')
        lon = soup.select_one('meta[property="place:location:longitude"], meta[itemprop="longitude"]')
        if lat and lon:
            coords = valid_coords({"lat": lat.get("content"), "lon": lon.get("content")})
            if coords:
                return coords

        for el in soup.select('[data-lat], [data-latitude]'):
            coords = valid_coords({
                "lat": el.get("data-lat") or el.get("data-latitude"),
                "lon": el.get("data-lng") or el.get("data-lon") or el.get("data-longitude"),
            })
            if coords:
                return coords

        for iframe in soup.find_all('iframe', src=True):
            m = COORDS_PAIR_REVERSED_RE.search(iframe['src'].replace('%2C', ','))
            if m:
                coords = valid_coords({"lat": f"{m.group(3)}.{m.group(4)}", "lon": f"{m.group(1)}.{m.group(2)}"})
                if coords:
                    return coords

        for script in soup.find_all('script'):
            text = script.string or ''
            m = COORDS_PAIR_RE.search(text)
            if m:
                coords = valid_coords({"lat": f"{m.group(1)}.{m.group(2)}", "lon": f"{m.group(3)}.{m.group(4)}"})
                if coords:
                    return coords

        return None

    def geocode_address(self, address):
        if not address:
            return None
        coords = valid_coords(geocode(address))
        if coords:
            return coords
        if not re.search(r'петербург|спб|ленинградская|область', address, re.IGNORECASE):
            return valid_coords(geocode(f"Санкт-Петербург, {address}"))
        return None

    def get_description(self, soup):
        description = None
        
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
        
        if not description:
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
                
                if description:
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

    def normalize_image_url(self, url):
        if not url:
            return None

        url = url.strip()

        if url.startswith("://"):
            url = url[3:]

        if url.startswith("http"):
            return url
        if "og_big_logo" in url:
            return None
        if "logo" in url:
            return None

        return urljoin(self.base_url, url)

    def get_place_urls_from_category(self, category_url, limit=7):
        html = self.fetch_html(category_url)
        if not html:
            return []

        soup = BeautifulSoup(html, 'html.parser')
        place_urls = []

        card_blocks = soup.select("div.view-content div.img-fluid")

        for block in card_blocks:
            a = block.select_one("a")
            if not a or not a.get("href"):
                continue

            url = urljoin(self.base_url, a["href"])

            img = block.select_one("img")
            img_url = None
            if img:
                img_url = img.get("data-src") or img.get("src")

            if img_url:
                img_url = urljoin(self.base_url, img_url)

            place_urls.append({
                "url": url,
                "image_url": img_url
            })

            if len(place_urls) >= limit:
                break

        return place_urls

    def parse_place(self, url, category_name, preview_image=None):
        html = self.fetch_html(url)
        if not html:
            return None
        
        soup = BeautifulSoup(html, 'html.parser')
        
        h1 = soup.find('h1', class_='page-title')
        if not h1:
            h1 = soup.find('h1')
        name = h1.get_text(strip=True) if h1 else None
        if not name:
            return None
        
        address = self.get_address(soup)
        work_time = self.get_work_time(soup)
        description = self.get_description(soup)
        image_url = self.get_high_quality_image(soup, preview_image)
        
        if image_url:
            image_url = self.normalize_image_url(image_url)

        if not image_url:
            return None

        clean_name = re.sub(r'[^\w\s-]', '', name).strip()
        image_filename = download_image(image_url, clean_name, self.images_dir)
        if image_filename:
            image_filename = f"places_images/{os.path.basename(image_filename)}"

        coords = self.get_coords(soup) or self.geocode_address(address)

        mapped_category = map_category(category_name)
        if mapped_category == "Другое":
            mapped_category = map_category(name)
        return {
            "id": f"peterburg_{url.split('/')[-1]}",
            "category": mapped_category,
            "name": name,
            "address": address,
            "work_time": work_time,
            "description": description,
            "tags": self.generate_tags(name, description, mapped_category),
            "coords": coords,
            "metro": None,
            "image_filename": image_filename,
            "source": "peterburg.center",
            "url": url
        }

    def get_high_quality_image(self, soup, preview_url):
        fotorama = soup.find('div', class_='fotorama')
        if fotorama:
            for img in fotorama.find_all('img'):
                full_src = img.get('data-full') or img.get('data-big') or img.get('src')
                
                if full_src and preview_url and (preview_url.split('/')[-1] in full_src):
                    return urljoin(self.base_url, full_src)

        if preview_url and 'styles/' in preview_url:
            return preview_url.split('/styles/')[0] + '/' + preview_url.split('/')[-1]

        return preview_url
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
                
                place_urls = self.get_place_urls_from_category(category_url, limit=self.per_category)
                
                for j, place_data in enumerate(place_urls, 1):
                    place_url = place_data["url"]
                    preview_image = place_data["image_url"]
                    try:
                        place_result = self.parse_place(
                            place_url,
                            category_name,
                            preview_image
                        )
                        if place_result:
                            all_data.append(place_result)
                        
                        time.sleep(1)
                        
                    except Exception as e:
                        print(f" Ошибка: {e}")
                        continue
                time.sleep(2)
                
            except Exception as e:
                print(f"Ошибка {category_url}: {e}")
                continue
        return all_data
    
    def generate_tags(self, name, description, category):
        text = f"{name} {description or ''} {category}".lower()
        tags = set()
        rules = {
            "дети": ["детям", "ребёнок", "семь", "школь", "дошколь", "сказк"],
            "музеи": ["музей", "экспози", "выстав"],
            "театр": ["театр", "спектак", "постанов"],
            "религия": ["собор", "храм", "церковь", "монастыр"],
            "парк": ["парк", "сад", "аллея"],
            "история": ["истор", "памятник", "эпох", "романов"],
            "вид": ["вид", "панорам", "смотров"],
            "экскурсии": ["экскурс"],
            "бесплатно": ["бесплат"],
        }
        for tag, keywords in rules.items():
            if any(k in text for k in keywords):
                tags.add(tag)
        if not tags:
            tags.add(category.lower())
        return list(tags)

if __name__ == "__main__":
    parser = PeterburgCenterParser()
    results = parser.parse()
    
    if results:
        save_to_json(results, 'data/places.json')
    else:
        print("Не удалось собрать")