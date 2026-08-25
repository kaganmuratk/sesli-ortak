"""Sesli Ortak - ekranin sol-alt kösesinde her zaman görünen küçük durum
göstergesi. "Sesli ortak arka planda beni dinliyor mu, kapalı mı, bir şey
mi kaydediyor?" sorusunu tarayıcıdaki kontrol panelini açmaya gerek
kalmadan tek bakışta cevaplamak için var (2026-08-24, Kağan Murat'ın
isteğiyle eklendi).

kontrol_sunucu.py tarafından alt-süreç olarak başlatılır/kapatılır - kendi
başına da çalıştırılabilir, o zaman /durum'a erişemezse "kapalı" gösterir.

XWayland üzerinden çalışır (GDK_BACKEND=x11) - Wayland'da bir istemci
penceresi "her zaman üstte" olmayı kendi başına isteyemez, bu compositor'ın
kararıdır; ama KWin, XWayland istemcileri için klasik X11 window-manager
override-redirect (POPUP) penceresini olduğu gibi destekliyor - kurulum
gerektiren gtk-layer-shell yerine bilinçli olarak bu yol seçildi.
"""

import json
import os

os.environ.setdefault("GDK_BACKEND", "x11")

import math
import sys
import urllib.request
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
from gi.repository import Gdk, GLib, Gtk  # noqa: E402

DURUM_URL = os.environ.get("SESLI_ORTAK_DURUM_URL", "http://127.0.0.1:5005/durum")

HERE = Path(__file__).parent
KOSE_DOSYASI = HERE / ".gosterge_kose"

GENISLIK, YUKSEKLIK = 190, 32
KENAR_BOSLUGU_X, KENAR_BOSLUGU_Y = 16, 40

# Surukleyip birakinca en yakinina yapisilan dort kose (2026-08-25, kullanici
# istegi - eskiden sabit sol-alttaydi, terminaldeki yaziyi kapatiyordu).
KOSELER = ("sol-alt", "sag-alt", "sol-ust", "sag-ust")
VARSAYILAN_KOSE = "sol-alt"

# templates/index.html ile aynı palet (--bg/--idle/--awake/--busy/--text)
RENK_BG = (0.043, 0.047, 0.063, 0.88)
RENK_DIM = (0.29, 0.31, 0.36)
RENK_DINLIYOR = (0.227, 0.427, 0.941)
RENK_KONUSUYOR = (0.941, 0.651, 0.227)
RENK_ISLENIYOR = (0.604, 0.361, 0.941)
RENK_METIN = (0.843, 0.851, 0.878)

DURUM_GORSELLERI = {
    "kapali": (RENK_DIM, "Sesli Ortak: Kapalı"),
    "dinliyor": (RENK_DINLIYOR, "Dinliyor"),
    "konusuyor": (RENK_KONUSUYOR, "Kaydediyor…"),
    "isleniyor": (RENK_ISLENIYOR, "İşleniyor…"),
}


def _kose_oku() -> str:
    try:
        kose = KOSE_DOSYASI.read_text().strip()
    except OSError:
        return VARSAYILAN_KOSE
    return kose if kose in KOSELER else VARSAYILAN_KOSE


def _kose_yaz(kose: str):
    try:
        KOSE_DOSYASI.write_text(kose)
    except OSError:
        pass


