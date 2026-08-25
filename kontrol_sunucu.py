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
import threading
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
_degistir_kilidi = threading.Lock()


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


def _tetikleyici_durumu() -> str:
    if not DURUM_DOSYASI.exists():
        return ""
    try:
        return json.loads(DURUM_DOSYASI.read_text()).get("durum") or ""
    except Exception:
        return ""


@app.route("/durum")
def durum():
    aktif = _calisiyor_mu()
    d = _tetikleyici_durumu() if aktif else ""
    return jsonify({
        "aktif": aktif,
        "konusuyor": d == "konusuyor",
        "isleniyor": d == "isleniyor",
        "sesli_acik": SESLI_MOD_BAYRAGI.exists(),
    })


def _baslat():
    """dinleyici.py'yi baslatir (zaten calisiyor olmadigini varsayar,
    cagiran _degistir_kilidi altinda emin olmali). /degistir ve
    /baslat_veya_bitir arasinda ortak."""
    global _surec
    _surec = subprocess.Popen(
        [str(PYTHON), str(HERE / "dinleyici.py")],
        cwd=HERE,
        stdout=subprocess.DEVNULL,
        stderr=open(HERE / "dinleyici.log", "a"),
    )
    # ASIL KOK NEDEN (2026-08-24, 18 hayalet surec birikti): tetikleyici.py
    # agir kutuphaneleri (mikrofon/VAD) ice aktardiktan SONRA kendi PID'sini
    # yaziyor - bu birkac saniye surebiliyor. Bu bekleme olmadan fonksiyon
    # hemen donuyordu; o birkac saniyelik pencerede gelen bir sonraki
    # /degistir cagrisi (kullanici "tepki vermiyor" sanip tekrar tiklayinca)
    # PID dosyasini henuz goremedigi icin sureci "calismiyor" saniyor ve
    # bir kopya daha baslatiyordu. Simdi PID dosyasi gercekten yazilana
    # kadar burada bekliyoruz - boylece bir sonraki cagri (ust uste
    # tiklansa bile) gercek durumu görür, kopya baslatmaz.
    beklenen = 0.0
    while _gercek_pid() is None and beklenen < 8.0:
        time.sleep(0.1)
        beklenen += 0.1


def _tamamen_kapat(calisan_pid: int):
    """dinleyici.py'yi tamamen oldurur (cagiran _degistir_kilidi altinda
    emin olmali). /degistir'in eski kapatma yolu, degismedi."""
    global _surec
    # Tam kapatma aninda bir transkripsiyon/temizleme isi surerse
    # (durum "isleniyor"), asagidaki SIGTERM o thread'i yarim birakip
    # mesaji sessizce kaybediyordu - 2026-08-24, 154sn'lik bir mesaj
    # tam bu yuzden hic ulasmadi (kayit bitti -> 3sn sonra kullanici
    # kapat'a bastı -> islem ortasinda oldu). Once isin bitmesini
    # bekliyoruz (makul bir tavan ile - donmus/hic bitmeyen bir istek
    # kullaniciyi sonsuza kadar kapatamaz durumda birakmasin).
    beklenen = 0.0
    while _tetikleyici_durumu() == "isleniyor" and beklenen < 90.0:
        time.sleep(0.2)
        beklenen += 0.2
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
    # Guvenlik agi: PID dosyasi sadece TEK bir sureci takip ediyor.
    # Gecmiste (2026-08-23, 2026-08-24) PID dosyasi disinda kalan
    # kopya tetikleyici.py surecleri birikmisti - "kapat" dedigimizde
    # kullanici gercekten kapanmasini bekliyor, dosyadaki tek PID'ye
    # guvenmek yetmiyor. Kendi PID'imiz disinda eslesen her seyi de
    # temizle (bu script "tetikleyici.py" stringini kendi komut
    # satirinda hic tasimadigi icin kendini vurma riski yok).
    subprocess.run(["pkill", "-9", "-f", "dinleyici.py"], check=False)


