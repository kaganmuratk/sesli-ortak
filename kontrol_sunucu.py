"""Sesli Ortak - kucuk kontrol paneli.
Iki bagimsiz anahtar var: buyuk daire mikrofon dinlemesini (tetikleyici.py)
ac/kapatir, kucuk anahtar ise cevaplarin sesli okunup okunmayacagini
(.sesli_mod_acik bayragi) belirler. Ikisi istenen herhangi bir kombinasyonda
kullanilabilir. Yaziya cevirme islerine hic karismiyor, o Claude Code'un
native /voice'una ait."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from flask import Flask, jsonify, render_template

app = Flask(__name__)

HERE = Path(__file__).parent
DURUM_DOSYASI = HERE / ".tetikleyici_durum.json"
SESLI_MOD_BAYRAGI = HERE / ".sesli_mod_acik"
PID_DOSYASI = HERE / ".tetikleyici_pid"
PYTHON = HERE / ".venv" / "bin" / "python3"

_surec: subprocess.Popen | None = None


def _pid_canli_mi(pid: int) -> bool:
    try:
        os.kill(pid, 0)  # sinyal gondermez, sadece varlik/izin kontrolu yapar
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True  # baska kullanicinin sureci ama var - bize ait olma ihtimali dusuk, temkinli davran


def _gercek_pid() -> int | None:
    """PID dosyasindaki surec gercekten calisiyor mu diye dogrudan isletim
    sistemine sorar - bu kontrol panelinin kendi hafizasina (_surec) degil,
    gercege dayanir. kontrol_sunucu.py yeniden baslatildiginda (bilgisayar
    kapanip acilmasi, oturum restart'i vb.) _surec sifirlaniyordu ama daha
    onceki tetikleyici.py sureci olmeden calismaya devam ediyordu - panel
    "kapali" gosterip kullanici tekrar "Baslat"a basinca ustune bir yenisi
    daha ekleniyordu. Zamanla boyle 11 tane hayalet surec birikti
    (2026-08-23'te tespit edildi, hepsi elle temizlendi). Artik PID dosyasi
    tek gercek kaynak: dosya var ve icindeki PID gercekten yasiyorsa
    "calisiyor" sayilir, yoksa (bayat dosya kalmis olsa bile) temizlenir."""
    if not PID_DOSYASI.exists():
        return None
    try:
        pid = int(PID_DOSYASI.read_text().strip())
    except (ValueError, OSError):
        PID_DOSYASI.unlink(missing_ok=True)
        return None
    if _pid_canli_mi(pid):
        return pid
    PID_DOSYASI.unlink(missing_ok=True)  # bayat dosya - surec cnokten olmus
    return None


def _calisiyor_mu() -> bool:
    return _gercek_pid() is not None


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
    calisan_pid = _gercek_pid()
    if calisan_pid is not None:
        # _surec bu PID'yi tanimiyor olabilir (baska bir kontrol_sunucu.py
        # instance'i baslatmis olabilir) - gercek PID'ye dogrudan sinyal
        # gonder, _surec'e guvenme.
        try:
            os.kill(calisan_pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        beklenen = 0.0
        while _pid_canli_mi(calisan_pid) and beklenen < 3.0:
            time.sleep(0.1)
            beklenen += 0.1
        _surec = None
        DURUM_DOSYASI.unlink(missing_ok=True)
        PID_DOSYASI.unlink(missing_ok=True)
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
