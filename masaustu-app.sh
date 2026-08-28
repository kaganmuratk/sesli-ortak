#!/bin/bash
# Sesli Ortak'ı bağımsız bir masaüstü uygulaması gibi açar. İlk sürüm Chrome
# --app modunu (ayrı pencere ama yine de tam bir tarayıcı süreci) kullanıyordu
# - Kağan Murat "gerçek uygulama olsun, tarayıcı açmasın" dedi (2026-08-28),
# bu yüzden masaustu-app.py (GTK3, tarayıcısız native pencere) ile değiştirildi.
# Panel (kontrol_sunucu.py, Flask) API'si hâlâ arkada çalışıyor - bu script ona
# native bir arayüz veriyor, kendisi bir şey render etmiyor.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANEL_URL="http://127.0.0.1:5005"

# Panel (kontrol_sunucu.py) zaten çalışıyor mu diye bak, çalışmıyorsa başlat.
if ! curl -s -o /dev/null -m 1 "$PANEL_URL/durum"; then
    echo "[masaustu-app] panel calismiyor, baslatiliyor..." >&2
    nohup "$HERE/.venv/bin/python3" "$HERE/kontrol_sunucu.py" \
        >>"$HERE/kontrol_sunucu.log" 2>&1 &
    disown
    # Panel ayaga kalkana kadar kisa bir bekleme (en fazla ~5sn).
    for _ in $(seq 1 25); do
        curl -s -o /dev/null -m 1 "$PANEL_URL/durum" && break
        sleep 0.2
    done
fi

# masaustu-app.py GTK/PyGObject kullanıyor - gosterge.py'deki gibi bilerek
# sistem Python'u (proje venv'inde PyGObject yok).
exec /usr/bin/python3 "$HERE/masaustu-app.py"
