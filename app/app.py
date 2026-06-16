import streamlit as st
import pandas as pd
import psycopg2
import geopandas as gpd
import folium
from streamlit_folium import st_folium
from shapely.geometry import Point, box
import os

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)

st.set_page_config(page_title="GIS Upravljanje Otpadom", layout="wide", initial_sidebar_state="expanded")
st.title("GIS Sistem za upravljanje otpadom — Novi Sad")

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
# DASHBOARD
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

    lokacije_cnt  = pd.read_sql("SELECT COUNT(*) as broj FROM lokacije", conn).iloc[0]['broj']
    kontejneri_cnt = pd.read_sql("SELECT COUNT(*) as broj FROM kontejneri", conn).iloc[0]['broj']
    deponije_cnt  = pd.read_sql("SELECT COUNT(*) as broj FROM deponije", conn).iloc[0]['broj']

    stanje_stats = pd.read_sql("SELECT stanje, COUNT(*) as broj FROM kontejneri GROUP BY stanje", conn)
    status_stats = pd.read_sql("SELECT status, COUNT(*) as broj FROM deponije GROUP BY status", conn)
    lokacije_data = pd.read_sql("SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn)
    conn.close()

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
    st.subheader("Mapa lokacija")

    mapa = folium.Map(location=[45.2552, 19.8362], zoom_start=12)
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga',
        overlay=False,
        control=True
    ).add_to(mapa)

    for _, row in lokacije_data.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"<b>{row['naziv']}</b>",
            tooltip=row['naziv']
        ).add_to(mapa)

    folium.LayerControl().add_to(mapa)
    st_folium(mapa, width=700, height=500)

