---

## Pokretanje aplikacije

### U terminalu:
```bash
cd app
streamlit run app.py
```

### U browser-u:
Automatski će se otvoriti na `http://localhost:8501`

Ako ne, ručno otvori: http://localhost:8501

---

## Stranica Dashboard

### Šta je ovo?
Početna stranica sa pregledom važnih informacija o sistemu.

### Šta vidiš?

#### 📊 Metrike (gornji deo)
Tri broja koji pokazuju:
- **📍 Lokacije** — Koliko lokacija je registrovano
- **🗑️ Kontejneri** — Koliko kontejnera postoji u sistemu
- **⚠️ Deponije** — Koliko deponija (originalnih + ML detektovanih)

#### 📈 Grafikoni (srednji deo)

**Kontejneri po stanju:**
- Prikazuje koliko je kontejnera u **dobrom**, **oštećenom** ili **lošem** stanju
- Koristi se za planiranje održavanja i popravki

**Deponije po statusu:**
- Prikazuje koliko je deponija **aktivnih**, **u sanaciji** ili **saniranih**
- Koristi se za praćenje statusa sanacije

#### 🗺️ Mapa lokacija (donji deo)
- Interaktivna mapa Novog Sada
- Plave tačke predstavljaju lokacije
- Klikni na marker da vidiš naziv lokacije
- Koristi `+` i `-` za zumiranje

### Kako koristiti?
1. Redovne preglede — Svaki dan vrati se na Dashboard
2. Analiza trendova — Poredi grafikone tokom vremena
3. Brz pregled — Provjeri broj svih elemenata sistema

---

## Stranica Lokacije

### Šta je ovo?
Stranica za upravljanje lokacijama gde se nalaze kontejneri i deponije.

### Gornji deo — Sve lokacije

**Tabela sa kolonama:**
- **ID** — Jedinstveni broj (automatski)
- **Naziv** — Naziv lokacije (npr. "Liman park")
- **Opština** — Opština (npr. "Novi Sad")
- **Adresa** — Puна adresa
- **Tip područja** — park, stambeno, industrijsko, itd.

### Donji deo — Dodaj novu lokaciju

#### Korak po korak:

1. **Naziv lokacije**
   - Upiši jasан naziv
   - Primeri: "Liman park", "Grbavica", "Sajmiste"

2. **Opština**
   - Upiši opštinu gde je lokacija
   - Za Novi Sad: "Novi Sad"

3. **Adresa**
   - Upiši detaljnu adresu
   - Primeri: "Bulevar cara Lazara", "Ulica Temerinska"

4. **Tip područja**
   - Klikni padajuću listu
   - Opcije:
     - **park** — Javni park
     - **stambeno** — Stambeno područje
     - **industrijsko** — Industrijska zona
     - **prigradsko** — Prigradsko područje
     - **druge** — Ostalo

5. **Geografska širina (lat)**
   - Upiši decimalni broj (npr. 45.2552)
   - **Gde pronaći:** Google Maps → Desni klik → "Šta je ovde?" → Kopiraj prvi broj

6. **Geografska dužina (lon)**
   - Upiši decimalni broj (npr. 19.8362)
   - **Gde pronaći:** Google Maps → Desni klik → "Šta je ovde?" → Kopiraj drugi broj

7. Klikni **"Spremi lokaciju"**
   - Trebala bi poruka: "✅ Lokacija je uspešno dodata!"

### Primeri lokacija:

| Naziv | Adresa | Lat | Lon |
|-------|--------|-----|-----|
| Liman park | Bulevar cara Lazara | 45.2396 | 19.8335 |
| Grbavica | Ulica Zarka Zrenjanina | 45.2431 | 19.8456 |
| Sajmiste | Hajduk Veljkova | 45.2678 | 19.8123 |

---

## Stranica Kontejneri

### Šta je ovo?
Stranica za upravljanje kontejnerima za otpad.

### Gornji deo — Svi kontejneri

**Tabela sa kolonama:**
- **ID** — Jedinstveni broj
- **Tip** — komunalni, reciklažni, podzemni
- **Kapacitet (litara)** — Veličina kontejnera
- **Stanje** — dobro, oštećen, loše
- **Lokacija** — Gde se nalazi kontejner

### Donji deo — Dodaj novi kontejner

#### Korak po korak:

1. **Tip kontejnera**
   - Klikni padajuću listu
   - Opcije:
     - **komunalni** — Za mešoviti otpad
     - **reciklažni** — Za razvrstan otpad
     - **podzemni** — Ukopani kontejner

2. **Kapacitet (litara)**
   - Upiši broj liitara
   - Tipični kapaciteti: 1100, 2500, 5000

3. **Stanje**
   - Klikni padajuću listu
   - Opcije:
     - **dobro** — Dobar tehn. stanj
     - **oštećen** — Ima lakšu oštećenja
     - **loše** — Teška oštećenja, trebalo bi zamenu

4. **Lokacija**
   - Klikni padajuću listu
   - Odaberi lokaciju koju si prethodno kreirao

5. Klikni **"Spremi kontejner"**
   - Trebala bi poruka: "✅ Kontejner je uspešno dodat!"

### Napomena
Prvo trebas da kreiram lokaciju na stranici "Lokacije" pre nego što dodaš kontejner!

---

## Stranica Deponije

### Šta je ovo?
Stranica za upravljanje divljim i registrovanim deponijama.

### Gornji deo — Sve deponije

