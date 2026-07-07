"""
app.py — Streamlit web aplikacija za GIS upravljanje otpadom u Vojvodini
Pruža grafički interfejs za:
- CRUD operacije nad svim tabelama u bazi
- Spatial analize (buffer, intersection, union, clip, difference)
- ML detekcija divljih deponija
- Interaktivne folium mape sa SHP i baza slojevima
"""

import streamlit as st
import pandas as pd
import psycopg2
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, box
from shapely import wkt as swkt
import os
from dotenv import load_dotenv

# Učitava DB_URL iz .env fajla
load_dotenv()
DB_URL = os.environ.get("DB_URL")

def get_connection():
    """Otvara novu konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


@st.cache_data
def ucitaj_shp_sloj(shp_path, max_objekata=800):
    """
    Učitava i filtrira SHP sloj na bbox Vojvodine, sa ograničenjem broja
    objekata. Ceo Vojvodina landuse sloj ima ~96.000 poligona — renderovanje
    svih u folium petlji praktično zamrzava stranicu, pa se uzima nasumični
    uzorak. @st.cache_data čuva rezultat u memoriji da se SHP ne učitava
    iznova pri svakom kliku na bilo koji widget u aplikaciji.
    """
    gdf = gpd.read_file(shp_path)
    gdf = gdf.cx[18.8:21.7, 44.6:46.2]
    if len(gdf) > max_objekata:
        gdf = gdf.sample(max_objekata, random_state=42)
    return gdf

# Konfiguracija stranice — wide layout za bolje korišćenje ekrana
st.set_page_config(page_title="GIS Upravljanje Otpadom", layout="wide", initial_sidebar_state="expanded")
st.title("GIS Sistem za upravljanje otpadom — Vojvodina")

# ── Bočni meni za navigaciju između stranica ──
with st.sidebar:
    st.header("Meni")
    menu = st.radio("Izaberi opciju:", [
        "Dashboard",
        "Lokacije",
        "Komunalna Preduzeća",
        "Kontejneri",
        "Deponije",
        "Inspekcije",
        "ML Detekcija",
        "Spatial Analiza"
    ])

# ─────────────────────────────────────────────
# DASHBOARD — pregled sistema
# ─────────────────────────────────────────────
if menu == "Dashboard":
    st.header("Dashboard")

    with st.expander("Uputstvo za upotrebu Dashboard-a"):
        st.markdown("""
        **Šta je Dashboard?**
        Početna stranica sa pregledom svih bitnih informacija o sistemu.

        - Lokacije, Kontejneri, Deponije — statistike u karticama
        - Grafikoni — stanje kontejnera i status deponija
        - Mapa — sve lokacije sa markerima; klikni na marker za detalje
        """)

    conn = get_connection()

    # Statistike — COUNT upiti za svaku tabelu
    lokacije_cnt   = pd.read_sql("SELECT COUNT(*) as broj FROM lokacije", conn).iloc[0]['broj']
    kontejneri_cnt = pd.read_sql("SELECT COUNT(*) as broj FROM kontejneri", conn).iloc[0]['broj']
    deponije_cnt   = pd.read_sql("SELECT COUNT(*) as broj FROM deponije", conn).iloc[0]['broj']

    # Distribucija stanja kontejnera i statusa deponija za grafikone
    stanje_stats = pd.read_sql("SELECT stanje, COUNT(*) as broj FROM kontejneri GROUP BY stanje", conn)
    status_stats = pd.read_sql("SELECT status, COUNT(*) as broj FROM deponije GROUP BY status", conn)
    lokacije_data = pd.read_sql("SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn)
    deponije_data = pd.read_sql("""
        SELECT naziv, status, povrsina_m2,
               ST_X(ST_Centroid(geom)) as lon, ST_Y(ST_Centroid(geom)) as lat
        FROM deponije WHERE geom IS NOT NULL
    """, conn)
    conn.close()

    # Metrike u 3 kolone
    col1, col2, col3 = st.columns(3)
    col1.metric("Lokacije", int(lokacije_cnt))
    col2.metric("Kontejneri", int(kontejneri_cnt))
    col3.metric("Deponije", int(deponije_cnt))

    st.divider()
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Kontejneri po stanju")
        st.bar_chart(stanje_stats.set_index('stanje')['broj'])
    with col2:
        st.subheader("Deponije po statusu")
        st.bar_chart(status_stats.set_index('status')['broj'])

    st.divider()
    st.subheader("Mapa lokacija i deponija")

    mapa = folium.Map(location=[45.25, 20.0], zoom_start=8)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery', name='Satelitska podloga', overlay=False, control=True
    ).add_to(mapa)

    fg_lok = folium.FeatureGroup(name='Lokacije', show=True)
    for _, row in lokacije_data.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"<b>{row['naziv']}</b>",
            tooltip=row['naziv']
        ).add_to(fg_lok)
    fg_lok.add_to(mapa)

    fg_dep = folium.FeatureGroup(name='Deponije', show=True)
    status_boje = {'aktivna': 'red', 'u sanaciji': 'orange', 'sanirana': 'green', 'detektovana': 'darkred'}
    for _, row in deponije_data.iterrows():
        color = status_boje.get(row['status'], 'gray')
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=6,
            popup=f"<b>{row['naziv']}</b><br>Status: {row['status']}<br>Površina: {row['povrsina_m2']:.0f} m²",
            tooltip=row['naziv'],
            color=color, fill=True, fillColor=color, fillOpacity=0.7
        ).add_to(fg_dep)
    fg_dep.add_to(mapa)

    folium.LayerControl().add_to(mapa)
    st_folium(mapa, width=700, height=500)

# ─────────────────────────────────────────────
# LOKACIJE — CRUD
# ─────────────────────────────────────────────
elif menu == "Lokacije":
    st.header("Lokacije")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje lokacijama.
        - Pregledaj sve lokacije u tabeli
        - Dodaj novu lokaciju sa koordinatama
        - Ažuriraj naziv, opštinu, adresu ili tip područja
        - Obriši lokaciju po ID-u (prethodno obriši kontejnere/deponije na toj lokaciji)
        """)

    conn = get_connection()

    # READ — prikaz svih lokacija
    st.subheader("Sve lokacije")
    lokacije_df = pd.read_sql("SELECT id, naziv, opstina, adresa, tip_podrucja FROM lokacije ORDER BY id", conn)
    st.dataframe(lokacije_df, use_container_width=True)

    st.divider()
    # CREATE — forma za dodavanje nove lokacije
    st.subheader("Dodaj novu lokaciju")
    col1, col2 = st.columns(2)
    with col1:
        naziv    = st.text_input("Naziv lokacije")
        opstina  = st.text_input("Opština")
    with col2:
        adresa       = st.text_input("Adresa")
        tip_podrucja = st.selectbox("Tip područja", ["park", "stambeno", "industrijsko", "prigradsko", "druge"])
    col1, col2 = st.columns(2)
    with col1:
        lat = st.number_input("Geografska širina (lat)", format="%.4f", value=45.2552)
    with col2:
        lon = st.number_input("Geografska dužina (lon)", format="%.4f", value=19.8362)

    if st.button("Spremi lokaciju"):
        if naziv and opstina and adresa:
            cursor = conn.cursor()
            # ST_SetSRID(ST_MakePoint(lon, lat), 4326) kreira PostGIS tačku u WGS84
            cursor.execute("""
                INSERT INTO lokacije (naziv, opstina, adresa, tip_podrucja, geom)
                VALUES (%s, %s, %s, %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            """, (naziv, opstina, adresa, tip_podrucja, lon, lat))
            conn.commit()
            cursor.close()
            st.success("Lokacija uspešno dodata!")
            st.rerun()
        else:
            st.error("Popuni sve obavezne podatke!")

    st.divider()
    # UPDATE — forma za ažuriranje lokacije (parcijalno: prazno polje zadržava staru vrednost)
    st.subheader("Ažuriraj lokaciju")
    st.caption("Unesi ID i samo polja koja želiš da promeniš — ostavi prazno (ili '(bez izmene)') da se zadrži postojeća vrednost.")
    col1, col2 = st.columns(2)
    with col1:
        upd_lok_id   = st.number_input("ID lokacije", min_value=1, step=1, key="upd_lok_id")
        upd_naziv    = st.text_input("Novi naziv", key="upd_lok_naziv")
        upd_opstina  = st.text_input("Nova opština", key="upd_lok_opstina")
    with col2:
        upd_adresa   = st.text_input("Nova adresa", key="upd_lok_adresa")
        upd_tip      = st.selectbox("Novi tip područja", ["(bez izmene)", "park", "stambeno", "industrijsko", "prigradsko", "druge"], key="upd_lok_tip")
    if st.button("Ažuriraj lokaciju"):
        upd_tip_vrednost = "" if upd_tip == "(bez izmene)" else upd_tip
        if upd_naziv or upd_opstina or upd_adresa or upd_tip_vrednost:
            cursor = conn.cursor()
            # COALESCE(NULLIF(%s,''), staro) — prazno polje ne menja postojeću vrednost
            cursor.execute("""
                UPDATE lokacije
                SET naziv = COALESCE(NULLIF(%s,''), naziv),
                    opstina = COALESCE(NULLIF(%s,''), opstina),
                    adresa = COALESCE(NULLIF(%s,''), adresa),
                    tip_podrucja = COALESCE(NULLIF(%s,''), tip_podrucja)
                WHERE id = %s
            """, (upd_naziv, upd_opstina, upd_adresa, upd_tip_vrednost, int(upd_lok_id)))
            conn.commit()
            cursor.close()
            st.success(f"Lokacija {upd_lok_id} uspešno ažurirana!")
            st.rerun()
        else:
            st.error("Unesi bar jedno polje za ažuriranje!")

    st.divider()
    # DELETE — brisanje lokacije po ID-u
    st.subheader("Obriši lokaciju")
    id_brisanje = st.number_input("ID lokacije za brisanje", min_value=1, step=1, key="del_lok")
    if st.button("Obriši lokaciju", key="btn_del_lok"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM lokacije WHERE id = %s", (int(id_brisanje),))
        conn.commit()
        cursor.close()
        st.success(f"Lokacija {id_brisanje} obrisana!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# KOMUNALNA PREDUZEĆA — CRUD
# ─────────────────────────────────────────────
elif menu == "Komunalna Preduzeća":
    st.header("Komunalna Preduzeća")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje komunalnim preduzećima.
        - Pregledaj sva preduzeća sa njihovim lokacijama
        - Dodaj novo komunalno preduzeće
        - Ažuriraj kontakt podatke i zonu pokrivenosti
        - Obriši preduzeće po ID-u
        """)

    conn = get_connection()

    # READ — prikaz svih preduzeća sa JOIN na lokacije
    st.subheader("Sva komunalna preduzeća")
    preduzeca_df = pd.read_sql("""
        SELECT kp.id, kp.naziv, kp.kontakt_telefon, kp.email,
               kp.zona_pokrivenosti, l.naziv as lokacija
        FROM komunalna_preduzeca kp
        JOIN lokacije l ON kp.lokacija_id = l.id
        ORDER BY kp.id
    """, conn)
    st.dataframe(preduzeca_df, use_container_width=True)

    st.divider()
    # CREATE — forma za dodavanje novog preduzeća
    st.subheader("Dodaj novo preduzeće")
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    col1, col2 = st.columns(2)
    with col1:
        pred_naziv = st.text_input("Naziv preduzeća")
        pred_tel   = st.text_input("Kontakt telefon")
    with col2:
        pred_email = st.text_input("Email")
        pred_zona  = st.text_input("Zona pokrivenosti")

    if len(lokacije_list) > 0:
        pred_lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist(), key="pred_lok")
    else:
        st.warning("Prvo kreiraj lokaciju!")
        pred_lokacija = None

    if st.button("Spremi preduzeće"):
        if pred_naziv and pred_tel and pred_lokacija:
            # Pretraži ID lokacije po odabranom nazivu
            lok_id = int(lokacije_list[lokacije_list['naziv'] == pred_lokacija]['id'].values[0])
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO komunalna_preduzeca (naziv, kontakt_telefon, email, zona_pokrivenosti, lokacija_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (pred_naziv, pred_tel, pred_email, pred_zona, lok_id))
            conn.commit()
            cursor.close()
            st.success(f"Preduzeće '{pred_naziv}' uspešno dodato!")
            st.rerun()
        else:
            st.error("Popuni naziv, telefon i lokaciju!")

    st.divider()
    # UPDATE — parcijalno ažuriranje (samo polja koja nisu prazna)
    st.subheader("Ažuriraj preduzeće")
    col1, col2 = st.columns(2)
    with col1:
        upd_pred_id  = st.number_input("ID preduzeća", min_value=1, step=1, key="upd_pred_id")
        upd_pred_tel = st.text_input("Novi telefon", key="upd_pred_tel")
    with col2:
        upd_pred_email = st.text_input("Novi email", key="upd_pred_email")
        upd_pred_zona  = st.text_input("Nova zona pokrivenosti", key="upd_pred_zona")

    if st.button("Ažuriraj preduzeće"):
        if upd_pred_tel or upd_pred_email or upd_pred_zona:
            cursor = conn.cursor()
            # COALESCE(NULLIF(novo,''), staro) — ako je novo polje prazno, zadrži staru vrednost
            cursor.execute("""
                UPDATE komunalna_preduzeca
                SET kontakt_telefon   = COALESCE(NULLIF(%s,''), kontakt_telefon),
                    email             = COALESCE(NULLIF(%s,''), email),
                    zona_pokrivenosti = COALESCE(NULLIF(%s,''), zona_pokrivenosti)
                WHERE id = %s
            """, (upd_pred_tel, upd_pred_email, upd_pred_zona, int(upd_pred_id)))
            conn.commit()
            cursor.close()
            st.success(f"Preduzeće {upd_pred_id} ažurirano!")
            st.rerun()
        else:
            st.error("Unesi bar jedno polje za ažuriranje!")

    st.divider()
    # DELETE
    st.subheader("Obriši preduzeće")
    del_pred_id = st.number_input("ID preduzeća za brisanje", min_value=1, step=1, key="del_pred")
    if st.button("Obriši preduzeće"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM komunalna_preduzeca WHERE id = %s", (int(del_pred_id),))
        conn.commit()
        cursor.close()
        st.success(f"Preduzeće {del_pred_id} obrisano!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# KONTEJNERI — CRUD
# ─────────────────────────────────────────────
elif menu == "Kontejneri":
    st.header("Kontejneri")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje kontejnerima.
        - **Dodaj** novi kontejner
        - **Ažuriraj** stanje kontejnera (dobro / ostecen / lose)
        - **Obriši** kontejner po ID-u
        """)

    conn = get_connection()

    # READ — svi kontejneri sa lokacijom
    st.subheader("Svi kontejneri")
    kontejneri_df = pd.read_sql("""
        SELECT k.id, k.tip, k.kapacitet_litara, k.stanje, k.datum_postavljanja,
               l.naziv as lokacija
        FROM kontejneri k
        JOIN lokacije l ON k.lokacija_id = l.id
        ORDER BY k.id
    """, conn)
    st.dataframe(kontejneri_df, use_container_width=True)

    st.divider()
    # CREATE
    st.subheader("Dodaj novi kontejner")
    col1, col2 = st.columns(2)
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    with col1:
        tip       = st.selectbox("Tip kontejnera", ["komunalni", "reciklazni", "reciklazni staklo", "reciklazni papir", "reciklazni metal"])
        kapacitet = st.number_input("Kapacitet (litara)", min_value=100, step=100, value=1100)
    with col2:
        stanje  = st.selectbox("Stanje", ["dobro", "ostecen", "lose"])
        if len(lokacije_list) > 0:
            lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist())
        else:
            st.warning("Prvo kreiraj lokaciju!")
            lokacija = None
    col1, col2 = st.columns(2)
    with col1:
        k_lat = st.number_input("Geografska širina (lat)", format="%.4f", value=45.2552, key="k_lat")
    with col2:
        k_lon = st.number_input("Geografska dužina (lon)", format="%.4f", value=19.8362, key="k_lon")

    if st.button("Spremi kontejner"):
        if lokacija:
            lokacija_id = int(lokacije_list[lokacije_list['naziv'] == lokacija]['id'].values[0])
            cursor = conn.cursor()
            # NOW() upisuje trenutni datum kao datum postavljanja
            cursor.execute("""
                INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id, geom)
                VALUES (%s, %s, %s, NOW(), %s, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
            """, (tip, kapacitet, stanje, lokacija_id, k_lon, k_lat))
            conn.commit()
            cursor.close()
            st.success("Kontejner uspešno dodat!")
            st.rerun()

    st.divider()
    # UPDATE — samo stanje se može menjati
    st.subheader("Ažuriraj stanje kontejnera")
    col1, col2 = st.columns(2)
    with col1:
        upd_id = st.number_input("ID kontejnera", min_value=1, step=1, key="upd_id")
    with col2:
        novo_stanje = st.selectbox("Novo stanje", ["dobro", "ostecen", "lose"], key="upd_stanje")
    if st.button("Ažuriraj kontejner"):
        cursor = conn.cursor()
        cursor.execute("UPDATE kontejneri SET stanje = %s WHERE id = %s", (novo_stanje, int(upd_id)))
        conn.commit()
        cursor.close()
        st.success(f"Kontejner {upd_id} ažuriran na: {novo_stanje}")
        st.rerun()

    st.divider()
    # DELETE
    st.subheader("Obriši kontejner")
    del_id = st.number_input("ID kontejnera za brisanje", min_value=1, step=1, key="del_k")
    if st.button("Obriši kontejner"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM kontejneri WHERE id = %s", (int(del_id),))
        conn.commit()
        cursor.close()
        st.success(f"Kontejner {del_id} obrisan!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# DEPONIJE — CRUD
# ─────────────────────────────────────────────
elif menu == "Deponije":
    st.header("Deponije")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje deponijama.
        - **Prijavi** novu deponiju
        - **Ažuriraj** status deponije (aktivna / u sanaciji / sanirana)
        - **Obriši** deponiju (briše i sve njene inspekcije)
        """)

    conn = get_connection()

    # READ — sve deponije sa lokacijom
    st.subheader("Sve deponije")
    deponije_df = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status, d.datum_otkrivanja,
               l.naziv as lokacija
        FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
        ORDER BY d.id
    """, conn)
    st.dataframe(deponije_df, use_container_width=True)

    st.divider()
    # CREATE — geometrija se kreira kao buffer oko koordinata lokacije
    st.subheader("Prijavi novu deponiju")
    col1, col2 = st.columns(2)
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    with col1:
        naziv    = st.text_input("Naziv deponije")
        povrsina = st.number_input("Površina (m²)", min_value=10, step=10, value=100)
    with col2:
        tip_otpada = st.selectbox("Tip otpada", ["komunalni otpad", "mesoviti otpad", "građevinski otpad", "industrijski otpad"])
        status     = st.selectbox("Status", ["aktivna", "u sanaciji", "sanirana"])

    if len(lokacije_list) > 0:
        lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist())
    else:
        st.warning("Prvo kreiraj lokaciju!")
        lokacija = None

    if st.button("Spremi deponiju"):
        if naziv and povrsina > 0 and lokacija:
            lokacija_id = int(lokacije_list[lokacije_list['naziv'] == lokacija]['id'].values[0])
            cursor = conn.cursor()
            # INSERT...SELECT preuzima koordinate iz tabele lokacije i kreira buffer poligon
            cursor.execute("""
                INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status,
                    datum_otkrivanja, lokacija_id, geom)
                SELECT %s, %s, %s, %s, NOW(), %s,
                    ST_Buffer(ST_SetSRID(ST_MakePoint(ST_X(geom), ST_Y(geom)), 4326)::geography, %s)::geometry
                FROM lokacije WHERE id = %s
            """, (naziv, povrsina, tip_otpada, status, lokacija_id, max(1, int(povrsina ** 0.5 / 2)), lokacija_id))
            conn.commit()
            cursor.close()
            st.success("Deponija uspešno dodata!")
            st.rerun()
        else:
            st.error("Popuni sve podatke!")

    st.divider()
    # UPDATE — samo status
    st.subheader("Ažuriraj status deponije")
    col1, col2 = st.columns(2)
    with col1:
        upd_dep_id = st.number_input("ID deponije", min_value=1, step=1, key="upd_dep")
    with col2:
        novi_status = st.selectbox("Novi status", ["aktivna", "u sanaciji", "sanirana"], key="upd_dep_status")
    if st.button("Ažuriraj deponiju"):
        cursor = conn.cursor()
        cursor.execute("UPDATE deponije SET status = %s WHERE id = %s", (novi_status, int(upd_dep_id)))
        conn.commit()
        cursor.close()
        st.success(f"Deponija {upd_dep_id} ažurirana na: {novi_status}")
        st.rerun()

    st.divider()
    # DELETE — briše i inspekcije zbog FK constraint-a
    st.subheader("Obriši deponiju")
    del_dep_id = st.number_input("ID deponije za brisanje", min_value=1, step=1, key="del_dep")
    if st.button("Obriši deponiju"):
        cursor = conn.cursor()
        # Inspekcije se moraju obrisati prve (strani ključ na deponiju)
        cursor.execute("DELETE FROM inspekcije WHERE deponija_id = %s", (int(del_dep_id),))
        cursor.execute("DELETE FROM deponije WHERE id = %s", (int(del_dep_id),))
        conn.commit()
        cursor.close()
        st.success(f"Deponija {del_dep_id} i njene inspekcije obrisane!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# INSPEKCIJE — CRUD
# ─────────────────────────────────────────────
elif menu == "Inspekcije":
    st.header("Inspekcije")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje inspekcijama deponija.
        - **Dodaj** novu inspekciju za bilo koju deponiju
        - **Ažuriraj** preporuku inspekcije
        - **Obriši** inspekciju po ID-u
        """)

    conn = get_connection()

    # READ — inspekcije sa statusom deponije
    st.subheader("Sve inspekcije")
    inspekcije_df = pd.read_sql("""
        SELECT i.id, i.datum, i.inspektor, i.nalaz, i.preporuka,
               d.naziv as deponija, d.status as status_deponije
        FROM inspekcije i
        JOIN deponije d ON i.deponija_id = d.id
        ORDER BY i.datum DESC
    """, conn)
    st.dataframe(inspekcije_df, use_container_width=True)

    st.divider()
    # CREATE
    st.subheader("Dodaj novu inspekciju")
    deponije_list = pd.read_sql("SELECT id, naziv FROM deponije ORDER BY naziv", conn)

    col1, col2 = st.columns(2)
    with col1:
        ins_datum     = st.date_input("Datum inspekcije")
        ins_inspektor = st.text_input("Inspektor")
    with col2:
        ins_nalaz     = st.text_area("Nalaz", height=80)
        ins_preporuka = st.text_area("Preporuka", height=80)

    if len(deponije_list) > 0:
        ins_deponija = st.selectbox("Deponija", deponije_list['naziv'].tolist())
    else:
        st.warning("Nema deponija u sistemu!")
        ins_deponija = None

    if st.button("Spremi inspekciju"):
        if ins_inspektor and ins_nalaz and ins_deponija:
            dep_id = int(deponije_list[deponije_list['naziv'] == ins_deponija]['id'].values[0])
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO inspekcije (datum, nalaz, preporuka, inspektor, deponija_id)
                VALUES (%s, %s, %s, %s, %s)
            """, (ins_datum, ins_nalaz, ins_preporuka, ins_inspektor, dep_id))
            conn.commit()
            cursor.close()
            st.success("Inspekcija uspešno dodata!")
            st.rerun()
        else:
            st.error("Popuni inspektor, nalaz i deponiju!")

    st.divider()
    # UPDATE — samo preporuka
    st.subheader("Ažuriraj preporuku")
    col1, col2 = st.columns(2)
    with col1:
        upd_ins_id = st.number_input("ID inspekcije", min_value=1, step=1, key="upd_ins")
    with col2:
        nova_preporuka = st.text_input("Nova preporuka", key="nova_prep")
    if st.button("Ažuriraj inspekciju"):
        if nova_preporuka:
            cursor = conn.cursor()
            cursor.execute("UPDATE inspekcije SET preporuka = %s WHERE id = %s", (nova_preporuka, int(upd_ins_id)))
            conn.commit()
            cursor.close()
            st.success(f"Inspekcija {upd_ins_id} ažurirana!")
            st.rerun()
        else:
            st.error("Unesi novu preporuku za ažuriranje!")

    st.divider()
    # DELETE
    st.subheader("Obriši inspekciju")
    del_ins_id = st.number_input("ID inspekcije za brisanje", min_value=1, step=1, key="del_ins")
    if st.button("Obriši inspekciju"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inspekcije WHERE id = %s", (int(del_ins_id),))
        conn.commit()
        cursor.close()
        st.success(f"Inspekcija {del_ins_id} obrisana!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# ML DETEKCIJA — pregled i upravljanje ML rezultatima
# ─────────────────────────────────────────────
elif menu == "ML Detekcija":
    st.header("ML Detekcija divljih deponija")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za pregled i upravljanje ML detektovanim divljim deponijama.

        **Kako funkcioniše ML detekcija?**
        Algoritam Random Forest se trenira na simuliranom satelitskom snimku čije su spektralne
        vrednosti postavljene na stvarne koordinate gradova i deponija iz baze (NDVI, osvetljenost,
        tekstura, NIR kanali). Pikseli klasifikovani sa verovatnoćom > 90% kao "deponija" upisuju se u bazu.

        - Možeš **ažurirati tip otpada** i **status** svake ML deponije
        """)

    conn = get_connection()

    # Prikaz samo ML deponija — identifikovane po 'ML' u nazivu
    ml_deponije = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status,
               d.datum_otkrivanja, l.naziv as lokacija
        FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
        WHERE d.naziv LIKE '%ML%'
        ORDER BY d.id
    """, conn)

    if len(ml_deponije) > 0:
        st.subheader(f"ML detektovane deponije ({len(ml_deponije)})")
        st.dataframe(ml_deponije, use_container_width=True)

        st.divider()
        # UPDATE — ažuriranje tipa i statusa ML deponije
        st.subheader("Ažuriraj atribute ML deponije")
        col1, col2, col3 = st.columns(3)
        with col1:
            ml_id = st.number_input("ID deponije", min_value=1, step=1, key="ml_upd_id")
        with col2:
            ml_tip = st.selectbox("Tip otpada", ["(bez izmene)", "komunalni otpad", "mesoviti otpad", "građevinski otpad", "industrijski otpad"], key="ml_tip")
        with col3:
            ml_status = st.selectbox("Status", ["(bez izmene)", "detektovana", "potvrđena", "u sanaciji", "sanirana"], key="ml_status")

        if st.button("Ažuriraj ML deponiju"):
            ml_tip_vrednost    = "" if ml_tip == "(bez izmene)" else ml_tip
            ml_status_vrednost = "" if ml_status == "(bez izmene)" else ml_status
            cursor = conn.cursor()
            # COALESCE(NULLIF(%s,''), staro) — "(bez izmene)" ne menja postojeću vrednost
            cursor.execute(
                """UPDATE deponije
                   SET tip_otpada = COALESCE(NULLIF(%s,''), tip_otpada),
                       status = COALESCE(NULLIF(%s,''), status)
                   WHERE id = %s""",
                (ml_tip_vrednost, ml_status_vrednost, int(ml_id))
            )
            conn.commit()
            cursor.close()
            st.success(f"Deponija {ml_id} ažurirana!")
            st.rerun()

        st.divider()
        # Mapa ML deponija — boja markera po statusu
        st.subheader("Mapa ML detektovanih deponija")
        ml_coords = pd.read_sql("""
            SELECT d.naziv, d.tip_otpada, d.status, d.povrsina_m2,
                   ST_X(ST_Centroid(d.geom)) as lon,
                   ST_Y(ST_Centroid(d.geom)) as lat
            FROM deponije d
            WHERE d.naziv LIKE '%ML%' AND d.geom IS NOT NULL
        """, conn)

        mapa_ml = folium.Map(location=[45.25, 20.0], zoom_start=8)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satelitska podloga',
            overlay=False,
            control=True
        ).add_to(mapa_ml)

        fg_ml = folium.FeatureGroup(name='ML deponije', show=True)
        for _, row in ml_coords.iterrows():
            # Boja markera zavisi od statusa detekcije
            color = 'red' if row['status'] == 'detektovana' else (
                    'orange' if row['status'] == 'potvrđena' else 'green')
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                popup=(f"<b>{row['naziv']}</b><br>"
                       f"Tip: {row['tip_otpada']}<br>"
                       f"Status: {row['status']}<br>"
                       f"Površina: {row['povrsina_m2']:.0f} m²"),
                color=color, fill=True, fillColor=color, fillOpacity=0.6
            ).add_to(fg_ml)
        fg_ml.add_to(mapa_ml)
        folium.LayerControl().add_to(mapa_ml)
        st_folium(mapa_ml, width=700, height=400)
    else:
        st.warning("Nema ML detektovanih deponija. Pokreni ml_detekcija.py da generišeš rezultate.")

    conn.close()

