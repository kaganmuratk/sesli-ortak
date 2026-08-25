#!/bin/bash
# Tek tuslu akilli kisayol (Kagan Murat'in Dikte'den alistigi Ctrl+Space icin):
# sesli-ortak kapaliysa baslatir, aciksa (dinliyor/kaydediyor fark etmez)
# "bitirdim, gonder" der - sureci OLDURMEZ. Tamamen kapatmak icin hala
# kisayol-toggle.sh (Ctrl+Alt+O) gerekiyor.
curl -s -X POST http://127.0.0.1:5005/baslat_veya_bitir > /dev/null
