"""Sürekli dinler (webrtcvad ile konuşma başlangıcı/bitişi algılar), konuşma
bitince Dikte'nin motorunu (~/dikte: transkripsiyon + temizleme + pano/yapıştırma)
kullanıp sonucu panoya kopyalar, o an odaktaki pencereye yapıştırır ve otomatik
gönderir (Enter). tetikleyici.py'nin aksine pencere bulma/odaklama YOK - Dikte'nin
felsefesiyle aynı: neredeysen oraya gider. Bu yüzden Claude Code dışında herhangi
bir pencerede de çalışır, ve "yanlış pencereye odaklandı" sınıfı bug hiç oluşmaz.

kontrol_sunucu.py'nin PID dosyası / durum dosyası / .ortak_konusuyor kilidiyle
aynı sözleşmeyi kullanır - panel tarafında hiçbir değişiklik gerekmiyor, sadece
hangi scripti başlattığı değişti.
"""

import array
import collections
import json
import math
import os
import queue
import signal
import sys
import threading
import time
import wave
from pathlib import Path

import sounddevice as sd
import webrtcvad

HERE = Path(__file__).parent
DIKTE_DIR = Path.home() / "dikte"
sys.path.insert(0, str(DIKTE_DIR))

# Dikte'nin modülleri stdlib-only (PyQt6 gerektiren audio.py'yi bilerek
# import etmiyoruz - kendi kayıt/VAD döngümüz zaten var, sadece motoru
# (transkripsiyon + temizleme + panoya yapıştırma) ödünç alıyoruz).
import api as dikte_api
import config as dikte_config
import paste as dikte_paste
import vad as dikte_vad

KONUSUYOR_KILIDI = HERE / ".ortak_konusuyor"       # hook_konustur.py bunu Ortak konusurken olusturur
SESLI_GIRIS_ISARETI = HERE / ".son_giris_sesli"     # gercek bir sesli mesaj gonderildiginde isaretlenir
DURUM_DOSYASI = HERE / ".tetikleyici_durum.json"
PID_DOSYASI = HERE / ".tetikleyici_pid"             # kontrol_sunucu.py gercek sureci bulabilsin diye

ORNEK_HIZI = 16000
KARE_SURESI_MS = 30
KARE_ORNEK = int(ORNEK_HIZI * KARE_SURESI_MS / 1000)
ON_TAMPON_KARE = 10           # ~300ms - konusma baslamadan onceki tamponu da isin icine kat
BASLAMA_ESIGI_KARE = 10       # ~300ms surekli konusma - arka plan gurultusu false-trigger'ini azaltmak icin
SESSIZLIK_ESIGI_KARE = 55     # ~1.65sn sessizlikten sonra konusma bitti say
VAD_AGRESIFLIK = 3            # 0-3, en yuksek - sadece net konusmayi sayar

OTOMATIK_GONDER = True        # yapistirdiktan sonra Enter'a da bas (kapatmak icin False yap)

vad = webrtcvad.Vad(VAD_AGRESIFLIK)
conf = dikte_config.Config()
_acik_kayit_var = False   # _temizlik() sinyal handler'i erisebilsin diye global tutuluyor
_zorla_bitir_istek = False  # /bitir (SIGUSR1) ile kontrol panelinden gelen "simdi bitir" istegi
_yapistirma_kilidi = threading.Lock()  # ust uste iki isleme ayni anda panoya yazmasin

# Birden fazla cumle ust uste islenebiliyor (bkz. _isle docstring) - o yuzden
# tek bir bayrak degil sayac tutuyoruz: son isin bitmesiyle "dinliyor"a donuyoruz.
_isleniyor_kilidi = threading.Lock()
_isleniyor_sayisi = 0


def _isleniyor_baslat():
    global _isleniyor_sayisi
    with _isleniyor_kilidi:
        _isleniyor_sayisi += 1
        _durum_yaz("isleniyor")


def _isleniyor_bitir():
    global _isleniyor_sayisi
    with _isleniyor_kilidi:
        _isleniyor_sayisi = max(0, _isleniyor_sayisi - 1)
        if _isleniyor_sayisi == 0 and not _acik_kayit_var:
            _durum_yaz("dinliyor")


def _log(msg: str):
    print(f"[dinleyici] {msg}", file=sys.stderr, flush=True)


def _durum_yaz(durum: str):
    try:
        DURUM_DOSYASI.write_text(json.dumps({"durum": durum}))
    except Exception:
        pass


