import streamlit as st
import pandas as pd
import psycopg2
from shapely.geometry import Point
import geopandas as gpd
import folium
from streamlit_folium import st_folium

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

# Postavi stranicu
st.set_page_config(page_title="GIS Upravljanje Otpadom", layout="wide", initial_sidebar_state="expanded")

# Naslov
st.title("🗺️ GIS Sistem za upravljanje otpadom — Novi Sad")

# Bočni meni
with st.sidebar:
    st.header("📋 Meni")
    menu = st.radio("Izaberi opciju:", [
        "Dashboard",
        "Lokacije",
        "Kontejneri",
        "Deponije",
        "ML Detekcija",
        "Spatial Analiza"
    ])

# ========== DASHBOARD ==========
if menu == "Dashboard":
    st.header("📊 Dashboard")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu Dashboard-a"):
        st.markdown("""
        ### Šta je Dashboard?
        Dashboard je početna stranica sa pregledom svih bitnih informacija o sistemu.
        
        ### Šta vidiš ovde?
        - **📍 Lokacije** — Broj svih registrovanih lokacija
        - **🗑️ Kontejneri** — Broj svih kontejnera u sistemu
        - **⚠️ Deponije** — Broj svih deponija (originalnih + ML detektovanih)
        
        ### Grafikoni
        - **Kontejneri po stanju** — Koliko je kontejnera u dobrom, oštećenom ili lošem stanju
        - **Deponije po statusu** — Koliko je deponija aktivnih, u sanaciji ili saniranih
        
        ### Mapa
        Mapa prikazuje sve lokacije sa markerima. Klikni na marker da vidiš naziv lokacije.
        
        ### Kako koristiti?
        1. Vrati se na dashboard kad god želiš da vidiš pregled sistema
        2. Koristi grafikone za analizu stanja kontejnera i deponija
        3. Koristi mapu za vizuelni pregled lokacija
        """)
    
    conn = get_connection()
    
    # Učitaj podatke
    lokacije = pd.read_sql("SELECT COUNT(*) as broj FROM lokacije", conn)
    kontejneri = pd.read_sql("SELECT COUNT(*) as broj FROM kontejneri", conn)
    deponije = pd.read_sql("SELECT COUNT(*) as broj FROM deponije", conn)
    
    # Statistika po stanju kontejnera
    stanje_stats = pd.read_sql("""
        SELECT stanje, COUNT(*) as broj 
        FROM kontejneri 
        GROUP BY stanje
    """, conn)
    
    # Statistika deponija po statusu
    status_stats = pd.read_sql("""
        SELECT status, COUNT(*) as broj 
        FROM deponije 
        GROUP BY status
    """, conn)
    
    # Lokacije sa koordinatama
    lokacije_data = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    
    conn.close()
    
    # Prikaži metrike
    col1, col2, col3 = st.columns(3)
    col1.metric("📍 Lokacije", lokacije.iloc[0]['broj'])
    col2.metric("🗑️ Kontejneri", kontejneri.iloc[0]['broj'])
    col3.metric("⚠️ Deponije", deponije.iloc[0]['broj'])
    
    st.divider()
    
    # Grafikoni
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("Kontejneri po stanju")
        st.bar_chart(stanje_stats.set_index('stanje')['broj'])
    
    with col2:
        st.subheader("Deponije po statusu")
        st.bar_chart(status_stats.set_index('status')['broj'])
    
    st.divider()
    
    # Mapa
    st.subheader("🗺️ Mapa lokacija")
    
    mapa = folium.Map(
        location=[45.2552, 19.8362],
        zoom_start=12,
        tiles='OpenStreetMap'
    )
    
    # Dodaj markere
    for idx, row in lokacije_data.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"<b>{row['naziv']}</b>",
            tooltip=row['naziv']
        ).add_to(mapa)
    
    st_folium(mapa, width=700, height=500)

