from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.chrome import ChromeDriverManager
import time
import re

class PeterburgCenterParser:
    def __init__(self):
        self.setup_driver()
        
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

    def clean_text(self, text):
        if text and text != "—":
            return re.sub(r'\s+', ' ', text).strip()
        return text

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
                    if self.is_valid_address(text):
                        return self.clean_text(text)
                    
                    if "Адрес:" in text:
                        address_part = text.split("Адрес:")[-1].strip()
                        if self.is_valid_address(address_part):
                            return self.clean_text(address_part)
        
        except:
            pass
        
        try:
            body_text = self.driver.find_element(By.TAG_NAME, 'body').text
            
            address_sections = body_text.split('Адрес:')
            if len(address_sections) > 1:
                potential_address = address_sections[1].split('\n')[0].strip()
                if self.is_valid_address(potential_address):
                    return self.clean_text(potential_address)
            
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
                    if self.is_valid_address(match):
                        return self.clean_text(match)
                        
        except:
            pass
        
        return "—"

    def is_valid_address(self, text):
        if not text or len(text) < 10:
            return False
        
        indicators = [
            'ул.', 'улица', 'пр.', 'проспект', 'наб.', 'набережная',
            'Санкт-Петербург', 'спб', 'д.', 'дом', 'площадь'
        ]
        text_lower = text.lower()
        return any(indicator in text_lower for indicator in indicators)

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
            return self.clean_text(result)
        
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
        
        return self.clean_text(description)

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
                cards = self.driver.find_elements(By.XPATH, '//div[contains(@class, "card")]//a[contains(@href, "/maps/")]')[:2]
                card_urls = [card.get_attribute("href") for card in cards if card.get_attribute("href")]
            except:
                card_urls = []
            
            for card_url in card_urls:
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
                    
                    place_data = {
                        "category": category_name,
                        "name": name,
                        "address": address,
                        "work_time": work_time,
                        "description": description
                    }
                    
                    all_data.append(place_data)
                    
                except Exception as e:
                    continue

        self.driver.quit()
        return all_data

    def print_results(self, results):

        for i, place in enumerate(results, 1):
            print(f"\n{i}. КАТЕГОРИЯ: {place['category']}")
            print(f"   Название: {place['name']}")
            print(f"   Адрес: {place['address']}")
            print(f"   Время работы: {place['work_time']}")
            print(f"   Описание: {place['description']}")
            print("-" * 80)

        print(f"\nВсего собрано записей: {len(results)}")

if __name__ == "__main__":
    parser = PeterburgCenterParser()
    results = parser.parse()
    parser.print_results(results)