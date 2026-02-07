import streamlit as st
import pandas as pd
import plotly.express as px
from openai import OpenAI
import sqlite3
import time
from datetime import datetime
import random

# ==========================================
# 1. SETUP DATABASE (DUAL DB ARCHITECTURE)
# ==========================================

# --- DB 1: TRANSAKSI (compliance.db) ---
def init_txn_db():
    conn = sqlite3.connect('compliance.db')
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS transactions
                 (id TEXT PRIMARY KEY, user TEXT, amount REAL, type TEXT, 
                  timestamp TEXT, location TEXT, flag TEXT, reason TEXT)''')
    
    # Seed Data (Data Awal)
    if c.execute('SELECT count(*) FROM transactions').fetchone()[0] == 0:
        seed_data = [
            ("TXN_101", "USER_001", 200, "Deposit", "2024-02-07 09:00", "UK", "Clean", "-"),
            ("TXN_102", "USER_002", 9900, "Deposit", "2024-02-07 10:15", "Malta", "Suspicious", "Potential Structuring (<$10k)"),
            ("TXN_103", "USER_001", 5000, "Withdrawal", "2024-02-07 11:00", "North Korea", "Suspicious", "High Risk Jurisdiction"),
            ("TXN_104", "USER_003", 50000, "Deposit", "2024-02-07 12:30", "Indonesia", "Suspicious", "Exceeds 500% Monthly Income")
        ]
        c.executemany('INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)', seed_data)
        conn.commit()
    conn.close()

def get_transactions():
    conn = sqlite3.connect('compliance.db')
    df = pd.read_sql_query("SELECT * FROM transactions", conn)
    conn.close()
    return df

def add_transaction(id, user, amount, type_txn, loc, flag, reason):
    conn = sqlite3.connect('compliance.db')
    c = conn.cursor()
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    c.execute("INSERT INTO transactions VALUES (?,?,?,?,?,?,?,?)", 
              (id, user, amount, type_txn, timestamp, loc, flag, reason))
    conn.commit()
    conn.close()

# --- DB 2: REGULASI (regulations.db) ---
def init_reg_db():
    conn = sqlite3.connect('regulations.db')
    c = conn.cursor()
    # Tabel Rules: ID, Kategori, Isi Aturan, Terakhir Update
    c.execute('''CREATE TABLE IF NOT EXISTS rules
                 (id INTEGER PRIMARY KEY AUTOINCREMENT, category TEXT, rule_text TEXT, last_updated TEXT)''')
    
    # Seed Data (Aturan Deriv)
    if c.execute('SELECT count(*) FROM rules').fetchone()[0] == 0:
        seed_rules = [
            ("AML Threshold", "Report all cash transactions exceeding $10,000 within 24 hours.", "2024-01-01"),
            ("KYC Requirement", "Mandatory ID verification for all withdrawals > $500.", "2024-01-01"),
            ("Crypto Assets", "Travel Rule applies to crypto transfers > $3,000.", "2024-01-15"),
            ("Sanctions", "Auto-block transactions from: North Korea, Iran, Syria.", "2023-12-01")
        ]
        c.executemany('INSERT INTO rules (category, rule_text, last_updated) VALUES (?,?,?)', seed_rules)
        conn.commit()
    conn.close()

def get_rules():
    conn = sqlite3.connect('regulations.db')
    df = pd.read_sql_query("SELECT * FROM rules", conn)
    conn.close()
    return df

def update_rule(category, new_text):
    conn = sqlite3.connect('regulations.db')
    c = conn.cursor()
    now = datetime.now().strftime("%Y-%m-%d")
    
    # KITA PAKAI UPDATE, BUKAN INSERT
    # Agar baris yang lama langsung terganti dengan teks baru
    c.execute("UPDATE rules SET rule_text = ?, last_updated = ? WHERE category = ?", 
              (new_text, now, category))
    
    # Jika kategori tidak ditemukan (misal aturan baru), baru kita Insert
    if c.rowcount == 0:
        c.execute("INSERT INTO rules (category, rule_text, last_updated) VALUES (?,?,?)", 
                  (category, new_text, now))
        
    conn.commit()
    conn.close()

# Inisialisasi kedua DB saat start
init_txn_db()
init_reg_db()

# ==========================================
# 2. LOGIKA AI (OPENAI)
# ==========================================
st.set_page_config(page_title="Deriv Sentinel", page_icon="🛡️", layout="wide")

# Ganti seluruh bagian 'customers = { ... }' dengan ini:

customers = {
    "USER_001": {"name": "John Doe", "risk_profile": "Low", "declared_income": 5000, "occupation": "Teacher", "country": "UK"},
    "USER_002": {"name": "Crypto King", "risk_profile": "High", "declared_income": 20000, "occupation": "Trader", "country": "Malta"},
    "USER_003": {"name": "Jane Smith", "risk_profile": "Medium", "declared_income": 8000, "occupation": "Consultant", "country": "Indonesia"},
    "USER_004": {"name": "Nguyen Van", "risk_profile": "Medium", "declared_income": 4500, "occupation": "Dev", "country": "Vietnam"},
    "USER_005": {"name": "Chinedu O", "risk_profile": "High", "declared_income": 15000, "occupation": "Importer", "country": "Nigeria"},
    "USER_006": {"name": "Hans Muller", "risk_profile": "Low", "declared_income": 9500, "occupation": "Engineer", "country": "Germany"},
    "USER_007": {"name": "Silva Santos", "risk_profile": "Medium", "declared_income": 6000, "occupation": "Artist", "country": "Brazil"},
    "USER_008": {"name": "Kenji Tanaka", "risk_profile": "Low", "declared_income": 12000, "occupation": "Manager", "country": "Japan"},
    "USER_009": {"name": "Amira Y", "risk_profile": "High", "declared_income": 30000, "occupation": "Investor", "country": "UAE"}
}

def analyze_behavior(transaction_row, profile, api_key):
    if not api_key: return "⚠️ API Key Missing."
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
        Act as Senior AML Officer. Analyze risk:
        User: {profile['name']} (${profile['declared_income']}/mo)
        Txn: ${transaction_row['amount']} in {transaction_row['location']}
        Flag Reason: {transaction_row['reason']}
        Explain risk concisely.
        """
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content
    except Exception as e: return str(e)

def analyze_regulation(new_rule, current_rules_str, api_key):
    if not api_key: return "⚠️ API Key Missing."
    try:
        client = OpenAI(api_key=api_key)
        prompt = f"""
        Act as Regulatory Analyst.
        
        CURRENT DERIV RULES (From Database):
        {current_rules_str}
        
        NEW REGULATORY NEWS:
        "{new_rule}"
        
        Task:
        1. Does this conflict with current rules?
        2. Propose exact text update for our database.
        3. Urgency?
        """
        response = client.chat.completions.create(model="gpt-3.5-turbo", messages=[{"role": "user", "content": prompt}])
        return response.choices[0].message.content
    except Exception as e: return str(e)

# ==========================================
# 3. UI DASHBOARD
# ==========================================

# SIDEBAR
with st.sidebar:

    st.markdown("""
        <h1 style='text-align: center; color: #ff4b4b;'>
            🛡️ DERIV<br>SENTINEL
        </h1>
        <p style='text-align: center; font-style: italic;'>
            AI Compliance Manager
        </p>
        <hr>
        """, unsafe_allow_html=True)

    #api_key = st.text_input("OpenAI API Key", type="password")
    # --- GANTI BARIS LAMA DENGAN BLOK INI ---
    
    # 1. Cek dulu apakah ada Kunci Rahasia di Server (Secrets)
    if "OPENAI_API_KEY" in st.secrets:
        st.success("✅ API Key Loaded from Secrets")
        api_key = st.secrets["OPENAI_API_KEY"]
    
    # 2. Jika tidak ada (misal dijalankan di laptop tanpa setup), baru minta input
    else:
        st.warning("⚠️ Manual Mode")
        api_key = st.text_input("Enter OpenAI API Key", type="password")
    
    st.divider()
    st.subheader("⚡ Simulate Transaction")
    new_user = st.selectbox("User", options=customers.keys())
    new_amount = st.number_input("Amount ($)", value=10000)
    new_loc = st.text_input("Location", "Russia")
    if st.button("Inject Data"):
        flag, reason = "Clean", "-"
        if new_amount > 9000: flag, reason = "Suspicious", "Structuring / High Vol"
        if new_loc in ["North Korea", "Iran", "Russia"]: flag, reason = "Suspicious", "Sanctioned Geo"
        
        #new_id = f"TXN_{datetime.now().strftime('%M%S')}"
        new_id = f"TXN_{random.randint(10000, 99999)}"
        add_transaction(new_id, new_user, new_amount, "Transfer", new_loc, flag, reason)
        st.success("Injected!")
        st.rerun()

# MAIN PAGE
st.title("🛡️ Deriv Sentinel: AI Compliance Manager")

tab1, tab2 = st.tabs(["🚨 Behavioral Monitoring", "⚖️ Regulatory Intelligence"])

# --- TAB 1: TRANSAKSI (DB 1) ---
# --- TAB 1: TRANSAKSI (DB 1) ---
with tab1:
    # Ambil data terbaru
    df_trans = get_transactions()
    
    # Metrics Utama
    c1, c2, c3 = st.columns(3)
    c1.metric("Total Txn", len(df_trans))
    c2.metric("Suspicious Alerts", len(df_trans[df_trans['flag']=="Suspicious"]), delta_color="inverse")
    c3.metric("DB Status", "Online (compliance.db)", "SQLite")

    st.divider()
    
    # Layout: Tabel di Kiri (Lebar), Panel Analisis di Kanan (Sempit/Sticky)
    # Kita pakai layout 2 kolom agar analisis selalu terlihat di samping tabel
    col_table, col_analysis = st.columns([2, 1])
    
    with col_table:
        st.subheader("🔴 Live Transaction Feed (Select Row to Analyze)")
        
        # Fungsi warna (Merah muda jika Suspicious)
        def highlight_suspicious(row):
            return ['background-color: #ffe6e6' if row['flag'] == 'Suspicious' else '' for _ in row]

        # TABEL INTERAKTIF
        # on_select="rerun" membuat app refresh saat baris diklik
        event = st.dataframe(
            df_trans.style.apply(highlight_suspicious, axis=1), 
            use_container_width=True,
            on_select="rerun",
            selection_mode="single-row",
            hide_index=True
        )
    
    with col_analysis:
        st.subheader("🔍 AI Risk Detective")
        
        # LOGIKA DETEKSI KLIK
        # Cek apakah ada baris yang dipilih?
        if len(event.selection.rows) > 0:
            # Ambil index baris yang dipilih
            selected_index = event.selection.rows[0]
            # Ambil data transaksi dari dataframe berdasarkan index
            txn = df_trans.iloc[selected_index]
            
            # Tampilkan Kartu Preview Transaksi
            with st.container(border=True):
                st.markdown(f"**Target:** `{txn['id']}`")
                st.markdown(f"**User:** {txn['user']}")
                st.markdown(f"**Flag:** :red[{txn['flag']}]")
                st.caption(f"Reason: {txn['reason']}")
            
            # Tombol Analisis (Hanya muncul jika baris dipilih)
            if st.button("⚡ ANALYZE THIS RISK", type="primary", use_container_width=True):
                if not api_key: 
                    st.error("Masukkan API Key di Sidebar")
                else:
                    # Ambil profil user
                    # Gunakan .get() agar tidak error jika user baru (safety code)
                    prof = customers.get(txn['user'], {
                        "name": "Unknown", "occupation": "N/A", 
                        "declared_income": 0, "country": "Unknown"
                    })
                    
                    with st.spinner("🤖 AI is connecting dots..."):
                        # Panggil Fungsi AI
                        res = analyze_behavior(txn, prof, api_key)
                        
                        # Hasil Analisis
                        st.success("Analysis Complete")
                        st.info(res)
                        
                        # Action Buttons
                        b1, b2 = st.columns(2)
                        b1.button("Freeze Account", use_container_width=True)
                        b2.button("Ignore Alert", use_container_width=True)
                        
        else:
            # Tampilan Default (Jika belum ada yang diklik)
            st.info("👈 Silakan **KLIK salah satu baris** di tabel sebelah kiri untuk memulai investigasi AI.")
            st.image("https://cdn-icons-png.flaticon.com/512/6134/6134346.png", width=100)
            st.caption("AI standby waiting for selection...")

# --- TAB 2: REGULASI (DB 2) ---

with tab2:
    st.header("📰 Regulatory Intelligence Engine")
    st.caption("AI memonitor berita regulasi dan mencocokkannya dengan database aturan internal.")
    
    col_db, col_sim = st.columns([1, 1])
    
    with col_db:
        st.subheader("🗄️ Active Rules (Click to Copy)")
        
        # 1. Ambil Data
        df_rules = get_rules()
        
        # 2. Tampilkan Tabel dengan Fitur SELEKSI
        # on_select="rerun" artinya saat diklik, aplikasi refresh untuk memproses data
        event = st.dataframe(
            df_rules,
            on_select="rerun",
            selection_mode="single-row",
            use_container_width=True,
            hide_index=True
        )
        
        # Konversi ke string untuk konteks AI (Background process)
        rules_context = df_rules.to_string(index=False)
        
    with col_sim:
        st.subheader("⚡ Simulate New Regulation")
        
        # 3. Logika "Copy to Input"
        # Default text jika tidak ada yang dipilih
        default_text = "URGENT: New Directive requires lowering Crypto Travel Rule threshold from $3,000 to $1,000 effective immediately."
        
        # Cek apakah user mengklik baris tabel?
        if len(event.selection.rows) > 0:
            selected_index = event.selection.rows[0]
            # Ambil kolom 'rule_text' dari baris yang dipilih
            copied_text = df_rules.iloc[selected_index]['rule_text']
            # Masukkan ke session state agar text area berubah
            st.session_state['reg_input_area'] = copied_text
        elif 'reg_input_area' not in st.session_state:
            # Jika belum ada state, isi default
            st.session_state['reg_input_area'] = default_text

        # 4. Render Text Area yang terikat dengan Session State
        new_reg = st.text_area(
            "Paste News/Update (Or Select from Table):",
            height=150,
            key="reg_input_area" # Kunci rahasia agar bisa diupdate otomatis
        )
        
        # --- TARUH INI DI BAWAH KOTAK TEXT AREA DI TAB 2 ---
        
        col_btn1, col_btn2 = st.columns([1, 1])
        
        with col_btn1:
            if st.button("Assess Impact", type="primary", use_container_width=True):
                # ... (Kode Assess Impact yang lama tetap di sini) ...
                if not api_key: 
                    st.error("Need API Key")
                else:
                    with st.spinner("Comparing against DB..."):
                        impact = analyze_regulation(new_reg, rules_context, api_key)
                        st.markdown("### ⚠️ Impact Analysis")
                        st.write(impact)
                        st.session_state['impact_done'] = True # Penanda analisis selesai

        with col_btn2:
            # Tombol ini hanya aktif/berguna setelah analisis, tapi kita tampilkan terus
            if st.button("💾 Auto-Update Database", type="secondary", use_container_width=True):
                
                # 1. Tentukan Kategori mana yang mau diupdate
                target_category = "General"
                
                # Cek: Apakah user tadi memilih baris di tabel? (Prioritas Utama)
                if len(event.selection.rows) > 0:
                    idx = event.selection.rows[0]
                    target_category = df_rules.iloc[idx]['category']
                
                # Cek: Jika tidak pilih tabel, tebak dari kata kunci teks input (Fallback)
                else:
                    if "Crypto" in new_reg: target_category = "Crypto Assets"
                    elif "AML" in new_reg: target_category = "AML Threshold"
                    elif "KYC" in new_reg: target_category = "KYC Requirement"
                
                # 2. Lakukan Update SQL
                # Kita asumsikan AI sudah merangkum aturan baru (Simulasi: kita pakai input mentah user)
                # Agar terlihat rapi, kita bisa tambahkan prefix simulasi
                formatted_rule = f"{new_reg} (Updated via AI)"
                
                update_rule(target_category, formatted_rule)
                
                # 3. Feedback Visual
                st.toast(f"✅ Rule '{target_category}' successfully updated in SQL Database!", icon="💾")
                time.sleep(1) # Jeda sedikit biar user lihat toast

                st.rerun() # Refresh halaman agar Tabel Kiri berubah datanya