# ========== LOKACIJE ==========
elif menu == "Lokacije":
    st.header("📍 Lokacije")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu stranice Lokacije"):
        st.markdown("""
        ### Šta je ova stranica?
        Stranica za upravljanje lokacijama — dodavanje, pregled i brisanje lokacija.
        
        ### Gornji deo — Sve lokacije
        Tabela prikazuje sve registrovane lokacije sa sledećim podacima:
        - **ID** — Jedinstveni identifikator
        - **Naziv** — Naziv lokacije
        - **Opština** — Opština u kojoj se nalazi
        - **Adresa** — Puна adresa
        - **Tip područja** — park, stambeno, industrijsko, itd.
        
        ### Donji deo — Dodaj novu lokaciju
        1. **Naziv lokacije** — Upiši jasan naziv (npr. "Liman park")
        2. **Opština** — Upiši opštinu (npr. "Novi Sad")
        3. **Adresa** — Upiši detaljnu adresu
        4. **Tip područja** — Odaberi iz padajuće liste
        5. **Geografska širina (lat)** — Upiši dekimalnu vrednost (npr. 45.2552)
        6. **Geografska dužina (lon)** — Upiši dekimalnu vrednost (npr. 19.8362)
        7. Klikni **"Spremi lokaciju"**
        
        ### Napomena
        Geografske koordinate (lat/lon) možeš pronaći na Google Maps.
        Klikni desni klik na mapu → "Šta je ovde?" za koordinate.
        """)
    
    conn = get_connection()
    
    # Prikaži sve lokacije
    st.subheader("Sve lokacije")
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, opstina, adresa, tip_podrucja FROM lokacije
    """, conn)
    
    st.dataframe(lokacije_df, use_container_width=True)
    
    st.divider()
    
    # Dodaj novu lokaciju
    st.subheader("➕ Dodaj novu lokaciju")
    
    col1, col2 = st.columns(2)
    
    with col1:
        naziv = st.text_input("Naziv lokacije")
        opstina = st.text_input("Opština")
    
    with col2:
        adresa = st.text_input("Adresa")
        tip_podrucja = st.selectbox("Tip područja", 
            ["park", "stambeno", "industrijsko", "prigradsko", "druge"])
    
    col1, col2 = st.columns(2)
    
    with col1:
        lat = st.number_input("Geografska širina (lat)", format="%.4f")
    
    with col2:
        lon = st.number_input("Geografska dužina (lon)", format="%.4f")
    
    if st.button("Spremi lokaciju"):
        if naziv and opstina and adresa:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO lokacije (naziv, opstina, adresa, tip_podrucja, geom)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            """, (naziv, opstina, adresa, tip_podrucja, lon, lat))
            conn.commit()
            st.success("✅ Lokacija je uspešno dodata!")
            st.rerun()
        else:
            st.error("❌ Popuni sve polje!")
    
    conn.close()

