import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from tqdm import tqdm
import sys

# Initialize WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Headless mode
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920x1080")
service = Service("chromedriver/chromedriver")
driver = webdriver.Chrome(service=service, options=options)

# Read categories from CSV
categories_df = pd.read_csv("categories.csv")

def get_landing_page():
    """Retrieve the latest hawksearch-landing-page element and return its shadowRoot"""
    WebDriverWait(driver, 10).until(
        EC.presence_of_element_located((By.TAG_NAME, "hawksearch-landing-page"))
    )
    time.sleep(2)  
    landing_page_element = driver.find_element(By.TAG_NAME, "hawksearch-landing-page")
    return landing_page_element

def get_product_data(landing_page_element, page_num, base_url):
    """Extract all product information from hawksearch-search-results-list"""
    all_products = []

    WebDriverWait(driver, 10).until(
        lambda d: driver.execute_script("""
            let landingPage = arguments[0].shadowRoot;
            let searchResults = landingPage.querySelector('hawksearch-search-results');
            return searchResults && searchResults.shadowRoot.querySelector('hawksearch-search-results-list') !== null;
        """, landing_page_element)
    )

    results_list_html = driver.execute_script("""
        let landingPage = arguments[0].shadowRoot;
        let searchResults = landingPage.querySelector('hawksearch-search-results');
        let resultsList = searchResults.shadowRoot.querySelector('hawksearch-search-results-list');
        return resultsList ? resultsList.shadowRoot.innerHTML : null;
    """, landing_page_element)
    
    if results_list_html:
        results_list_soup = BeautifulSoup(results_list_html, "html.parser")
        product_items = driver.execute_script("""
            let landingPage = arguments[0].shadowRoot;
            let searchResults = landingPage.querySelector('hawksearch-search-results');
            let resultsList = searchResults.shadowRoot.querySelector('hawksearch-search-results-list');
            return resultsList ? resultsList.shadowRoot.querySelectorAll('hawksearch-search-results-item') : [];
        """, landing_page_element)
        
        for item in product_items:
            try:
                item_html = driver.execute_script("return arguments[0].shadowRoot.innerHTML;", item)
                item_soup = BeautifulSoup(item_html, "html.parser")
                product_link_tag = item_soup.find("a", class_="search-results-list__item__image", href=True)
                if product_link_tag:
                    product_url = urljoin(base_url, product_link_tag["href"])
                    product_name = product_link_tag.get("aria-label", "No Name")
                    all_products.append([product_name, product_url])
            except Exception:
                pass  
    return all_products

def get_custom_category_data():
    """Extracts data for Custom Pins and Custom Challenge Coins"""
    all_products = []
    try:
        category_items = driver.find_elements(By.CSS_SELECTOR, "#main div.custom-pins-template div.category--info h3 a")
        for item in category_items:
            product_name = item.text.strip()
            product_url = item.get_attribute("href")
            all_products.append([product_name, product_url])
    except Exception as e:
        exceptions_log.append(f"❌ Error extracting custom category: {e}")
    
    return all_products

# Record Running Time
start_time = time.time()

# Create a list to store all products
all_products = []
exceptions_log = []  # List to store all exceptions

# 计算总任务数（用于进度条）
total_categories = len(categories_df['Category'].str.split(' > ').str[1].unique())
category_progress = tqdm(total=total_categories, desc="Processing Categories", unit="category")

