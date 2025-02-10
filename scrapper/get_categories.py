from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from bs4 import BeautifulSoup
import time
import pandas as pd

# Set ChromeDriver path
CHROME_DRIVER_PATH = "chromedriver/chromedriver"

# Configure WebDriver
options = webdriver.ChromeOptions()
options.add_argument("--headless")  # Run in headless mode (without opening a browser)
options.add_argument("--disable-gpu")
options.add_argument("--window-size=1920x1080")

# Start WebDriver
service = Service(CHROME_DRIVER_PATH)
driver = webdriver.Chrome(service=service, options=options)

# Access target URL
url = "https://www.pinmart.com/sitemap/categories"
driver.get(url)

# Wait for page to load
time.sleep(3)

# Get page HTML
html = driver.page_source
soup = BeautifulSoup(html, "html.parser")

# Find div with id="main"
main_div = soup.find("div", id="main")

# Recursive function to extract nested categories
def extract_nested_categories(element, parent_category=""):
    """
    Recursively extract nested categories and retrieve the lowest-level category with its URL.
    """
    categories = []
    category_count = 0  # Counter for extracted categories

    # Find all child <li> elements
    list_items = element.find_all("li", recursive=False)
    
    for li in list_items:
        # Extract category name
        category_name_tag = li.find("a")
        if category_name_tag:
            category_name = category_name_tag.text.strip()
            category_link = category_name_tag.get("href")
            
            # Construct full category path
            full_category = f"{parent_category} > {category_name}" if parent_category else category_name
            
            # Check for subcategories (nested <ul>)
            sublist = li.find("ul")
            if sublist:
                # Recursively extract subcategories
                subcategories, sub_count = extract_nested_categories(sublist, full_category)
                categories.extend(subcategories)
                category_count += sub_count
            else:
                # Only add the lowest-level category
                if category_link:
                    categories.append({"Category": category_name, "URL": category_link})
                    category_count += 1  # Increment count

    return categories, category_count

# Parse main content list
if main_div:
    main_list = main_div.find("ul")  # Find <ul> inside main_div
    categories_data, total_categories = extract_nested_categories(main_list) if main_list else ([], 0)
else:
    categories_data, total_categories = [], 0

# Save to CSV
df = pd.DataFrame(categories_data)
df.to_csv("categories.csv", index=False)

print(f"Scraping completed. {total_categories} categories saved to categories.csv.")

# Close WebDriver
driver.quit()
