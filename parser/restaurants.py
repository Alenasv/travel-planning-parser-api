import requests
import time
import random
from bs4 import BeautifulSoup
import re
import json

class KudagoParser:
    def __init__(self):
        self.session = requests.Session()
        self.setup_headers()
        
    def setup_headers(self):
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7',
        })
    def clean_text(self, text):
        if text and text != "—":
            return re.sub(r'\s+', ' ', text).strip()
        return text

    def get_restaurant_list(self):
        url = "https://kudago.com/spb/restaurants/"
        
        try:
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                return []
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return self.extract_restaurant_links(soup)
            
        except Exception as e:
            return []

    def extract_restaurant_links(self, soup):
        links = []
        restaurant_cards = soup.find_all('a', href=True)
        
        for card in restaurant_cards:
            href = card.get('href')
            if href and '/spb/place/' in href and not href.endswith('#comments'):
                if href.startswith('http'):
                    full_url = href
                else:
                    full_url = f"https://kudago.com{href}"
                
                full_url = full_url.split('#')[0].split('?')[0]
                
                if full_url not in links:
                    links.append(full_url)
                    if len(links) >= 3:
                        break
        
        return links

    def get_restaurant_details(self, url):
        try:
            response = self.session.get(url, timeout=15)
            response.encoding = 'utf-8'
            
            if response.status_code != 200:
                return None
            
            soup = BeautifulSoup(response.text, 'html.parser')
            return self.parse_restaurant_page(soup, url)
            
        except Exception as e:
            return None

    def parse_restaurant_page(self, soup, url):
           try:
            name = self.extract_name(soup)
            address = self.extract_address(soup)
            work_time = self.extract_work_time(soup)
            description = self.extract_description(soup)
            image_url = self.extract_image(soup)

            if name:
                return {
                    'name': self.clean_text(name),
                    'address': self.clean_text(address) if address else 'Адрес не указан',
                    'work_time': self.clean_text(work_time) if work_time else '—',
                    'description': self.clean_text(description) if description else '—',
                    'image_url': image_url if image_url else '—',
                    'category': 'Рестораны',
                    'source': 'kudago'
                }
           except Exception as e:
            pass
           return None

    def extract_image(self, soup):
        try:
            img_tag = soup.find('img', class_='post-big-preview-image')
            if img_tag:
                src = img_tag.get('data-full') or img_tag.get('src')
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    return src
        except Exception as e:
            pass
        return None

    def extract_name(self, soup):
        name_element = soup.find('h1')
        if name_element:
            return name_element.get_text(strip=True)
        
        meta_title = soup.find('meta', property='og:title')
        if meta_title:
            return meta_title.get('content', '')
        
        title_element = soup.find('title')
        if title_element:
            return title_element.get_text(strip=True)
        
        return None

    def extract_address(self, soup):
        address_selectors = [
            '.location-address',
            '.post-place-address',
            '.addresses-list',
            '.post-address',
            '[class*="address"]',
            '[class*="location"]'
        ]
        
        for selector in address_selectors:
            try:
                elements = soup.select(selector)
                for element in elements:
                    text = element.get_text(strip=True)
                    if self.is_valid_address(text):
                        return text
            except:
                continue
        
        try:
            address_labels = soup.find_all(text=re.compile(r'Адрес', re.IGNORECASE))
            for label in address_labels:
                parent = label.parent
                if parent:
                    siblings = parent.find_next_siblings()
                    for sibling in siblings:
                        text = sibling.get_text(strip=True)
                        if self.is_valid_address(text):
                            return text
        except:
            pass
        
        try:
            text = soup.get_text()
            address_patterns = [
                r'ул\.\s*[^,\n]+',
                r'улица\s*[^,\n]+',
                r'проспект\s*[^,\n]+',
                r'пр\.\s*[^,\n]+',
                r'набережная\s*[^,\n]+',
                r'наб\.\s*[^,\n]+',
                r'Адрес[:\s]*([^\n]{10,100})',
                r'адрес[:\s]*([^\n]{10,100})'
            ]
            
            for pattern in address_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    address = match.strip()
                    if len(address) > 10 and self.is_valid_address(address):
                        return address
        except:
            pass
        
        return None

    def extract_work_time(self, soup):
        try:
            scripts = soup.find_all('script', type='application/ld+json')
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get('@type') in ['FoodEstablishment', 'Restaurant']:
                        opening_hours = data.get('openingHours')
                        if opening_hours:
                            if isinstance(opening_hours, list):
                                return ' | '.join(opening_hours[:3])
                            else:
                                return str(opening_hours)
                except:
                    continue
        except:
            pass
        
        try:
            text = soup.get_text()
            
            schedule_patterns = [
                r'Расписание\s*\n\s*([^\n]+)',
                r'Расписание\s*[:\-]\s*([^\n]+)',
                r'Расписание\s*([^\n]{1,50})'
            ]
            
            for pattern in schedule_patterns:
                matches = re.findall(pattern, text, re.IGNORECASE)
                for match in matches:
                    if match and len(match.strip()) > 3:
                        time_text = match.strip()
                        if any(time_indicator in time_text.lower() for time_indicator in 
                              ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс', 'круглосуточно', 'весь день']):
                            return time_text
        except:
            pass
        
        try:
            schedule_elements = soup.find_all(string=re.compile(r'^Расписание$', re.IGNORECASE))
            
            for element in schedule_elements:
                parent = element.parent
                if parent:
                    next_elements = parent.find_next_siblings()
                    for next_elem in next_elements:
                        text = next_elem.get_text(strip=True)
                        if text and any(time_indicator in text.lower() for time_indicator in 
                                      ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']):
                            return text
                    
                    children = parent.find_all(text=True)
                    found_schedule = False
                    for child in children:
                        if found_schedule and child.strip() and len(child.strip()) > 3:
                            if any(time_indicator in child.lower() for time_indicator in 
                                  ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']):
                                return child.strip()
                        if 'расписание' in child.lower():
                            found_schedule = True
        except:
            pass
        
        try:
            schedule_headers = soup.find_all(['h2', 'h3', 'h4', 'strong', 'div'], 
                                           string=re.compile(r'Расписание', re.IGNORECASE))
            
            for header in schedule_headers:
                next_elem = header.find_next()
                if next_elem:
                    text = next_elem.get_text(strip=True)
                    if text and any(time_indicator in text.lower() for time_indicator in 
                                  ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']):
                        return text
                
                parent = header.parent
                if parent:
                    parent_text = parent.get_text()
                    parts = parent_text.split(header.get_text(), 1)
                    if len(parts) > 1:
                        after_schedule = parts[1].strip()
                        first_line = after_schedule.split('\n')[0].strip()
                        if first_line and any(time_indicator in first_line.lower() for time_indicator in 
                                            ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс']):
                            return first_line
        except:
            pass
        
        try:
            text = soup.get_text()
            lines = text.split('\n')
            
            for i, line in enumerate(lines):
                line_clean = line.strip()
                if 'расписание' in line_clean.lower():
                    for j in range(i + 1, min(i + 3, len(lines))):
                        next_line = lines[j].strip()
                        if next_line and len(next_line) > 3:
                            if any(time_indicator in next_line.lower() for time_indicator in 
                                  ['ежедневно', 'пн', 'вт', 'ср', 'чт', 'пт', 'сб', 'вс', 'круглосуточно']):
                                return next_line
                            elif not any(exclude in next_line.lower() for exclude in 
                                       ['адрес', 'телефон', 'цена', 'руб']):
                                if len(next_line) < 50:
                                    return next_line
        except:
            pass
        
        return None

    def extract_description(self, soup):
        content_selectors = [
            '.post-big-content',
            '.post-content',
            '.post-body',
            '.place-description',
            '.post-description'
        ]
        
        for selector in content_selectors:
            try:
                element = soup.select_one(selector)
                if element:
                    paragraphs = element.find_all('p')
                    for p in paragraphs:
                        text = p.get_text(strip=True)
                        if len(text) > 50 and not any(word in text.lower() for word in ['адрес', 'расписание', 'время работы', 'режим работы', 'телефон']):
                            if len(text) > 300:
                                return text[:300] + "..."
                            return text
            except:
                continue
        
        try:
            meta_desc = soup.find('meta', property='og:description')
            if meta_desc:
                desc = meta_desc.get('content', '')
                if len(desc) > 50:
                    if len(desc) > 300:
                        return desc[:300] + "..."
                    return desc
        except:
            pass
        
        return None

    def is_valid_address(self, text):
        if not text or len(text) < 10:
            return False
        
        indicators = ['ул.', 'улица', 'пр.', 'проспект', 'наб.', 'Санкт-Петербург', 'спб', 'д.', 'дом']
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in indicators)

    def parse(self):
        results = []
        
        restaurant_urls = self.get_restaurant_list()
        
        if not restaurant_urls:
            return results
        
        for i, url in enumerate(restaurant_urls, 1):
            restaurant_data = self.get_restaurant_details(url)
            if restaurant_data:
                results.append(restaurant_data)
            
            if i < len(restaurant_urls):
                delay = random.uniform(2, 4)
                time.sleep(delay)
        
        return results

    def print_results(self, results):

        for i, place in enumerate(results, 1):
            print(f"\n{i}. КАТЕГОРИЯ: {place['category']}")
            print(f"   Название: {place['name']}")
            print(f"   Адрес: {place['address']}")
            print(f"   Время работы: {place['work_time']}")
            print(f"   Описание: {place['description']}")
            print("-" * 80)

    def save_to_json(self, results, filename="food_places.json"):
        try:
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=4)
            print(f"Данные сохранены в {filename}")
        except Exception as e:
            print(f"Ошибка при сохранении JSON: {e}")

if __name__ == "__main__":
    parser = KudagoParser()
    results = parser.parse()
    parser.print_results(results)
    parser.save_to_json(results)