**Tabela sa kolonama:**
- **ID** — Jedinstveni broj
- **Naziv** — Naziv deponije
- **Površina (m²)** — Veličina u kvadratnim metrima
- **Tip otpada** — Vrsta otpada
- **Status** — aktivna, u sanaciji, sanirana
- **Lokacija** — Gde se nalazi

### Donji deo — Prijavi novu deponiju

#### Korak po korak:

1. **Naziv deponije**
   - Upiši jasan naziv
   - Primeri: "Deponija Klisa", "Divlja deponija Detelinara"

2. **Površina (m²)**
   - Upiši površinu u kvadratnim metrima
   - Može se meriti na Google Maps ili na terenu
   - Primer: 500 m²

3. **Tip otpada**
   - Klikni padajuću listu
   - Opcije:
     - **komunalni** — Domaćinski otpad
     - **građevinski** — Gradevinski materijal
     - **mešoviti** — Mešoviti otpad
     - **industrijski** — Industrijski otpad

4. **Status**
   - Klikni padajuću listu
   - Opcije:
     - **aktivna** — Trenutno se koristi/mulja
     - **u sanaciji** — U toku je čišćenje
     - **sanirana** — Čišćenje je završeno

5. **Lokacija**
   - Klikni padajuću listu
   - Odaberi najbližu lokaciju

6. Klikni **"Spremi deponiju"**
   - Trebala bi poruka: "✅ Deponija je uspešno dodata!"
   - Sistema će automatski kreirati geometriju (poligon) oko lokacije

### Kako ažurirati status sanacije?
Trenutno u aplikaciji ne možeš direktno ažurirati, ali to možeš uraditi:
1. Obriši staru deponiju
2. Kreiraj novu sa novim statusom

---

## Stranica ML Detekcija

### Šta je ovo?
Stranica sa ML detektovanim divljim deponijama.

### Šta je ML detekcija?
Algoritmi mašinskog učenja analiziraju satelitske snimke i detektuju nove/neznane deponije.

### Šta vidiš?

**Tabela sa ML detektovanim deponijama:**
- **Naziv** — Automatski "ML Deponija #1", itd.
- **Površina (m²)** — Detektovana površina
- **Tip otpada** — Procenjena vrsta
- **Status** — Uvek "detektovana"
- **Lokacija** — Najbliža registrovana lokacija

### Kako koristiti?

1. **Pregledi rezultate**
   - Vidi koja je detektovana deponija
   - Provjeri sigurnost detekcije (confidence score)

2. **Poseti lokaciju**
   - Odi na adresu lokacije
   - Provjeri da li je deponija stvarno tu

3. **Kreiraj zvanično deponiju**
   - Ako je potvrđena — kreiraj je na stranici "Deponije"
   - Ako nije — ignoriraj

### Napomena
ML detekcija je simulacija. U stvarnoj aplikaciji koristili bi satelitske snimke (Sentinel-2) ili dron snimke.

---

## Stranica Spatial Analiza

### Šta je ovo?
Stranica za geografske analize i izračunavanja.

### Šta je spatial analiza?
Spatial analiza omogućava geografske operacije kao što su:
- Distanca između lokacija
- Buffer zone oko lokacija
- Pronalaženje preklapanja
- Pronalaženje lokacija u određenoj zoni

### Gornji deo — Distanca između lokacija

#### Kako koristiti:

1. **Prva lokacija**
   - Klikni padajuću listu
   - Odaberi prvu lokaciju

2. **Druga lokacija**
   - Klikni padajuću listu
   - Odaberi drugu lokaciju (različitu od prve)

3. Klikni **"Izračunaj distancu"**
   - Trebala bi poruka sa distancom u metrima
   - Primeri: "Distanca: 1026 metara"

### Šta se racunla?
Sisteme koristi **haversine distancu** — matematička formula za distancu između dve tačke na kugli (Zemlji).

### Primena:
- **Logistika** — Optimizacija ruta za prikupljanje
- **Planiranje** — Određivanje lokacija novih kontejnera
- **Analiza** — Pronalaženje obrasca u distribuciji

---

## Česti problemi

### Problem: "Nema ML detektovanih deponija"
**Rešenje:** 
- ML detekcija je simulacija
- Deponije se kreiraju kada pokreneš Python skriptu `deo3_ml/ml_detekcija.py`
- Svi ML detektovani su već u bazi (sa "ML" u nazivu)

### Problem: "Greška pri dodavanju lokacije"
**Rešenje:**
- Popuni sva polja
- Provjeri da su koordinate (lat/lon) validne
- Lat treba da bude između -90 i 90
- Lon treba da bude između -180 i 180

### Problem: "Nema lokacija u padajućoj listi"
**Rešenje:**
- Prvo kreiraj lokaciju na stranici "Lokacije"
- Čekaj da se aplikacija osvezi

### Problem: "Mapa se ne prikazuje"
**Rešenje:**
- Čekaj nekoliko sekundi da se mapa učita
- Provjeri da li imaš internet konekciju
- Osvezi stranicu (F5)

### Problem: "Konekcija na bazu neće"
**Rešenje:**
- Provjeri .env fajl — da li je DB_URL ispravan
- Provjeri da li imaš internet
- Provjeri da li je Supabase server dostupan
- Kontaktiraj administratora baze

### Problem: "Aplikacija je spora"
**Rešenje:**
- To je normalno pri prvom učitavanju
- Čekaj da se sve učita
- Ako je previše spora — provjeri internet konekciju

---

## Kontakt i Podrška

**Ako imaš problema:**
1. Provjeri [Česti problemi](#česti-problemi)
2. Kontaktiraj administratora
3. Kreiraj issue na GitHub-u