@app.route("/degistir", methods=["POST"])
def degistir():
    # Kilit olmadan, ust uste (cift tiklama, sayfa yenilenmesi, paralel bir
    # curl cagrisi vb.) gelen iki /degistir istegi ayni anda "calismiyor"
    # gorup ikisi de yeni bir tetikleyici.py baslatabiliyordu - bu tek
    # basina yeterli degildi, asil sorun asagida.
    with _degistir_kilidi:
        calisan_pid = _gercek_pid()
        if calisan_pid is not None:
            _tamamen_kapat(calisan_pid)
        else:
            _baslat()
        return jsonify({"aktif": _calisiyor_mu()})


@app.route("/bitir", methods=["POST"])
def bitir():
    # /degistir'den farkli: sureci OLDURMEZ. Su an acik bir kayit varsa
    # (arka plan gurultusu vb. yuzunden sessizlik esigi tetiklenmemis olsa
    # bile) SIGUSR1 ile dinleyici.py'ye "simdi bitir, isle, gonder" der -
    # dinleme devam eder. Kayit yoksa (idle "dinliyor") no-op.
    pid = _gercek_pid()
    if pid is not None:
        try:
            os.kill(pid, signal.SIGUSR1)
        except ProcessLookupError:
            pass
    return jsonify({"gonderildi": pid is not None})


@app.route("/baslat_veya_bitir", methods=["POST"])
def baslat_veya_bitir():
    # Tek tuşlu "akıllı" kısayol (ör. Ctrl+Space) icin: KAPALIYSA baslatir,
    # ACIKSA (dinliyor ya da kayit yapiyor fark etmez) /bitir ile ayniyi
    # yapar - sureci OLDURMEZ. Tamamen kapatmak icin hala ayri /degistir
    # (ör. Ctrl+Alt+O) gerekiyor - kullanicinin 2026-08-25 istegi: Dikte'deki
    # Ctrl+Space alonini sesli-ortak'a tasimak, ama "kapat" anlamina gelmeden.
    with _degistir_kilidi:
        calisan_pid = _gercek_pid()
        if calisan_pid is None:
            _baslat()
            return jsonify({"aktif": True, "aksiyon": "baslatildi"})
    try:
        os.kill(calisan_pid, signal.SIGUSR1)
    except ProcessLookupError:
        pass
    return jsonify({"aktif": True, "aksiyon": "bitir"})


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


def _gostergeyi_baslat() -> subprocess.Popen | None:
    # gosterge.py GTK/PyGObject kullanıyor - bu proje venv'inde (sadece
    # Flask/sounddevice/webrtcvad icin kurulu) degil, sistem Python'unda
    # bulunuyor. Bilerek sistem yorumlayicisi sabit verildi.
    try:
        return subprocess.Popen(
            ["/usr/bin/python3", str(HERE / "gosterge.py")],
            cwd=HERE,
            stdout=subprocess.DEVNULL,
            stderr=open(HERE / "gosterge.log", "a"),
        )
    except Exception as e:
        print(f"Gosterge baslatilamadi (onemsiz, panel calismaya devam eder): {e}", file=sys.stderr)
        return None


if __name__ == "__main__":
    print("Sesli Ortak kontrol paneli: http://127.0.0.1:5005", file=sys.stderr)

    _gosterge_sureci = _gostergeyi_baslat()

    def _temizle_ve_cik(signum=None, frame=None):
        if _gosterge_sureci is not None:
            _gosterge_sureci.terminate()
        sys.exit(0)

    # SIGTERM varsayilan olarak Python finally bloklarini calistirmadan
    # sureci hemen sonlandirir - gostergeyi de kapatmak icin acikca yakala.
    signal.signal(signal.SIGTERM, _temizle_ve_cik)

    try:
        # threaded=True: /degistir kapatirken "isleniyor" bitene kadar bekleyebiliyor
        # (yeni), bu bekleme sirasinda /durum'un (panelin spinner'i) bloklanmamasi icin.
        app.run(host="127.0.0.1", port=5005, debug=False, threaded=True)
    finally:
        if _gosterge_sureci is not None:
            _gosterge_sureci.terminate()