# ========== KONTEJNERI ==========
elif menu == "Kontejneri":
    st.header("🗑️ Kontejneri")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu stranice Kontejneri"):
        st.markdown("""
        ### Šta je ova stranica?
        Stranica za upravljanje kontejnerima — dodavanje novih i pregled postojećih kontejnera.
        
        ### Gornji deo — Svi kontejneri
        Tabela prikazuje sve kontejnere sa sledećim podacima:
        - **ID** — Jedinstveni identifikator
        - **Tip** — komunalni, reciklažni, podzemni
        - **Kapacitet (litara)** — Kapacitet kontejnera
        - **Stanje** — dobro, oštećen, loše
        - **Lokacija** — Gde se nalazi kontejner
        
        ### Donji deo — Dodaj novi kontejner
        1. **Tip kontejnera** — Odaberi iz padajuće liste
        2. **Kapacitet (litara)** — Upiši kapacitet (1100, 2500, 5000, itd.)
        3. **Stanje** — Odaberi trenutno stanje
        4. **Lokacija** — Odaberi lokaciju iz padajuće liste
        5. Klikni **"Spremi kontejner"**
        
        ### Napomena
        Lokaciju prvo trebas da kreiram na stranici "Lokacije".
        """)
    
    conn = get_connection()
    
    # Prikaži sve kontejnere
    st.subheader("Svi kontejneri")
    kontejneri_df = pd.read_sql("""
        SELECT k.id, k.tip, k.kapacitet_litara, k.stanje, 
               l.naziv as lokacija FROM kontejneri k
        JOIN lokacije l ON k.lokacija_id = l.id
    """, conn)
    
    st.dataframe(kontejneri_df, use_container_width=True)
    
    st.divider()
    
    # Dodaj novi kontejner
    st.subheader("➕ Dodaj novi kontejner")
    
    col1, col2 = st.columns(2)
    
    with col1:
        tip = st.selectbox("Tip kontejnera", 
            ["komunalni", "reciklažni", "podzemni"])
        kapacitet = st.number_input("Kapacitet (litara)", min_value=100, step=100)
    
    with col2:
        stanje = st.selectbox("Stanje", ["dobro", "oštećen", "loše"])
        
        # Učitaj lokacije
        lokacije_list = pd.read_sql(
            "SELECT id, naziv FROM lokacije ORDER BY naziv", conn
        )
        if len(lokacije_list) > 0:
            lokacija = st.selectbox("Lokacija", 
                lokacije_list['naziv'].tolist(),
                index=0)
        else:
            st.warning("⚠️ Prvo kreiraj lokaciju na stranici 'Lokacije'")
            lokacija = None
    
    if st.button("Spremi kontejner"):
        if lokacija:
            lokacija_id = lokacije_list[lokacije_list['naziv'] == lokacija]['id'].values[0]
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id)
                VALUES (%s, %s, %s, NOW(), %s)
            """, (tip, kapacitet, stanje, lokacija_id))
            conn.commit()
            st.success("✅ Kontejner je uspešno dodat!")
            st.rerun()
        else:
            st.error("❌ Prvo kreiraj lokaciju!")
    
    conn.close()

# ========== DEPONIJE ==========
elif menu == "Deponije":
    st.header("⚠️ Deponije")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu stranice Deponije"):
        st.markdown("""
        ### Šta je ova stranica?
        Stranica za upravljanje deponijama — dodavanje novih i pregled postojećih deponija.
        
        ### Gornji deo — Sve deponije
        Tabela prikazuje sve deponije sa sledećim podacima:
        - **ID** — Jedinstveni identifikator
        - **Naziv** — Naziv deponije
        - **Površina (m²)** — Površina deponije u kvadratnim metrima
        - **Tip otpada** — komunalni, građevinski, mešoviti, industrijski
        - **Status** — aktivna, u sanaciji, sanirana
        - **Lokacija** — Gde se nalazi deponija
        
        ### Donji deo — Prijavi novu deponiju
        1. **Naziv deponije** — Upiši jasan naziv (npr. "Deponija Klisa 1")
        2. **Površina (m²)** — Upiši površinu u kvadratnim metrima
        3. **Tip otpada** — Odaberi tip otpada
        4. **Status** — Odaberi trenutni status (aktivna, u sanaciji, sanirana)
        5. **Lokacija** — Odaberi lokaciju iz padajuće liste
        6. Klikni **"Spremi deponiju"**
        
        ### Napomena
        Površina deponije se može meriti na terenu ili na satelitskoj snimci.
        Status se može promeniti kasnije dok se sanacija sprovodi.
        """)
    
    conn = get_connection()
    
    # Prikaži sve deponije
    st.subheader("Sve deponije")
    deponije_df = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status,
               l.naziv as lokacija FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
    """, conn)
    
    st.dataframe(deponije_df, use_container_width=True)
    
    st.divider()
    
    # Dodaj novu deponiju
    st.subheader("➕ Prijavi novu deponiju")
    
    col1, col2 = st.columns(2)
    
    with col1:
        naziv = st.text_input("Naziv deponije")
        povrsina = st.number_input("Površina (m²)", min_value=10, step=10)
    
    with col2:
        tip_otpada = st.selectbox("Tip otpada", 
            ["komunalni", "građevinski", "mešoviti", "industrijski"])
        status = st.selectbox("Status", 
            ["aktivna", "u sanaciji", "sanirana"])
    
    lokacije_list = pd.read_sql(
        "SELECT id, naziv FROM lokacije ORDER BY naziv", conn
    )
    
    if len(lokacije_list) > 0:
        lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist())
    else:
        st.warning("⚠️ Prvo kreiraj lokaciju na stranici 'Lokacije'")
        lokacija = None
    
    if st.button("Spremi deponiju"):
        if naziv and povrsina > 0 and lokacija:
            lokacija_id = lokacije_list[lokacije_list['naziv'] == lokacija]['id'].values[0]
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status, 
                    datum_otkrivanja, lokacija_id, geom)
                SELECT %s, %s, %s, %s, NOW(), %s,
                    ST_Buffer(ST_SetSRID(ST_MakePoint(ST_X(geom), ST_Y(geom)), 4326)::geography, %s)::geometry
                FROM lokacije WHERE id = %s
            """, (naziv, povrsina, tip_otpada, status, lokacija_id, int(povrsina**0.5/2), lokacija_id))
            conn.commit()
            st.success("✅ Deponija je uspešno dodata!")
            st.rerun()
        else:
            st.error("❌ Popuni sve polje pravilno!")
    
    conn.close()

# ========== ML DETEKCIJA ==========
elif menu == "ML Detekcija":
    st.header("🤖 ML Detekcija")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu stranice ML Detekcija"):
        st.markdown("""
        ### Šta je ova stranica?
        Stranica za pregled ML detektovanih divljih deponija.
        
        ### Šta je ML detekcija?
        Algoritmi mašinskog učenja automatski analiziraju satelitske snimke
        i detektuju potencijalne divlje deponije.
        
        ### Šta vidiš ovde?
        Tabela sa svim ML detektovanim deponijama:
        - **Naziv** — Naziv ML detektovane deponije
        - **Površina (m²)** — Detektovana površina
        - **Tip otpada** — Vrsta otpada
        - **Status** — Uvek "detektovana"
        - **Lokacija** — Najbliža registrovana lokacija
        
        ### Kako koristiti?
        1. Pregledam ML detektovane deponije
        2. Proverim koja je sigurnost detekcije (confidence)
        3. Posećujem lokaciju na terenu
        4. Kreiram zvanično deponiju ako je potvrđena
        """)
    
    conn = get_connection()
    
    st.info("Ovde se nalaze ML detektovane deponije")
    
    # Prikaži ML detektovane deponije
    ml_deponije = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status,
               l.naziv as lokacija FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
        WHERE d.naziv LIKE '%ML%'
    """, conn)
    
    if len(ml_deponije) > 0:
        st.subheader("ML Detektovane deponije")
        st.dataframe(ml_deponije, use_container_width=True)
    else:
        st.warning("Nema ML detektovanih deponija")
    
    conn.close()

