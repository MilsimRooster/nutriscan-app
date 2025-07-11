import streamlit as st
import cv2
import pyzbar.pyzbar as pyzbar
import json
import os
import logging
import numpy as np
import requests
import pandas as pd
import matplotlib.pyplot as plt

# Setup logging to file
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.FileHandler("nutriscan.log")]
)

def load_nutrition_db():
    """Load or create the local barcode cache."""
    db_path = "nutrition_db.json"
    if not os.path.exists(db_path):
        logging.info(f"Creating {db_path}")
        with open(db_path, "w") as f:
            json.dump({"barcodes": {}}, f)
    try:
        with open(db_path, "r") as f:
            logging.info(f"Loaded {db_path}")
            return json.load(f)
    except Exception as e:
        logging.error(f"Failed to load {db_path}: {e}")
        return {"barcodes": {}}

def save_nutrition_db(db):
    """Save barcode cache to nutrition_db.json."""
    try:
        with open("nutrition_db.json", "w") as f:
            json.dump(db, f, indent=2)
        logging.info("Saved nutrition_db.json")
    except Exception as e:
        logging.error(f"Failed to save nutrition_db.json: {e}")

def fetch_barcode_data(barcode):
    """Fetch nutritional data from Open Food Facts."""
    try:
        url = f"https://world.openfoodfacts.org/api/v0/product/{barcode}.json"
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            logging.warning(f"Open Food Facts API failed for {barcode}: Status {response.status_code}")
            return None
        data = response.json()
        if data.get("status") != 1 or not data.get("product"):
            logging.warning(f"No product found for barcode {barcode}")
            return None
        product = data["product"]
        nutriments = product.get("nutriments", {})
        result = {
            "name": product.get("product_name", "Unknown Product"),
            "calories": nutriments.get("energy-kcal_100g", 0),
            "fat": nutriments.get("fat_100g", 0),
            "carbs": nutriments.get("carbohydrates_100g", 0),
            "protein": nutriments.get("proteins_100g", 0),
            "sugar": nutriments.get("sugars_100g", 0),
            "fiber": nutriments.get("fiber_100g", 0)
        }
        logging.info(f"Fetched data for {barcode}: {result['name']}")
        return result
    except Exception as e:
        logging.error(f"Open Food Facts API error for {barcode}: {e}")
        return None

def scan_barcode(image):
    """Scan a barcode and return nutritional data with preprocessing."""
    db = load_nutrition_db()
    if not db:
        return None
    try:
        # Preprocess image: resize to 800px width, convert to grayscale
        width = 800
        aspect = image.shape[1] / image.shape[0]
        height = int(width / aspect)
        image_resized = cv2.resize(image, (width, height))
        image_gray = cv2.cvtColor(image_resized, cv2.COLOR_BGR2GRAY)
        
        barcodes = pyzbar.decode(image_gray)
        if not barcodes:
            logging.info("No barcodes found in image")
            return None
        for barcode in barcodes:
            barcode_data = barcode.data.decode("utf-8")
            if barcode.type == "PDF417":
                logging.warning(f"Skipping unsupported PDF417 barcode: {barcode_data}")
                st.warning(f"PDF417 barcode {barcode_data} not supported. Use UPC/EAN format.")
                continue
            nutritional_info = db["barcodes"].get(barcode_data)
            if nutritional_info:
                logging.info(f"Barcode {barcode_data} found in cache: {nutritional_info['name']}")
                return nutritional_info
            nutritional_info = fetch_barcode_data(barcode_data)
            if nutritional_info:
                db["barcodes"][barcode_data] = nutritional_info
                save_nutrition_db(db)
                return nutritional_info
            logging.warning(f"Barcode {barcode_data} not found in Open Food Facts")
            st.warning(f"Barcode {barcode_data} not found in database or Open Food Facts.")
        return None
    except Exception as e:
        logging.error(f"Barcode scanning failed: {e}")
        return None

def check_nutrition(data, max_calories, min_protein, max_fat, max_carbs, max_sugar, min_fiber):
    """Check if nutritional data meets user preferences with detailed feedback."""
    if not data:
        return False, []
    mismatches = []
    if data.get("calories", 0) > max_calories: mismatches.append(f"Calories ({data['calories']} > {max_calories})")
    if data.get("protein", 0) < min_protein: mismatches.append(f"Protein ({data['protein']} < {min_protein})")
    if data.get("fat", 0) > max_fat: mismatches.append(f"Fat ({data['fat']} > {max_fat})")
    if data.get("carbs", 0) > max_carbs: mismatches.append(f"Carbs ({data['carbs']} > {max_carbs})")
    if data.get("sugar", 0) > max_sugar: mismatches.append(f"Sugar ({data['sugar']} > {max_sugar})")
    if data.get("fiber", 0) < min_fiber: mismatches.append(f"Fiber ({data['fiber']} < {min_fiber})")
    return len(mismatches) == 0, mismatches

