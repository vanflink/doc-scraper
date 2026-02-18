import streamlit as st
import cloudscraper  # <--- DAS IST NEU
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
        secret_pw = st.secrets["app_password"]
        if st.session_state.password_input == secret_pw:
            st.session_state.authenticated = True
            del st.session_state.password_input
        else:
            st.error("❌ Wrong password")
    except FileNotFoundError:
        st.error("⚠️ Secrets file not found.")
    except KeyError:
        st.error("⚠️ Key Error in Secrets.")

if not st.session_state.authenticated:
    st.title("🔒 Login Required")
    st.text_input("Please enter the password:", type="password", key="password_input", on_change=check_password)
    st.stop()

# =========================================================
#  ⬇️ MAIN TOOL (DOC CLOUDSCRAPER VERSION) ⬇️
# =========================================================

st.title("➕ Doc Scraper (Anti-Block)")
st.markdown("Paste your list of PZNs below. Uses advanced evasion to bypass blocks.")

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
    normalized_input = pzn_input.replace(',', '\n')
    pzns = [line.strip() for line in normalized_input.split('\n') if line.strip()]
    
    if not pzns:
        st.error("Please enter at least one PZN.")
    else:
        with col2:
            st.info(f"Processing {len(pzns)} products...")
            progress_bar = st.progress(0)
            status_text = st.empty()
            
        results = []
        
        # --- HIER IST DER TRICK ---
        # Wir erstellen einen "Scraper", der sich wie ein echter Browser verhält
        scraper = cloudscraper.create_scraper() 

        for i, pzn in enumerate(pzns):
            url = f"https://www.docmorris.de/{pzn}"
            status_text.text(f"Fetching PZN {pzn} ({i+1}/{len(pzns)})...")
            
            try:
                # Wir nutzen jetzt 'scraper.get' statt 'requests.get'
                response = scraper.get(url, timeout=20)
                
                if response.status_code == 200:
                    soup = BeautifulSoup(response.content, "html.parser")
                    
                    # --- CORE DATA ---
                    name = get_text(soup, "h1")
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
                        "Link": url
                    })
                    
                elif response.status_code == 404:
                    results.append({"PZN": pzn, "Name": "❌ Not found", "Link": url})
                elif response.status_code == 403:
                    results.append({"PZN": pzn, "Name": "⛔ Blocked (Try again later)", "Link": url})
                else:
                    results.append({"PZN": pzn, "Name": f"Error {response.status_code}", "Link": url})

            except Exception as e:
                # Cloudscraper wirft oft spezifische Fehler, wenn er Cloudflare nicht lösen kann
                results.append({"PZN": pzn, "Name": "Error", "Link": url, "Marke": str(e)})
            
            progress_bar.progress((i + 1) / len(pzns))
            # Zufällige Pause, um menschlich zu wirken
            time.sleep(random.uniform(2.0, 4.0)) 

        status_text.text("✅ Finished!")
        
        if results:
            df = pd.DataFrame(results)
            cols = ["PZN", "Name", "Marke", "Preis", "Wirkstoffe", "Dosierung", "Link"]
            final_cols = [c for c in cols if c in df.columns]
            df = df[final_cols]
            
            st.divider()
            st.dataframe(df, use_container_width=True)
            
            csv = df.to_csv(index=False, sep=";", encoding="utf-8-sig").encode('utf-8-sig')
            st.download_button(label="💾 Download CSV", data=csv, file_name="doc_export.csv", mime="text/csv")
