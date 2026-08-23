"""Buton acikken surekli dinler: konusma basladiginda Ortak'in penceresine
gecip Space'e basarak native /voice kaydini baslatir, konusma bitince tekrar
Space'e basip gonderir. Uyandirma kelimesi yok - kullanici butonu bilerek
actigi icin (gunluk/tam konusma oturumu), her konusma dogrudan islenir."""

import collections
import json
import os
import queue
import signal
import subprocess
import sys
import time
from pathlib import Path

import sounddevice as sd
import webrtcvad

HERE = Path(__file__).parent
KONUSUYOR_KILIDI = HERE / ".ortak_konusuyor"  # hook_konustur.py bunu Ortak konusurken olusturur
SESLI_GIRIS_ISARETI = HERE / ".son_giris_sesli"  # gercek bir sesli mesaj gonderildiginde isaretlenir
DURUM_DOSYASI = HERE / ".tetikleyici_durum.json"
PID_DOSYASI = HERE / ".tetikleyici_pid"  # kontrol_sunucu.py yeniden baslasa bile gercek sureci bulabilsin diye
KWIN_JS = Path("/tmp/kwin_odakla_ortak.js")
KWIN_PLUGIN_ADI = "ortak-odakla-daemon"


def _load_env():
    env_path = HERE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


_load_env()
TERMINAL_SINIFI = os.environ.get("ORTAK_TERMINAL_SINIFI", "org.kde.konsole")
PENCERE_ANAHTARI = os.environ.get("ORTAK_PENCERE_ANAHTARI", "")
if not PENCERE_ANAHTARI:
    sys.exit(
        "[tetikleyici] .env icinde ORTAK_PENCERE_ANAHTARI ayarli degil.\n"
        "Ortak'in calistigi terminal penceresinin basligindan gecen, "
        "benzersiz bir kelime yaz (orn. proje klasor adin)."
    )

ORNEK_HIZI = 16000
KARE_SURESI_MS = 30
KARE_ORNEK = int(ORNEK_HIZI * KARE_SURESI_MS / 1000)
ON_TAMPON_KARE = 10           # ~300ms - konusma baslamadan onceki tamponu da isin icine kat
BASLAMA_ESIGI_KARE = 10       # ~300ms surekli konusma - fan/arka plan gurultusu false-trigger'ini azaltmak icin yukseltildi (2026-08-22)
SESSIZLIK_ESIGI_KARE = 55     # ~1.65sn sessizlikten sonra konusma bitti say (erken kesmesin diye guvenli tarafta kaldik)
VAD_AGRESIFLIK = 3            # 0-3, en yuksek - sadece net konusmayi sayar, arka plan gurultusunu eler

vad = webrtcvad.Vad(VAD_AGRESIFLIK)
_kwin_script_id: str | None = None
_acik_kayit_var = False  # _temizlik() sinyal handler'i erisebilsin diye global tutuluyor


def _log(msg: str):
    print(f"[tetikleyici] {msg}", file=sys.stderr, flush=True)


def _durum_yaz(durum: str):
    try:
        DURUM_DOSYASI.write_text(json.dumps({"durum": durum}))
    except Exception:
        pass


def _kwin_script_yukle():
    global _kwin_script_id
    anahtar_js = json.dumps(PENCERE_ANAHTARI)  # JS string olarak guvenli kacis
    sinif_js = json.dumps(TERMINAL_SINIFI)
    KWIN_JS.write_text(
        'var wins = workspace.windowList();\n'
        'for (var i = 0; i < wins.length; i++) {\n'
        '    var w = wins[i];\n'
        f'    if (w.resourceClass === {sinif_js} && w.caption.indexOf({anahtar_js}) !== -1) {{\n'
        '        workspace.activeWindow = w;\n'
        '        break;\n'
        '    }\n'
        '}\n'
    )
    subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", KWIN_PLUGIN_ADI],
                    capture_output=True)
    sonuc = subprocess.run(
        ["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.loadScript", str(KWIN_JS), KWIN_PLUGIN_ADI],
        capture_output=True, text=True,
    )
    _kwin_script_id = sonuc.stdout.strip()
    _log(f"KWin odaklama script'i yuklendi, id={_kwin_script_id}")


