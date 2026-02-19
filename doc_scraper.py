import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Doc Scraper", page_icon="➕", layout="wide")

# --- AUTHENTICATION LOGIC ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    try:
        secret_pw = st.secrets["app_password"]
        if st.session_state.password_input == secret_pw:
            st.session_state.authenticated = True
            del st.session_state.password_input
        else:
            st.error("❌ Wrong password")
    except Exception:
        st.error("⚠️ Secrets not configured.")

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    st.text_input("Please enter the password:", type="password", key="password_input", on_change=check_password)
    st.stop()

# =========================================================
#  ⬇️ MAIN TOOL (ECO MODE + SMART PZN + DEEP SCANNER) ⬇️
# =========================================================

st.title("➕ Doc Scraper (Eco Mode)")
st.markdown("Fetches PZN data via ScraperAPI. Automatically fixes missing leading zeros.")

# Beispiel für kaputte PZNs ohne Nullen
default_pzns = "40554, 3161577\n18661452\nPZN: 1234567"
col1, col2 = st.columns([1, 2])

with col1:
    pzn_input = st.text_area("Enter PZNs:", value=default_pzns, height=300)
    start_button = st.button("🚀 Fetch Data", type="primary", use_container_width=True)

def get_text(soup, selector):
    """Safely extracts text."""
    if not soup:
        return "n.a."
    element = soup.select_one(selector)
    if element:
        return element.get_text(strip=True, separator="\n")
    return "n.a."

