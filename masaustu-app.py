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

# Taskbar'da genel/varsayilan (sari) bir ikon yerine kendi ikonumuzun
# gorunmesi icin: prgname StartupWMClass ile eslesmeli (.desktop dosyasindaki
# StartupWMClass=sesli-ortak), ikon da hicolor tema dizinine kurulu
# (~/.local/share/icons/hicolor/256x256/apps/sesli-ortak.png) - 2026-08-28.
GLib.set_prgname("sesli-ortak")

PANEL_URL = os.environ.get("SESLI_ORTAK_PANEL_URL", "http://127.0.0.1:5005")
IKON_YOLU = os.path.expanduser(
    "~/.local/share/icons/hicolor/256x256/apps/sesli-ortak.png"
)

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
        self.set_default_size(360, 540)
        self.connect("destroy", Gtk.main_quit)
        if os.path.exists(IKON_YOLU):
            self.set_icon_from_file(IKON_YOLU)

        # templates/index.html'deki koyu arkaplan (--bg) - GTK varsayilan tema
        # rengini eziyoruz ki tarayicidakiyle ayni his versin.
        stil = Gtk.CssProvider()
        stil.load_from_data(
            b"""
            window { background-color: #0b0c10; }
            label { color: #6b7080; }
            label.baslik {
                color: #6b7080;
                font-size: 11px;
                letter-spacing: 2px;
            }
            label.ipucu {
                color: #6b7080;
                font-size: 11px;
            }
            """
        )
        Gtk.StyleContext.add_provider_for_screen(
            self.get_screen(), stil, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION
        )

        self._durum = "kapali"
        self._nabiz = 0.0
        self._panel_eristi_mi = True

        disari = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        disari.set_border_width(28)
        disari.set_halign(Gtk.Align.CENTER)
        disari.set_valign(Gtk.Align.CENTER)
        self.add(disari)

        baslik = Gtk.Label(label="SESLİ ORTAK")
        baslik.get_style_context().add_class("baslik")
        disari.pack_start(baslik, False, False, 0)

        self.orb = Gtk.DrawingArea()
        self.orb.set_size_request(ORB_CAP + 70, ORB_CAP + 70)
        self.orb.connect("draw", self._orb_ciz)
        self.orb.add_events(self.orb.get_events() | 0x200)  # BUTTON_PRESS_MASK
        self.orb.connect("button-press-event", self._orb_tiklandi)
        disari.pack_start(self.orb, False, False, 0)

        self.asama_etiketi = Gtk.Label(label="yükleniyor...")
        disari.pack_start(self.asama_etiketi, False, False, 0)

        ipucu = Gtk.Label(
            label="Açıkken direkt konuş, otomatik algılar.\nKonuşmayı bitirince kendiliğinden gönderir."
        )
        ipucu.get_style_context().add_class("ipucu")
        ipucu.set_justify(Gtk.Justification.CENTER)
        disari.pack_start(ipucu, False, False, 0)

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
        GLib.timeout_add(60, self._nabiz_tik)
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
        # dinliyor'da da yavas bir "nefes" var (templates/index.html'deki
        # #ring.dinliyor animasyonu), sadece konusuyor/isleniyor'da hizli nabiz.
        if self._durum in ("dinliyor", "konusuyor", "isleniyor"):
            hiz = 0.10 if self._durum == "dinliyor" else 0.28
            self._nabiz += hiz
            self.orb.queue_draw()
        return True

    def _orb_ciz(self, alan, cr):
        import cairo

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
        aktif_mi = self._durum not in ("kapali", "erisilemiyor")
        genlik = {"dinliyor": 0.06, "konusuyor": 0.10, "isleniyor": 0.03}.get(self._durum, 0.0)
        nabiz_carpani = 1.0 + genlik * math.sin(self._nabiz)

        # dis parlama: azalan opaklikta ustuste halkalar (CSS box-shadow'un
        # Cairo'da blur olmadan taklidi)
        if aktif_mi:
            for i, alfa in ((0, 0.10), (1, 0.06), (2, 0.03)):
                cr.set_source_rgba(*renk, alfa)
                cr.arc(merkez_x, merkez_y, (yaricap + 8 + i * 14) * nabiz_carpani, 0, 2 * math.pi)
                cr.fill()

        # dis halka (statik cizgi, templates'teki #ring)
        cr.set_source_rgba(*renk, 0.55 if aktif_mi else 0.3)
        cr.set_line_width(2)
        if self._durum == "isleniyor":
            cr.set_dash([6, 4])
        cr.arc(merkez_x, merkez_y, yaricap + 32, 0, 2 * math.pi)
        cr.stroke()
        cr.set_dash([])

        # ic top - radyal gradyan (templates'teki radial-gradient(35% 30%))
        yaricap_top = yaricap * (nabiz_carpani if aktif_mi else 1.0)
        gradyan = cairo.RadialGradient(
            merkez_x - yaricap_top * 0.3, merkez_y - yaricap_top * 0.35, 1,
            merkez_x, merkez_y, yaricap_top,
        )
        acik = tuple(min(c * 1.7, 1.0) for c in renk)
        koyu = tuple(c * 0.35 for c in renk)
        gradyan.add_color_stop_rgb(0, *acik)
        gradyan.add_color_stop_rgb(1, *koyu)
        cr.set_source(gradyan)
        cr.arc(merkez_x, merkez_y, yaricap_top, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgb(*RENK_METIN)
        cr.select_font_face("sans-serif")
        cr.set_font_size(13)
        metin = "Durdur" if aktif_mi else "Başlat"
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
