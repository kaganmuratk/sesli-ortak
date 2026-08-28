#!/bin/bash
# Sesli Ortak'ı bağımsız bir masaüstü uygulaması gibi açar: kontrol panelini
# (Flask, 127.0.0.1:5005) tarayıcı sekmesi olarak değil, adres çubuğu/sekme
# barı olmayan ayrı bir Chrome penceresinde (--app modu) gösterir. Panel her
# zamanki gibi Flask üzerinden çalışmaya devam eder, bu script sadece ona
# native bir pencere kabuğu giydiriyor (2026-08-28, Kağan Murat'ın isteğiyle).
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PANEL_URL="http://127.0.0.1:5005"
PROFIL_DIZINI="$HOME/.cache/sesli-ortak-app-chrome"

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

exec google-chrome-stable \
    --app="$PANEL_URL" \
    --user-data-dir="$PROFIL_DIZINI" \
    --class=SesliOrtakApp \
    --window-size=420,560 \
    --no-first-run \
    --no-default-browser-check