if start_button:
    try:
        api_key = st.secrets["scraper_api_key"]
    except KeyError:
        st.error("🚨 API Key missing! Add 'scraper_api_key' to Secrets.")
        st.stop()

    # --- SMARTER PZN WASCHGANG ---
    normalized_input = pzn_input.replace(',', '\n')
    raw_lines = [line.strip() for line in normalized_input.split('\n') if line.strip()]
    
    pzns = []
    for line in raw_lines:
        # 1. Wirft alle Buchstaben und Sonderzeichen raus, behält nur Zahlen
        clean_num = re.sub(r'\D', '', line)
        
        if clean_num:
            # 2. Füllt die Zahl mit führenden Nullen auf exakt 8 Stellen auf
            padded_pzn = clean_num.zfill(8)
            pzns.append(padded_pzn)
            
    # 3. Duplikate entfernen (aber Reihenfolge beibehalten)
    pzns = list(dict.fromkeys(pzns))
    # -----------------------------
    
    if not pzns:
        st.error("Please enter at least one valid PZN.")
    else:
        with col2:
            st.info(f"Processing {len(pzns)} products...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
        results = []

        for i, pzn in enumerate(pzns):
            # Nutzt jetzt die saubere, 8-stellige PZN für den Link
            target_url = f"https://www.docmorris.de/{pzn}"
            status_text.text(f"Fetching PZN {pzn} ({i+1}/{len(pzns)})...")
            
            payload = {
                'api_key': api_key,
                'url': target_url,
                'country_code': 'de', 
            }
            
            try:
                response = requests.get('http://api.scraperapi.com', params=payload, timeout=60)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")
                    
                    # --- BASIS DATEN ---
                    name = get_text(soup, "h1")
                    if " - Jetzt" in name: name = name.split(" - Jetzt")[0].strip()
                    brand = get_text(soup, "a.underline.text-neutral-700")
                    price = get_text(soup, "div.mr-2")
                    
                    # --- HERSTELLER & TIEFENSAN FÜR ADRESSE ---
                    hersteller = get_text(soup, ".text-left.font-semibold span")
                    if hersteller == "n.a." and brand != "n.a.":
                        hersteller = brand

                    hersteller_adresse = "n.a."

                    # Stufe 1: JSON-LD
                    for script in soup.find_all("script", type="application/ld+json"):
                        try:
                            data = json.loads(script.string)
                            items = data if isinstance(data, list) else [data]
                            for item in items:
                                if "Product" in item.get("@type", ""):
                                    manuf = item.get("manufacturer", {})
                                    if isinstance(manuf, dict):
                                        addr = manuf.get("address", {})
                                        if isinstance(addr, dict):
                                            street = addr.get("streetAddress", "")
                                            zip_code = addr.get("postalCode", "")
                                            city = addr.get("addressLocality", "")
                                            if zip_code or city:
                                                hersteller_adresse = f"{street}, {zip_code} {city}".strip(" ,")
                                                break
                        except Exception:
                            pass

                    # Stufe 2: React State
                    if hersteller_adresse == "n.a.":
                        for script in soup.find_all("script"):
                            text = script.string or ""
                            if "postalCode" in text or "zipCode" in text:
                                street_match = re.search(r'"(?:streetAddress|street|strasse)"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
                                zip_match = re.search(r'"(?:postalCode|zipCode|zip|plz)"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
                                city_match = re.search(r'"(?:addressLocality|city|ort)"\s*:\s*"([^"]+)"', text, re.IGNORECASE)
                                
                                if zip_match and city_match:
                                    street = street_match.group(1) if street_match else ""
                                    hersteller_adresse = f"{street}, {zip_match.group(1)} {city_match.group(1)}".strip(" ,")
                                    break

                    # Stufe 3: Fallback Regex
                    if hersteller_adresse == "n.a.":
                        full_text = soup.get_text(" ", strip=True)
                        match = re.search(r"(?:Pharmazeutischer Unternehmer|Hersteller)[\s:]*(.*?)(?:Telefon|Tel\.|Fax|E-Mail|Stand|Zu Risiken|www\.)", full_text, re.IGNORECASE)
                        if match and 5 < len(match.group(1).strip()) < 150:
                            hersteller_adresse = match.group(1).strip()

                    # --- DROPDOWNS ---
                    wirkstoffe = get_text(soup, "#Wirkstoffe-content")
                    if wirkstoffe == "n.a.": wirkstoffe = get_text(soup, "div.p-0.rounded-lg")
                    dosierung = get_text(soup, "#Dosierung-content")
                    nebenwirkungen = get_text(soup, "#Nebenwirkungen-content")
                    gegenanzeigen = get_text(soup, "#Gegenanzeigen-content")
                    hilfsstoffe = get_text(soup, "#Hilfsstoffe-content")
                    warnhinweise = get_text(soup, "#WarnhinweiseHilfsstoffe-content")
                    wechselwirkungen = get_text(soup, "#Wechselwirkungen-content")
                    anwendungsgebiete = get_text(soup, "#Anwendungsgebiete-content")
                    anwendungshinweise = get_text(soup, "#Anwendungshinweise-content")
                    patientenhinweise = get_text(soup, "#Patientenhinweise-content")
                    stillzeit = get_text(soup, "#Stillzeit-content")
                    if stillzeit == "n.a.": stillzeit = get_text(soup, ".rounded-lg span > ul")
                    produktbeschreibung = get_text(soup, "div.innerHtml")

                    results.append({
                        "PZN": pzn,  # Speichert die saubere, 8-stellige PZN
                        "Name": name,
                        "Hersteller": hersteller,
                        "Adresse": hersteller_adresse,
                        "Marke": brand,
                        "Preis": price,
                        "Wirkstoffe": wirkstoffe,
                        "Dosierung": dosierung,
                        "Anwendungsgebiete": anwendungsgebiete,
                        "Anwendungshinweise": anwendungshinweise,
                        "Patientenhinweise": patientenhinweise,
                        "Nebenwirkungen": nebenwirkungen,
                        "Gegenanzeigen": gegenanzeigen,
                        "Wechselwirkungen": wechselwirkungen,
                        "Warnhinweise": warnhinweise,
                        "Hilfsstoffe": hilfsstoffe,
                        "Stillzeit": stillzeit,
                        "Produktbeschreibung": produktbeschreibung[:1000],
                        "Link": target_url
                    })
                    
                elif response.status_code == 404:
                    results.append({"PZN": pzn, "Name": "❌ Not found", "Link": target_url})
                elif response.status_code == 403:
                    results.append({"PZN": pzn, "Name": "⛔ Blocked", "Link": target_url})
                else:
                    results.append({"PZN": pzn, "Name": f"Error {response.status_code}", "Link": target_url})

            except Exception as e:
                results.append({"PZN": pzn, "Name": "Error", "Link": target_url, "Hersteller": str(e)})
            
            progress_bar.progress((i + 1) / len(pzns))
            time.sleep(0.5) 

        status_text.text("✅ Finished!")
        
        if results:
            df = pd.DataFrame(results)
            
            cols = [
                "PZN", "Name", "Hersteller", "Adresse", "Marke", "Preis", 
                "Wirkstoffe", "Dosierung", "Anwendungsgebiete", "Anwendungshinweise",
                "Patientenhinweise", "Nebenwirkungen", "Gegenanzeigen", "Wechselwirkungen",
                "Warnhinweise", "Hilfsstoffe", "Stillzeit", "Produktbeschreibung", "Link"
            ]
            final_cols = [c for c in cols if c in df.columns]
            df = df[final_cols]
            
            st.divider()
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode('utf-8-sig')
            st.download_button(label="💾 Download CSV", data=csv, file_name="doc_eco_export.csv", mime="text/csv")
