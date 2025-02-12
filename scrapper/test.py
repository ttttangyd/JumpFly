import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from urllib.parse import urljoin
import os

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
    all_product_data = []

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
                    all_product_data.append([product_name, product_url])
            except Exception:
                pass  
    return all_product_data

def get_custom_category_data():
    """Extracts data for Custom Pins and Custom Challenge Coins"""
    all_product_data = []
    try:
        category_items = driver.find_elements(By.CSS_SELECTOR, "#main div.custom-pins-template div.category--info h3 a")
        for item in category_items:
            product_name = item.text.strip()
            product_url = item.get_attribute("href")
            all_product_data.append([product_name, product_url])
    except Exception as e:
        print(f"❌ Error extracting custom category: {e}")
    
    return all_product_data

# Record Running Time
start_time = time.time()

# Process categories
for excel_name, subcategories in categories_df.groupby(categories_df['Category'].str.split(' > ').str[1]):
    if pd.isna(excel_name):
        continue  # Skip invalid categories
    
    print(f"\n🚀 Crawling category: {excel_name}")
    writer = pd.ExcelWriter(f"{excel_name}.xlsx", engine="xlsxwriter")

    sheet_count = 0  # Track number of sheets in the file

    # Check if there is a third-level category
    if subcategories['Category'].str.count(" > ").max() >= 2:
        for sheet_name, sheet_subcategories in subcategories.groupby(categories_df['Category'].str.split(' > ').str[2]):
            if pd.isna(sheet_name):
                continue  # Skip invalid subcategories
            
            print(f"📂 Crawling subcategory: {sheet_name}")

            all_product_data = []  # Store products in this sheet
            subcategory_names = []  # Track subcategory names

            for _, row in sheet_subcategories.iterrows():
                subcategory_path = row["Category"].split(" > ")
                category_url = row["URL"]
                
                print(f"🔍 Crawling: {subcategory_path[-1]} ({category_url})")
                driver.get(category_url)
                time.sleep(3)

                try:
                    if any("custom" in part.lower().strip() for part in subcategory_path):
                        print(f"🔍 Using custom scraper for {subcategory_path[-1]}")
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
                        if len(subcategory_path) > 3:
                            all_product_data.extend([[subcategory_path[-1], i+1, name, url] for i, (name, url) in enumerate(product_data)])
                            subcategory_names.append(subcategory_path[-1])
                        else:
                            all_product_data.extend([[i+1, name, url] for i, (name, url) in enumerate(product_data)])

                except Exception as e:
                    print(f"❌ Error while crawling {subcategory_path[-1]}: {e}")

            # If no data, create an empty sheet
            if not all_product_data:
                print(f"⚠️ No products found for {sheet_name}. Creating empty sheet...")
                df_products = pd.DataFrame(columns=["Num", "Product Name", "Product URL"])
                subcategory_count = 0
            else:
                # **Ensure "Num" is in the correct position**
                if len(subcategory_path) > 3:
                    df_products = pd.DataFrame(all_product_data, columns=["Subcategory", "Num", "Product Name", "Product URL"])
                else:
                    df_products = pd.DataFrame(all_product_data, columns=["Num", "Product Name", "Product URL"])
                subcategory_count = len(set(subcategory_names))

            # Write to Excel and merge subcategory cells
            df_products.to_excel(writer, sheet_name=sheet_name[:31], index=False)

            workbook = writer.book
            worksheet = writer.sheets[sheet_name[:31]]

            # Merge subcategory cells if applicable
            if "Subcategory" in df_products.columns:
                subcategory_ranges = df_products.groupby("Subcategory").apply(lambda x: (x.index[0]+1, x.index[-1]+1)).to_dict()
                for subcategory, (start_row, end_row) in subcategory_ranges.items():
                    worksheet.merge_range(start_row, 0, end_row, 0, subcategory, workbook.add_format({'align': 'center', 'valign': 'vcenter'}))

            sheet_count += 1
            print(f"✅ Data extracted for {sheet_name} in {excel_name} ({subcategory_count} subcategories)")

    else:
        # If no third-level category, use second-level category as sheet
        sheet_name = excel_name[:31]
        print(f"📂 Crawling single-level category: {sheet_name}")

        all_product_data = []

        for _, row in subcategories.iterrows():
            subcategory_path = row["Category"].split(" > ")
            category_url = row["URL"]
            
            print(f"🔍 Crawling: {subcategory_path[-1]} ({category_url})")
            driver.get(category_url)
            time.sleep(3)

            try:
                if any("custom" in part.lower().strip() for part in subcategory_path):
                    print(f"🔍 Using custom scraper for {subcategory_path[-1]}")
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

                all_product_data.extend([[i+1, name, url] for i, (name, url) in enumerate(product_data)])

            except Exception as e:
                print(f"❌ Error while crawling {sheet_name}: {e}")

        df_products = pd.DataFrame(all_product_data, columns=["Num", "Product Name", "Product URL"])
        df_products.to_excel(writer, sheet_name=sheet_name, index=False)
        sheet_count += 1

        print(f"✅ Data extracted for {sheet_name} in {excel_name} (No subcategory)")

    writer.close()
    print(f"📑 {excel_name} completed with {sheet_count} sheets\n")

# Close WebDriver
driver.quit()

# Print Running time
end_time = time.time()
print(f"⏳ Total execution time: {end_time - start_time:.2f} seconds")
