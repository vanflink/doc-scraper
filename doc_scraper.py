import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import re
import json
import gspread
from google.oauth2.service_account import Credentials

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
#  ⬇️ MAIN TOOL (ECO MODE + CLEAN EXPORT) ⬇️
# =========================================================

st.title("➕ Doc Scraper (Eco Mode)")
st.markdown("Fetches PZN data via ScraperAPI. Missing data will be completely blank.")

default_pzns = "40554, 3161577\n18661452"
col1, col2 = st.columns([1, 2])

with col1:
    pzn_input = st.text_area("Enter PZNs:", value=default_pzns, height=300)
    start_button = st.button("🚀 Fetch Data", type="primary", use_container_width=True)

def get_text(soup, selector):
    """Safely extracts text. Returns empty string if not found."""
    if not soup:
        return ""
    element = soup.select_one(selector)
    if element:
        return element.get_text(strip=True, separator="\n")
    return ""

if start_button:
    try:
        api_key = st.secrets["scraper_api_key"]
    except KeyError:
        st.error("🚨 API Key missing! Add 'scraper_api_key' to Secrets.")
        st.stop()

    normalized_input = pzn_input.replace(',', '\n')
    raw_lines = [line.strip() for line in normalized_input.split('\n') if line.strip()]
    
    pzns = []
    for line in raw_lines:
        clean_num = re.sub(r'\D', '', line)
        if clean_num:
            padded_pzn = clean_num.zfill(8)
            pzns.append(padded_pzn)
            
    pzns = list(dict.fromkeys(pzns))
    
    if not pzns:
        st.error("Please enter at least one valid PZN.")
    else:
        with col2:
            st.info(f"Processing {len(pzns)} products...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
        results = []

        for i, pzn in enumerate(pzns):
            target_url = f"https://www.docmorris.de/{pzn}"
            # NEU: Bild URL generieren
            bild_url = f"https://login.apopixx.de/media/image/web/750/web_schraeg/{pzn}.jpg"
            
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
                    
                    # --- HERSTELLER & ADRESSE ---
                    hersteller = get_text(soup, ".text-left.font-semibold span")
                    if hersteller == "" and brand != "":
                        hersteller = brand

                    hersteller_adresse = ""
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

                    if hersteller_adresse == "":
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

                    if hersteller_adresse == "":
                        full_text = soup.get_text(" ", strip=True)
                        match = re.search(r"(?:Pharmazeutischer Unternehmer|Hersteller)[\s:]*(.*?)(?:Telefon|Tel\.|Fax|E-Mail|Stand|Zu Risiken|www\.)", full_text, re.IGNORECASE)
                        if match and 5 < len(match.group(1).strip()) < 150:
                            hersteller_adresse = match.group(1).strip()

                    # --- DROPDOWNS ---
                    wirkstoffe = get_text(soup, "#Wirkstoffe-content")
                    if wirkstoffe == "": wirkstoffe = get_text(soup, "div.p-0.rounded-lg")
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
                    if stillzeit == "": stillzeit = get_text(soup, ".rounded-lg span > ul")
                    produktbeschreibung = get_text(soup, "div.innerHtml")

                    results.append({
                        "PZN": pzn,
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
                        "Link": target_url,
                        "Bild-Link": bild_url # NEU HINZUGEFÜGT
                    })
                    
                elif response.status_code == 404:
                    results.append({"PZN": pzn, "Name": "❌ Not found", "Link": target_url, "Bild-Link": bild_url})
                elif response.status_code == 403:
                    results.append({"PZN": pzn, "Name": "⛔ Blocked", "Link": target_url, "Bild-Link": bild_url})
                else:
                    results.append({"PZN": pzn, "Name": f"Error {response.status_code}", "Link": target_url, "Bild-Link": bild_url})

            except Exception as e:
                results.append({"PZN": pzn, "Name": "Error", "Link": target_url, "Bild-Link": bild_url, "Hersteller": str(e)})
            
            progress_bar.progress((i + 1) / len(pzns))
            time.sleep(0.5) 

        status_text.text("✅ Finished!")
        
        if results:
            df = pd.DataFrame(results)
            
            # --- DIE ZAUBERZEILE: Macht alle Pandas "NaN" und "None" zu leeren Feldern ---
            df = df.fillna("")
            
            # NEU: "Bild-Link" in die Spalten aufgenommen
            cols = [
                "PZN", "Name", "Hersteller", "Adresse", "Marke", "Preis", 
                "Wirkstoffe", "Dosierung", "Anwendungsgebiete", "Anwendungshinweise",
                "Patientenhinweise", "Nebenwirkungen", "Gegenanzeigen", "Wechselwirkungen",
                "Warnhinweise", "Hilfsstoffe", "Stillzeit", "Produktbeschreibung", "Link", "Bild-Link"
            ]
            final_cols = [c for c in cols if c in df.columns]
            df = df[final_cols]
            
            # Speichere df in der Session State, damit es für den GSheets Upload verfügbar bleibt
            st.session_state.final_df = df
            
if 'final_df' in st.session_state:
    df = st.session_state.final_df
    
    st.divider()
    st.dataframe(df, use_container_width=True)
    
    col_dl, col_gs = st.columns(2)
    
    with col_dl:
        csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode('utf-8-sig')
        st.download_button(label="💾 Download CSV", data=csv, file_name="doc_clean_export.csv", mime="text/csv", use_container_width=True)
        
    with col_gs:
        # --- GOOGLE SHEETS EXPORT LOGIC ---
        if st.button("📤 In Google Sheets überschreiben", type="secondary", use_container_width=True):
            try:
                # 1. Credentials aus Streamlit Secrets laden
                scopes = ["https://www.googleapis.com/auth/spreadsheets"]
                creds = Credentials.from_service_account_info(st.secrets["gcp_service_account"], scopes=scopes)
                client = gspread.authorize(creds)
                
                # 2. Sheet ID aus deiner URL
                sheet_id = "1yI0VVb1iNy0KkP4b8wVOFuWT08gWxgC75p1uZKIgAMI"
                sheet = client.open_by_key(sheet_id).sheet1 # Nimmt das erste Tabellenblatt
                
                # 3. Daten überschreiben (Zuerst alles löschen, dann Headers + Rows einfügen)
                sheet.clear()
                sheet.update([df.columns.values.tolist()] + df.values.tolist())
                
                st.success("✅ Google Sheet erfolgreich aktualisiert!")
            except Exception as e:
                st.error(f"❌ Fehler beim Upload: {e}")
                st.info("Hast du die `gcp_service_account` Secrets hinterlegt und das Sheet für die Service-Mail freigegeben?")
