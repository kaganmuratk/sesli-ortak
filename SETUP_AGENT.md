# Kurulum talimatı (AI ajanları için)

Bu dosya bir insana değil, bu repoyu kuran AI ajanına (Claude Code, Codex, vs.)
yazıldı. Kullanıcı "bu repoyu benim için kur" dediğinde, aşağıdaki adımları
sırayla, gerçekten çalıştırarak uygula — anlatma, yap.

## 0. Önce doğrula

Bu araç **sadece Linux + KDE Plasma (Wayland)** üzerinde çalışır (pencere
odaklama KWin script API'sine dayanıyor). Kullanıcının ortamını kontrol et:

```bash
echo $XDG_CURRENT_DESKTOP   # "KDE" içermeli
which qdbus6 ydotool uv ffmpeg paplay
```

Eksik binary varsa kullanıcıya söyle, hangi paket yöneticisiyle kurulacağını
bul (`pacman`, `apt`, vb.), kurulumu öner — kendi kararınla sessizce paket
kurma, kullanıcıya sor.

`ydotoold` daemon'ının çalışır durumda olduğunu doğrula (`pgrep ydotoold`);
çalışmıyorsa nasıl başlatılacağını kullanıcının dağıtımına göre araştır
(genelde bir systemd servisi veya elle `sudo ydotoold &`).

## 1. Bağımlılıkları kur

```bash
uv sync
uv run python3 -m piper.download_voices tr_TR-dfki-medium
```

## 2. .env oluştur

```bash
cp .env.example .env
```

Kullanıcıya sor:
- ElevenLabs kullanmak ister mi? (İstemezse `ELEVENLABS_API_KEY`'i boş bırak,
  sistem otomatik Piper'a düşer — tamamen ücretsiz.)
- `ORTAK_PENCERE_ANAHTARI` **zorunlu** — kullanıcının Claude Code'u çalıştırdığı
  terminal penceresinin başlığından geçen, benzersiz bir kelime olmalı
  (genelde proje klasör adı). Bunu tahmin etme, kullanıcıya sor ya da
  kendi çalıştığın oturumun pencere başlığını kontrol et.
- Konsole dışında bir terminal kullanıyorsa `ORTAK_TERMINAL_SINIFI`'nı
  o terminalin KWin `resourceClass`'ına göre ayarla (KWin script konsolundan
  ya da `qdbus6 org.kde.KWin ...` ile bulunabilir; kesin değilsen kullanıcıya
  sor).

## 3. Claude Code hook'unu bağla

Kullanıcının **kendi projesinin** `.claude/settings.json` dosyasını oku (yoksa
oluştur), şunu ekle/birleştir — var olan diğer hook'ları KORU, üzerine yazma:

```json
{
  "voice": { "enabled": true, "mode": "tap" },
  "hooks": {
    "Stop": [
      { "hooks": [{ "type": "command",
        "command": "\"$CLAUDE_PROJECT_DIR/.claude/hooks/speak-if-voice.sh\"",
        "timeout": 5 }] }
    ]
  }
}
```

`claude-hooks/speak-if-voice.sh`'ı kullanıcının projesindeki `.claude/hooks/`
klasörüne kopyala, içindeki `SESLI_DIR` yolunu bu reponun gerçek konumuna göre
düzelt, `chmod +x` yap.

## 4. Doğrula

```bash
uv run python3 tts.py "Merhaba, ben Ortak. Ses sistemi çalışıyor."
```

Ses duyulmalı. Duyulmuyorsa sırayla kontrol et: `.env` doğru mu, `paplay`
başka bir ses cihazına mı çalıyor, ElevenLabs key geçerli mi (hata mesajı
stderr'e basılır).

Sonra kontrol panelini başlat:

```bash
uv run python3 kontrol_sunucu.py
```

`http://127.0.0.1:5005` açılmalı. Kullanıcıya paneli göster, mikrofonu açıp
bir şey söylemesini iste, Claude Code'un doğru pencereye odaklanıp
konuşmayı yazıya döktüğünü birlikte doğrulayın.

## Düşük risk / yüksek risk ayrımı

Yukarıdaki adımların hepsi (bağımlılık kurma, .env doldurma, hook bağlama)
geri alınabilir ve düşük risklidir — kullanıcı "kur" dediyse tek tek onay
istemene gerek yok. Ama şunlarda mutlaka dur ve sor:
- `sudo` gerektiren bir adım (ör. `ydotoold` sistem servisi kurulumu)
- Kullanıcının var olan `.claude/settings.json`'ındaki başka hook'ları
  silmek/değiştirmek zorunda kalırsan
- ElevenLabs'e gerçek para harcanacaksa (ücretsiz planın dışına çıkarsa)
