"""
ml_detekcija.py — Detekcija divljih deponija pomoću Random Forest algoritma
Pipeline:
1. Generisanje trening podataka iz OSM landuse poligona (ili sintetički fallback)
2. Treniranje RandomForestClassifier na 4 spektralne feture (NDVI, Osvetljenost, Tekstura, NIR)
3. Primena modela za detekciju potencijalnih deponija oko poznatih lokacija
4. Upis detektovanih deponija u PostGIS bazu
5. Prostorne analize rezultata i vizuelizacija na folium mapi
"""

import os
import pandas as pd
import psycopg2
import numpy as np
import folium
import geopandas as gpd
from datetime import datetime
from shapely.geometry import Point
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder

# Putanja do sačuvanog modela (za buduće pokretanje bez ponovnog treniranja)
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model', 'model_deponije.pkl')

# URL konekcije se učitava iz env varijable, uz fallback na hardkodirani string
DB_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"
)

def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# 1a. Trening podaci iz stvarnih OSM landuse poligona
# ─────────────────────────────────────────────

# Putanja do SHP fajlova (relativan od lokacije ovog skripte)
SHP_DIR = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')

def generiraj_trening_podatke_iz_shp(n_pixela: int = 2000):
    """
    Generiše trening podatke bazirane na stvarnim OSM landuse poligonima.
    Svaki fclass tip (forest, industrial, water...) mapira se na fizički
    realne spektralne vrednosti (NDVI, Osvetljenost, Tekstura, NIR).

    Spektralni potpisi su bazirani na poznatim karakteristikama:
    - vegetacija: visok NDVI (fotosinteza), visok NIR (refleksija lista)
    - voda:       nizak NDVI, nizak NIR (upijanje svetlosti)
    - izgradjeno: srednji NDVI, visoka tekstura (heterogena površina)
    - deponija:   nizak NDVI, visoka osvetljenost i tekstura (mešoviti materijal)

    Vraća X (feture) i y (labele klasa).
    Ako SHP fajl nije dostupan, poziva fallback sintetičku generaciju.
    """
    landuse_path = os.path.join(SHP_DIR, 'gis_osm_landuse_a_free_1.shp')
    if not os.path.exists(landuse_path):
        print("SHP fajl nije pronađen — koristim sintetičke podatke.")
        return generiraj_trening_podatke(n_pixela)

    # Učitaj landuse SHP i filtriraj na oblast Vojvodine
    gdf = gpd.read_file(landuse_path)
    gdf = gdf.cx[19.6:20.1, 45.1:45.5].copy()

    # Mapiranje OSM fclass kategorija na spektralne klase
    klasa_mapa = {
        'forest': 'vegetacija', 'park': 'vegetacija', 'meadow': 'vegetacija',
        'farmland': 'vegetacija', 'allotments': 'vegetacija', 'grass': 'vegetacija',
        'scrub': 'vegetacija', 'nature_reserve': 'vegetacija',
        'residential': 'izgradjeno', 'commercial': 'izgradjeno',
        'industrial': 'izgradjeno', 'retail': 'izgradjeno',
        'water': 'voda', 'reservoir': 'voda', 'basin': 'voda',
    }

    # Spektralni potpisi po klasi: (srednja vrednost, standardna devijacija)
    spektralni_potpisi = {
        'vegetacija': {'ndvi': (0.65, 0.08), 'brightness': (0.30, 0.06), 'texture': (0.20, 0.06), 'nir': (0.70, 0.08)},
        'voda':       {'ndvi': (0.02, 0.04), 'brightness': (0.22, 0.05), 'texture': (0.08, 0.03), 'nir': (0.12, 0.05)},
        'izgradjeno': {'ndvi': (0.12, 0.07), 'brightness': (0.68, 0.10), 'texture': (0.75, 0.10), 'nir': (0.42, 0.09)},
        'deponija':   {'ndvi': (0.10, 0.09), 'brightness': (0.78, 0.12), 'texture': (0.88, 0.10), 'nir': (0.33, 0.10)},
    }

    np.random.seed(42)
    X_list, y_list = [], []

    for klasa, potpis in spektralni_potpisi.items():
        if klasa == 'deponija':
            # Deponije su retke — manji udeo u trening setu
            n = n_pixela // 6
        else:
            # Broj uzoraka proporcionalan broju OSM poligona te klase
            fclasses = [k for k, v in klasa_mapa.items() if v == klasa]
            n_poligona = len(gdf[gdf['fclass'].isin(fclasses)])
            n = max(50, min(n_poligona * 8, n_pixela // 3))

        p = potpis
        # Generiši normalno distribuirane feture (clip na [0,1] opseg)
        features = np.column_stack([
            np.clip(np.random.normal(p['ndvi'][0],       p['ndvi'][1],       n), 0, 1),
            np.clip(np.random.normal(p['brightness'][0], p['brightness'][1], n), 0, 1),
            np.clip(np.random.normal(p['texture'][0],    p['texture'][1],    n), 0, 1),
            np.clip(np.random.normal(p['nir'][0],        p['nir'][1],        n), 0, 1),
        ])
        X_list.append(features)
        y_list.extend([klasa] * n)

    X = np.vstack(X_list)
    y = np.array(y_list)
    # Izmešaj uzorke da se izbegne redosled po klasama tokom treniranja
    idx = np.random.permutation(len(y))
    print(f"Trening podaci iz {len(gdf)} OSM landuse poligona: {len(X)} uzoraka, klase: {np.unique(y).tolist()}")
    return X[idx], y[idx]


# ─────────────────────────────────────────────
# 1b. Rezervna sintetička generacija (fallback)
# ─────────────────────────────────────────────

def generiraj_trening_podatke(n_pixela: int = 2000):
    """
    Sintetički trening podaci bazirani na poznatim spektralnim potpisima klasa.
    Koristi se kada SHP fajlovi nisu dostupni.
    Simulira multispektralne satelitske kanale: [NDVI, Osvetljenost, Tekstura, NIR]
    """
    np.random.seed(42)

    klase = {
        'vegetacija':  {'ndvi': (0.65, 0.08), 'brightness': (0.30, 0.06), 'texture': (0.20, 0.06), 'nir': (0.70, 0.08)},
        'voda':        {'ndvi': (0.02, 0.04), 'brightness': (0.22, 0.05), 'texture': (0.08, 0.03), 'nir': (0.12, 0.05)},
        'izgradjeno':  {'ndvi': (0.12, 0.07), 'brightness': (0.68, 0.10), 'texture': (0.75, 0.10), 'nir': (0.42, 0.09)},
        'deponija':    {'ndvi': (0.10, 0.09), 'brightness': (0.78, 0.12), 'texture': (0.88, 0.10), 'nir': (0.33, 0.10)},
    }
    # Udeo svake klase u trening skupu (vegetacija dominira kao u stvarnom svetu)
    distribucija = {'vegetacija': 0.40, 'voda': 0.15, 'izgradjeno': 0.30, 'deponija': 0.15}

    X_list, y_list = [], []
    for klasa, udeo in distribucija.items():
        n = int(n_pixela * udeo)
        p = klase[klasa]
        features = np.column_stack([
            np.clip(np.random.normal(p['ndvi'][0],       p['ndvi'][1],       n), 0, 1),
            np.clip(np.random.normal(p['brightness'][0], p['brightness'][1], n), 0, 1),
            np.clip(np.random.normal(p['texture'][0],    p['texture'][1],    n), 0, 1),
            np.clip(np.random.normal(p['nir'][0],        p['nir'][1],        n), 0, 1),
        ])
        X_list.append(features)
        y_list.extend([klasa] * n)

    X = np.vstack(X_list)
    y = np.array(y_list)
    idx = np.random.permutation(len(y))
    return X[idx], y[idx]


# ─────────────────────────────────────────────
# 2. Treniranje Random Forest modela
# ─────────────────────────────────────────────

def treniraj_model(X, y):
    """
    Trenira RandomForestClassifier i ispisuje evaluaciju.
    80/20 split: 80% trening, 20% test.
    stratify=y osigurava isti udeo klasa u oba skupa.
    n_jobs=-1 koristi sve dostupne CPU jezgre za paralelno treniranje.
    """
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    # 150 stabala, max dubina 12 — balans između preciznosti i brzine
    clf = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    tacnost = accuracy_score(y_test, y_pred)

    print("\n" + "=" * 60)
    print("EVALUACIJA MODELA — Random Forest")
    print("=" * 60)
    print(f"Ukupna tacnost: {tacnost:.1%}")
    print("\nKlasifikacioni izveštaj:")
    print(classification_report(y_test, y_pred))

    # Važnost atributa — koliko svaka fetura doprinosi klasifikaciji
    feature_names = ['NDVI', 'Osvetljenost', 'Tekstura', 'NIR']
    importances = clf.feature_importances_
    print("Važnost atributa (feature importance):")
    for name, imp in sorted(zip(feature_names, importances), key=lambda x: -x[1]):
        print(f"  {name}: {imp:.3f}")

    return clf


# ─────────────────────────────────────────────
# 3. Primena modela — detekcija deponija
# ─────────────────────────────────────────────

def detektuj_deponije(clf, lokacije_df, n_uzoraka_po_lokaciji: int = 80):
    """
    Primenjuje trenirani model na spektralne uzorke generisane oko svake lokacije.
    Za svaku lokaciju generiše n_uzoraka_po_lokaciji nasumičnih spektralnih vektora,
    klasifikuje ih i uzima do 3 piksela klasifikovanih kao 'deponija' sa confidence > 0.55.

    confidence = verovatnoća klase 'deponija' prema predict_proba().
    Prag 0.55 filtrira nesigurne detekcije.
    """
    np.random.seed(123)
    # Indeks klase 'deponija' u nizu klasa modela
    deponija_klasa_idx = list(clf.classes_).index('deponija')
    deponije_ml = []

    for _, lokacija in lokacije_df.iterrows():
        # Uniformno distribuirani spektralni pikseli — simulacija skeniranja okoline
        X_nova = np.column_stack([
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
        ])

        y_pred  = clf.predict(X_nova)
        y_proba = clf.predict_proba(X_nova)

        # Pronađi piksele klasifikovane kao deponija
        deponija_pikseli = np.where(y_pred == 'deponija')[0]

        # Uzmi max 3 detekcije po lokaciji da se izbegne prenatrpavanje
        for i, px in enumerate(deponija_pikseli[:3]):
            confidence = y_proba[px, deponija_klasa_idx]
            if confidence < 0.55:
                continue  # Preskoči detekcije ispod praga pouzdanosti

            # Nasumični pomak koordinata od centra lokacije (max ±1.5km aprox)
            offset_lat = np.random.uniform(-0.015, 0.015)
            offset_lon = np.random.uniform(-0.015, 0.015)

            deponije_ml.append({
                'naziv':           f"ML Deponija {lokacija['naziv'][:5]}-{i+1}",
                'lat':             lokacija['lat'] + offset_lat,
                'lon':             lokacija['lon'] + offset_lon,
                'povrsina_m2':     round(np.random.uniform(60, 900), 1),
                'tip_otpada':      np.random.choice(['komunalni', 'gradjevinski', 'mesoviti', 'industrijski']),
                'status':          'detektovana',
                'confidence':      round(float(confidence), 3),
                'datum_detekcije': datetime.now().strftime('%Y-%m-%d'),
                # Sačuvaj spektralne feture za dokumentaciju detekcije
                'ndvi':            round(float(X_nova[px, 0]), 3),
                'brightness':      round(float(X_nova[px, 1]), 3),
                'texture':         round(float(X_nova[px, 2]), 3),
                'nir':             round(float(X_nova[px, 3]), 3),
            })

    df = pd.DataFrame(deponije_ml)
    if df.empty:
        print("Model nije detektovao nijednu deponiju sa confidence > 0.55")
    return df


# ─────────────────────────────────────────────
# 4. Upisivanje u PostGIS bazu
# ─────────────────────────────────────────────

def upisi_deponije_u_bazu(deponije_df):
    """
    Upisuje ML detektovane deponije u PostGIS tabelu deponije.
    Za svaku deponiju:
    1. Pronalazi najbližu lokaciju u bazi (ST_Distance + ORDER BY LIMIT 1)
    2. Kreira buffer poligon oko koordinate detekcije kao geometriju
    Svaki INSERT se commit-uje odvojeno — greška jednog ne blokira ostale.
    """
    if deponije_df.empty:
        return
    print(f"\nUpisujem {len(deponije_df)} ML deponija u bazu...")
    conn = get_connection()
    cursor = conn.cursor()

    for _, depo in deponije_df.iterrows():
        try:
            # Pronađi najbližu lokaciju iz baze merenjem geodetske distance
            cursor.execute("""
                SELECT id FROM lokacije
                ORDER BY ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                LIMIT 1
            """, (depo['lon'], depo['lat']))
            lokacija_id = cursor.fetchone()[0]

            # Upiši deponiju sa ST_Buffer kao geometrijom (krug oko detekcije)
            cursor.execute("""
                INSERT INTO deponije
                    (naziv, povrsina_m2, tip_otpada, status, datum_otkrivanja, lokacija_id, geom)
                VALUES (%s, %s, %s, %s, %s, %s,
                    ST_Buffer(
                        ST_SetSRID(ST_MakePoint(%s, %s), 4326)::geography,
                        %s
                    )::geometry)
            """, (
                depo['naziv'], depo['povrsina_m2'], depo['tip_otpada'],
                depo['status'], depo['datum_detekcije'], lokacija_id,
                depo['lon'], depo['lat'],
                # Radijus proporcionalan površini deponije
                int(depo['povrsina_m2'] ** 0.5 / 2)
            ))
            conn.commit()
        except Exception as e:
            print(f"Greška pri upisu {depo['naziv']}: {e}")
            conn.rollback()

    cursor.close()
    conn.close()
    print("Deponije upisane!")


# ─────────────────────────────────────────────
# 5. Prostorne analize sa ML rezultatima
# ─────────────────────────────────────────────

def prostorne_analize(deponije_df, lokacije_df):
    """
    Izvodi 5 prostornih analiza nad ML detektovanim deponijama:
    1. Buffer 300m — zone uticaja svake deponije
    2. Sjoin — koje lokacije su unutar buffer zona
    3. Agregacija — ukupna površina i prosečni confidence
    4. Distribucija — raspored po tipu otpada
    5. Distanca — koliko je svaka deponija od najbliže lokacije
    """
    if deponije_df.empty:
        print("Nema ML deponija za analizu.")
        return

    print("\n" + "=" * 60)
    print("PROSTORNE ANALIZE SA ML REZULTATIMA")
    print("=" * 60)

    # Kreiraj GeoDataFrame od ML deponija
    geometry = [Point(row['lon'], row['lat']) for _, row in deponije_df.iterrows()]
    gdf_ml = gpd.GeoDataFrame(deponije_df.copy(), geometry=geometry, crs='EPSG:4326')

    # Kreiraj GeoDataFrame od lokacija iz baze
    geom_lok = [Point(row['lon'], row['lat']) for _, row in lokacije_df.iterrows()]
    gdf_lok  = gpd.GeoDataFrame(lokacije_df.copy(), geometry=geom_lok, crs='EPSG:4326')

    # Projekcija u UTM za precizne distance i buffer u metrima
    gdf_ml_utm  = gdf_ml.to_crs('EPSG:32634')
    gdf_lok_utm = gdf_lok.to_crs('EPSG:32634')

    # Analiza 1: Buffer 300m — zone uticaja ML deponija
    buffer_zone = gdf_ml_utm.copy()
    buffer_zone['geometry'] = gdf_ml_utm.geometry.buffer(300)
    buffer_zone = buffer_zone.to_crs('EPSG:4326')
    print(f"\n1. Buffer zone (300m): {len(buffer_zone)} zona kreirano")

    # Analiza 2: Koje lokacije iz baze se nalaze unutar buffer zona
    overlap = gpd.sjoin(gdf_lok, buffer_zone[['geometry']], how='inner', predicate='intersects')
    print(f"2. Lokacije unutar 300m buffer zona: {len(overlap)}")
    if not overlap.empty:
        print("   Lokacije:", overlap['naziv'].tolist())

    # Analiza 3: Statistike detektovanih deponija
    print(f"\n3. Ukupna detektovana površina: {deponije_df['povrsina_m2'].sum():.1f} m²")
    print(f"   Prosečna površina: {deponije_df['povrsina_m2'].mean():.1f} m²")
    print(f"   Prosečni confidence: {deponije_df['confidence'].mean():.3f}")

    # Analiza 4: Koliko deponija po tipu otpada
    print("\n4. Distribucija po tipu otpada:")
    print(deponije_df['tip_otpada'].value_counts().to_string())

    # Analiza 5: Distanca svake ML deponije do najbliže lokacije u bazi
    print("\n5. Distanca do najbliže lokacije (UTM, metri):")
    for _, ml_row in gdf_ml_utm.iterrows():
        distances = gdf_lok_utm.geometry.distance(ml_row.geometry)
        min_dist  = distances.min()
        naj_lok   = lokacije_df.iloc[distances.idxmin()]['naziv']
        print(f"   {ml_row['naziv']}: {min_dist:.0f} m od '{naj_lok}'")


# ─────────────────────────────────────────────
# 6. Kreiranje mape
# ─────────────────────────────────────────────

def kreiraj_mapu(originalne_deponije, ml_deponije_df):
    """
    Kreira folium mapu sa dva sloja:
    - Originalne deponije (narandžasti markeri)
    - ML detektovane deponije (crveni markeri sa confidence score-om)
    Esri satelitska podloga za kontekst.
    """
    mapa = folium.Map(location=[45.25, 20.0], zoom_start=8)

    # Satelitska raster podloga
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga',
        overlay=False,
        control=True
    ).add_to(mapa)

    # Sloj originalnih deponija iz baze
    fg_orig = folium.FeatureGroup(name='Originalne deponije', show=True)
    for _, row in originalne_deponije.iterrows():
        folium.Marker(
            location=[row['lat'], row['lon']],
            popup=(f"<b>{row['naziv']}</b><br>"
                   f"Površina: {row['povrsina_m2']:.0f} m²<br>"
                   f"Tip: {row['tip_otpada']}<br>"
                   f"Status: {row['status']}"),
            icon=folium.Icon(color='orange', icon='trash'),
            tooltip=row['naziv']
        ).add_to(fg_orig)
    fg_orig.add_to(mapa)

    # Sloj ML detektovanih deponija (crveni kružići sa confidence-om)
    fg_ml = folium.FeatureGroup(name='ML Detektovane deponije', show=True)
    for _, row in ml_deponije_df.iterrows():
        folium.CircleMarker(
            location=[row['lat'], row['lon']],
            radius=8,
            popup=(f"<b>{row['naziv']}</b><br>"
                   f"Confidence: {row['confidence']:.1%}<br>"
                   f"Površina: {row['povrsina_m2']:.0f} m²<br>"
                   f"NDVI: {row['ndvi']:.3f} | Tekstura: {row['texture']:.3f}"),
            color='red', fill=True, fillColor='red', fillOpacity=0.7,
            tooltip=f"{row['naziv']} ({row['confidence']:.0%})"
        ).add_to(fg_ml)
    fg_ml.add_to(mapa)

    folium.LayerControl().add_to(mapa)
    mapa.save('mapa_ml_rezultati.html')
    print("Mapa sacuvana kao 'mapa_ml_rezultati.html'")


# ─────────────────────────────────────────────
# MAIN — pokretanje kompletnog ML pipeline-a
# ─────────────────────────────────────────────

if __name__ == "__main__":
    # Učitaj lokacije iz baze kao osnovu za detekciju
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    conn.close()

    print("LOKACIJE U SISTEMU:")
    print(lokacije_df.to_string(index=False))

    # Korak 1: Generiši trening podatke iz OSM landuse SHP (fallback: sintetički)
    print("\nGenerisanje trening podataka iz OSM landuse poligona...")
    X, y = generiraj_trening_podatke_iz_shp(n_pixela=2000)
    print(f"Trening skup: {len(X)} uzoraka, klase: {np.unique(y).tolist()}")

    # Korak 2: Treniraj Random Forest model i prikaži evaluaciju
    clf = treniraj_model(X, y)

    # Korak 3: Primeni model na okolinu svake lokacije
    ml_deponije_df = detektuj_deponije(clf, lokacije_df, n_uzoraka_po_lokaciji=80)
    print(f"\nDetektovano {len(ml_deponije_df)} ML deponija (confidence > 0.55)")
    if not ml_deponije_df.empty:
        print(ml_deponije_df[['naziv', 'povrsina_m2', 'tip_otpada', 'confidence']].to_string(index=False))

    # Korak 4: Upiši detektovane deponije u PostGIS bazu
    upisi_deponije_u_bazu(ml_deponije_df)

    # Korak 5: Izvedi prostorne analize nad rezultatima
    prostorne_analize(ml_deponije_df, lokacije_df)

    # Korak 6: Kreiraj mapu sa originalnim i ML deponijama
    conn2 = get_connection()
    sve = pd.read_sql("""
        SELECT naziv, povrsina_m2, tip_otpada, status,
               ST_X(ST_Centroid(geom)) as lon,
               ST_Y(ST_Centroid(geom)) as lat
        FROM deponije WHERE geom IS NOT NULL
    """, conn2)
    conn2.close()

    # Razdvoji originalne od ML deponija po nazivu
    originalne = sve[~sve['naziv'].str.contains('ML', na=False)]
    detektovane = ml_deponije_df if not ml_deponije_df.empty else sve[sve['naziv'].str.contains('ML', na=False)]
    kreiraj_mapu(originalne, detektovane)

    print("\n=== DEO 3 ZAVRSEN! ===")
