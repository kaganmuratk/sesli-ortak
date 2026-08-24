"""Stop hook'undan cagrilir. Sesli mod acikken (.sesli_mod_acik varsa)
Claude'un son cevabini sesli okur. Kapaliyken hicbir sey yapmaz.

Sesli modu Ortak (Claude), kullanicinin "sesli mod ac/kapat" gibi bir
istegine karsilik, dogrudan bu dosyayi touch/silme ile acip kapatir -
ozel bir komut ya da arayuz gerekmez."""

import json
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
SESLI_MOD_BAYRAGI = HERE / ".sesli_mod_acik"
KONUSUYOR_KILIDI = HERE / ".ortak_konusuyor"  # dinleyici.py bunu gorunce mikrofon tetiklemesini durdurur
SESLI_GIRIS_ISARETI = HERE / ".son_giris_sesli"  # dinleyici.py gercek bir sesli mesaj gonderince isaretler
MAX_BEKLEME_SN = 60  # baska bir cevap konusuyorsa en fazla bu kadar bekle, sonra pes gec


def _mikrofonu_ayarla(sustur: bool):
    try:
        subprocess.run(
            ["pactl", "set-source-mute", "@DEFAULT_SOURCE@", "1" if sustur else "0"],
            capture_output=True, timeout=2,
        )
    except Exception:
        pass  # sessizce gec - susturma basarisiz olsa bile konusma devam etsin


def main():
    if not SESLI_MOD_BAYRAGI.exists():
        return

    # Sadece gercekten sesle gelen bir mesaja sesli cevap ver - elle
    # yazilan mesajlarda bu isaret hic olusmaz, o yuzden burada sessizce cikariz.
    sesli_giris_miydi = SESLI_GIRIS_ISARETI.exists()
    SESLI_GIRIS_ISARETI.unlink(missing_ok=True)
    if not sesli_giris_miydi:
        return

    try:
        veri = json.load(sys.stdin)
    except Exception:
        return

    metin = (veri.get("last_assistant_message") or "").strip()
    if not metin:
        return

    sys.path.insert(0, str(HERE))
    import tts

    # Baska bir cevap su an konusuyorsa, uzerine binmek yerine sirada bekle
    beklenen = 0.0
    while KONUSUYOR_KILIDI.exists() and beklenen < MAX_BEKLEME_SN:
        time.sleep(0.2)
        beklenen += 0.2

    KONUSUYOR_KILIDI.touch()
    _mikrofonu_ayarla(sustur=True)
    try:
        tts.speak(metin)
    finally:
        _mikrofonu_ayarla(sustur=False)
        KONUSUYOR_KILIDI.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
