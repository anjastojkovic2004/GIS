---

## Baza podataka

Baza podataka je hostovana na **Supabase** cloud platformi i koristi **PostgreSQL** sa **PostGIS** ekstenzijom koja omogućava skladištenje i obradu geografskih podataka (tačke, poligoni, linije).

### Šema baze

Baza se sastoji od 5 međusobno povezanih tabela:

#### `lokacije`
Čuva geografske lokacije na teritoriji Novog Sada. Svaka lokacija ima naziv, adresu, tip područja i geografsku koordinatu u obliku tačke (POINT geometrija).

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv lokacije |
| opstina | VARCHAR | Naziv opštine |
| adresa | VARCHAR | Adresa lokacije |
| tip_podrucja | VARCHAR | Tip područja (park, stambeno, industrijsko...) |
| geom | GEOMETRY(Point) | Geografska koordinata |

#### `kontejneri`
Evidencija kontejnera za otpad postavljenih na lokacijama u gradu. Prati tip kontejnera, kapacitet, stanje i datum postavljanja.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| tip | VARCHAR | Tip kontejnera (komunalni, reciklažni, podzemni) |
| kapacitet_litara | INTEGER | Kapacitet u litrima |
| stanje | VARCHAR | Trenutno stanje (dobro, oštećen, loše) |
| datum_postavljanja | DATE | Datum kada je kontejner postavljen |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |

#### `deponije`
Evidencija divljih deponija otkrivenih na teritoriji grada. Sadrži informacije o površini, tipu otpada, statusu sanacije i geografskom obliku deponije u obliku poligona.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv deponije |
| povrsina_m2 | FLOAT | Površina u kvadratnim metrima |
| tip_otpada | VARCHAR | Tip otpada (komunalni, građevinski, mešoviti) |
| status | VARCHAR | Status (aktivna, u sanaciji, sanirana) |
| datum_otkrivanja | DATE | Datum kada je deponija otkrivena |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |
| geom | GEOMETRY(Polygon) | Geografski oblik deponije |

#### `komunalna_preduzeca`
Evidencija komunalnih preduzeća zaduženih za upravljanje otpadom u određenim zonama grada.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| naziv | VARCHAR | Naziv preduzeća |
| kontakt_telefon | VARCHAR | Broj telefona |
| email | VARCHAR | Email adresa |
| zona_pokrivenosti | VARCHAR | Zona kojom preduzeće upravlja |
| lokacija_id | INTEGER FK | Veza sa tabelom lokacije |

#### `inspekcije`
Evidencija inspekcijskih pregleda divljih deponija. Beleži datum pregleda, nalaz, preporuku i ime inspektora.

| Kolona | Tip | Opis |
|---|---|---|
| id | SERIAL PK | Jedinstveni identifikator |
| datum | DATE | Datum inspekcije |
| nalaz | TEXT | Opis nalaza na terenu |
| preporuka | TEXT | Preporuka inspektora |
| inspektor | VARCHAR | Ime i prezime inspektora |
| deponija_id | INTEGER FK | Veza sa tabelom deponije |

---

## Deo 1 – Python SQL

### Šta je urađeno

Kreirana je PostgreSQL baza podataka sa PostGIS ekstenzijom na Supabase cloud platformi. Konekcija na bazu ostvarena je iz Pythona korišćenjem biblioteke `psycopg2`.

Kreirano je 5 tabela sa primarnim i stranim ključevima koji međusobno povezuju tabele. U svaku tabelu ručno je uneto najmanje 5 redova podataka koji se odnose na lokacije, kontejnere, deponije, komunalna preduzeća i inspekcije na teritoriji Novog Sada.

Implementirane su CRUD operacije:
- **CREATE** – dodavanje novih kontejnera i deponija
- **READ** – čitanje svih podataka u pandas DataFrame
- **UPDATE** – ažuriranje stanja kontejnera
- **DELETE** – brisanje zapisa iz baze

Napisano je 6 SQL upita koji koriste JOIN spoj dve ili više tabela sa WHERE filterima:
1. Kontejneri sa nazivima lokacija
2. Samo aktivne deponije sa lokacijama
3. Inspekcije sa nazivima deponija sortirane po datumu
4. Komunalna preduzeća sa lokacijama i tipom područja
5. Oštećeni i loši kontejneri filtrirani po stanju
6. Deponije, inspekcije i lokacije spojene u jednom upitu sa filterom po površini

