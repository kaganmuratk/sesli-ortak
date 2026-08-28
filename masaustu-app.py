"""Sesli Ortak - gerçek (tarayıcısız) masaüstü uygulaması. templates/index.html'in
GTK3 karşılığı: aynı /durum, /degistir, /bitir, /sesli_degistir, /kes endpoint'lerini
kullanır ama Flask panelini bir tarayıcı penceresinde değil, native bir GTK penceresinde
gösterir. gosterge.py'deki kanıtlanmış GTK3/Cairo/urllib deseni tekrar kullanıldı - bu
sistemde WebKit2 (pywebview/Chrome-app-mode gerektiren yollar) yok, GTK3 Cairo çizimi var
(2026-08-28, Kağan Murat "direkt uygulama olsun, tarayıcı açmasın" dedi).

kontrol_sunucu.py'yi başlatmaz/durdurmaz - Flask panel ayrı çalışmaya devam eder, bu sadece
ona native bir arayüz sağlar. Panel API'si kapalıysa "kapalı/erişilemiyor" gösterir.
"""

import json
import math
import os
import urllib.error
import urllib.request

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk  # noqa: E402

PANEL_URL = os.environ.get("SESLI_ORTAK_PANEL_URL", "http://127.0.0.1:5005")

# templates/index.html ile ayni palet
RENK_BG = (0.043, 0.047, 0.063)
RENK_DIM = (0.29, 0.31, 0.36)
RENK_DINLIYOR = (0.227, 0.427, 0.941)
RENK_KONUSUYOR = (0.941, 0.651, 0.227)
RENK_ISLENIYOR = (0.604, 0.361, 0.941)
RENK_METIN = (0.843, 0.851, 0.878)
RENK_METIN_DIM = (0.42, 0.44, 0.50)

ORB_CAP = 150


def _istek(yol: str, post: bool = False) -> dict:
    url = f"{PANEL_URL}{yol}"
    try:
        req = urllib.request.Request(url, method="POST" if post else "GET")
        if post:
            req.data = b""
        with urllib.request.urlopen(req, timeout=1.5) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return {}


