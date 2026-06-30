"""
ml_detekcija.py — ML detekcija divljih deponija iz satelitskog snimka
Pipeline koji prati stvarni workflow daljinskog istraživanja:
1. Kreiranje višekanalnog GeoTIFF rasterskog snimka (simulacija Sentinel-2),
   sa spektralnim potpisima postavljenim NA STVARNE KOORDINATE gradova i
   deponija iz baze (ne nasumične pozicije)
2. Ekstrakcija spektralnih obeležja po pikselima (B2, B3, B4, B8, NDVI, tekstura)
3. Kreiranje trening labela iz poznatih lokacija deponija
4. Treniranje Random Forest klasifikatora na pikselima snimka
5. Klasifikacija celog snimka piksel po piksel
6. Konverzija klasifikovanih piksela u vektorske poligone (rasterio.features.shapes)
7. Upis geometrija detektovanih deponija u PostGIS bazu (vezano za najbližu lokaciju)
8. Prostorne analize i prikaz na folium mapi
"""

import os
import random
import numpy as np
import pandas as pd
import psycopg2
import folium
import geopandas as gpd
import rasterio
from rasterio.transform import from_bounds, rowcol
from rasterio.features import shapes
from rasterio.crs import CRS
from scipy.ndimage import uniform_filter, binary_closing, label
from scipy.ndimage import sum as ndi_sum
from shapely.geometry import shape, Point
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from dotenv import load_dotenv

load_dotenv()
DB_URL = os.environ.get("DB_URL")

SHP_DIR     = os.path.join(os.path.dirname(__file__), '..', 'serbia_shp')
RASTER_PATH = os.path.join(os.path.dirname(__file__), 'vojvodina_snimak.tif')

# Vojvodina bounding box (WGS84)
VOJV_MINX, VOJV_MINY = 18.8, 44.6
VOJV_MAXX, VOJV_MAXY = 21.7, 46.2

# Dimenzije rasterskog snimka — ~100m/piksel preko cele Vojvodine
RASTER_W, RASTER_H = 2280, 1780


def get_connection():
    """Otvara konekciju na PostgreSQL/PostGIS bazu."""
    return psycopg2.connect(DB_URL)


# ─────────────────────────────────────────────
# 1. Kreiranje satelitskog snimka (GeoTIFF)
# ─────────────────────────────────────────────