# ========== SPATIAL ANALIZA ==========
elif menu == "Spatial Analiza":
    st.header("🔍 Spatial Analiza")
    
    # Uputstvo
    with st.expander("📖 Uputstvo za upotrebu stranice Spatial Analiza"):
        st.markdown("""
        ### Šta je ova stranica?
        Stranica za geografske analize — distanca, buffer zone, itd.
        
        ### Šta je spatial analiza?
        Spatial analiza omogućava geografske operacije kao što su:
        - Izračunavanje distanci između lokacija
        - Pronalaženje lokacija u zaštitnim zonama
        - Buffer zone oko lokacija
        - Pronalaženje preklapanja i preseka
        
        ### Kako koristiti Distancu?
        1. Odaberi prvu lokaciju iz padajuće liste
        2. Odaberi drugu lokaciju iz padajuće liste
        3. Klikni **"Izračunaj distancu"**
        4. Rezultat će biti prikazan ispod u metrima
        
        ### Napomena
        Distanca se izračunava kao haversine distanca na površini Zemlje
        (geodetska distanca, ne prosta linija).
        """)
    
    conn = get_connection()
    
    # Distanca između lokacija
    st.subheader("📏 Distanca između lokacija")
    
    lokacije_list = pd.read_sql(
        "SELECT id, naziv FROM lokacije ORDER BY naziv", conn
    )
    
    if len(lokacije_list) >= 2:
        col1, col2 = st.columns(2)
        
        with col1:
            loc1 = st.selectbox("Prva lokacija", lokacije_list['naziv'].tolist(), key="loc1")
        
        with col2:
            loc2 = st.selectbox("Druga lokacija", lokacije_list['naziv'].tolist(), key="loc2", index=1)
        
        if st.button("Izračunaj distancu"):
            loc1_id = lokacije_list[lokacije_list['naziv'] == loc1]['id'].values[0]
            loc2_id = lokacije_list[lokacije_list['naziv'] == loc2]['id'].values[0]
            
            distanca = pd.read_sql(f"""
                SELECT ST_Distance(
                    (SELECT geom FROM lokacije WHERE id = {loc1_id})::geography,
                    (SELECT geom FROM lokacije WHERE id = {loc2_id})::geography
                ) as distanca
            """, conn)
            
            dist_value = distanca.iloc[0]['distanca']
            st.success(f"✅ Distanca između {loc1} i {loc2}: **{dist_value:.0f} metara**")
    else:
        st.warning("⚠️ Kreiraj najmanje dve lokacije da bi izračunao distancu!")
    
    conn.close()