class SesliOrtakPenceresi(Gtk.Window):
    def __init__(self):
        super().__init__(title="Sesli Ortak")
        self.set_default_size(320, 420)
        self.set_resizable(False)
        self.connect("destroy", Gtk.main_quit)

        self._durum = "kapali"
        self._nabiz = 0.0
        self._panel_eristi_mi = True

        disari = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        disari.set_border_width(24)
        self.add(disari)

        self.orb = Gtk.DrawingArea()
        self.orb.set_size_request(ORB_CAP + 40, ORB_CAP + 40)
        self.orb.connect("draw", self._orb_ciz)
        self.orb.add_events(self.orb.get_events() | 0x200)  # BUTTON_PRESS_MASK
        self.orb.connect("button-press-event", self._orb_tiklandi)
        disari.pack_start(self.orb, False, False, 0)

        self.asama_etiketi = Gtk.Label(label="yükleniyor...")
        disari.pack_start(self.asama_etiketi, False, False, 0)

        self.bitir_dugmesi = Gtk.Button(label="Bitirdim, gönder")
        self.bitir_dugmesi.connect("clicked", lambda w: _istek("/bitir", post=True))
        self.bitir_dugmesi.set_no_show_all(True)
        disari.pack_start(self.bitir_dugmesi, False, False, 0)

        sesli_satiri = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        sesli_satiri.set_halign(Gtk.Align.CENTER)
        sesli_satiri.pack_start(Gtk.Label(label="Sesli cevap"), False, False, 0)
        self.sesli_anahtari = Gtk.Switch()
        self.sesli_anahtari.connect("state-set", self._sesli_degistirildi)
        sesli_satiri.pack_start(self.sesli_anahtari, False, False, 0)
        disari.pack_start(sesli_satiri, False, False, 0)

        kes_dugmesi = Gtk.Button(label="Kes")
        kes_dugmesi.connect("clicked", lambda w: _istek("/kes", post=True))
        disari.pack_start(kes_dugmesi, False, False, 0)

        GLib.timeout_add(700, self._durumu_guncelle)
        GLib.timeout_add(80, self._nabiz_tik)
        self._durumu_guncelle()

    def _orb_tiklandi(self, widget, event):
        _istek("/degistir", post=True)
        GLib.timeout_add(150, lambda: (self._durumu_guncelle(), False)[1])
        return True

    def _sesli_degistirildi(self, widget, durum):
        # Gtk.Switch "state-set" olayi zaten anahtari yeni duruma cevirir - biz
        # sadece sunucuya haber veriyoruz, tekrar toggle etmiyoruz (cift toggle
        # onlemek icin False dondurmuyoruz, varsayilan davranisa birakiyoruz).
        _istek("/sesli_degistir", post=True)
        return False

    def _durumu_guncelle(self):
        veri = _istek("/durum")
        self._panel_eristi_mi = bool(veri) or veri == {}
        if not veri:
            self._panel_eristi_mi = False
            self._durum = "erisilemiyor"
            self.asama_etiketi.set_text("panel çalışmıyor (kontrol_sunucu.py kapalı olabilir)")
            self.bitir_dugmesi.hide()
            self.orb.queue_draw()
            return True

        if not veri.get("aktif"):
            self._durum = "kapali"
            self.asama_etiketi.set_text("kapalı")
        elif veri.get("isleniyor"):
            self._durum = "isleniyor"
            self.asama_etiketi.set_text("işleniyor... (kapatma, bitmesini bekler)")
        elif veri.get("konusuyor"):
            self._durum = "konusuyor"
            self.asama_etiketi.set_text("seni dinliyor...")
        else:
            self._durum = "dinliyor"
            self.asama_etiketi.set_text("açık, dinliyor")

        if veri.get("konusuyor"):
            self.bitir_dugmesi.show()
        else:
            self.bitir_dugmesi.hide()

        self.sesli_anahtari.set_state(bool(veri.get("sesli_acik")))
        self.orb.queue_draw()
        return True

    def _nabiz_tik(self):
        if self._durum in ("konusuyor", "isleniyor"):
            self._nabiz += 0.25
            self.orb.queue_draw()
        return True

    def _orb_ciz(self, alan, cr):
        genislik = alan.get_allocated_width()
        yukseklik = alan.get_allocated_height()
        merkez_x, merkez_y = genislik / 2, yukseklik / 2
        yaricap = ORB_CAP / 2

        renkler = {
            "kapali": RENK_DIM,
            "erisilemiyor": RENK_DIM,
            "dinliyor": RENK_DINLIYOR,
            "konusuyor": RENK_KONUSUYOR,
            "isleniyor": RENK_ISLENIYOR,
        }
        renk = renkler.get(self._durum, RENK_DIM)
        nabizli_mi = self._durum in ("konusuyor", "isleniyor")
        parlaklik = 1.0 + (0.12 * math.sin(self._nabiz) if nabizli_mi else 0.0)

        # dis halka
        cr.set_source_rgba(*renk, 0.5)
        cr.set_line_width(2)
        if self._durum == "isleniyor":
            cr.set_dash([6, 4])
        cr.arc(merkez_x, merkez_y, yaricap + 18, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])

        # ic top
        cr.set_source_rgb(
            min(renk[0] * parlaklik, 1.0),
            min(renk[1] * parlaklik, 1.0),
            min(renk[2] * parlaklik, 1.0),
        )
        cr.arc(merkez_x, merkez_y, yaricap * (1.0 + (0.04 if nabizli_mi else 0.0) * math.sin(self._nabiz)), 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgb(*RENK_METIN)
        cr.select_font_face("sans-serif")
        cr.set_font_size(13)
        metin = "Durdur" if self._durum not in ("kapali", "erisilemiyor") else "Başlat"
        genislik_metin = cr.text_extents(metin)[2]
        cr.move_to(merkez_x - genislik_metin / 2, merkez_y + 4)
        cr.show_text(metin)
        return False


def main():
    pencere = SesliOrtakPenceresi()
    pencere.show_all()
    pencere.bitir_dugmesi.hide()
    Gtk.main()


if __name__ == "__main__":
    main()