def plot_nutrition_histogram(db):
    """Plot histogram of key nutrients from past scans."""
    nutrients = ["calories", "protein", "fat", "carbs", "sugar", "fiber"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    axes = axes.flatten()
    for i, nutrient in enumerate(nutrients):
        values = [item.get(nutrient, 0) for item in db["barcodes"].values()]
        if values:
            axes[i].hist(values, bins=10, color=["skyblue", "lightgreen", "salmon", "gold", "violet", "lime"][i % 6])
            axes[i].set_title(f"{nutrient.capitalize()} Distribution")
            axes[i].set_xlabel(f"{nutrient.capitalize()} (g/100g except cal)")
    plt.tight_layout()
    st.pyplot(fig)

def main():
    """Main Streamlit app."""
    st.title("NutriScan: Barcode Scanner")
    st.write("Scan food barcodes with your iPhone photos! Powered by Open Food Facts.")
    st.write("Note: Adjust sliders based on scan results or label values (e.g., cornflakes: 357 cal, 85.7g carbs).")

    # Authentication
    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if not st.session_state.logged_in:
        st.subheader("Login")
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        if st.button("Login"):
            if username == "user" and password == "pass":
                st.session_state.logged_in = True
                st.success("Logged in!")
                st.rerun()
            else:
                st.error("Invalid username or password")
        return

    # Main app
    st.subheader("Nutritional Preferences")
    db = load_nutrition_db()
    avg_nutrients = {k: np.mean([item.get(k, 0) for item in db["barcodes"].values()]) for k in ["calories", "protein", "fat", "carbs", "sugar", "fiber"]}
    defaults = {
        "calories": avg_nutrients["calories"] if db["barcodes"] else 400,
        "protein": avg_nutrients["protein"] if db["barcodes"] else 2,
        "fat": avg_nutrients["fat"] if db["barcodes"] else 5,
        "carbs": avg_nutrients["carbs"] if db["barcodes"] else 90,
        "sugar": avg_nutrients["sugar"] if db["barcodes"] else 10,
        "fiber": avg_nutrients["fiber"] if db["barcodes"] else 1
    }
    max_calories = st.slider("Max Calories per Serving", 100, 1500, int(defaults["calories"]), 10)
    min_protein = st.slider("Min Protein per Serving (g)", 0, 50, int(defaults["protein"]), 1)
    max_fat = st.slider("Max Fat per Serving (g)", 0, 50, int(defaults["fat"]), 1)
    max_carbs = st.slider("Max Carbs per Serving (g)", 0, 100, int(defaults["carbs"]), 5)
    max_sugar = st.slider("Max Sugar per Serving (g)", 0, 50, int(defaults["sugar"]), 1)
    min_fiber = st.slider("Min Fiber per Serving (g)", 0, 20, int(defaults["fiber"]), 1)

    st.subheader("Scan History")
    plot_nutrition_histogram(db)

    st.subheader("Upload Barcode Image")
    uploaded_file = st.file_uploader("Choose an image (JPG)", type=["jpg", "jpeg"])

    if uploaded_file:
        try:
            # Image preview
            st.image(uploaded_file, caption="Uploaded Barcode", use_container_width=True)
            
            # Read image
            file_bytes = np.asarray(bytearray(uploaded_file.read()), dtype=np.uint8)
            image = cv2.imdecode(file_bytes, cv2.IMREAD_COLOR)
            if image is None:
                st.error("Failed to read image. Try another file.")
                logging.error("Failed to read uploaded image")
                return

            # Process barcode
            result = scan_barcode(image)
            
            # Display result
            if result:
                st.success(f"Found: {result.get('name')}")
                # Display as table
                df = pd.DataFrame([result], columns=["name", "calories", "fat", "carbs", "protein", "sugar", "fiber"])
                st.table(df)
                meets_criteria, mismatches = check_nutrition(result, max_calories, min_protein, max_fat, max_carbs, max_sugar, min_fiber)
                if meets_criteria:
                    st.write("✅ Meets your preferences!")
                else:
                    st.write("❌ Does not meet preferences!")
                    if mismatches:
                        st.write("Details:", ", ".join(mismatches))
                    else:
                        st.warning("No specific mismatch details available. Check image or sliders.")
                # Export option
                if st.button("Export Results"):
                    df.to_csv("scan_results.csv", index=False)
                    st.success("Exported to scan_results.csv!")
            else:
                st.error("Barcode not recognized. Check nutriscan.log for details.")
        except Exception as e:
            st.error("Processing failed. Check nutriscan.log.")
            logging.error(f"Image processing failed: {e}")

if __name__ == "__main__":
    try:
        logging.info("Starting NutriScan App")
        main()
        logging.info("NutriScan App completed")
    except Exception as e:
        logging.error(f"App crashed: {e}")
        st.error("App crashed. Check nutriscan.log.")