def _kwin_script_bosalt():
    if _kwin_script_id is not None:
        subprocess.run(["qdbus6", "org.kde.KWin", "/Scripting", "org.kde.kwin.Scripting.unloadScript", KWIN_PLUGIN_ADI],
                        capture_output=True)


def _temizlik(*_):
    # Kontrol panelinden mikrofon kapatilmasi (SIGTERM) ya da baska bir disaridan
    # gelen sinyal, TAM O SIRADA bir kayit acikken gelirse - eskiden bu fonksiyon
    # native kaydi hic kapatmadan cikiyordu. Native'de kayit acik kalirken script
    # kapaniyor, kullanici tekrar actiginda yeni process "konusuyor=False" saniyor
    # ama native hala "acik" - bir sonraki gercek konusmada gonderilen Space,
    # native'in acik kaydini baslatmak yerine KAPATIYORDU (kullanicinin "susmama
    # ragmen mesaj gitti, sonra konustugumda algilamadi/gondermedi" sikayetinin
    # kok nedeni muhtemelen buydu, crash-safe donguyu atlayan bir yoldan).
    if _acik_kayit_var:
        _log("kapatma sinyali geldi, acik kayit vardi -> guvenlik icin kapatiyorum")
        try:
            _kayit_bitir()
        except Exception as e:
            _log(f"guvenlik kapatmasi basarisiz oldu: {e!r}")
    DURUM_DOSYASI.unlink(missing_ok=True)
    SESLI_GIRIS_ISARETI.unlink(missing_ok=True)
    PID_DOSYASI.unlink(missing_ok=True)
    _kwin_script_bosalt()
    sys.exit(0)


def _odakla():
    if _kwin_script_id is not None:
        subprocess.run(["qdbus6", "org.kde.KWin", f"/Scripting/Script{_kwin_script_id}", "org.kde.kwin.Script.run"],
                        capture_output=True)


def _kayit_baslat():
    _odakla()
    subprocess.run(["ydotool", "key", "57:1", "57:0"])  # Space


def _kayit_bitir():
    _odakla()
    subprocess.run(["ydotool", "key", "57:1", "57:0"])  # Space - normalde gonderir
    # Guvenlik agi: native /voice'un yaziya cevirmeyi (transkripsiyon) bitirip
    # kutuya yazmasi degisken bir sure alabiliyor - sabit tek seferlik 0.3sn'lik
    # bekleme bunu her zaman yakalayamiyordu. Eger Enter, yaziya cevirme daha
    # bitmeden gonderilirse bos bir kutuya gidiyor (etkisiz), metin birkac
    # saniye sonra gelince kimse "gonder" demeden kutuda asili kaliyor - sonraki
    # konusma bu asili kalan metnin uzerine karisiyordu. Tek Enter yerine
    # birden fazla Enter'i artan araliklarla gonderiyoruz: yaziya cevirme hangi
    # anda biterse bitsin en az biri dogru zamana denk geliyor. Kutu zaten
    # bosaldiysa fazladan Enter'lar zararsizdir (bos kutuda etkisizdir).
    onceki_bekleme = 0.0
    for hedef_bekleme in (0.3, 0.9, 1.8):
        time.sleep(hedef_bekleme - onceki_bekleme)
        subprocess.run(["ydotool", "key", "28:1", "28:0"])  # Enter
        onceki_bekleme = hedef_bekleme


