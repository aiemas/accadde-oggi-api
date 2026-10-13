
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import local
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.laseriea.org"
NAPOLISSIMO = "https://www.napolissimo.net/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/131.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://www.napolissimo.net/",
}
thread_data = local()
LAVORATORI = 6

MESI = {
    "gen": 1, "gennaio": 1,
    "feb": 2, "febbraio": 2,
    "mar": 3, "marzo": 3,
    "apr": 4, "aprile": 4,
    "mag": 5, "maggio": 5,
    "giu": 6, "giugno": 6,
    "lug": 7, "luglio": 7,
    "ago": 8, "agosto": 8,
    "set": 9, "sett": 9, "settembre": 9,
    "ott": 10, "ottobre": 10,
    "nov": 11, "novembre": 11,
    "dic": 12, "dicembre": 12,
}


def sessione():
    if not hasattr(thread_data, "session"):
        thread_data.session = requests.Session()
        thread_data.session.headers.update(HEADERS)
    return thread_data.session


def scarica(url):
    r = sessione().get(url, timeout=25)
    r.raise_for_status()
    return BeautifulSoup(r.text, "html.parser")


def testo(elemento):
    return elemento.get_text(" ", strip=True) if elemento else ""


def normalizza(s):
    s = unicodedata.normalize("NFKD", s.casefold())
    s = "".join(c for c in s if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]", "", s)


def stessa_squadra(cercata, nome):
    a = normalizza(cercata)
    b = normalizza(nome)
    return bool(a and b and (a == b or a in b or b in a))


def data_giorno_mese(s):
    s = s.strip().replace(",", " ")
    s = re.sub(r"\s+", " ", s)

    # Formato 03/12/2025 oppure 03-12-2025
    m = re.search(r"\b(\d{1,2})[/.-](\d{1,2})[/.-](\d{2,4})\b", s)
    if m:
        return int(m.group(1)), int(m.group(2))

    # Formato 3 dicembre 2025, 10 feb 2026, 18 set. 2025
    m = re.search(
        r"\b(\d{1,2})\s+([a-zàèéìòù.]+)\s+\d{4}\b",
        s, re.IGNORECASE
    )
    if m:
        mese = m.group(2).lower().rstrip(".")
        mese = MESI.get(mese)
        if mese:
            return int(m.group(1)), mese

    # Formato storico 26-12-35
    m = re.search(r"\b(\d{1,2})-(\d{1,2})-(\d{2})\b", s)
    if m:
        return int(m.group(1)), int(m.group(2))

    return None


def trova_stagioni(squadra):
    slug = normalizza(squadra)
    url = f"{BASE}/squadra/{slug}/"
    print(f"\nApro: {url}")

    soup = scarica(url)
    stagioni = set()

    for a in soup.select("a[href]"):
        href = urljoin(url, a["href"])
        if re.search(r"/serie-a-\d{4}-\d{4}/?$", href):
            stagioni.add(href.rstrip("/") + "/")

    return sorted(stagioni, reverse=True)


def trova_giornate(stagione):
    soup = scarica(stagione)
    giornate = set()

    for a in soup.select("a[href]"):
        href = urljoin(stagione, a["href"])
        if re.search(
            r"/serie-a-\d{4}-\d{4}/giornata-\d+/?$", href
        ):
            giornate.add(href.rstrip("/") + "/")

    return giornate


def leggi_giornata(url, squadra, giorno, mese):
    soup = scarica(url)
    trovate = []

    for riga in soup.select("tbody tr"):
        data = testo(riga.select_one(".match-date"))
        casa = testo(riga.select_one(".team-home a"))
        risultato = testo(riga.select_one(".score"))
        trasferta = testo(riga.select_one(".team-away a"))

        if not all((data, casa, risultato, trasferta)):
            continue

        try:
            g, m, _ = map(int, data.split("/"))
        except ValueError:
            continue

        if g != giorno or m != mese:
            continue

        if not (
            stessa_squadra(squadra, casa)
            or stessa_squadra(squadra, trasferta)
        ):
            continue

        trovate.append({
            "data": data,
            "casa": casa,
            "risultato": risultato,
            "trasferta": trasferta,
            "competizione": "Serie A",
            "url": url,
        })

    return trovate



