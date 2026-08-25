#!/bin/bash
# Kisayol tusuyla su an acik olan kaydi (varsa) hemen bitirip isler/gonderir -
# tarayici panelindeki "Bitirdim, gonder" butonuyla aynisi. /degistir'in
# aksine sureci OLDURMEZ, dinlemeye devam eder. Arka plan gurultusu (fan,
# ezan vb.) yuzunden otomatik sessizlik algisi tetiklenmezse bunun icin var.
curl -s -X POST http://127.0.0.1:5005/bitir > /dev/null