def kreiraj_snimak():
    """
    Kreira sintetički 4-kanalni GeoTIFF koji simulira Sentinel-2 satelitski snimak.
    Kanali: B2 (plavi), B3 (zeleni), B4 (crveni), B8 (NIR — blisko infracrveno)

    Spektralni potpisi po tipu površine:
    - Vegetacija (polja, šume): visok NIR, nizak crveni → visok NDVI (fotosinteza)
    - Urbano (gradovi): uniformne srednje vrednosti svih kanala
    - Deponije: nizak NIR, visok crveni, visoka tekstura → negativan/nizak NDVI

    Urbane zone i deponije se NE postavljaju nasumično — koriste se stvarne
    koordinate iz baze (lokacije i deponije tabele). Radijus mrlje deponije
    je proporcionalan njenoj stvarnoj površini (povrsina_m2), pa labele
    koje model trenira odgovaraju realnoj geografiji, ne izmišljenim tačkama.
    """
    np.random.seed(42)
    h, w = RASTER_H, RASTER_W

    # Osnova: vegetacija — dominantan tip terena u ravnoj Vojvodini
    b2 = np.random.normal(0.08, 0.02, (h, w)).clip(0.01, 1.0)
    b3 = np.random.normal(0.11, 0.02, (h, w)).clip(0.01, 1.0)
    b4 = np.random.normal(0.07, 0.02, (h, w)).clip(0.01, 1.0)
    b8 = np.random.normal(0.45, 0.06, (h, w)).clip(0.01, 1.0)  # visok NIR

    transform = from_bounds(VOJV_MINX, VOJV_MINY, VOJV_MAXX, VOJV_MAXY, width=w, height=h)
    pixel_w_m = (VOJV_MAXX - VOJV_MINX) * 111320 * np.cos(np.radians(45.4)) / w
    pixel_h_m = (VOJV_MAXY - VOJV_MINY) * 111320 / h
    pixel_size_m = (pixel_w_m + pixel_h_m) / 2

    conn = get_connection()
    lokacije_df = pd.read_sql(
        "SELECT naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn)
    deponije_df = pd.read_sql(
        "SELECT naziv, povrsina_m2, ST_X(ST_Centroid(geom)) as lon, "
        "ST_Y(ST_Centroid(geom)) as lat FROM deponije WHERE naziv NOT LIKE '%ML%'", conn)
    conn.close()

    # Urbane zone — na stvarnim koordinatama gradova iz baze (lokacije)
    for _, lok in lokacije_df.iterrows():
        row, col = rowcol(transform, lok['lon'], lok['lat'])
        r = np.random.randint(15, 35)
        row0, row1 = max(0, row - r), min(h, row + r + 1)
        col0, col1 = max(0, col - r), min(w, col + r + 1)
        yi, xi = np.ogrid[row0:row1, col0:col1]
        m = (xi - col)**2 + (yi - row)**2 < r**2
        n = int(m.sum())
        b2[row0:row1, col0:col1][m] = np.random.normal(0.17, 0.02, n)
        b3[row0:row1, col0:col1][m] = np.random.normal(0.17, 0.02, n)
        b4[row0:row1, col0:col1][m] = np.random.normal(0.15, 0.02, n)
        b8[row0:row1, col0:col1][m] = np.random.normal(0.22, 0.03, n)  # nizak NIR za urbano

    # Deponije — na stvarnim koordinatama iz baze, radijus prati stvarnu povrsina_m2
    landfill_masks = []
    for _, dep in deponije_df.iterrows():
        row, col = rowcol(transform, dep['lon'], dep['lat'])
        if not (0 <= row < h and 0 <= col < w):
            continue
        radius_m = max(30.0, (dep['povrsina_m2'] / np.pi) ** 0.5)
        r = max(1, min(40, round(radius_m / pixel_size_m)))
        row0, row1 = max(0, row - r), min(h, row + r + 1)
        col0, col1 = max(0, col - r), min(w, col + r + 1)
        yi, xi = np.ogrid[row0:row1, col0:col1]
        m = (xi - col)**2 + (yi - row)**2 <= r**2
        n = int(m.sum())
        if n == 0:
            continue

        b2[row0:row1, col0:col1][m] = np.random.normal(0.14, 0.03, n)
        b3[row0:row1, col0:col1][m] = np.random.normal(0.12, 0.03, n)
        b4_patch = np.random.normal(0.22, 0.04, n)
        b4_patch += np.random.normal(0, 0.04, n)  # tekstura — heterogenost deponije
        b4[row0:row1, col0:col1][m] = b4_patch
        b8[row0:row1, col0:col1][m] = np.random.normal(0.11, 0.03, n)   # nizak NIR

        full_mask = np.zeros((h, w), dtype=bool)
        full_mask[row0:row1, col0:col1] = m
        landfill_masks.append(full_mask)

    b2, b3, b4, b8 = [np.clip(x, 0.01, 1.0) for x in [b2, b3, b4, b8]]

    with rasterio.open(
        RASTER_PATH, 'w',
        driver='GTiff', height=h, width=w,
        count=4, dtype=np.float32,
        crs=CRS.from_epsg(4326), transform=transform
    ) as dst:
        dst.write(b2.astype(np.float32), 1)  # B2 — plavi
        dst.write(b3.astype(np.float32), 2)  # B3 — zeleni
        dst.write(b4.astype(np.float32), 3)  # B4 — crveni
        dst.write(b8.astype(np.float32), 4)  # B8 — NIR

    print(f"Snimak kreiran: {RASTER_PATH} ({w}×{h} piksela, ~{pixel_size_m:.0f}m/piksel)")
    print(f"  Urbane zone na {len(lokacije_df)} stvarnih lokacija, "
          f"deponije na {len(landfill_masks)} stvarnih OSM lokacija")
    return landfill_masks


# ─────────────────────────────────────────────
# 2. Ekstrakcija spektralnih obeležja
# ─────────────────────────────────────────────

def ekstrahuj_karakteristike():
    """
    Čita GeoTIFF i izračunava 7 spektralnih obeležja po svakom pikselu:
    B2, B3, B4, B8 — sirove vrednosti kanala
    NDVI = (B8 - B4) / (B8 + B4) — vegetacijski indeks
    Tekstura — lokalna standardna devijacija B4 (deponije su heterogene)
    Osvetljenost — prosek vidljivih kanala

    Vraća matricu [n_piksela × 7] i metapodatke rasterа.
    """
    with rasterio.open(RASTER_PATH) as src:
        b2 = src.read(1).astype(np.float32)
        b3 = src.read(2).astype(np.float32)
        b4 = src.read(3).astype(np.float32)
        b8 = src.read(4).astype(np.float32)
        transform = src.transform
        crs       = src.crs
        h, w      = b2.shape

    # NDVI: vegetacija > 0.3, urbano 0.1–0.3, deponije < 0.1
    ndvi = np.where((b8 + b4) > 0, (b8 - b4) / (b8 + b4), 0.0)

    # Tekstura — lokalna standardna devijacija B4 kanala (3×3 prozor)
    mean_b4  = uniform_filter(b4, size=3)
    mean_sq  = uniform_filter(b4 ** 2, size=3)
    tekstura = np.sqrt(np.maximum(mean_sq - mean_b4 ** 2, 0))

    brightness = (b2 + b3 + b4) / 3.0

    features = np.stack([
        b2.ravel(), b3.ravel(), b4.ravel(), b8.ravel(),
        ndvi.ravel(), tekstura.ravel(), brightness.ravel()
    ], axis=1)

    print(f"Ekstahovano: {features.shape[0]} piksela × {features.shape[1]} obeležja")
    return features, ndvi, transform, crs, h, w


# ─────────────────────────────────────────────
# 3. Trening labele
# ─────────────────────────────────────────────

def kreiraj_labele(landfill_masks, h, w):
    """
    Kreira binarnu matricu labela iz pozicija sintetičkih deponija u snimku.
    1 = piksel pripada deponiji, 0 = sve ostalo.
    U stvarnom projektu, labele bi se dobijale rasterizacijom
    ručno anotiranih poligona (npr. iz QGIS-a) ili OSM landfill sloja.
    """
    labels = np.zeros(h * w, dtype=np.int32)
    for mask in landfill_masks:
        labels[mask.ravel()] = 1
    n_dep = labels.sum()
    print(f"Labele: {n_dep} deponija / {len(labels) - n_dep} ostalo ({n_dep/(h*w)*100:.1f}%)")
    return labels


# ─────────────────────────────────────────────
# 4. Treniranje Random Forest
# ─────────────────────────────────────────────

def treniraj_model(features, labels):
    """
    Trenira Random Forest na uzorku piksela rasterskog snimka.
    Klasa 'deponija' je veoma retka (< 0.1% piksela na ~100m rezoluciji),
    pa se uzimaju SVI pikseli deponije plus nasumični uzorak ostalih piksela —
    čist nasumični uzorak od svih piksela bi skoro uvek promašio retku klasu.
    stratify=y osigurava isti udeo deponija u trening i test skupu.
    """
    dep_idx    = np.where(labels == 1)[0]
    ostali_idx = np.where(labels == 0)[0]

    n_ostali = min(8000, len(ostali_idx))
    ostali_sample = np.random.choice(ostali_idx, n_ostali, replace=False)

    idx = np.concatenate([dep_idx, ostali_sample])
    X_s, y_s = features[idx], labels[idx]

    X_train, X_test, y_train, y_test = train_test_split(
        X_s, y_s, test_size=0.2, random_state=42, stratify=y_s
    )

    clf = RandomForestClassifier(n_estimators=150, max_depth=12, random_state=42, n_jobs=-1)
    clf.fit(X_train, y_train)

    y_pred = clf.predict(X_test)
    print(f"\nTačnost: {accuracy_score(y_test, y_pred):.1%}")
    print(classification_report(y_test, y_pred, target_names=['Nije deponija', 'Deponija']))

    feature_names = ['B2', 'B3', 'B4', 'B8', 'NDVI', 'Tekstura', 'Osvetljenost']
    print("Važnost obeležja (feature importance):")
    for name, imp in sorted(zip(feature_names, clf.feature_importances_), key=lambda x: -x[1]):
        print(f"  {name}: {imp:.3f}")

    return clf


# ─────────────────────────────────────────────
# 5. Klasifikacija i vektorizacija
# ─────────────────────────────────────────────

def klasifikuj_i_vektorizuj(clf, features, transform, h, w):
    """
    Klasifikuje sve piksele snimka i konvertuje susedne piksele klase 'deponija'
    u vektorske poligone koristeći rasterio.features.shapes().

    Ovo je standardni raster→vektor korak u GIS obradi satelitskih snimaka:
    - Svaki blok susednih piksela iste klase postaje jedan poligon
    - shapes() koristi GeoTransform za ispravne geografske koordinate poligona

    Closing spaja susedne fragmente jedne deponije u kompaktan poligon, a
    uklanjanje malih povezanih komponenti briše izolovan šum bez gubljenja
    malih (ali stvarnih) deponija — binary_opening bi to uradio jer zahteva
    pun 3×3 blok, što briše i legitimne male detekcije.

    Klasa 'deponija' je veoma retka (~0.02% piksela), pa čak i mali procenat
    pogrešno klasifikovanih piksela na celom snimku (4M piksela) stvara stotine
    lažnih detekcija razbacanih po vegetaciji — standardni predict() koristi
    prag 0.5 što je previše permisivno. Visok prag verovatnoće (0.9) drastično
    smanjuje lažne pozitive, uz manji gubitak tačnih detekcija.
    """
    proba = clf.predict_proba(features)[:, list(clf.classes_).index(1)]
    predictions = (proba > 0.9).astype(np.uint8).reshape(h, w)
    predictions = binary_closing(predictions, structure=np.ones((3, 3))).astype(np.uint8)

    labeled, n_labels = label(predictions)
    if n_labels > 0:
        sizes = ndi_sum(predictions, labeled, range(1, n_labels + 1))
        sum_labels = np.where(sizes < 3)[0] + 1   # ukloni komponente manje od 3 piksela (šum)
        predictions[np.isin(labeled, sum_labels)] = 0

    n_dep = predictions.sum()
    print(f"Klasifikovano {n_dep} piksela kao deponija ({n_dep/(h*w)*100:.1f}% snimka)")

    geometries = []
    # shapes() vraća (GeoJSON rečnik, vrednost piksela) parove
    for geom_dict, value in shapes(predictions, connectivity=4, transform=transform):
        if value == 1:
            geom = shape(geom_dict)
            # Filtriraj rubne artefakte vektorizacije (< pola piksela ~ 100m rezolucije)
            area_m2 = geom.area * (111320 ** 2)
            if area_m2 > 5000:
                geometries.append(geom)

    print(f"Vektorizovano {len(geometries)} poligona deponija")
    return geometries, predictions


# ─────────────────────────────────────────────
# 6. Upis u PostGIS
# ─────────────────────────────────────────────

def upisi_u_bazu(geometries):
    """
    Upisuje vektorske poligone ML detektovanih deponija u PostGIS tabelu deponije.
    Geometrija se upisuje direktno iz Shapely WKT — nema buffer aproksimacije,
    već stvarni oblik detektovanog poligona iz raster→vektor konverzije.
    Svaka deponija se vezuje za geografski najbližu lokaciju (PostGIS <-> operator).
    """
    if not geometries:
        print("Nema geometrija za upis.")
        return

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) FROM lokacije")
    if cursor.fetchone()[0] == 0:
        print("Nema lokacija u bazi!")
        cursor.close()
        conn.close()
        return

    tipovi = ['komunalni', 'gradjevinski', 'mesoviti', 'industrijski']
    count  = 0

    for i, geom in enumerate(geometries[:20]):
        wkt        = geom.wkt
        area       = geom.area * (111320 ** 2)  # stepeni² → m² (aproksimacija)
        centroid   = geom.centroid

        cursor.execute("""
            SELECT id FROM lokacije
            ORDER BY geom <-> ST_SetSRID(ST_MakePoint(%s, %s), 4326)
            LIMIT 1
        """, (centroid.x, centroid.y))
        lok_id = cursor.fetchone()[0]

        cursor.execute("""
            INSERT INTO deponije (naziv, povrsina_m2, tip_otpada, status,
                datum_otkrivanja, lokacija_id, geom)
            VALUES (%s, %s, %s, %s, NOW(), %s, ST_GeomFromText(%s, 4326))
        """, (f"ML Deponija {i+1}", round(area, 1),
              random.choice(tipovi), 'detektovana', lok_id, wkt))
        count += 1

    conn.commit()
    cursor.close()
    conn.close()
    print(f"Upisano {count} ML deponija u PostGIS bazu.")


