# ➕ Doc Scraper

A Streamlit-based internal tool to extract pharmaceutical product data via PZN (Pharmazentralnummer). It uses ScraperAPI to bypass blocks and exports clean CSV files.

## ✨ Features
* **Smart PZN Formatting:** Auto-cleans inputs and pads to exactly 8 digits.
* **Eco Mode:** Highly efficient ScraperAPI usage without JS rendering (only 1 credit/request).
* **Deep Address Scanner:** Extracts hidden manufacturer addresses via JSON-LD, React states, and Regex.
* **Comprehensive Data:** Fetches price, active ingredients, dosage, side effects, and more.
* **Secure:** Password-protected access.

---

## 🚀 Usage (For Team Members)
1. Open the Streamlit Cloud link.
2. Enter the app password.
3. Paste a list of PZNs (formatting doesn't matter).
4. Click **Fetch Data** and download your `.csv` file.

---

## 💻 Local Development

### 1. Setup
Clone the repository and install the dependencies:
```bash
git clone <YOUR_GITHUB_REPO_LINK>
cd doc-scraper
pip install -r requirements.txt
