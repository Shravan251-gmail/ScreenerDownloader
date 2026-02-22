#!/usr/bin/env python3
"""
Screener Master Pro - Streamlit UI
Downloads Annual Reports, Credit Ratings, Transcripts, Presentations, and Quarterly Reports
from Screener.in with a clean web interface.

Usage:
    streamlit run screener_app.py

Requirements:
    pip install streamlit selenium requests
    Google Chrome must be installed.
"""

import streamlit as st
import time
import re
import requests
import zipfile
import io
import tempfile
from pathlib import Path
from datetime import datetime, timedelta

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.action_chains import ActionChains


# ============================================================
# PAGE CONFIG
# ============================================================
st.set_page_config(page_title="Screener Master Pro", page_icon="📈", layout="wide")


# ============================================================
# SESSION STATE INIT
# ============================================================
if "search_results" not in st.session_state:
    st.session_state.search_results = []
if "selected_company" not in st.session_state:
    st.session_state.selected_company = None


# ============================================================
# HELPER: FILE DOWNLOADER
# ============================================================
def download_file(url: str, filepath: Path) -> bool:
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
        }
        response = requests.get(url, headers=headers, timeout=60, stream=True)
        response.raise_for_status()
        filepath.parent.mkdir(parents=True, exist_ok=True)
        with open(filepath, "wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        if filepath.stat().st_size < 1000:
            filepath.unlink()
            return False
        return True
    except Exception:
        return False


# ============================================================
# HELPER: SEARCH SCREENER API
# ============================================================
def search_screener(company_name: str):
    try:
        session = requests.Session()
        session.headers.update({"User-Agent": "Mozilla/5.0"})
        search_url = f"https://www.screener.in/api/company/search/?q={company_name}"
        response = session.get(search_url, timeout=10)
        return response.json()
    except Exception:
        return []


# ============================================================
# SIDEBAR
# ============================================================
with st.sidebar:
    st.header("1. Search Company")

    company_input = st.text_input("Company Name", placeholder="e.g. Reliance")

    if st.button("🔍 Search Screener"):
        if company_input.strip():
            with st.spinner("Searching..."):
                results = search_screener(company_input.strip())
                st.session_state.search_results = results
                st.session_state.selected_company = None
        else:
            st.warning("Please enter a company name.")

    if st.session_state.search_results:
        company_names = [r["name"] for r in st.session_state.search_results[:10]]
        selected_name = st.selectbox("Select exact company:", company_names)
        for r in st.session_state.search_results:
            if r["name"] == selected_name:
                st.session_state.selected_company = r
                break
        if st.session_state.selected_company:
            st.success(f"Selected: {st.session_state.selected_company['name']}")

    st.divider()

    # --- DOWNLOAD OPTIONS ---
    st.header("2. Download Options")
    d_annual = st.checkbox("Annual Reports", value=True)
    d_credit = st.checkbox("Credit Ratings", value=True)
    d_transcripts = st.checkbox("Transcripts")
    d_presentations = st.checkbox("Presentations")
    d_quarterly = st.checkbox("Quarterly Reports")

    st.divider()

    # --- HISTORY LIMITS (only show relevant ones) ---
    st.header("3. History Limits")
    st.caption("Set to 0 for all available data")

    num_annual = 1
    num_credit = 1
    num_concalls = 4
    num_quarterly = 4

    if d_annual:
        num_annual = st.number_input("How many years of Annual Reports would you like to download?", min_value=0, value=1)
    if d_credit:
        num_credit = st.number_input("How many years of Credit Rating Reports would you like to download?", min_value=0, value=1)
    if d_transcripts or d_presentations:
        num_concalls = st.number_input("How many quarters of Transcripts/Presentations would you like to download?", min_value=0, value=4)
    if d_quarterly:
        num_quarterly = st.number_input("How many Quarterly Results would you like to download?", min_value=0, value=4)

    if not (d_annual or d_credit or d_transcripts or d_presentations or d_quarterly):
        st.info("Select at least one download option above.")


# ============================================================
# MAIN AREA
# ============================================================
st.title("📈 Screener Master Pro")

st.caption("This program retrieves data from Screener.in and is contingent on Screener working. Google Chrome must be installed on your system for this program to work.")

if not st.session_state.selected_company:
    st.info("👈 Search for a company in the sidebar, select it, choose your download options, then click **Start Download** below.")

any_selected = d_annual or d_credit or d_transcripts or d_presentations or d_quarterly

if st.session_state.selected_company and not any_selected:
    st.warning("Please select at least one document type to download.")

# ============================================================
# START DOWNLOAD + CLEAN PROGRESS
# ============================================================
if st.session_state.selected_company and any_selected:
    if st.button("🚀 Start Master Download", type="primary"):

        selected = st.session_state.selected_company
        screener_url = f"https://www.screener.in{selected.get('url', '')}"
        company_display_name = selected["name"]

        downloaded_count = 0
        skipped_count = 0
        failed_count = 0
        driver = None

        # A single status line that updates in place
        progress_status = st.empty()
        # Container for completion messages
        results_container = st.container()

        progress_status.info(f"⏳ **Download in progress** — Setting up browser...")

        try:
            # --- BROWSER SETUP ---
            # Uses Selenium's built-in selenium-manager to auto-match ChromeDriver
            # to the installed Chrome version. No webdriver-manager needed.
            chrome_options = Options()
            chrome_options.add_argument("--headless=new")
            chrome_options.add_argument("--no-sandbox")
            chrome_options.add_argument("--disable-dev-shm-usage")
            chrome_options.add_argument("--window-size=1920,10000")

            driver = webdriver.Chrome(options=chrome_options)
            driver.set_page_load_timeout(60)

            progress_status.info(f"⏳ **Download in progress** — Loading {company_display_name}...")
            driver.get(screener_url)
            time.sleep(5)

            safe_company_name = re.sub(r"[^\w\-_\. ]", "_", company_display_name)
            temp_base = Path(tempfile.mkdtemp())
            company_dir = temp_base / safe_company_name

            # ============================
            # ANNUAL REPORTS
            # ============================
            if d_annual:
                progress_status.info("⏳ **Download in progress** — Processing Annual Reports...")

                annual_cutoff_date = None if num_annual == 0 else datetime.now() - timedelta(days=num_annual * 365)

                try:
                    h = driver.find_element(By.XPATH, "//h3[contains(text(), 'Annual reports')]")
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", h)
                    time.sleep(3)
                except: pass

                if num_annual == 0 or num_annual > 5:
                    try:
                        sec = driver.find_element(By.XPATH, "//h3[contains(text(), 'Annual reports')]/parent::div")
                        smb = sec.find_element(By.CSS_SELECTOR, "div.show-more-box")
                        ico = smb.find_element(By.CSS_SELECTOR, "i.icon-down")
                        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", ico)
                        time.sleep(1)
                        try:
                            ActionChains(driver).move_to_element(ico).perform()
                            time.sleep(0.5)
                        except: pass
                        try: ico.click()
                        except: driver.execute_script("arguments[0].click();", ico)
                        time.sleep(3)
                        for _ in range(10):
                            driver.execute_script("window.scrollBy(0, 100);")
                            time.sleep(0.3)
                        time.sleep(1)
                    except: pass

                time.sleep(2)

                all_links = driver.find_elements(By.TAG_NAME, "a")
                annual_reports = []
                seen = set()
                for link in all_links:
                    try:
                        text = link.text.strip()
                        href = link.get_attribute("href")
                        ym = re.search(r"20\d{2}", text)
                        if ym and "financial year" in text.lower() and "from" in text.lower() and href and href not in seen:
                            year = int(ym.group())
                            if annual_cutoff_date and datetime(year, 12, 31) < annual_cutoff_date:
                                continue
                            annual_reports.append({"year": year, "url": href})
                            seen.add(href)
                    except: continue

                annual_reports.sort(key=lambda x: x["year"], reverse=True)

                annual_dir = company_dir / "Annual_Reports"
                section_dl = 0
                section_skip = 0
                section_fail = 0
                for idx, rpt in enumerate(annual_reports, 1):
                    yr = rpt["year"]
                    fp = annual_dir / f"Annual_Report_{yr}.pdf"
                    if fp.exists() and fp.stat().st_size > 5000:
                        section_skip += 1
                        skipped_count += 1
                    else:
                        if download_file(rpt["url"], fp):
                            section_dl += 1
                            downloaded_count += 1
                        else:
                            section_fail += 1
                            failed_count += 1
                    if idx < len(annual_reports): time.sleep(1)

                with results_container:
                    msg = f"✅ **Annual Reports** — {section_dl} downloaded"
                    if section_skip: msg += f", {section_skip} already existed"
                    if section_fail: msg += f", {section_fail} failed"
                    if not annual_reports: msg = "⊙ **Annual Reports** — none found"
                    st.write(msg)

            # ============================
            # CREDIT RATINGS
            # ============================
            if d_credit:
                progress_status.info("⏳ **Download in progress** — Processing Credit Ratings...")

                credit_cutoff_date = None if num_credit == 0 else datetime.now() - timedelta(days=num_credit * 365)

                try:
                    h = driver.find_element(By.XPATH, "//h3[contains(text(), 'Credit ratings')]")
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", h)
                    time.sleep(3)
                except: pass

                try:
                    sec = driver.find_element(By.XPATH, "//h3[contains(text(), 'Credit ratings')]/parent::div")
                    smb = sec.find_element(By.CSS_SELECTOR, "div.show-more-box")
                    ico = smb.find_element(By.CSS_SELECTOR, "i.icon-down")
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", ico)
                    time.sleep(1)
                    try:
                        ActionChains(driver).move_to_element(ico).perform()
                        time.sleep(0.5)
                    except: pass
                    try: ico.click()
                    except: driver.execute_script("arguments[0].click();", ico)
                    time.sleep(3)
                    for _ in range(10):
                        driver.execute_script("window.scrollBy(0, 100);")
                        time.sleep(0.3)
                    time.sleep(1)
                except: pass

                time.sleep(2)

                all_links = driver.find_elements(By.TAG_NAME, "a")
                ratings = []
                seen = set()
                for link in all_links:
                    try:
                        text = link.text.strip()
                        href = link.get_attribute("href") or ""
                        if ("rating update" in text.lower() or "rating" in text.lower()) and "from" in text.lower() and href and href not in seen:
                            dm = re.search(r"(\d{1,2})\s+([A-Za-z]{3})\s+(\d{4})", text)
                            if dm:
                                day, ms, yr = dm.groups()
                                months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                                mo = months.get(ms.lower()[:3])
                                if mo:
                                    rd = datetime(int(yr), mo, int(day))
                                    if credit_cutoff_date and rd < credit_cutoff_date: continue
                                    am = re.search(r"from\s+(\w+)", text.lower())
                                    ag = am.group(1) if am else "unknown"
                                    ratings.append({"date": rd, "url": href, "agency": ag})
                                    seen.add(href)
                    except: continue

                ratings.sort(key=lambda x: x["date"], reverse=True)

                ratings_dir = company_dir / "Credit_Ratings"
                section_dl = 0
                section_skip = 0
                section_fail = 0
                for idx, rat in enumerate(ratings, 1):
                    ds = rat["date"].strftime("%Y-%m-%d")
                    ag = rat["agency"].upper()
                    fp = ratings_dir / f"Credit_Rating_{ds}_{ag}.pdf"
                    if fp.exists() and fp.stat().st_size > 5000:
                        section_skip += 1
                        skipped_count += 1
                    else:
                        if download_file(rat["url"], fp):
                            section_dl += 1
                            downloaded_count += 1
                        else:
                            section_fail += 1
                            failed_count += 1
                    if idx < len(ratings): time.sleep(1)

                with results_container:
                    msg = f"✅ **Credit Ratings** — {section_dl} downloaded"
                    if section_skip: msg += f", {section_skip} already existed"
                    if section_fail: msg += f", {section_fail} failed"
                    if not ratings: msg = "⊙ **Credit Ratings** — none found"
                    st.write(msg)

            # ============================
            # TRANSCRIPTS & PRESENTATIONS
            # ============================
            if d_transcripts or d_presentations:
                progress_status.info("⏳ **Download in progress** — Processing Transcripts & Presentations...")

                try:
                    h = driver.find_element(By.XPATH, "//h3[contains(text(), 'Concalls')]")
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", h)
                    time.sleep(2)
                    driver.execute_script("window.scrollBy(0, 200);")
                    time.sleep(2)
                except: pass

                try:
                    driver.execute_script("window.scrollBy(0, 300);")
                    time.sleep(2)
                    for btn in driver.find_elements(By.CSS_SELECTOR, "button.show-more-button"):
                        try:
                            par = btn.find_element(By.XPATH, "../..")
                            if "concall" in par.text.lower():
                                btn.click()
                                time.sleep(10)
                                for _ in range(20):
                                    driver.execute_script("window.scrollBy(0, 250);")
                                    time.sleep(0.3)
                                time.sleep(5)
                                try:
                                    h2 = driver.find_element(By.XPATH, "//h3[contains(text(), 'Concalls')]")
                                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'start'});", h2)
                                    time.sleep(3)
                                except: pass
                                break
                        except: continue
                except: pass

                time.sleep(3)

                all_links = driver.find_elements(By.TAG_NAME, "a")
                concalls_data = {}
                for link in all_links:
                    try:
                        text = link.text.strip().lower()
                        href = link.get_attribute("href") or ""
                        is_t = text == "transcript"
                        is_p = text == "ppt"
                        if (is_t or is_p) and href:
                            date_found = None
                            for xpath in ["..", "../..", "../../.."]:
                                try:
                                    el = link.find_element(By.XPATH, xpath)
                                    dm = re.search(r"([A-Za-z]{3})\s+(\d{4})", el.text)
                                    if dm:
                                        date_found = f"{dm.group(1)} {dm.group(2)}"
                                        break
                                except: pass
                            if date_found:
                                try:
                                    months = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                                    ms, yr = date_found.split()
                                    mo = months.get(ms.lower()[:3])
                                    cd = datetime(int(yr), mo, 1)
                                    ds = cd.strftime("%Y-%m")
                                    if ds not in concalls_data:
                                        concalls_data[ds] = {"date": cd, "display": date_found, "transcript": None, "ppt": None}
                                    if is_t: concalls_data[ds]["transcript"] = href
                                    elif is_p: concalls_data[ds]["ppt"] = href
                                except: continue
                    except: continue

                sorted_dates = sorted(concalls_data.keys(), reverse=True)
                if num_concalls and num_concalls > 0:
                    sorted_dates = sorted_dates[:num_concalls]

                t_dir = company_dir / "Transcripts"
                p_dir = company_dir / "Presentations"

                t_dl = 0; t_skip = 0; t_fail = 0
                p_dl = 0; p_skip = 0; p_fail = 0

                for idx, dk in enumerate(sorted_dates, 1):
                    d = concalls_data[dk]

                    if d_transcripts and d["transcript"]:
                        fp = t_dir / f"Transcript_{dk}.pdf"
                        if fp.exists() and fp.stat().st_size > 1000:
                            t_skip += 1; skipped_count += 1
                        else:
                            if download_file(d["transcript"], fp):
                                t_dl += 1; downloaded_count += 1
                            else:
                                t_fail += 1; failed_count += 1

                    if d_presentations and d["ppt"]:
                        fp = p_dir / f"PPT_{dk}.pdf"
                        if fp.exists() and fp.stat().st_size > 1000:
                            p_skip += 1; skipped_count += 1
                        else:
                            if download_file(d["ppt"], fp):
                                p_dl += 1; downloaded_count += 1
                            else:
                                p_fail += 1; failed_count += 1

                    if idx < len(sorted_dates): time.sleep(1)

                with results_container:
                    if d_transcripts:
                        msg = f"✅ **Transcripts** — {t_dl} downloaded"
                        if t_skip: msg += f", {t_skip} already existed"
                        if t_fail: msg += f", {t_fail} failed"
                        if not sorted_dates: msg = "⊙ **Transcripts** — none found"
                        st.write(msg)

                    if d_presentations:
                        msg = f"✅ **Presentations** — {p_dl} downloaded"
                        if p_skip: msg += f", {p_skip} already existed"
                        if p_fail: msg += f", {p_fail} failed"
                        if not sorted_dates: msg = "⊙ **Presentations** — none found"
                        st.write(msg)

            # ============================
            # QUARTERLY REPORTS
            # ============================
            if d_quarterly:
                progress_status.info("⏳ **Download in progress** — Processing Quarterly Reports...")

                try:
                    h = driver.find_element(By.XPATH, "//h2[contains(text(), 'Quarterly Results')]")
                    driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", h)
                    time.sleep(2)
                except: pass

                time.sleep(2)

                all_links = driver.find_elements(By.TAG_NAME, "a")
                qr = []
                for link in all_links:
                    try:
                        href = link.get_attribute("href") or ""
                        aria = link.get_attribute("aria-label") or ""
                        if "raw pdf" in aria.lower() and "/company/source/quarter/" in href:
                            try:
                                ptd = link.find_element(By.XPATH, "..")
                                tbl = ptd.find_element(By.XPATH, "ancestor::table[1]")
                                hdrs = tbl.find_elements(By.XPATH, ".//thead//th | .//tr[1]//td")
                                row = ptd.find_element(By.XPATH, "..")
                                cells = row.find_elements(By.TAG_NAME, "td")
                                ci = None
                                for i, c in enumerate(cells):
                                    if c == ptd: ci = i; break
                                if ci is not None and ci < len(hdrs):
                                    ht = hdrs[ci].text.strip()
                                    dm = re.search(r"([A-Za-z]{3})\s+(\d{4})", ht)
                                    if dm:
                                        ms, yr = dm.groups()
                                        months_map = {"jan":1,"feb":2,"mar":3,"apr":4,"may":5,"jun":6,"jul":7,"aug":8,"sep":9,"oct":10,"nov":11,"dec":12}
                                        mo = months_map.get(ms.lower()[:3])
                                        if mo:
                                            qr.append({"date": datetime(int(yr), mo, 1), "display": f"{ms} {yr}", "date_str": f"{yr}-{mo:02d}", "url": href})
                            except: pass
                    except: continue

                qr.sort(key=lambda x: x["date"], reverse=True)
                if num_quarterly and num_quarterly > 0:
                    qr = qr[:num_quarterly]

                q_dir = company_dir / "Quarterly_Reports"
                section_dl = 0
                section_skip = 0
                section_fail = 0
                for idx, rpt in enumerate(qr, 1):
                    fp = q_dir / f"Quarterly_Report_{rpt['date_str']}.pdf"
                    if fp.exists() and fp.stat().st_size > 5000:
                        section_skip += 1; skipped_count += 1
                    else:
                        if download_file(rpt["url"], fp):
                            section_dl += 1; downloaded_count += 1
                        else:
                            section_fail += 1; failed_count += 1
                    if idx < len(qr): time.sleep(1)

                with results_container:
                    msg = f"✅ **Quarterly Reports** — {section_dl} downloaded"
                    if section_skip: msg += f", {section_skip} already existed"
                    if section_fail: msg += f", {section_fail} failed"
                    if not qr: msg = "⊙ **Quarterly Reports** — none found"
                    st.write(msg)

            # DONE
            progress_status.success(f"✅ **Download complete!** Click the button below to save your files.")

        except Exception as e:
            progress_status.error(f"❌ Error: {str(e)}")
        finally:
            if driver:
                try: driver.quit()
                except: pass

        # SUMMARY
        st.divider()
        st.markdown("### 📊 Download Summary")
        c1, c2, c3 = st.columns(3)
        c1.metric("Downloaded", downloaded_count)
        c2.metric("Skipped", skipped_count)
        c3.metric("Failed", failed_count)

        # AUTO-DOWNLOAD ZIP
        if downloaded_count > 0 and company_dir.exists():
            import base64
            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
                for file_path in sorted(company_dir.rglob("*")):
                    if file_path.is_file():
                        arcname = file_path.relative_to(company_dir.parent)
                        zf.write(file_path, arcname)
            zip_buffer.seek(0)
            b64 = base64.b64encode(zip_buffer.read()).decode()
            zip_filename = f"{safe_company_name}.zip"
            auto_download_html = f'''
                <html>
                <body>
                <a id="auto_dl" href="data:application/zip;base64,{b64}" download="{zip_filename}"></a>
                <script>document.getElementById("auto_dl").click();</script>
                </body>
                </html>
            '''
            st.components.v1.html(auto_download_html, height=0)