# ─────────────────────────────────────────────
# 7. Prostorne analize
# ─────────────────────────────────────────────

def prostorne_analize(geometries):
    """
    5 prostornih analiza nad ML detektovanim deponijama:
    1. Ukupna površina svih detektovanih deponija
    2. Union — spajanje poligona u jednu geometriju
    3. Buffer 500m — zona uticaja oko deponija
    4. Sjoin — koje lokacije iz baze su u blizini deponija
    5. Distribucija veličina (min, max, prosek)
    """
    if not geometries:
        print("Nema ML deponija za analizu.")
        return

    gdf_ml  = gpd.GeoDataFrame(
        {'naziv': [f'ML Deponija {i+1}' for i in range(len(geometries))]},
        geometry=geometries, crs='EPSG:4326'
    )
    gdf_utm = gdf_ml.to_crs('EPSG:32634')

    print("\n=== PROSTORNE ANALIZE ML REZULTATA ===")
    print(f"1. Detektovano deponija: {len(gdf_ml)}")
    print(f"   Ukupna površina: {gdf_utm.geometry.area.sum():.0f} m²")

    union_area = gdf_utm.geometry.union_all().area
    print(f"2. Union svih poligona: {union_area:.0f} m²")

    buf = gdf_utm.copy()
    buf['geometry'] = gdf_utm.geometry.buffer(500)
    print(f"3. Buffer 500m — zona uticaja: {buf.geometry.union_all().area:.0f} m²")

    conn = get_connection()
    lok_df = pd.read_sql(
        "SELECT id, naziv, ST_X(geom) as lon, ST_Y(geom) as lat FROM lokacije", conn
    )
    conn.close()

    geom_lok = [Point(r['lon'], r['lat']) for _, r in lok_df.iterrows()]
    gdf_lok  = gpd.GeoDataFrame(lok_df, geometry=geom_lok, crs='EPSG:4326').to_crs('EPSG:32634')

    overlap = gpd.sjoin(gdf_lok, buf[['geometry']], how='inner', predicate='intersects')
    print(f"4. Lokacije unutar 500m od ML deponija: {len(overlap)}")

    areas = gdf_utm.geometry.area
    print(f"5. Veličine — min: {areas.min():.0f} m², max: {areas.max():.0f} m², prosek: {areas.mean():.0f} m²")


