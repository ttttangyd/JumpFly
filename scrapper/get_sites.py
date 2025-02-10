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

    # Extract hawksearch-search-results-list shadow DOM
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

                    all_product_data.append({
                        "Page": page_num,
                        "Product Name": product_name,
                        "Product URL": product_url
                    })

            except Exception as e:
                pass  

    return all_product_data

i = 0
total_start_time = time.time()  # Start total timer

# Iterate through each category URL
for index, row in categories_df.iterrows():
    
    if i == 5:  # Limit to 5 categories for testing
        break
    else:
        i += 1

    category_name = row["Category"]
    category_url = row["URL"]

    print(f"\n🚀 Crawling category: {category_name}")

    category_start_time = time.time()  # Start timer for this category

    driver.get(category_url)
    time.sleep(3)

    try:
        landing_page_element = get_landing_page()

        # Extract first page product data
        product_data = get_product_data(landing_page_element, page_num=1, base_url=category_url)

        # Extract pagination content
        pagination_html = driver.execute_script("""
            let landingPage = arguments[0].shadowRoot;
            let searchResults = landingPage.querySelector('hawksearch-search-results');
            let pagination = searchResults.shadowRoot.querySelector('hawksearch-pagination');
            return pagination ? pagination.shadowRoot.innerHTML : null;
        """, landing_page_element)

        if pagination_html:
            pagination_soup = BeautifulSoup(pagination_html, "html.parser")
            page_links = pagination_soup.select(".pagination__page[href]")

            # Preserve order and remove duplicates
            from collections import OrderedDict
            page_urls = list(OrderedDict.fromkeys([urljoin(category_url, link["href"]) for link in page_links]))

            print(f"Found {len(page_urls) + 1} pagination links")
        else:
            page_urls = []

        # Iterate through each pagination link
        for page_num, page_url in enumerate(page_urls, start=2):  
            driver.get(page_url)
            time.sleep(3)

            landing_page_element = get_landing_page()

            page_product_data = get_product_data(landing_page_element, page_num, base_url=category_url)
            product_data.extend(page_product_data)  

        # Save product data to Excel
        output_filename = f"{category_name}.xlsx"
        df_products = pd.DataFrame([(row["Product URL"], row["Product Name"]) for row in product_data], 
                                   columns=["Product URL", "Product Name"])
        df_products.to_excel(output_filename, index=False)

        category_end_time = time.time()
        category_duration = category_end_time - category_start_time
        print(f"✅ Data extraction completed for {category_name}. Saved to {output_filename}")
        print(f"⏱ Time taken: {category_duration:.2f} seconds")

    except Exception as e:
        print(f"❌ Error while crawling {category_name}: {e}")

total_end_time = time.time()
total_duration = total_end_time - total_start_time
print(f"\n⏳ Total time taken for all categories: {total_duration:.2f} seconds")

# Close WebDriver
driver.quit()