def pagine_napolissimo():
    """
    Cerca gli archivi delle coppe esplorando anche i link intermedi.
    Include direttamente l'archivio noto della Coppa Italia.
    """
    iniziali = [
        NAPOLISSIMO,
        "https://www.napolissimo.net/Coppa_Italia_2025-2026.html",
    ]

    da_visitare = [(url, 0) for url in iniziali]
    visitate = set()
    pagine = {iniziali[1]}
    massimo_pagine = 100
    profondita_massima = 3

    while da_visitare and len(visitate) < massimo_pagine:
        url, livello = da_visitare.pop(0)
        url = url.split("#")[0]

        if url in visitate:
            continue

        visitate.add(url)

        try:
            soup = scarica(url)
        except Exception as e:
            print(f"\nPagina non accessibile: {url} ({e})")
            continue

        for a in soup.select("a[href]"):
            href = urljoin(url, a["href"]).split("#")[0]
            parti = urlparse(href)

            if parti.netloc.lower() not in {
                "napolissimo.net",
                "www.napolissimo.net",
            }:
                continue

            nome = (
                a.get("href", "") + " " + testo(a)
            ).casefold()
            percorso = parti.path.casefold()

            # Riconosce gli archivi delle competizioni.
            if (
                "coppa_italia" in percorso
                or "coppa-italia" in percorso
                or "champions" in percorso
                or "champion" in nome
                or "coppa italia" in nome
            ):
                pagine.add(href)

            # Esplora anche le pagine intermedie dei menu.
            if (
                livello < profondita_massima
                and href not in visitate
                and not any(href == u for u, _ in da_visitare)
            ):
                da_visitare.append((href, livello + 1))

    return sorted(pagine)

def estrai_partite_napolissimo(url, giorno, mese):
    soup = scarica(url)

    print("DEBUG URL:", url)
    print("DEBUG TITOLO:", soup.title.get_text(" ", strip=True) if soup.title else "nessun titolo")
    trovate = []

    if "champions" in url.lower():
        competizione = "Champions League"
    elif "coppa" in url.lower():
        competizione = "Coppa Italia"
    else:
        return []

    for riga in soup.select("tr"):
        celle = [testo(c) for c in riga.find_all(["td", "th"])]
        celle = [c for c in celle if c]

        if len(celle) < 3:
            continue

        intera_riga = " | ".join(celle)
        dm = data_giorno_mese(intera_riga)

        if not dm or dm != (giorno, mese):
            continue

        # Cerca una cella che contenga entrambe le squadre.
        partita = None
        indice_partita = -1

        for i, cella in enumerate(celle):
            if re.search(r"\s[-–]\s", cella):
                # Evita celle che siano soltanto un punteggio.
                if not re.fullmatch(
                    r"\s*\d+\s*[-–]\s*\d+.*", cella
                ):
                    partita = cella
                    indice_partita = i
                    break

        if not partita:
            continue

        # Estrae il punteggio dalla cella successiva o dalla stessa riga.
        risultato = ""
        for cella in celle[indice_partita + 1:]:
            m = re.search(
                r"\b(\d+)\s*[-–]\s*(\d+)"
                r"(?:\s*\(([^)]*)\))?",
                cella
            )
            if m:
                risultato = f"{m.group(1)}-{m.group(2)}"
                if m.group(3):
                    risultato += f" ({m.group(3).strip()})"
                break

        if not risultato:
            continue

        squadre = re.split(r"\s+[-–]\s+", partita, maxsplit=1)
        if len(squadre) != 2:
            continue

        casa, trasferta = [s.strip() for s in squadre]

        # Le pagine di Napolissimo archiviano le partite del Napoli.
        if not (
            stessa_squadra("Napoli", casa)
            or stessa_squadra("Napoli", trasferta)
        ):
            continue

        # La data viene presa dalla riga, conservando la forma originale.
        data_originale = ""
        for cella in celle:
            if data_giorno_mese(cella) == (giorno, mese):
                data_originale = cella
                break

        trovate.append({
            "data": data_originale or f"{giorno:02d}/{mese:02d}",
            "casa": casa,
            "risultato": risultato,
            "trasferta": trasferta,
            "competizione": competizione,
            "url": url,
        })

    return trovate


