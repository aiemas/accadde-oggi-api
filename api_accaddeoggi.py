
from flask import Flask, jsonify, request
import os
import re
import subprocess
import sys

app = Flask(__name__)

CARTELLA = os.path.dirname(os.path.abspath(__file__))
SCRIPT = os.path.join(CARTELLA, "mirkonuovo.py")


@app.route("/")
def home():
    return jsonify({
        "app": "Accadde Oggi",
        "stato": "API funzionante"
    })


@app.route("/cerca")
def cerca():
    giorno = request.args.get("giorno", type=int)
    mese = request.args.get("mese", type=int)
    squadra = request.args.get("squadra", "Napoli").strip()
    scelta = request.args.get("scelta", "4").strip()

    if not squadra:
        return jsonify({"errore": "Inserisci una squadra."}), 400

    if giorno is None or mese is None or mese not in range(1, 13):
        return jsonify({"errore": "Giorno o mese non valido."}), 400

    giorni_per_mese = [
        31, 29, 31, 30, 31, 30,
        31, 31, 30, 31, 30, 31
    ]

    if giorno not in range(1, giorni_per_mese[mese - 1] + 1):
        return jsonify({"errore": "Giorno non valido."}), 400

    if scelta not in {"1", "2", "3", "4"}:
        return jsonify({"errore": "Scelta competizioni non valida."}), 400

    if not os.path.isfile(SCRIPT):
        return jsonify({
            "errore": "Non trovo mirkonuovo.py nella cartella dell'API."
        }), 500

    dati = f"{squadra}\n{giorno}\n{mese}\n{scelta}\nn\n"

    try:
        processo = subprocess.run(
            [sys.executable, "-u", SCRIPT],
            input=dati,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            errors="replace",
            cwd=CARTELLA,
            timeout=900
        )

        testo_output = processo.stdout or ""
        testo_errori = processo.stderr or ""

        if processo.returncode != 0:
            return jsonify({
                "errore": "Il motore di ricerca ha restituito un errore.",
                "dettagli": testo_errori[-3000:]
            }), 500

        
        posizione = testo_output.rfind("PARTITE DEL")

        if posizione >= 0:
            rapporto = testo_output[posizione:]
        else:
            rapporto = testo_output[-5000:]

        rapporto = rapporto.split("\nAltra ricerca?")[0]

        return jsonify({
            "giorno": f"{giorno:02d}/{mese:02d}",
            "squadra": squadra,
            "risultati": rapporto.strip(),
            "stato": "Ricerca completata"
        })

    except subprocess.TimeoutExpired:
        return jsonify({
            "errore": "La ricerca ha superato il limite di 15 minuti."
        }), 504

    except Exception as e:
        return jsonify({
            "errore": str(e)
        }), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)