def _dinleme_dongusu():
    """Tek bir dinleme oturumu. Herhangi bir sebeple (cihaz hatasi, VAD
    exception'i vb.) kesilirse, finally bloğu acik kalan kaydi native
    tarafinda guvenle kapatir - boylece script/native state'i asla
    birbirinden kopmaz (biri 'kapali' sanirken digeri 'acik' kalmaz)."""
    global _acik_kayit_var
    q: "queue.Queue[bytes]" = queue.Queue()

    def ses_geldi(indata, frames, time_info, status):
        q.put(bytes(indata))

    _durum_yaz("dinliyor")
    try:
        with sd.RawInputStream(
            samplerate=ORNEK_HIZI, blocksize=KARE_ORNEK, dtype="int16", channels=1, callback=ses_geldi
        ):
            on_tampon = collections.deque(maxlen=ON_TAMPON_KARE)
            baslama_sayaci = 0
            sessiz_sayac = 0

            while True:
                kare = q.get()

                if KONUSUYOR_KILIDI.exists():
                    # Ortak su an konusmaya basladi (TTS). Eger tam o anda bir kayit
                    # aciksa (_acik_kayit_var), once onu duzgunce kapatalim - yoksa
                    # acik kalan native kayit Ortak'in sesini de icine alip
                    # transkripti kirletir.
                    if _acik_kayit_var:
                        _log("Ortak konusmaya basladi, acik kaydi kapatiyorum")
                        _kayit_bitir()
                        _acik_kayit_var = False
                        _durum_yaz("dinliyor")
                    baslama_sayaci = 0
                    on_tampon.clear()
                    continue

                konusma_mi = vad.is_speech(kare, ORNEK_HIZI)

                if not _acik_kayit_var:
                    on_tampon.append(kare)
                    if konusma_mi:
                        baslama_sayaci += 1
                        if baslama_sayaci >= BASLAMA_ESIGI_KARE:
                            _acik_kayit_var = True
                            sessiz_sayac = 0
                            _log("konusma basladi -> Space")
                            _durum_yaz("konusuyor")
                            _kayit_baslat()
                    else:
                        baslama_sayaci = 0
                else:
                    if konusma_mi:
                        sessiz_sayac = 0
                    else:
                        sessiz_sayac += 1
                        if sessiz_sayac >= SESSIZLIK_ESIGI_KARE:
                            _acik_kayit_var = False
                            baslama_sayaci = 0
                            on_tampon.clear()
                            _log("konusma bitti -> gonder")
                            _durum_yaz("dinliyor")
                            _kayit_bitir()
                            SESLI_GIRIS_ISARETI.touch()  # bu gercek bir sesli mesajdi, hook_konustur.py buna bakip sesli cevap versin
    finally:
        if _acik_kayit_var:
            _log("dinleme dongusu beklenmedik sekilde kesildi, acik kayit vardi -> guvenlik icin kapatiyorum")
            try:
                _kayit_bitir()
            except Exception as e:
                _log(f"guvenlik kapatmasi da basarisiz oldu: {e!r}")
            finally:
                _acik_kayit_var = False


def calistir():
    signal.signal(signal.SIGTERM, _temizlik)
    signal.signal(signal.SIGINT, _temizlik)

    # PID dosyasi: kontrol_sunucu.py yeniden baslarsa (bilgisayar kapanip
    # acilmasi, oturum restart'i vb.) kendi hafizasindaki surec referansini
    # kaybediyor - PID dosyasi olmadan bu process "hayalet" kalip sonsuza
    # kadar mikrofonu dinlemeye devam ediyordu, panel ise "kapali" gosterip
    # kullanici "Baslat"a basinca bir yenisini daha baslatiyordu. Zamanla
    # boyle 11 tane hayalet sureç birikti (2026-08-23'te tespit edildi).
    # Artik kontrol_sunucu.py bu dosyadan gercek PID'yi okuyup canli olup
    # olmadigini kendisi dogrulayabiliyor.
    PID_DOSYASI.write_text(str(os.getpid()))

    _kwin_script_yukle()
    _log("baslatildi, dinliyor")

    # Cihaz/VAD kaynakli beklenmedik bir hata olursa (bluetooth kesintisi,
    # uyku/uyanma, PipeWire yeniden baslamasi vb.) process eskiden sessizce
    # cokuyordu ve kontrol paneli disaridan manuel restart gerektiriyordu -
    # bu sirada native tarafta acik kalan bir kayit varsa, script ile native
    # arasindaki state kopuyor ve bir sonraki konusma Space'i "baslat" yerine
    # "durdur" olarak native'e ulasiyordu (kullanicinin "konusuyorum ama
    # yazmiyor/gondermiyor" sikayetinin kok nedeni buydu). Artik disaridan
    # gorunmeyecek sekilde kendi kendini toparlayip devam ediyor.
    while True:
        try:
            _dinleme_dongusu()
        except Exception as e:
            _log(f"beklenmedik hata, kurtarmaya calisiyorum: {e!r}")
            time.sleep(1)  # cihazin toparlanmasi icin kisa bir nefes


if __name__ == "__main__":
    calistir()
