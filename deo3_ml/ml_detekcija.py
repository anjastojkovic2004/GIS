import pandas as pd
import psycopg2
import numpy as np
import folium
import geopandas as gpd
import joblib
import os
from datetime import datetime
from shapely.geometry import Point
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.preprocessing import LabelEncoder

MODEL_PATH = os.path.join(os.path.dirname(__file__), 'model_deponije.pkl')

DB_URL = "postgresql://postgres.vtmpqdgrtntctvbusxec:NoviSad2024!@aws-0-eu-west-1.pooler.supabase.com:6543/postgres"

def get_connection():
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# 1. Generisanje sintetičkih satelitskih podataka
# ─────────────────────────────────────────────
def generiraj_trening_podatke(n_pixela: int = 2000):
    """
    Simulira multispektralne satelitske kanale:
    [NDVI, Osvetljenost, Tekstura, NIR]

    Svaka klasa ima karakteristične spektralne potpise:
    - vegetacija: visok NDVI, nizak NIR
    - voda:       nizak NDVI, visoka refleksija u NIR
    - izgradjeno: srednji NDVI, visoka tekstura
    - deponija:   nizak NDVI, visoka osvetljenost i tekstura (mesoviti materijal)
    """
    np.random.seed(42)

    klase = {
        'vegetacija':  {'ndvi': (0.65, 0.08), 'brightness': (0.30, 0.06), 'texture': (0.20, 0.06), 'nir': (0.70, 0.08)},
        'voda':        {'ndvi': (0.02, 0.04), 'brightness': (0.22, 0.05), 'texture': (0.08, 0.03), 'nir': (0.12, 0.05)},
        'izgradjeno':  {'ndvi': (0.12, 0.07), 'brightness': (0.68, 0.10), 'texture': (0.75, 0.10), 'nir': (0.42, 0.09)},
        'deponija':    {'ndvi': (0.10, 0.09), 'brightness': (0.78, 0.12), 'texture': (0.88, 0.10), 'nir': (0.33, 0.10)},
    }
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
    """Trenira RandomForestClassifier i ispisuje evaluaciju."""
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

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

    # Važnost atributa
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
    Primenjuje trenirani model na sintetičke piksele
    generisane oko svake lokacije. Pikseli klasifikovani
    kao 'deponija' sa confidence > 0.55 postaju detektovani objekti.
    """
    np.random.seed(123)
    deponija_klasa_idx = list(clf.classes_).index('deponija')
    deponije_ml = []

    for _, lokacija in lokacije_df.iterrows():
        # Sintetički spektralni pikseli u okolini lokacije
        X_nova = np.column_stack([
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
            np.random.uniform(0.0, 1.0, n_uzoraka_po_lokaciji),
        ])

        y_pred  = clf.predict(X_nova)
        y_proba = clf.predict_proba(X_nova)

        deponija_pikseli = np.where(y_pred == 'deponija')[0]

        for i, px in enumerate(deponija_pikseli[:3]):
            confidence = y_proba[px, deponija_klasa_idx]
            if confidence < 0.55:
                continue

            offset_lat = np.random.uniform(-0.015, 0.015)
            offset_lon = np.random.uniform(-0.015, 0.015)

            deponije_ml.append({
                'naziv':          f"ML Deponija {lokacija['naziv'][:5]}-{i+1}",
                'lat':            lokacija['lat'] + offset_lat,
                'lon':            lokacija['lon'] + offset_lon,
                'povrsina_m2':    round(np.random.uniform(60, 900), 1),
                'tip_otpada':     np.random.choice(['komunalni', 'gradjevinski', 'mesoviti', 'industrijski']),
                'status':         'detektovana',
                'confidence':     round(float(confidence), 3),
                'datum_detekcije': datetime.now().strftime('%Y-%m-%d'),
                'ndvi':           round(float(X_nova[px, 0]), 3),
                'brightness':     round(float(X_nova[px, 1]), 3),
                'texture':        round(float(X_nova[px, 2]), 3),
                'nir':            round(float(X_nova[px, 3]), 3),
            })

    df = pd.DataFrame(deponije_ml)
    if df.empty:
        print("Model nije detektovao nijednu deponiju sa confidence > 0.55")
    return df


# ─────────────────────────────────────────────
# 4. Upisivanje u PostGIS bazu
# ─────────────────────────────────────────────
def upisi_deponije_u_bazu(deponije_df):
    if deponije_df.empty:
        return
    print(f"\nUpisujem {len(deponije_df)} ML deponija u bazu...")
    conn = get_connection()
    cursor = conn.cursor()

    for _, depo in deponije_df.iterrows():
        try:
            cursor.execute("""
                SELECT id FROM lokacije
                ORDER BY ST_Distance(geom, ST_SetSRID(ST_MakePoint(%s, %s), 4326))
                LIMIT 1
            """, (depo['lon'], depo['lat']))
            lokacija_id = cursor.fetchone()[0]

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
    if deponije_df.empty:
        print("Nema ML deponija za analizu.")
        return

    print("\n" + "=" * 60)
    print("PROSTORNE ANALIZE SA ML REZULTATIMA")
    print("=" * 60)

    # Kreiraj GeoDataFrame od ML deponija
    geometry = [Point(row['lon'], row['lat']) for _, row in deponije_df.iterrows()]
    gdf_ml = gpd.GeoDataFrame(deponije_df.copy(), geometry=geometry, crs='EPSG:4326')

    # Kreiraj GeoDataFrame od lokacija
    geom_lok = [Point(row['lon'], row['lat']) for _, row in lokacije_df.iterrows()]
    gdf_lok  = gpd.GeoDataFrame(lokacije_df.copy(), geometry=geom_lok, crs='EPSG:4326')

    # Projekcija u UTM za precizne distance i buffer
    gdf_ml_utm  = gdf_ml.to_crs('EPSG:32634')
    gdf_lok_utm = gdf_lok.to_crs('EPSG:32634')

    # Analiza 1: Buffer 300m oko ML deponija — zone uticaja
    buffer_zone = gdf_ml_utm.copy()
    buffer_zone['geometry'] = gdf_ml_utm.geometry.buffer(300)
    buffer_zone = buffer_zone.to_crs('EPSG:4326')
    print(f"\n1. Buffer zone (300m): {len(buffer_zone)} zona kreirano")

    # Analiza 2: Lokacije unutar buffer zona (within/intersects)
    overlap = gpd.sjoin(gdf_lok, buffer_zone[['geometry']], how='inner', predicate='intersects')
    print(f"2. Lokacije unutar 300m buffer zona: {len(overlap)}")
    if not overlap.empty:
        print("   Lokacije:", overlap['naziv'].tolist())

    # Analiza 3: Ukupna površina detektovanih deponija
    print(f"\n3. Ukupna detektovana površina: {deponije_df['povrsina_m2'].sum():.1f} m²")
    print(f"   Prosečna površina: {deponije_df['povrsina_m2'].mean():.1f} m²")
    print(f"   Prosečni confidence: {deponije_df['confidence'].mean():.3f}")

    # Analiza 4: Distribucija po tipu otpada
    print("\n4. Distribucija po tipu otpada:")
    print(deponije_df['tip_otpada'].value_counts().to_string())

    # Analiza 5: Distanca svake ML deponije do najbliže lokacije
    print("\n5. Distanca do najbliže lokacije (UTM, metri):")
    for idx, ml_row in gdf_ml_utm.iterrows():
        distances = gdf_lok_utm.geometry.distance(ml_row.geometry)
        min_dist  = distances.min()
        naj_lok   = lokacije_df.iloc[distances.idxmin()]['naziv']
        print(f"   {ml_row['naziv']}: {min_dist:.0f} m od '{naj_lok}'")


# ─────────────────────────────────────────────
# 6. Kreiranje mape
# ─────────────────────────────────────────────
def kreiraj_mapu(originalne_deponije, ml_deponije_df):
    mapa = folium.Map(location=[45.2552, 19.8362], zoom_start=12)

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery',
        name='Satelitska podloga',
        overlay=False,
        control=True
    ).add_to(mapa)

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
# MAIN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    conn = get_connection()
    lokacije_df = pd.read_sql("""
        SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije
    """, conn)
    conn.close()

    print("LOKACIJE U SISTEMU:")
    print(lokacije_df.to_string(index=False))

    # 1. Učitaj model ako postoji, inače treniraj i sačuvaj
    if os.path.exists(MODEL_PATH):
        print(f"\nUčitavam sačuvani model iz '{MODEL_PATH}'...")
        clf = joblib.load(MODEL_PATH)
        print("Model učitan!")
    else:
        print("\nGenerisanje sintetickih satelitskih podataka...")
        X, y = generiraj_trening_podatke(n_pixela=2000)
        print(f"Trening skup: {len(X)} piksela, klase: {np.unique(y).tolist()}")

        clf = treniraj_model(X, y)

        joblib.dump(clf, MODEL_PATH)
        print(f"Model sačuvan kao '{MODEL_PATH}'")

    # 3. Primeni model — detekcija
    ml_deponije_df = detektuj_deponije(clf, lokacije_df, n_uzoraka_po_lokaciji=80)
    print(f"\nDetektovano {len(ml_deponije_df)} ML deponija (confidence > 0.55)")
    if not ml_deponije_df.empty:
        print(ml_deponije_df[['naziv', 'povrsina_m2', 'tip_otpada', 'confidence']].to_string(index=False))

    # 4. Upiši u bazu
    upisi_deponije_u_bazu(ml_deponije_df)

    # 5. Prostorne analize
    prostorne_analize(ml_deponije_df, lokacije_df)

    # 6. Mapa
    conn2 = get_connection()
    sve = pd.read_sql("""
        SELECT naziv, povrsina_m2, tip_otpada, status,
               ST_X(ST_Centroid(geom)) as lon,
               ST_Y(ST_Centroid(geom)) as lat
        FROM deponije WHERE geom IS NOT NULL
    """, conn2)
    conn2.close()

    originalne = sve[~sve['naziv'].str.contains('ML', na=False)]
    detektovane = ml_deponije_df if not ml_deponije_df.empty else sve[sve['naziv'].str.contains('ML', na=False)]
    kreiraj_mapu(originalne, detektovane)

    print("\n=== DEO 3 ZAVRSEN! ===")