# ─────────────────────────────────────────────
# SPATIAL ANALIZA — prostorne operacije i mapa
# ─────────────────────────────────────────────
elif menu == "Spatial Analiza":
    st.header("Spatial Analiza")

    with st.expander("Uputstvo"):
        st.markdown("""
        Geografske analize nad podacima sistema.

        **Distanca** — izračunava geodetsku distancu između dve odabrane lokacije.

        **Overlay Operacije** — 5 prostornih operacija, zona rizika 3km oko deponija:
        - Buffer (zona rizika 3km oko svake deponije)
        - Intersection (koji gradovi padaju u zonu rizika)
        - Union (spajanje svih zona)
        - Clip (lokacije unutar Vojvodine)
        - Difference (gradovi izvan svih zona rizika)

        **Mapa** — SHP slojevi + podaci iz baze na satelitskoj podlozi.
        """)

    conn = get_connection()

    # ── Distanca između dve lokacije ──────────
    st.subheader("Distanca između lokacija")
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)

    if len(lokacije_list) >= 2:
        col1, col2 = st.columns(2)
        with col1:
            loc1 = st.selectbox("Prva lokacija",  lokacije_list['naziv'].tolist(), key="loc1")
        with col2:
            loc2 = st.selectbox("Druga lokacija", lokacije_list['naziv'].tolist(), key="loc2", index=1)

        if st.button("Izračunaj distancu"):
            loc1_id = int(lokacije_list[lokacije_list['naziv'] == loc1]['id'].values[0])
            loc2_id = int(lokacije_list[lokacije_list['naziv'] == loc2]['id'].values[0])

            cursor = conn.cursor()
            # ST_Distance sa ::geography kastom računa distancu u metrima (geodetska linija)
            cursor.execute("""
                SELECT ST_Distance(
                    (SELECT geom FROM lokacije WHERE id = %s)::geography,
                    (SELECT geom FROM lokacije WHERE id = %s)::geography
                ) as distanca
            """, (loc1_id, loc2_id))
            dist_value = cursor.fetchone()[0]
            cursor.close()
            st.success(f"Distanca između **{loc1}** i **{loc2}**: **{dist_value:.0f} metara**")
    else:
        st.warning("Kreiraj najmanje dve lokacije!")

    st.divider()

    # ── 5 Overlay Operacija ───────────────────
    st.subheader("Overlay Operacije (5 prostornih analiza)")

    # Učitaj lokacije sa koordinatama za geopandas operacije
    lokacije_geo = pd.read_sql(
        "SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn
    )

    # Učitaj deponije sa geometrijom — zona rizika se pravi oko deponija, ne lokacija
    deponije_geo = pd.read_sql(
        "SELECT id, naziv, status, ST_AsText(geom) as geom_wkt FROM deponije WHERE geom IS NOT NULL", conn
    )

    if not lokacije_geo.empty and not deponije_geo.empty:
        # Kreiraj GeoDataFrame od lokacija (tačke u WGS84)
        geometry = [Point(row['lon'], row['lat']) for _, row in lokacije_geo.iterrows()]
        gdf_lok = gpd.GeoDataFrame(lokacije_geo.copy(), geometry=geometry, crs='EPSG:4326')

        # Kreiraj GeoDataFrame od deponija (pravi poligoni iz WKT)
        dep_geometry = [swkt.loads(g) for g in deponije_geo['geom_wkt']]
        gdf_dep = gpd.GeoDataFrame(deponije_geo.copy(), geometry=dep_geometry, crs='EPSG:4326')
        gdf_dep_utm = gdf_dep.to_crs('EPSG:32634')

        # 1. BUFFER — zona rizika 3km oko svake deponije
        with st.expander("1. Buffer — zona rizika 3km oko svake deponije"):
            gdf_buf_utm = gdf_dep_utm.copy()
            gdf_buf_utm['geometry'] = gdf_dep_utm.geometry.buffer(3000)
            # Vrati u WGS84 za prikaz i daljnje operacije
            gdf_buf = gdf_buf_utm.to_crs('EPSG:4326')
            # Površina se računa u UTM (ha = m² / 10000)
            gdf_buf['povrsina_ha'] = (gdf_buf_utm.geometry.area / 10000).round(2)
            st.dataframe(
                gdf_buf[['naziv', 'povrsina_ha']].rename(columns={'povrsina_ha': 'Površina zone (ha)'}),
                use_container_width=True
            )
            st.caption(f"Ukupna kombinovana površina svih zona: {gdf_buf_utm.geometry.area.sum()/10000:.2f} ha")

        # 2. INTERSECTION — koji gradovi padaju u zonu rizika neke deponije
        with st.expander("2. Intersection — gradovi unutar zone rizika"):
            joined = gpd.sjoin(gdf_lok, gdf_buf[['naziv', 'geometry']], how='inner', predicate='intersects')
            if joined.empty:
                st.info("Nijedan grad ne pada u zonu rizika neke deponije.")
            else:
                st.dataframe(
                    joined[['naziv_left', 'naziv_right']].rename(
                        columns={'naziv_left': 'Grad', 'naziv_right': 'Deponija (zona rizika)'}
                    ),
                    use_container_width=True
                )
                st.caption(f"Pronađeno {len(joined)} preklapanja.")

        # 3. UNION — spajanje svih zona rizika u jednu bez preklapanja
        with st.expander("3. Union — spajanje svih zona rizika u jednu"):
            # union_all spaja sve geometrije u jednu
            union_geom = gdf_buf_utm.geometry.union_all()
            union_area_ha = union_geom.area / 10000
            st.metric("Ukupna površina unije svih zona", f"{union_area_ha:.2f} ha")
            st.caption("Union spaja sve zone rizika u jedan poligon eliminišući preklapanja.")

        # 4. CLIP — lokacije unutar prave granice Vojvodine (ne bbox)
        with st.expander("4. Clip — lokacije unutar Vojvodine"):
            # Prava administrativna granica (admin_level4) — bbox bi zahvatio
            # i delove Rumunije/Mađarske jer Vojvodina nije pravougaonog oblika
            shp_dir_clip = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'serbia_shp')
            adminareas = gpd.read_file(os.path.join(shp_dir_clip, 'gis_osm_adminareas_a_free_1.shp'))
            voj_geom = adminareas[adminareas['name'].str.contains('Војводина', na=False)].iloc[0].geometry
            gdf_clip_box = gpd.GeoDataFrame([1], geometry=[voj_geom], crs='EPSG:4326')
            clipped = gpd.clip(gdf_lok, gdf_clip_box)
            st.dataframe(
                clipped[['naziv', 'lon', 'lat']].rename(columns={'lon': 'Lon', 'lat': 'Lat'}),
                use_container_width=True
            )
            st.caption(f"{len(clipped)} od {len(gdf_lok)} lokacija je unutar granice Vojvodine.")

        # 5. DIFFERENCE — gradovi koji su van svih zona rizika
        with st.expander("5. Difference — gradovi IZVAN zona rizika"):
            joined_all = gpd.sjoin(gdf_lok, gdf_buf[['naziv', 'geometry']], how='left', predicate='intersects')
            # index_right IS NULL = grad nije ni u jednoj zoni rizika
            outside = joined_all[joined_all['index_right'].isna()].drop_duplicates(subset='id')
            if outside.empty:
                st.info("Svi gradovi se nalaze unutar neke zone rizika.")
            else:
                # naziv_left jer sjoin preimeuje kolone kada oba DF-a imaju 'naziv'
                st.dataframe(
                    outside[['naziv_left', 'lon', 'lat']].rename(columns={'naziv_left': 'naziv'}),
                    use_container_width=True
                )
                st.caption(f"{len(outside)} gradova je izvan svih zona rizika.")
    else:
        st.warning("Nema lokacija ili deponija za overlay operacije.")

    st.divider()

    # ── Mapa sa SHP slojevima i bazom ─────────
    st.subheader("Mapa sa SHP slojevima i satelitskom podlogom")

    st.caption("Simbologija — izaberi boje za prikaz na mapi ispod")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        boja_lok = st.color_picker("Lokacije", "#0000FF")
    with col2:
        boja_aktivna = st.color_picker("Deponija — aktivna", "#FF0000")
    with col3:
        boja_sanacija = st.color_picker("Deponija — u sanaciji", "#FFA500")
    with col4:
        boja_sanirana = st.color_picker("Deponija — sanirana", "#008000")

    lokacije_data = pd.read_sql(
        "SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn
    )
    # ST_Centroid za deponije jer su poligoni — uzima centroid za prikaz markera
    deponije_data = pd.read_sql("""
        SELECT naziv, tip_otpada, status, povrsina_m2,
               ST_X(ST_Centroid(geom)) as lon,
               ST_Y(ST_Centroid(geom)) as lat
        FROM deponije WHERE geom IS NOT NULL
    """, conn)
    conn.close()

    mapa = folium.Map(location=[45.25, 20.0], zoom_start=8)

    # Raster podloga — satelitski snimak
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga (Raster)',
        overlay=False,
        control=True
    ).add_to(mapa)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap', overlay=False, control=True).add_to(mapa)

    # Zona rizika oko deponija — podrazumevano isključena
    if not lokacije_geo.empty and not deponije_geo.empty:
        fg_buf = folium.FeatureGroup(name='Zona rizika (3km)', show=False)
        for _, row in gdf_buf.iterrows():
            geom = row.geometry
            if geom is None:
                continue
            coords = []
            if geom.geom_type == 'Polygon':
                coords = [[y, x] for x, y in geom.exterior.coords]
            elif geom.geom_type == 'MultiPolygon':
                coords = [[y, x] for x, y in list(geom.geoms)[0].exterior.coords]
            if coords:
                folium.Polygon(
                    locations=coords,
                    popup=f"Zona rizika: {row['naziv']}",
                    color='blue', fill=True, fillColor='blue',
                    fillOpacity=0.15, weight=2, dashArray='5,5'
                ).add_to(fg_buf)
        fg_buf.add_to(mapa)

    # SHP sloj — OSM mesta (tačke), podrazumevano isključen
    shp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'serbia_shp')
    places_shp = os.path.join(shp_dir, 'gis_osm_places_free_1.shp')
    if os.path.exists(places_shp):
        try:
            novi_sad_box = ucitaj_shp_sloj(places_shp, max_objekata=800)
            fg_places = folium.FeatureGroup(name='OSM Mesta (SHP)', show=False)
            for _, row in novi_sad_box.iterrows():
                if row.geometry is not None and row.geometry.geom_type == 'Point':
                    folium.CircleMarker(
                        location=[row.geometry.y, row.geometry.x],
                        radius=4,
                        popup=str(row.get('name', '')),
                        color='purple', fill=True, fillOpacity=0.6
                    ).add_to(fg_places)
            fg_places.add_to(mapa)
        except Exception:
            pass  # Preskoči ako SHP fajl nije validan

    # SHP sloj — OSM korišćenje zemljišta (poligoni), podrazumevano isključen
    landuse_shp = os.path.join(shp_dir, 'gis_osm_landuse_a_free_1.shp')
    if os.path.exists(landuse_shp):
        try:
            land_clip = ucitaj_shp_sloj(landuse_shp, max_objekata=800)
            fg_land = folium.FeatureGroup(name='OSM Korišćenje zemljišta (SHP)', show=False)
            landuse_colors = {
                'residential': '#f0e68c', 'industrial': '#cd853f',
                'commercial': '#ffa07a', 'forest': '#228b22',
                'farmland': '#adff2f', 'park': '#90ee90'
            }
            for _, row in land_clip.iterrows():
                if row.geometry is not None:
                    ftype = row.get('fclass', 'other')
                    color = landuse_colors.get(ftype, '#cccccc')
                    geom = row.geometry
                    coords = []
                    if geom.geom_type == 'Polygon':
                        coords = [[y, x] for x, y in geom.exterior.coords]
                    elif geom.geom_type == 'MultiPolygon':
                        coords = [[y, x] for x, y in list(geom.geoms)[0].exterior.coords]
                    if coords:
                        folium.Polygon(
                            locations=coords,
                            popup=f"Tip: {ftype}",
                            color=color, fill=True, fillColor=color, fillOpacity=0.4, weight=1
                        ).add_to(fg_land)
            fg_land.add_to(mapa)
        except Exception:
            pass

    # Sloj — lokacije iz baze (boja podešena u color_picker iznad)
    fg_lok = folium.FeatureGroup(name='Lokacije (baza)', show=True)
    for _, row in lokacije_data.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=f"<b>{row['naziv']}</b>",
            tooltip=row['naziv'],
            color=boja_lok, fill=True, fillColor=boja_lok, fillOpacity=0.8
        ).add_to(fg_lok)
    fg_lok.add_to(mapa)

    # Sloj — deponije iz baze (boja po statusu, podešava se u color_picker iznad)
    fg_dep = folium.FeatureGroup(name='Deponije (baza)', show=True)
    status_boje = {
        'aktivna': boja_aktivna,
        'u sanaciji': boja_sanacija,
        'sanirana': boja_sanirana,
    }
    for _, row in deponije_data.iterrows():
        color = status_boje.get(row['status'], boja_aktivna)
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=10,
            popup=(f"<b>{row['naziv']}</b><br>"
                   f"Tip: {row['tip_otpada']}<br>"
                   f"Status: {row['status']}<br>"
                   f"Površina: {row['povrsina_m2']:.0f} m²"),
            color=color, fill=True, fillColor=color, fillOpacity=0.6
        ).add_to(fg_dep)
    fg_dep.add_to(mapa)

    # Kontrola slojeva — dugme za uključivanje/isključivanje
    folium.LayerControl(collapsed=False).add_to(mapa)
    st_folium(mapa, width=750, height=550)
