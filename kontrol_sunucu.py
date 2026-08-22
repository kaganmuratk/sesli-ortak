"""Sesli Ortak - kucuk kontrol paneli.
Iki bagimsiz anahtar var: buyuk daire mikrofon dinlemesini (tetikleyici.py)
ac/kapatir, kucuk anahtar ise cevaplarin sesli okunup okunmayacagini
(.sesli_mod_acik bayragi) belirler. Ikisi istenen herhangi bir kombinasyonda
kullanilabilir. Yaziya cevirme islerine hic karismiyor, o Claude Code'un
native /voice'una ait."""

import json
import signal
import subprocess
import sys
from pathlib import Path

from flask import Flask, jsonify, render_template

app = Flask(__name__)

HERE = Path(__file__).parent
DURUM_DOSYASI = HERE / ".tetikleyici_durum.json"
SESLI_MOD_BAYRAGI = HERE / ".sesli_mod_acik"
PYTHON = HERE / ".venv" / "bin" / "python3"

_surec: subprocess.Popen | None = None


def _calisiyor_mu() -> bool:
    global _surec
    return _surec is not None and _surec.poll() is None


@app.route("/")
def anasayfa():
    return render_template("index.html")


@app.route("/durum")
def durum():
    aktif = _calisiyor_mu()
    konusuyor = False
    if aktif and DURUM_DOSYASI.exists():
        try:
            konusuyor = json.loads(DURUM_DOSYASI.read_text()).get("durum") == "konusuyor"
        except Exception:
            pass
    return jsonify({"aktif": aktif, "konusuyor": konusuyor, "sesli_acik": SESLI_MOD_BAYRAGI.exists()})


@app.route("/degistir", methods=["POST"])
def degistir():
    global _surec
    if _calisiyor_mu():
        _surec.send_signal(signal.SIGTERM)
        _surec.wait(timeout=3)
        _surec = None
        DURUM_DOSYASI.unlink(missing_ok=True)
    else:
        _surec = subprocess.Popen(
            [str(PYTHON), str(HERE / "tetikleyici.py")],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=open(HERE / "tetikleyici.log", "a"),
        )
    return jsonify({"aktif": _calisiyor_mu()})


@app.route("/sesli_degistir", methods=["POST"])
def sesli_degistir():
    if SESLI_MOD_BAYRAGI.exists():
        SESLI_MOD_BAYRAGI.unlink()
    else:
        SESLI_MOD_BAYRAGI.touch()
    return jsonify({"sesli_acik": SESLI_MOD_BAYRAGI.exists()})


@app.route("/kes", methods=["POST"])
def kes():
    # o an calan TTS sesini (paplay) aninda durdurur - konusmaci ayrimiyla
    # ugrasmadan, manuel bir "kesinti" dugmesi
    subprocess.run(["pkill", "-9", "-f", "paplay"])
    return jsonify({"kesildi": True})


if __name__ == "__main__":
    print("Sesli Ortak kontrol paneli: http://127.0.0.1:5005", file=sys.stderr)
    app.run(host="127.0.0.1", port=5005, debug=False)