# Process categories
for category, subcategories in categories_df.groupby(categories_df['Category'].str.split(' > ').str[1]):
    if pd.isna(category):
        continue  # Skip invalid categories
    
    sys.stdout.write(f"\r🚀 Crawling category: {category}\n")
    sys.stdout.flush()
    
    has_third_level = subcategories['Category'].str.count(" > ").max() >= 2
    has_fourth_level = subcategories['Category'].str.count(" > ").max() >= 3
    has_fifth_level = subcategories['Category'].str.count(" > ").max() >= 4

    # Check if there is a third-level category
    if has_third_level:
        subcategory_progress = tqdm(total=len(subcategories), desc=f"Processing {category}", unit="subcategory", leave=False)
        for subcategory, third_level_category in subcategories.groupby(categories_df['Category'].str.split(' > ').str[2]):
            if pd.isna(subcategory):
                continue  # Skip invalid subcategories
            
            sys.stdout.write(f"\r    📂 Crawling subcategory: {subcategory}\n")
            sys.stdout.flush()

            for _, row in third_level_category.iterrows():
                third_level_path = row["Category"].split(" > ")
                full_category = row["Category"]
                third_level_category = third_level_path[3] if len(third_level_path) > 3 else "Null"
                fourth_level_category = third_level_path[4] if len(third_level_path) > 4 else "Null"
                fifth_level_category = third_level_path[5] if len(third_level_path) > 5 else "Null"
                category_url = row["URL"]
                
                sys.stdout.write(f"\r       🔍 Crawling third_level_category: {third_level_path[-1]}\n")
                sys.stdout.flush()

                driver.get(category_url)
                time.sleep(3)

                try:
                    if any("custom" in part.lower().strip() for part in third_level_path):
                        product_data = get_custom_category_data()
                    else:
                        landing_page_element = get_landing_page()
                        product_data = get_product_data(landing_page_element, page_num=1, base_url=category_url)

                        # Handle pagination
                        pagination_html = driver.execute_script("""
                            let landingPage = arguments[0].shadowRoot;
                            let searchResults = landingPage.querySelector('hawksearch-search-results');
                            let pagination = searchResults.shadowRoot.querySelector('hawksearch-pagination');
                            return pagination ? pagination.shadowRoot.innerHTML : null;
                        """, landing_page_element)

                        if pagination_html:
                            pagination_soup = BeautifulSoup(pagination_html, "html.parser")
                            page_links = pagination_soup.select(".pagination__page[href]")
                            from collections import OrderedDict
                            page_urls = list(OrderedDict.fromkeys([urljoin(category_url, link["href"]) for link in page_links]))
                        else:
                            page_urls = []

                        for page_num, page_url in enumerate(page_urls, start=2):  
                            driver.get(page_url)
                            time.sleep(3)
                            landing_page_element = get_landing_page()
                            page_product_data = get_product_data(landing_page_element, page_num, base_url=category_url)
                            product_data.extend(page_product_data)  

                    # Merge all data for this sheet
                    if product_data:
                        all_products.extend([[full_category, category, subcategory, third_level_category, fourth_level_category, fifth_level_category, i+1, name, url] 
                            for i, (name, url) in enumerate(product_data)])
                except Exception as e:
                    exceptions_log.append(f"❌ Error while crawling {third_level_path[-1]}: {e}")

                subcategory_progress.update(1)
        subcategory_progress.close()

    else:
        for _, row in subcategories.iterrows():
            third_level_path = row["Category"].split(" > ")
            category_url = row["URL"]
            subcategory, third_level_category, fourth_level_category, fifth_level_category = "Null", "Null", "Null", "Null"

            driver.get(category_url)
            time.sleep(3)

            try:
                if any("custom" in part.lower().strip() for part in third_level_path):
                    product_data = get_custom_category_data()
                else:
                    landing_page_element = get_landing_page()
                    product_data = get_product_data(landing_page_element, page_num=1, base_url=category_url)

                    pagination_html = driver.execute_script("""
                        let landingPage = arguments[0].shadowRoot;
                        let searchResults = landingPage.querySelector('hawksearch-search-results');
                        let pagination = searchResults.shadowRoot.querySelector('hawksearch-pagination');
                        return pagination ? pagination.shadowRoot.innerHTML : null;
                    """, landing_page_element)

                    if pagination_html:
                        pagination_soup = BeautifulSoup(pagination_html, "html.parser")
                        page_links = pagination_soup.select(".pagination__page[href]")
                        from collections import OrderedDict
                        page_urls = list(OrderedDict.fromkeys([urljoin(category_url, link["href"]) for link in page_links]))
                    else:
                        page_urls = []

                    for page_num, page_url in enumerate(page_urls, start=2):  
                        driver.get(page_url)
                        time.sleep(3)
                        landing_page_element = get_landing_page()
                        page_product_data = get_product_data(landing_page_element, page_num, base_url=category_url)
                        product_data.extend(page_product_data)  

                all_products.extend([[i+1, name, url] for i, (name, url) in enumerate(product_data)])
            except Exception as e:
                exceptions_log.append(f"❌ Error while crawling {subcategory}: {e}")
    
    category_progress.update(1)
category_progress.close()

# Save data to Excel
df_products = pd.DataFrame(all_products, columns=["Full-category", "Category", "Subcategory", "Third-level-category", "Fourth-level-category", "Fifth-level-category", "Num", "Product Name", "Product URL"])
df_products.to_excel("all_products.xlsx", sheet_name="Products", index=False)

# Print Exception Summary
if exceptions_log:
    print("\n❗ Exception Summary:")
    for log in exceptions_log:
        print(log)

# Print Running Time
end_time = time.time()
print(f"⏳ Total execution time: {end_time - start_time:.2f} seconds")

# Close WebDriver
driver.quit()