# ─────────────────────────────────────────────
# 8. Mapa rezultata
# ─────────────────────────────────────────────

def kreiraj_mapu(geometries):
    """
    Kreira folium mapu sa slojem ML detektovanih deponija prikazanih kao
    stvarni vektorski poligoni (ne aproksimativni kružni markeri).
    Esri satelitska podloga za vizuelni kontekst.
    """
    mapa = folium.Map()
    mapa.fit_bounds([[VOJV_MINY, VOJV_MINX], [VOJV_MAXY, VOJV_MAXX]])

    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Esri World Imagery', name='Satelitska podloga',
        overlay=False, control=True
    ).add_to(mapa)

    fg = folium.FeatureGroup(name='ML Detektovane deponije', show=True)
    for i, geom in enumerate(geometries):
        if geom.geom_type == 'Polygon':
            coords = [[y, x] for x, y in geom.exterior.coords]
            area   = geom.area * (111320 ** 2)
            popup_html = f"<b>ML Deponija {i+1}</b><br>Površina: {area:.0f} m²"
            folium.Polygon(
                locations=coords,
                popup=popup_html,
                color='red', fill=True, fillColor='red', fillOpacity=0.5, weight=2
            ).add_to(fg)
            # Marker na centroidu — poligon sam po sebi nije uvek dovoljno uočljiv
            centroid = geom.centroid
            folium.Marker(
                location=[centroid.y, centroid.x],
                popup=popup_html,
                tooltip=f"ML Deponija {i+1}",
                icon=folium.Icon(color='red', icon='warning-sign', prefix='glyphicon')
            ).add_to(fg)
    fg.add_to(mapa)

    folium.LayerControl().add_to(mapa)
    out = os.path.join(os.path.dirname(__file__), 'mapa_ml_rezultati.html')
    mapa.save(out)
    print(f"Mapa sačuvana: {out}")