# ─────────────────────────────────────────────
# LOKACIJE
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

    st.subheader("Sve lokacije")
    lokacije_df = pd.read_sql("SELECT id, naziv, opstina, adresa, tip_podrucja FROM lokacije ORDER BY id", conn)
    st.dataframe(lokacije_df, use_container_width=True)

    st.divider()
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
    st.subheader("Ažuriraj lokaciju")
    col1, col2 = st.columns(2)
    with col1:
        upd_lok_id   = st.number_input("ID lokacije", min_value=1, step=1, key="upd_lok_id")
        upd_naziv    = st.text_input("Novi naziv", key="upd_lok_naziv")
        upd_opstina  = st.text_input("Nova opština", key="upd_lok_opstina")
    with col2:
        upd_adresa   = st.text_input("Nova adresa", key="upd_lok_adresa")
        upd_tip      = st.selectbox("Novi tip područja", ["park", "stambeno", "industrijsko", "prigradsko", "druge"], key="upd_lok_tip")
    if st.button("Ažuriraj lokaciju"):
        if upd_naziv and upd_opstina and upd_adresa:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE lokacije
                SET naziv = %s, opstina = %s, adresa = %s, tip_podrucja = %s
                WHERE id = %s
            """, (upd_naziv, upd_opstina, upd_adresa, upd_tip, int(upd_lok_id)))
            conn.commit()
            cursor.close()
            st.success(f"Lokacija {upd_lok_id} uspešno ažurirana!")
            st.rerun()
        else:
            st.error("Popuni sve polja za ažuriranje!")

    st.divider()
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
# KOMUNALNA PREDUZEĆA
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
    st.subheader("Dodaj novo preduzeće")
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    col1, col2 = st.columns(2)
    with col1:
        pred_naziv   = st.text_input("Naziv preduzeća")
        pred_tel     = st.text_input("Kontakt telefon")
    with col2:
        pred_email   = st.text_input("Email")
        pred_zona    = st.text_input("Zona pokrivenosti")

    if len(lokacije_list) > 0:
        pred_lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist(), key="pred_lok")
    else:
        st.warning("Prvo kreiraj lokaciju!")
        pred_lokacija = None

    if st.button("Spremi preduzeće"):
        if pred_naziv and pred_tel and pred_lokacija:
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
            cursor.execute("""
                UPDATE komunalna_preduzeca
                SET kontakt_telefon = COALESCE(NULLIF(%s,''), kontakt_telefon),
                    email           = COALESCE(NULLIF(%s,''), email),
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
# KONTEJNERI
# ─────────────────────────────────────────────
elif menu == "Kontejneri":
    st.header("Kontejneri")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za upravljanje kontejnerima.
        - **Dodaj** novi kontejner
        - **Ažuriraj** stanje kontejnera (dobro / oštećen / loše)
        - **Obriši** kontejner po ID-u
        """)

    conn = get_connection()

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
    st.subheader("Dodaj novi kontejner")
    col1, col2 = st.columns(2)
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    with col1:
        tip      = st.selectbox("Tip kontejnera", ["komunalni", "reciklažni", "podzemni"])
        kapacitet = st.number_input("Kapacitet (litara)", min_value=100, step=100, value=1100)
    with col2:
        stanje  = st.selectbox("Stanje", ["dobro", "oštećen", "loše"])
        if len(lokacije_list) > 0:
            lokacija = st.selectbox("Lokacija", lokacije_list['naziv'].tolist())
        else:
            st.warning("Prvo kreiraj lokaciju!")
            lokacija = None

    if st.button("Spremi kontejner"):
        if lokacija:
            lokacija_id = int(lokacije_list[lokacije_list['naziv'] == lokacija]['id'].values[0])
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO kontejneri (tip, kapacitet_litara, stanje, datum_postavljanja, lokacija_id)
                VALUES (%s, %s, %s, NOW(), %s)
            """, (tip, kapacitet, stanje, lokacija_id))
            conn.commit()
            cursor.close()
            st.success("Kontejner uspešno dodat!")
            st.rerun()

    st.divider()
    st.subheader("Ažuriraj stanje kontejnera")
    col1, col2 = st.columns(2)
    with col1:
        upd_id = st.number_input("ID kontejnera", min_value=1, step=1, key="upd_id")
    with col2:
        novo_stanje = st.selectbox("Novo stanje", ["dobro", "oštećen", "loše"], key="upd_stanje")
    if st.button("Ažuriraj kontejner"):
        cursor = conn.cursor()
        cursor.execute("UPDATE kontejneri SET stanje = %s WHERE id = %s", (novo_stanje, int(upd_id)))
        conn.commit()
        cursor.close()
        st.success(f"Kontejner {upd_id} ažuriran na: {novo_stanje}")
        st.rerun()

    st.divider()
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
# DEPONIJE
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
    st.subheader("Prijavi novu deponiju")
    col1, col2 = st.columns(2)
    lokacije_list = pd.read_sql("SELECT id, naziv FROM lokacije ORDER BY naziv", conn)
    with col1:
        naziv    = st.text_input("Naziv deponije")
        povrsina = st.number_input("Površina (m²)", min_value=10, step=10, value=100)
    with col2:
        tip_otpada = st.selectbox("Tip otpada", ["komunalni", "građevinski", "mešoviti", "industrijski"])
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
    st.subheader("Obriši deponiju")
    del_dep_id = st.number_input("ID deponije za brisanje", min_value=1, step=1, key="del_dep")
    if st.button("Obriši deponiju"):
        cursor = conn.cursor()
        cursor.execute("DELETE FROM inspekcije WHERE deponija_id = %s", (int(del_dep_id),))
        cursor.execute("DELETE FROM deponije WHERE id = %s", (int(del_dep_id),))
        conn.commit()
        cursor.close()
        st.success(f"Deponija {del_dep_id} i njene inspekcije obrisane!")
        st.rerun()

    conn.close()

