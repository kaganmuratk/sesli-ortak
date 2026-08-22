"""Stop hook'undan cagrilir. Sesli mod acikken (.sesli_mod_acik varsa)
Claude'un son cevabini sesli okur. Kapaliyken hicbir sey yapmaz.

Sesli modu Ortak (Claude), kullanicinin "sesli mod ac/kapat" gibi bir
istegine karsilik, dogrudan bu dosyayi touch/silme ile acip kapatir -
ozel bir komut ya da arayuz gerekmez."""

import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).parent
SESLI_MOD_BAYRAGI = HERE / ".sesli_mod_acik"
KONUSUYOR_KILIDI = HERE / ".ortak_konusuyor"  # tetikleyici.py bunu gorunce mikrofon tetiklemesini durdurur
MAX_BEKLEME_SN = 60  # baska bir cevap konusuyorsa en fazla bu kadar bekle, sonra pes gec


def main():
    if not SESLI_MOD_BAYRAGI.exists():
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
    try:
        tts.speak(metin)
    finally:
        KONUSUYOR_KILIDI.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
