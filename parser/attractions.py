from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import re
import uuid
from parser.utils import create_directories, clean_text, download_image, is_valid_address, save_to_json

class PeterburgCenterParser:
    def __init__(self, images_dir='places_images'):
        self.images_dir = images_dir
        self.setup_driver()
        create_directories(images_dir)
        
    def setup_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        options.add_argument("--log-level=3")
        
        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()), 
            options=options
        )
        self.wait = WebDriverWait(self.driver, 15)

    def extract_image_url(self):
        try:
            fotorama_selectors = [
                '//div[contains(@class, "fotorama__stage__frame")]//img[@src]',
                '//div[contains(@class, "fotorama__active")]//img[@src]',
                '//img[contains(@class, "fotorama__img")]'
            ]
            
            for selector in fotorama_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        src = img.get_attribute('src')
                        if src and 'peterburg.center' in src:
                            return src
                except:
                    continue
            
            img_selectors = [
                '//div[contains(@class, "main-content")]//img[@src]',
                '//article//img[@src]',
                '//div[contains(@class, "content")]//img[@src]',
                '//img[contains(@class, "field-name-field-image")]',
                '//img[@alt]'
            ]
            
            for selector in img_selectors:
                try:
                    images = self.driver.find_elements(By.XPATH, selector)
                    for img in images:
                        src = img.get_attribute('src')
                        if src and 'peterburg.center' in src:
                            return src
                except:
                    continue
            
            meta_selectors = [
                '//meta[@property="og:image"]',
                '//meta[@name="og:image"]'
            ]
            
            for selector in meta_selectors:
                try:
                    meta = self.driver.find_element(By.XPATH, selector)
                    src = meta.get_attribute('content')
                    if src:
                        return src
                except:
                    continue
            
            return None
                
        except Exception as e:
            print(f"Ошибка при поиске изображения: {e}")
            return None

    def get_address(self):
        address = "—"
        try:
            address_selectors = [
                '//*[contains(@class, "address")]',
                '//*[contains(@class, "location")]',
                '//*[contains(text(), "Адрес:")]',
                '//*[contains(text(), "Адрес ")]',
            ]
            
            for selector in address_selectors:
                elements = self.driver.find_elements(By.XPATH, selector)
                for element in elements:
                    text = element.text.strip()
                    if is_valid_address(text):
                        return clean_text(text)
                    
                    if "Адрес:" in text:
                        address_part = text.split("Адрес:")[-1].strip()
                        if is_valid_address(address_part):
                            return clean_text(address_part)
        
        except:
            pass
        
        try:
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            address_sections = body_text.split('Адрес:')
            if len(address_sections) > 1:
                potential_address = address_sections[1].split('\n')[0].strip()
                if is_valid_address(potential_address):
                    return clean_text(potential_address)
            
            address_patterns = [
                r'Адрес:\s*([^\n]{10,80})',
                r'Санкт-Петербург[^,\n]{0,50}',
                r'ул\.\s*[^,\n]{5,40}',
                r'улица\s*[^,\n]{5,40}',
                r'проспект\s*[^,\n]{5,40}',
                r'набережная\s*[^,\n]{5,40}'
            ]
            
            for pattern in address_patterns:
                matches = re.findall(pattern, body_text, re.IGNORECASE)
                for match in matches:
                    if isinstance(match, tuple):
                        match = match[0]
                    if is_valid_address(match):
                        return clean_text(match)
                        
        except:
            pass
        
        return "—"

    def get_work_time(self):
        work_time_info = []
        
        try:
            schedule_headers = self.driver.find_elements(
                By.XPATH, 
                '//h2[contains(text(), "Режим работы") or contains(text(), "Время работы")] | //h3[contains(text(), "Режим работы") or contains(text(), "Время работы")]'
            )
            
            for header in schedule_headers:
                try:
                    parent = header.find_element(By.XPATH, '..')
                    parent_text = parent.text
                    
                    header_text = header.text
                    work_text = parent_text.split(header_text)[-1].strip()
                    
                    lines = work_text.split('\n')
                    for line in lines[:10]:  
                        line = line.strip()
                        if line and len(line) > 5:
                            if any(indicator in line for indicator in [':', '—', 'работает', 'касса', 'выходной', 'понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']):
                                work_time_info.append(line)
                    
                    break  
                    
                except Exception as e:
                    continue
                    
        except Exception as e:
            pass
        
        if not work_time_info:
            try:
                list_items = self.driver.find_elements(By.TAG_NAME, 'li')
                for item in list_items:
                    text = item.text.strip()
                    if (any(keyword in text.lower() for keyword in ['музей работает', 'работает:', 'касса работает', 'выходной']) or
                        (any(day in text.lower() for day in ['понедельник', 'вторник', 'среда', 'четверг', 'пятница', 'суббота', 'воскресенье']) and 
                         any(time_indicator in text for time_indicator in [':', '—', '00']))):
                        work_time_info.append(text)
            except:
                pass
        
        if work_time_info:
            result = ' | '.join(work_time_info[:8])  
            if len(result) > 400:
                result = result[:400] + "..."
            return clean_text(result)
        
        return "—"

    def get_description(self):
        description = "—"
        
        try:
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            if 'Официальный сайт' in body_text or 'Телефон' in body_text:
                sections = re.split(r'Официальный сайт|Телефон/факс|Телефон', body_text)
                
                if len(sections) > 1:
                    after_contacts = sections[-1]
                    
                    lines = after_contacts.split('\n')
                    for line in lines:
                        line_clean = line.strip()
                        if (len(line_clean) > 80 and 
                            not any(exclude in line_clean.lower() for exclude in [
                                'режим работы', 'время работы', 'расписание', 'цена',
                                'билет', 'стоимость', 'руб.', 'заказ экскурсий',
                                'адрес', 'телефон', 'сайт', 'email', '@'
                            ]) and
                            any(desc_word in line_clean.lower() for desc_word in [
                                'является', 'служил', 'расположен', 'находится',
                                'образцом', 'площадь', 'река', 'парк', 'дворец',
                                'музей', 'архитектур', 'истори', 'культур',
                                'композиционным', 'ансамбль', 'резиденция'
                            ])):
                            
                            description = line_clean
                            break
            
            if description == "—":
                content_selectors = [
                    '//div[contains(@class, "field-name-body")]',
                    '//div[contains(@class, "content")]',
                    '//div[contains(@class, "description")]',
                    '//article',
                    '//main'
                ]
                
                for selector in content_selectors:
                    elements = self.driver.find_elements(By.XPATH, selector)
                    for element in elements:
                        paragraphs = element.find_elements(By.TAG_NAME, 'p')
                        for p in paragraphs:
                            text = p.text.strip()
                            if (len(text) > 80 and 
                                not any(exclude in text.lower() for exclude in [
                                    'режим работы', 'время работы', 'расписание',
                                    'телефон', 'сайт', 'цена', 'билет', 'руб.'
                                ]) and
                                any(desc_word in text.lower() for desc_word in [
                                    'музей', 'коллекция', 'экспонат', 'дворец',
                                    'парк', 'архитектур', 'истори', 'культур'
                                ])):
                                
                                description = text
                                break
                        if description != "—":
                            break
                    if description != "—":
                        break
        
        except Exception as e:
            pass
        
        if description != "—" and len(description) > 350:
            description = description[:350] + "..."
        
        return clean_text(description)

    def parse(self):
        url = "https://peterburg.center/dostoprimechatelnocti"
        self.driver.get(url)
        time.sleep(3)
        
        categories = self.driver.find_elements(By.XPATH, '//div[@class="dropdown-menu"]/a[contains(@href,"category")]')
        category_urls = [link.get_attribute("href") for link in categories]

        all_data = []

        if category_urls:
            first_category_url = category_urls[0]
            self.driver.get(first_category_url)
            time.sleep(3)
            
            try:
                category_name = self.driver.find_element(By.TAG_NAME, "h1").text.strip()
            except:
                category_name = "Достопримечательности"
            
            try:
                cards = self.driver.find_elements(By.XPATH, '//div[contains(@class, "card")]//a[contains(@href, "/maps/")]')[:3]
                card_urls = [card.get_attribute("href") for card in cards if card.get_attribute("href")]
            except:
                card_urls = []
            
            for i, card_url in enumerate(card_urls, 1):
                try:
                    self.driver.get(card_url)
                    time.sleep(3)
                    
                    try:
                        name = self.driver.find_element(By.TAG_NAME, "h1").text.strip()
                    except:
                        name = "—"
                    
                    address = self.get_address()
                    work_time = self.get_work_time()
                    description = self.get_description()
                    
                    image_url = self.extract_image_url()
                    image_filename = None
                    if image_url and name != "—":
                        image_filename = download_image(image_url, name, self.images_dir)
                    
                    place_data = {
                        "id": str(uuid.uuid4()),
                        "category": category_name,
                        "name": name,
                        "address": address,
                        "work_time": work_time,
                        "description": description,
                        "image_filename": image_filename if image_filename else "default_place.jpg",
                        "source": "peterburg.center",
                        "url": card_url
                    }
                    
                    all_data.append(place_data)
                    
                except Exception as e:
                    print(f"Ошибка при парсинге карточки: {e}")
                    continue

        self.driver.quit()
        return all_data

if __name__ == "__main__":
    parser = PeterburgCenterParser()
    results = parser.parse()
    save_to_json(results, 'places.json')