# ─────────────────────────────────────────────
# INSPEKCIJE
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
    st.subheader("Dodaj novu inspekciju")
    deponije_list = pd.read_sql("SELECT id, naziv FROM deponije ORDER BY naziv", conn)

    col1, col2 = st.columns(2)
    with col1:
        ins_datum    = st.date_input("Datum inspekcije")
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
    st.subheader("Ažuriraj preporuku")
    col1, col2 = st.columns(2)
    with col1:
        upd_ins_id = st.number_input("ID inspekcije", min_value=1, step=1, key="upd_ins")
    with col2:
        nova_preporuka = st.text_input("Nova preporuka", key="nova_prep")
    if st.button("Ažuriraj inspekciju"):
        cursor = conn.cursor()
        cursor.execute("UPDATE inspekcije SET preporuka = %s WHERE id = %s", (nova_preporuka, int(upd_ins_id)))
        conn.commit()
        cursor.close()
        st.success(f"Inspekcija {upd_ins_id} ažurirana!")
        st.rerun()

    st.divider()
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
# ML DETEKCIJA
# ─────────────────────────────────────────────
elif menu == "ML Detekcija":
    st.header("ML Detekcija divljih deponija")

    with st.expander("Uputstvo"):
        st.markdown("""
        Stranica za pregled i upravljanje ML detektovanim divljim deponijama.

        **Kako funkcioniše ML detekcija?**
        Algoritam Random Forest se trenira na sintetičkim multispektralnim podacima
        (simulacija NDVI, osvetljenosti, teksture, NIR kanala satelitskog snimka).
        Pikseli klasifikovani kao "deponija" grupišu se u objekte i upisuju u bazu.

        - **Confidence** — sigurnost modela (0–1); viša vrednost = pouzdanija detekcija
        - Možeš **ažurirati tip otpada** i **status** svake ML deponije
        """)

    conn = get_connection()

    ml_deponije = pd.read_sql("""
        SELECT d.id, d.naziv, d.povrsina_m2, d.tip_otpada, d.status,
               d.datum_otkrivanja,
               l.naziv as lokacija
        FROM deponije d
        JOIN lokacije l ON d.lokacija_id = l.id
        WHERE d.naziv LIKE '%ML%'
        ORDER BY d.id
    """, conn)

    if len(ml_deponije) > 0:
        st.subheader(f"ML detektovane deponije ({len(ml_deponije)})")
        st.dataframe(ml_deponije, use_container_width=True)

        st.divider()
        st.subheader("Ažuriraj atribute ML deponije")
        col1, col2, col3 = st.columns(3)
        with col1:
            ml_id = st.number_input("ID deponije", min_value=1, step=1, key="ml_upd_id")
        with col2:
            ml_tip = st.selectbox("Tip otpada", ["komunalni", "građevinski", "mešoviti", "industrijski"], key="ml_tip")
        with col3:
            ml_status = st.selectbox("Status", ["detektovana", "potvrđena", "u sanaciji", "sanirana"], key="ml_status")

        if st.button("Ažuriraj ML deponiju"):
            cursor = conn.cursor()
            cursor.execute(
                "UPDATE deponije SET tip_otpada = %s, status = %s WHERE id = %s",
                (ml_tip, ml_status, int(ml_id))
            )
            conn.commit()
            cursor.close()
            st.success(f"Deponija {ml_id} ažurirana!")
            st.rerun()

        st.divider()
        st.subheader("Mapa ML detektovanih deponija")
        ml_coords = pd.read_sql("""
            SELECT d.naziv, d.tip_otpada, d.status, d.povrsina_m2,
                   ST_X(ST_Centroid(d.geom)) as lon,
                   ST_Y(ST_Centroid(d.geom)) as lat
            FROM deponije d
            WHERE d.naziv LIKE '%ML%' AND d.geom IS NOT NULL
        """, conn)

        mapa_ml = folium.Map(location=[45.2552, 19.8362], zoom_start=12)
        folium.TileLayer(
            tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
            attr='Esri',
            name='Satelitska podloga',
            overlay=False,
            control=True
        ).add_to(mapa_ml)

        fg_ml = folium.FeatureGroup(name='ML deponije', show=True)
        for _, row in ml_coords.iterrows():
            color = 'red' if row['status'] == 'detektovana' else (
                    'orange' if row['status'] == 'potvrđena' else 'green')
            folium.CircleMarker(
                location=[row['lat'], row['lon']],
                radius=8,
                popup=(f"<b>{row['naziv']}</b><br>"
                       f"Tip: {row['tip_otpada']}<br>"
                       f"Status: {row['status']}<br>"
                       f"Površina: {row['povrsina_m2']:.0f} m²"),
                color=color,
                fill=True,
                fillColor=color,
                fillOpacity=0.6
            ).add_to(fg_ml)
        fg_ml.add_to(mapa_ml)
        folium.LayerControl().add_to(mapa_ml)
        st_folium(mapa_ml, width=700, height=400)
    else:
        st.warning("Nema ML detektovanih deponija. Pokreni ml_detekcija.py da generišeš rezultate.")

    conn.close()

