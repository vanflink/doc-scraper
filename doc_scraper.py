import streamlit as st
import requests
from bs4 import BeautifulSoup
import pandas as pd
import time
import random

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="Doc Scraper", page_icon="➕", layout="wide")

# --- AUTHENTICATION LOGIC ---
if 'authenticated' not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    try:
        # Wir prüfen nur das App-Passwort, der API-Key wird später genutzt
        secret_pw = st.secrets["app_password"]
        if st.session_state.password_input == secret_pw:
            st.session_state.authenticated = True
            del st.session_state.password_input
        else:
            st.error("❌ Wrong password")
    except Exception:
        st.error("⚠️ Secrets not configured correctly.")

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    st.text_input("Please enter the password:", type="password", key="password_input", on_change=check_password)
    st.stop()

# =========================================================
#  ⬇️ MAIN TOOL (SCRAPERAPI VERSION) ⬇️
# =========================================================

st.title("➕ Doc Scraper (Pro Proxy)")
st.markdown("Paste your list of PZNs below. Uses ScraperAPI to bypass WAF blocks.")

default_pzns = "40554, 3161577\n18661452"
col1, col2 = st.columns([1, 2])

with col1:
    pzn_input = st.text_area("Enter PZNs:", value=default_pzns, height=300)
    start_button = st.button("🚀 Fetch Data", type="primary", use_container_width=True)

def get_text(soup, selector):
    element = soup.select_one(selector)
    if element:
        return element.get_text(strip=True, separator=" ")
    return "n.a."

if start_button:
    # 1. API KEY LADEN
    try:
        api_key = st.secrets["scraper_api_key"]
    except KeyError:
        st.error("🚨 API Key missing! Please add 'scraper_api_key' to Streamlit Secrets.")
        st.stop()

    normalized_input = pzn_input.replace(',', '\n')
    pzns = [line.strip() for line in normalized_input.split('\n') if line.strip()]
    
    if not pzns:
        st.error("Please enter at least one PZN.")
    else:
        with col2:
            st.info(f"Processing {len(pzns)} products via Proxy...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
        results = []

        for i, pzn in enumerate(pzns):
            target_url = f"https://www.docmorris.de/{pzn}"
            status_text.text(f"Fetching PZN {pzn} ({i+1}/{len(pzns)})...")
            
            # Anfrage über ScraperAPI leiten
            payload = {
                'api_key': api_key,
                'url': target_url,
                'keep_headers': 'true', 
            }
            
            try:
                # Wir rufen api.scraperapi.com auf, nicht DocMorris direkt
                response = requests.get('http://api.scraperapi.com', params=payload, timeout=60)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")
                    
                    # --- DATEN EXTRAHIEREN ---
                    name = get_text(soup, "h1")
                    # Bereinigung: "- Jetzt..." entfernen
                    if " - Jetzt" in name:
                        name = name.split(" - Jetzt")[0].strip()

                    brand = get_text(soup, "a.underline.text-neutral-700")
                    price = get_text(soup, "div.mr-2")
                    
                    # --- DETAILS ---
                    wirkstoffe = get_text(soup, "#Wirkstoffe-content")
                    if wirkstoffe == "n.a.": 
                        wirkstoffe = get_text(soup, "div.p-0.rounded-lg")

                    dosierung = get_text(soup, "#Dosierung-content")
                    nebenwirkungen = get_text(soup, "#Nebenwirkungen-content")
                    
                    results.append({
                        "PZN": pzn,
                        "Name": name,
                        "Marke": brand,
                        "Preis": price,
                        "Wirkstoffe": wirkstoffe[:500], 
                        "Dosierung": dosierung[:500],
                        "Link": target_url
                    })
                    
                elif response.status_code == 404:
                    results.append({"PZN": pzn, "Name": "❌ Not found", "Link": target_url})
                elif response.status_code == 403:
                    results.append({"PZN": pzn, "Name": "⛔ Blocked (Check API Quota)", "Link": target_url})
                else:
                    results.append({"PZN": pzn, "Name": f"Error {response.status_code}", "Link": target_url})

            except Exception as e:
                results.append({"PZN": pzn, "Name": "Error", "Link": target_url, "Marke": str(e)})
            
            progress_bar.progress((i + 1) / len(pzns))
            # Kurze Pause reicht, da wir über Proxy gehen
            time.sleep(0.5) 

        status_text.text("✅ Finished!")
        
        if results:
            df = pd.DataFrame(results)
            # Spalten sortieren
            cols = ["PZN", "Name", "Marke", "Preis", "Wirkstoffe", "Dosierung", "Link"]
            final_cols = [c for c in cols if c in df.columns]
            df = df[final_cols]
            
            st.divider()
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode('utf-8-sig')
            st.download_button(label="💾 Download CSV", data=csv, file_name="doc_export.csv", mime="text/csv")