class Gosterge(Gtk.Window):
    def __init__(self):
        super().__init__(type=Gtk.WindowType.POPUP)
        self.set_app_paintable(True)
        self.set_decorated(False)
        self.set_can_focus(False)
        self.set_accept_focus(False)
        self.set_default_size(GENISLIK, YUKSEKLIK)
        self.stick()

        ekran = self.get_screen()
        rgba = ekran.get_rgba_visual()
        if rgba is not None:
            self.set_visual(rgba)

        self._durum = "kapali"
        self._nabiz = 0.0
        self._kose = _kose_oku()
        self._surukleniyor = False
        self._surukleme_baslangic_isaretci = (0, 0)
        self._surukleme_baslangic_pencere = (0, 0)

        self.alan = Gtk.DrawingArea()
        self.alan.set_size_request(GENISLIK, YUKSEKLIK)
        self.alan.connect("draw", self._ciz)
        self.alan.add_events(
            Gdk.EventMask.BUTTON_PRESS_MASK
            | Gdk.EventMask.BUTTON_RELEASE_MASK
            | Gdk.EventMask.POINTER_MOTION_MASK
        )
        self.alan.connect("button-press-event", self._surukleme_baslat)
        self.alan.connect("motion-notify-event", self._surukleme_hareket)
        self.alan.connect("button-release-event", self._surukleme_bitir)
        self.add(self.alan)

        self._konumlandir()

        GLib.timeout_add(400, self._durumu_guncelle)
        GLib.timeout_add(80, self._nabiz_tik)

    def _kose_geometrisi(self, kose, geo):
        if kose == "sag-alt":
            return (
                geo.x + geo.width - GENISLIK - KENAR_BOSLUGU_X,
                geo.y + geo.height - YUKSEKLIK - KENAR_BOSLUGU_Y,
            )
        if kose == "sol-ust":
            return geo.x + KENAR_BOSLUGU_X, geo.y + KENAR_BOSLUGU_Y
        if kose == "sag-ust":
            return geo.x + geo.width - GENISLIK - KENAR_BOSLUGU_X, geo.y + KENAR_BOSLUGU_Y
        return geo.x + KENAR_BOSLUGU_X, geo.y + geo.height - YUKSEKLIK - KENAR_BOSLUGU_Y  # sol-alt

    def _konumlandir(self):
        display = self.get_screen().get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        x, y = self._kose_geometrisi(self._kose, geo)
        self.move(x, y)

    def _surukleme_baslat(self, widget, event):
        if event.button != 1:
            return False
        self._surukleniyor = True
        self._surukleme_baslangic_isaretci = (event.x_root, event.y_root)
        self._surukleme_baslangic_pencere = self.get_position()
        return True

    def _surukleme_hareket(self, widget, event):
        if not self._surukleniyor:
            return False
        dx = event.x_root - self._surukleme_baslangic_isaretci[0]
        dy = event.y_root - self._surukleme_baslangic_isaretci[1]
        self.move(
            int(self._surukleme_baslangic_pencere[0] + dx),
            int(self._surukleme_baslangic_pencere[1] + dy),
        )
        return True

    def _surukleme_bitir(self, widget, event):
        if event.button != 1 or not self._surukleniyor:
            return False
        self._surukleniyor = False
        self._en_yakin_koseye_yapistir()
        return True

    def _en_yakin_koseye_yapistir(self):
        display = self.get_screen().get_display()
        monitor = display.get_primary_monitor() or display.get_monitor(0)
        geo = monitor.get_geometry()
        pencere_x, pencere_y = self.get_position()
        merkez_x = pencere_x + GENISLIK / 2
        merkez_y = pencere_y + YUKSEKLIK / 2
        sol = merkez_x < geo.x + geo.width / 2
        ust = merkez_y < geo.y + geo.height / 2
        if sol and ust:
            self._kose = "sol-ust"
        elif not sol and ust:
            self._kose = "sag-ust"
        elif sol and not ust:
            self._kose = "sol-alt"
        else:
            self._kose = "sag-alt"
        self._konumlandir()
        _kose_yaz(self._kose)

    def _durumu_guncelle(self):
        try:
            with urllib.request.urlopen(DURUM_URL, timeout=0.5) as r:
                veri = json.loads(r.read())
        except Exception:
            veri = {"aktif": False}

        if not veri.get("aktif"):
            yeni = "kapali"
        elif veri.get("isleniyor"):
            yeni = "isleniyor"
        elif veri.get("konusuyor"):
            yeni = "konusuyor"
        else:
            yeni = "dinliyor"

        if yeni != self._durum:
            self._durum = yeni
            self.alan.queue_draw()
        return True

    def _nabiz_tik(self):
        if self._durum in ("konusuyor", "isleniyor"):
            self._nabiz += 0.25
            self.alan.queue_draw()
        return True

    def _ciz(self, alan, cr):
        genislik = alan.get_allocated_width()
        yukseklik = alan.get_allocated_height()
        yaricap = yukseklik / 2

        cr.set_source_rgba(*RENK_BG)
        self._yuvarlak_dikdortgen(cr, 0, 0, genislik, yukseklik, yaricap)
        cr.fill()

        renk, metin = DURUM_GORSELLERI[self._durum]
        nabizli_mi = self._durum in ("konusuyor", "isleniyor")
        parlaklik = 1.0 + (0.25 * math.sin(self._nabiz) if nabizli_mi else 0.0)

        merkez_x, merkez_y = yukseklik, yukseklik / 2
        cr.set_source_rgb(
            min(renk[0] * parlaklik, 1.0),
            min(renk[1] * parlaklik, 1.0),
            min(renk[2] * parlaklik, 1.0),
        )
        cr.arc(merkez_x, merkez_y, 5, 0, 2 * math.pi)
        cr.fill()

        cr.set_source_rgb(*RENK_METIN)
        cr.select_font_face("sans-serif")
        cr.set_font_size(12)
        _, _, _, metin_yuksekligi, _, _ = cr.text_extents(metin)
        cr.move_to(yukseklik + 14, yukseklik / 2 + metin_yuksekligi / 2)
        cr.show_text(metin)
        return False

    @staticmethod
    def _yuvarlak_dikdortgen(cr, x, y, genislik, yukseklik, yaricap):
        cr.new_sub_path()
        cr.arc(x + genislik - yaricap, y + yaricap, yaricap, -math.pi / 2, 0)
        cr.arc(x + genislik - yaricap, y + yukseklik - yaricap, yaricap, 0, math.pi / 2)
        cr.arc(x + yaricap, y + yukseklik - yaricap, yaricap, math.pi / 2, math.pi)
        cr.arc(x + yaricap, y + yaricap, yaricap, math.pi, 3 * math.pi / 2)
        cr.close_path()


def main():
    pencere = Gosterge()
    pencere.show_all()
    Gtk.main()


if __name__ == "__main__":
    main()