# ─────────────────────────────────────────────
# SPATIAL ANALIZA
# ─────────────────────────────────────────────
elif menu == "Spatial Analiza":
    st.header("Spatial Analiza")

    with st.expander("Uputstvo"):
        st.markdown("""
        Geografske analize nad podacima sistema.

        **Distanca** — izračunava geodetsku distancu između dve odabrane lokacije.

        **Overlay Operacije** — 5 prostornih operacija nad lokacijama:
        - Buffer (zaštitna zona 500m)
        - Intersection (lokacije u buffer zonama)
        - Union (spajanje svih zona)
        - Clip (lokacije unutar Novi Sad oblasti)
        - Difference (lokacije izvan buffer zona)

        **Mapa** — SHP slojevi + podaci iz baze na satelitskoj podlozi.
        """)

    conn = get_connection()

    # ── Distanca ──────────────────────────────
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

    # ── Overlay Operacije ─────────────────────
    st.subheader("Overlay Operacije (5 prostornih analiza)")

    lokacije_geo = pd.read_sql(
        "SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn
    )

    if not lokacije_geo.empty:
        # Kreiraj GeoDataFrame lokacija
        geometry = [Point(row['lon'], row['lat']) for _, row in lokacije_geo.iterrows()]
        gdf_lok = gpd.GeoDataFrame(lokacije_geo.copy(), geometry=geometry, crs='EPSG:4326')
        gdf_lok_utm = gdf_lok.to_crs('EPSG:32634')

        # 1. BUFFER
        with st.expander("1. Buffer — zaštitna zona 500m oko svake lokacije"):
            gdf_buf_utm = gdf_lok_utm.copy()
            gdf_buf_utm['geometry'] = gdf_lok_utm.geometry.buffer(500)
            gdf_buf = gdf_buf_utm.to_crs('EPSG:4326')
            gdf_buf['povrsina_ha'] = (gdf_buf_utm.geometry.area / 10000).round(2)
            st.dataframe(
                gdf_buf[['naziv', 'povrsina_ha']].rename(columns={'povrsina_ha': 'Površina zone (ha)'}),
                use_container_width=True
            )
            st.caption(f"Ukupna kombinovana površina svih zona: {gdf_buf_utm.geometry.area.sum()/10000:.2f} ha")

        # 2. INTERSECTION
        with st.expander("2. Intersection — lokacije unutar buffer zona"):
            joined = gpd.sjoin(gdf_lok, gdf_buf[['naziv', 'geometry']], how='inner', predicate='intersects')
            joined = joined[joined['naziv_left'] != joined['naziv_right']]
            if joined.empty:
                st.info("Nijedna lokacija ne ulazi u buffer zonu druge lokacije.")
            else:
                st.dataframe(
                    joined[['naziv_left', 'naziv_right']].rename(
                        columns={'naziv_left': 'Lokacija', 'naziv_right': 'Unutar zone'}
                    ),
                    use_container_width=True
                )
                st.caption(f"Pronađeno {len(joined)} preklapanja.")

        # 3. UNION
        with st.expander("3. Union — spajanje svih buffer zona u jednu"):
            union_geom = gdf_buf_utm.geometry.unary_union
            union_area_ha = union_geom.area / 10000
            st.metric("Ukupna površina unije svih zona", f"{union_area_ha:.2f} ha")
            st.caption("Union spaja sve buffer zone u jedan poligon eliminišući preklapanja.")

        # 4. CLIP
        with st.expander("4. Clip — lokacije unutar oblasti Novog Sada"):
            clip_box_geom = box(19.7, 45.1, 20.0, 45.4)
            gdf_clip_box  = gpd.GeoDataFrame([1], geometry=[clip_box_geom], crs='EPSG:4326')
            clipped = gpd.clip(gdf_lok, gdf_clip_box)
            st.dataframe(
                clipped[['naziv', 'lon', 'lat']].rename(
                    columns={'lon': 'Lon', 'lat': 'Lat'}
                ),
                use_container_width=True
            )
            st.caption(f"{len(clipped)} od {len(gdf_lok)} lokacija je unutar bbox Novog Sada (19.7–20.0°E, 45.1–45.4°N).")

        # 5. DIFFERENCE
        with st.expander("5. Difference — lokacije IZVAN buffer zona"):
            joined_all = gpd.sjoin(gdf_lok, gdf_buf[['naziv', 'geometry']], how='left', predicate='intersects')
            # Lokacije koje ne ulaze ni u jednu tuđu zonu
            outside = joined_all[
                joined_all['index_right'].isna() |
                (joined_all['naziv_left'] == joined_all['naziv_right'])
            ].drop_duplicates(subset='id')
            if outside.empty:
                st.info("Sve lokacije se nalaze unutar buffer zona.")
            else:
                st.dataframe(outside[['naziv', 'lon', 'lat']], use_container_width=True)
                st.caption(f"{len(outside)} lokacija je izvan buffer zona ostalih lokacija.")
    else:
        st.warning("Nema lokacija za overlay operacije.")

    st.divider()

    # ── Mapa sa SHP slojevima ─────────────────
    st.subheader("Mapa sa SHP slojevima i satelitskom podlogom")

    lokacije_data = pd.read_sql(
        "SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn
    )
    deponije_data = pd.read_sql("""
        SELECT naziv, tip_otpada, status, povrsina_m2,
               ST_X(ST_Centroid(geom)) as lon,
               ST_Y(ST_Centroid(geom)) as lat
        FROM deponije WHERE geom IS NOT NULL
    """, conn)
    conn.close()

    mapa = folium.Map(location=[45.2552, 19.8362], zoom_start=12)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga (Raster)',
        overlay=False,
        control=True
    ).add_to(mapa)
    folium.TileLayer('OpenStreetMap', name='OpenStreetMap', overlay=False, control=True).add_to(mapa)

    # Buffer zone sloj na mapi
    if not lokacije_geo.empty:
        fg_buf = folium.FeatureGroup(name='Buffer zone 500m', show=False)
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
                    popup=f"Buffer zona: {row['naziv']}",
                    color='blue', fill=True, fillColor='blue',
                    fillOpacity=0.15, weight=2, dashArray='5,5'
                ).add_to(fg_buf)
        fg_buf.add_to(mapa)

    # SHP sloj — mesta (places)
    shp_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'serbia_shp')
    places_shp = os.path.join(shp_dir, 'gis_osm_places_free_1.shp')
    if os.path.exists(places_shp):
        try:
            gdf_places = gpd.read_file(places_shp)
            novi_sad_box = gdf_places.cx[19.6:20.1, 45.1:45.5]
            fg_places = folium.FeatureGroup(name='OSM Mesta (SHP)', show=False)
            for _, row in novi_sad_box.iterrows():
                if row.geometry is not None and row.geometry.geom_type == 'Point':
                    folium.CircleMarker(
                        location=[row.geometry.y, row.geometry.x],
                        radius=4,
                        popup=str(row.get('name', '')),
                        color='purple',
                        fill=True,
                        fillOpacity=0.6
                    ).add_to(fg_places)
            fg_places.add_to(mapa)
        except Exception:
            pass

    # SHP sloj — korišćenje zemljišta
    landuse_shp = os.path.join(shp_dir, 'gis_osm_landuse_a_free_1.shp')
    if os.path.exists(landuse_shp):
        try:
            gdf_land = gpd.read_file(landuse_shp)
            land_clip = gdf_land.cx[19.7:20.0, 45.15:45.40]
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
                    coords = []
                    geom = row.geometry
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

    # Sloj — lokacije iz baze
    fg_lok = folium.FeatureGroup(name='Lokacije (baza)', show=True)
    for _, row in lokacije_data.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=f"<b>{row['naziv']}</b>",
            tooltip=row['naziv'],
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(fg_lok)
    fg_lok.add_to(mapa)

    # Sloj — deponije iz baze
    fg_dep = folium.FeatureGroup(name='Deponije (baza)', show=True)
    for _, row in deponije_data.iterrows():
        color = 'red' if row['status'] == 'aktivna' else ('orange' if row['status'] == 'u sanaciji' else 'green')
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

    folium.LayerControl(collapsed=False).add_to(mapa)
    st_folium(mapa, width=750, height=550)