# ─────────────────────────────────────────────
# MAIN — kompletan ML pipeline
# ─────────────────────────────────────────────

if __name__ == "__main__":
    print("=== ML DETEKCIJA DIVLJIH DEPONIJA IZ SATELITSKOG SNIMKA ===\n")

    print("Korak 1: Kreiranje satelitskog snimka (GeoTIFF)...")
    landfill_masks = kreiraj_snimak()

    print("\nKorak 2: Ekstrakcija spektralnih obeležja iz snimka...")
    features, ndvi, transform, crs, h, w = ekstrahuj_karakteristike()

    print("\nKorak 3: Kreiranje trening labela...")
    labels = kreiraj_labele(landfill_masks, h, w)

    print("\nKorak 4: Treniranje Random Forest modela na pikselima...")
    clf = treniraj_model(features, labels)

    print("\nKorak 5: Klasifikacija snimka i vektorizacija...")
    geometries, predictions = klasifikuj_i_vektorizuj(clf, features, transform, h, w)

    print("\nKorak 6: Upis u PostGIS bazu...")
    upisi_u_bazu(geometries)

    print("\nKorak 7: Prostorne analize...")
    prostorne_analize(geometries)

    print("\nKorak 8: Kreiranje mape...")
    kreiraj_mapu(geometries)

    print("\n=== DEO 3 ZAVRSEN! ===")