def cerca():
    squadra = input("Squadra: ").strip()
    if not squadra:
        return

    try:
        giorno = int(input("Giorno (1-31): "))
        mese = int(input("Mese (1-12): "))
        if not 1 <= giorno <= 31 or not 1 <= mese <= 12:
            raise ValueError
    except ValueError:
        print("Giorno o mese non valido.")
        return

    print("\nQuali competizioni vuoi cercare?")
    print("1 - Solo Serie A")
    print("2 - Serie A + Coppa Italia")
    print("3 - Serie A + Champions League")
    print("4 - Tutte e tre")

    scelta = input("Scelta (1-4): ").strip()
    if scelta not in {"1", "2", "3", "4"}:
        print("Scelta non valida.")
        return

    cerca_coppa = scelta in {"2", "4"}
    cerca_champions = scelta in {"3", "4"}
    risultati = []
    errori = 0

    # SERIE A: conserva il metodo originale.
    try:
        stagioni = trova_stagioni(squadra)
        print(f"\nStagioni Serie A trovate: {len(stagioni)}")

        giornate = set()
        with ThreadPoolExecutor(max_workers=LAVORATORI) as pool:
            lavori = {pool.submit(trova_giornate, s): s for s in stagioni}

            for i, futuro in enumerate(as_completed(lavori), 1):
                try:
                    giornate.update(futuro.result())
                except Exception as e:
                    errori += 1
                    print(f"\nErrore stagione: {e}")

                print(
                    f"Giornate individuate: {i}/{len(lavori)}",
                    end="\r", flush=True
                )

        print(f"\nGiornate Serie A da controllare: {len(giornate)}")

        with ThreadPoolExecutor(max_workers=LAVORATORI) as pool:
            lavori = {
                pool.submit(
                    leggi_giornata, url, squadra, giorno, mese
                ): url
                for url in giornate
            }

            for i, futuro in enumerate(as_completed(lavori), 1):
                try:
                    risultati.extend(futuro.result())
                except Exception:
                    errori += 1

                if i % 20 == 0 or i == len(lavori):
                    print(f"Serie A: {i}/{len(lavori)} giornate")

    except Exception as e:
        errori += 1
        print(f"\nErrore durante la ricerca Serie A: {e}")

    # COPPA ITALIA E CHAMPIONS: archivio Napoli.
    if cerca_coppa or cerca_champions:
        if not stessa_squadra(squadra, "Napoli"):
            print(
                "\nNota: le pagine delle coppe su Napolissimo "
                "riguardano le partite del Napoli. "
                "Le coppe verranno quindi saltate per questa squadra."
            )
        else:
            print("\nCerco le pagine delle coppe su Napolissimo...")
            try:
                pagine = pagine_napolissimo()
                if cerca_coppa:
                    pagine = [
                        u for u in pagine
                        if "coppa_italia_" in u.lower()
                        or "coppa italia" in u.lower()
                    ]
                else:
                    pagine = [
                        u for u in pagine
                        if "champions" in u.lower()
                    ]

                if cerca_coppa and cerca_champions:
                    pagine = pagine_napolissimo()
                    pagine = [
                        u for u in pagine
                        if (
                            "coppa_italia_" in u.lower()
                            or "coppa italia" in u.lower()
                            or "champions" in u.lower()
                        )
                    ]

                print(f"Pagine delle coppe individuate: {len(pagine)}")

                with ThreadPoolExecutor(max_workers=LAVORATORI) as pool:
                    lavori = {
                        pool.submit(
                            estrai_partite_napolissimo,
                            url, giorno, mese
                        ): url
                        for url in pagine
                    }

                    for i, futuro in enumerate(as_completed(lavori), 1):
                        try:
                            risultati.extend(futuro.result())
                        except Exception as e:
                            errori += 1
                            print(f"\nPagina non letta: {lavori[futuro]}")

                        if i % 10 == 0 or i == len(lavori):
                            print(f"Coppe: {i}/{len(lavori)} pagine")

            except Exception as e:
                errori += 1
                print(f"\nErrore durante la ricerca delle coppe: {e}")

    # Elimina duplicati.
    uniche = {}
    for p in risultati:
        chiave = (
            p["data"], p["casa"], p["risultato"],
            p["trasferta"], p["competizione"]
        )
        uniche[chiave] = p

    risultati = list(uniche.values())

    def chiave_data(p):
        dm = data_giorno_mese(p["data"])
        anno = re.search(r"\b(19|20)\d{2}\b", p["data"])
        return (
            int(anno.group()) if anno else 0,
            dm[1] if dm else 0,
            dm[0] if dm else 0
        )

    risultati.sort(key=chiave_data)

    print("\n" + "=" * 65)
    print(f"PARTITE DEL {giorno:02d}/{mese:02d} - {squadra.upper()}")
    print("=" * 65)

    if not risultati:
        print("Nessuna partita trovata nelle pagine scaricate.")
    else:
        for p in risultati:
            print(
                f'{p["data"]} | {p["competizione"]} | '
                f'{p["casa"]} {p["risultato"]} {p["trasferta"]}'
            )
            print(f'Fonte: {p["url"]}\n')

        print(f"Totale: {len(risultati)} partite")

    if errori:
        print(
            f"\nAttenzione: {errori} richieste fallite. "
            "I risultati potrebbero essere incompleti."
        )


if __name__ == "__main__":
    while True:
        cerca()
        if input("\nAltra ricerca? (s/n): ").strip().lower() != "s":
            break