def _rms(kare: bytes) -> float:
    """audio.chunk_levels'daki rms hesabinin aynisi (0..1) - PyQt6'siz."""
    samples = array.array("h")
    kullanilabilir = len(kare) - (len(kare) % 2)
    if kullanilabilir <= 0:
        return 0.0
    samples.frombytes(kare[:kullanilabilir])
    return min(1.0, math.sqrt(sum(s * s for s in samples) / len(samples)) / 32768.0)


def _wav_yaz(pcm: bytes) -> Path:
    yol = HERE / f".gecici-{time.time_ns()}.wav"
    with wave.open(str(yol), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(ORNEK_HIZI)
        w.writeframes(pcm)
    return yol


def _isle(pcm: bytes, rms_degerleri: list[float], sure_sn: float):
    """Arka planda calisir: transkribe et, temizle, yapistir, gonder. Ana
    dinleme dongusunu bloklamaz - konusurken bir onceki cumle hala islenirken
    yeni bir cumleye baslayabilirsin."""
    wav_yolu = None
    _isleniyor_baslat()
    try:
        if conf["skip_silent"]:
            istatistik = dikte_vad.analyse(
                rms_degerleri, KARE_SURESI_MS / 1000, conf["speech_margin_db"]
            )
            if dikte_vad.is_silent(
                istatistik, conf["silence_db"], conf["speech_margin_db"],
                conf["min_voiced_seconds"],
            ):
                _log(f"sessizlik sayildi, API'ye gitmiyor ({round(istatistik['speech_db'])} dB)")
                return

        wav_yolu = _wav_yaz(pcm)
        hedef = conf.transcribe_target()
        ham = dikte_api.transcribe(
            hedef, str(wav_yolu), language=conf["language"], prompt=conf["transcribe_prompt"]
        )

        if conf["filter_hallucinations"] and dikte_vad.looks_like_hallucination(ham, sure_sn):
            _log(f"uydurma cumle sayildi, atlaniyor: {ham[:60]!r}")
            return

        metin = ham
        if conf["cleanup_enabled"]:
            try:
                metin = dikte_api.cleanup(
                    ham, conf.openrouter_key(), conf["cleanup_model"],
                    conf.cleanup_prompt(), reasoning=conf["cleanup_reasoning"],
                    base_url=conf["openrouter_base_url"],
                )
            except dikte_api.ApiError as exc:
                _log(f"temizleme basarisiz, ham transkript kullaniliyor: {exc}")
                metin = ham

        with _yapistirma_kilidi:
            dikte_paste.copy(metin)
            dikte_paste.press(conf["paste_shortcut"])
            if OTOMATIK_GONDER:
                time.sleep(0.25)
                dikte_paste.press("enter")

        SESLI_GIRIS_ISARETI.touch()
        _log(f"gonderildi: {metin[:60]!r}")

    except dikte_api.ApiError as exc:
        _log(f"API hatasi: {exc}")
    except dikte_paste.PasteError as exc:
        _log(f"yapistirma hatasi: {exc}")
    except Exception as exc:  # sessizce cokme
        _log(f"beklenmedik hata: {exc!r}")
    finally:
        if wav_yolu and wav_yolu.exists():
            try:
                wav_yolu.unlink()
            except OSError:
                pass
        _isleniyor_bitir()


def _temizlik(signum=None, frame=None):
    PID_DOSYASI.unlink(missing_ok=True)
    DURUM_DOSYASI.unlink(missing_ok=True)
    sys.exit(0)


def _zorla_bitir_isaretle(signum=None, frame=None):
    # kontrol_sunucu.py /bitir ile bu sinyali gonderir - "tamamen kapat"tan
    # (SIGTERM, sureci oldurur, kayitli-ama-islenmemis sesi kaybeder) farkli
    # olarak, sadece o an acik olan kaydi sessizlik esigini beklemeden hemen
    # bitirip normal isleme/gonderme yoluna sokar, dinlemeye devam eder.
    # Arka plan gurultusu (vantilator, ezan vb.) sessizlik algisini bozdugunda
    # kullanicinin manuel "bitti, gonder" demesi icin (2026-08-25).
    global _zorla_bitir_istek
    _zorla_bitir_istek = True


def _dinleme_dongusu():
    global _acik_kayit_var, _zorla_bitir_istek
    q: "queue.Queue[bytes]" = queue.Queue()

    def ses_geldi(indata, frames, time_info, status):
        q.put(bytes(indata))

    _durum_yaz("dinliyor")
    with sd.RawInputStream(
        samplerate=ORNEK_HIZI, blocksize=KARE_ORNEK, dtype="int16", channels=1, callback=ses_geldi
    ):
        on_tampon = collections.deque(maxlen=ON_TAMPON_KARE)
        tampon: list[bytes] = []
        rms_degerleri: list[float] = []
        baslama_sayaci = 0
        sessiz_sayac = 0

        def _bitir_ve_isle(sebep: str):
            nonlocal tampon, rms_degerleri, baslama_sayaci
            global _acik_kayit_var
            _acik_kayit_var = False
            baslama_sayaci = 0
            on_tampon.clear()
            _log(f"konusma bitti ({sebep}) -> isleniyor")
            # Durumu burada "dinliyor"a cevirmiyoruz - _isle() kendi basinda
            # "isleniyor" yazacak, bitince "dinliyor"a donecek. Onceden burada
            # erken "dinliyor" yazilmasi, uzun bir transkripsiyon/temizleme
            # surerken panelin "acik, dinliyor" gostermesine (hicbir isaret
            # vermemesine) sebep oluyordu - kullanici islemin surdugunu
            # goremedigi icin kapat/ac kisayoluna basip in-flight isi SIGTERM
            # ile oldurebiliyordu (2026-08-24, 154sn'lik bir mesaj bu sekilde
            # kayboldu).
            pcm = b"".join(tampon)
            sure_sn = len(pcm) / 2 / ORNEK_HIZI
            threading.Thread(
                target=_isle, args=(pcm, list(rms_degerleri), sure_sn), daemon=True
            ).start()
            tampon = []
            rms_degerleri = []

        while True:
            kare = q.get()

            if _zorla_bitir_istek:
                _zorla_bitir_istek = False
                if _acik_kayit_var:
                    # Sessizlik esigini (arka plan gurultusu vb. yuzunden hic
                    # tetiklenmemis olabilir) beklemeden, o ana kadar kaydedileni
                    # simdi bitir ve isle - sureci OLDURMEZ, dinlemeye devam eder.
                    _bitir_ve_isle("manuel")
                # Acik kayit yoksa (henuz konusma baslamamis) yapacak bir sey yok.

            if KONUSUYOR_KILIDI.exists():
                # Ortak su an konusuyor (TTS) - kendi sesini dinlememesi icin
                # acik bir kayit varsa iptal et, tampon biriktirme.
                if _acik_kayit_var:
                    _log("Ortak konusmaya basladi, acik kaydi iptal ediyorum")
                    _acik_kayit_var = False
                    tampon = []
                    rms_degerleri = []
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
                        tampon = list(on_tampon)
                        rms_degerleri = [_rms(k) for k in tampon]
                        _log("konusma basladi")
                        _durum_yaz("konusuyor")
                else:
                    # Sert sifirlama yerine "sizdirarak" azalt (2026-08-25):
                    # arka plan gurultusu (fan, ezan vb.) VAD'i ara sira yanlis
                    # siniflandirip tek bir kareyi "konusma degil" sayabiliyor -
                    # eskiden bu TEK kare bile 300ms'lik ilerlemeyi komple
                    # sifirlayip gercek konusmanin hic baslamamis gibi
                    # gorunmesine sebep oluyordu. Su an sadece 1 geri aliyoruz,
                    # yani konusma karelerinin >yarisi doğru siniflenirse ilerleme
                    # birikmeye devam ediyor. Salt gurultu (hic konusma yokken)
                    # hala 0'a dogru sizip esigi asamiyor - false-trigger korumasi
                    # (e49b826) bozulmuyor.
                    baslama_sayaci = max(0, baslama_sayaci - 1)
            else:
                tampon.append(kare)
                rms_degerleri.append(_rms(kare))
                if konusma_mi:
                    # Ayni sizdirma mantigi burada da: konusma sirasindaki kisa
                    # bir gurultu kaynakli "konusma" karesi, birikmis sessizlik
                    # sayacini komple sifirlamasin - yoksa fan/ezan sesi yuzunden
                    # "sustun" hic algilanmiyordu (2026-08-25, kullanici bildirdi).
                    sessiz_sayac = max(0, sessiz_sayac - 1)
                else:
                    sessiz_sayac += 1
                    if sessiz_sayac >= SESSIZLIK_ESIGI_KARE:
                        _bitir_ve_isle("sessizlik")


def calistir():
    signal.signal(signal.SIGTERM, _temizlik)
    signal.signal(signal.SIGINT, _temizlik)
    signal.signal(signal.SIGUSR1, _zorla_bitir_isaretle)
    PID_DOSYASI.write_text(str(os.getpid()))
    _log("baslatildi, dinliyor (pencere odaklama yok, panoya yapistiriyor)")
    while True:
        try:
            _dinleme_dongusu()
        except Exception as e:
            _log(f"beklenmedik hata, kurtarmaya calisiyorum: {e!r}")
            time.sleep(1)


if __name__ == "__main__":
    calistir()
