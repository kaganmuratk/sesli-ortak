# Sesli Ortak

> Claude Code oturumunla sesle konuş, sesli cevap al — hepsi tam o an ekranında
> açık olan **aynı** terminal oturumunda. Ayrı bir pencere, ayrı bir uygulama yok.
>
> *(EN: A lightweight voice layer for Claude Code — speak to it and hear replies,
> synced to the exact terminal session you already have open. Linux/KDE Plasma only.)*

## Ne yapar

Claude Code'un kendi native `/voice` dikte özelliğini konuşmayı otomatik
başlatıp bitirecek şekilde tetikler, cevapları da (istersen) sesli okur.
Elini klavyeye götürmeden, "sesli mod" açıkken konuşmaya başladığın an
mikrofon algılar, Claude Code'un çalıştığı pencereye otomatik geçer,
konuşmanı yazıya döker ve gönderir. Cevap gelince de (ElevenLabs veya
tamamen ücretsiz yerel bir ses ile) sesli okur.

Uyandırma kelimesi yok — "sesli mod" düğmesini sen açıp kapatıyorsun, açıkken
her konuşma otomatik işlenir.

## Mimari

Üç bağımsız parça, hiçbiri Claude Code'un kendi mimarisine dokunmuyor:

1. **Girdi — Claude Code'un native `/voice`'u.** Konuşmayı yazıya çeviren asıl
   iş burada oluyor (resmi özellik, ücretsiz, `.claude/settings.json` içinde
   `"voice": {"enabled": true, "mode": "tap"}` ile açılır).
2. **Otomatik tetikleme — `tetikleyici.py`.** Mikrofonu sürekli dinler
   (WebRTC VAD ile konuşma/sessizlik ayrımı), konuşma başlayınca KWin
   scripting (`qdbus6`) ile doğru terminal penceresine odaklanıp `ydotool`
   ile Space'e basar (native kaydı başlatır/durdurur).
3. **Çıktı — `hook_konustur.py` + `tts.py`.** Claude Code'un `Stop` hook'undan
   tetiklenir, son cevabı ElevenLabs (birincil) ya da Piper (tamamen yerel/
   ücretsiz yedek) ile seslendirir.

Üç parça arasında dosya tabanlı basit kilitler var (`.ortak_konusuyor` vb.) —
soket veya kuyruk yok, kasıtlı olarak basit tutuldu.

## Önkoşullar

Bu araç **Linux + KDE Plasma (Wayland)** için yazıldı, pencere odaklama KWin'in
script API'sine dayanıyor. Farklı bir masaüstü ortamında (GNOME, Windows, macOS)
`tetikleyici.py`'deki `_kwin_script_yukle`/`_odakla` fonksiyonlarını kendi
platformunun pencere yönetimine göre uyarlaman gerekir.

- Linux, KDE Plasma 6 (Wayland)
- `qdbus6` (KDE ile birlikte gelir)
- `ydotool` + `ydotoold` (çalışır durumda; syntetik tuş basma için)
- [`uv`](https://docs.astral.sh/uv/) (Python paket/venv yönetimi)
- `ffmpeg`, `paplay` (ses dönüştürme/çalma)
- Claude Code hesabı, `/voice` özelliği açık
- (Opsiyonel ama önerilir) [ElevenLabs](https://elevenlabs.io) hesabı — ücretsiz
  planı yeterli. Hiç istemiyorsan tamamen atlanabilir, sistem otomatik olarak
  yerel/ücretsiz Piper TTS'e düşer.

## Kurulum

```bash
git clone <bu-repo> sesli-ortak
cd sesli-ortak
uv sync                                   # bağımlılıkları kurar, .venv oluşturur
uv run python3 -m piper.download_voices tr_TR-dfki-medium   # ücretsiz yedek ses modeli
cp .env.example .env
```

`.env` dosyasını doldur:

- `ELEVENLABS_API_KEY`, `ELEVENLABS_VOICE_ID` — istersen (boş bırakırsan
  doğrudan Piper kullanılır).
- `ORTAK_PENCERE_ANAHTARI` — **zorunlu.** Claude Code'u çalıştırdığın terminal
  penceresinin başlığından geçen, benzersiz bir kelime (örn. proje klasör adın).
- `ORTAK_TERMINAL_SINIFI` — Konsole dışında bir terminal kullanıyorsan değiştir.

Claude Code tarafında (`.claude/settings.json`, kendi projenin kökünde):

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

`claude-hooks/speak-if-voice.sh` dosyasını kendi projenin `.claude/hooks/`
klasörüne kopyala (içindeki yol varsayımını kendi klasör yapına göre kontrol et).

## Kullanım

```bash
uv run python3 kontrol_sunucu.py
```

`http://127.0.0.1:5005` adresinde küçük bir kontrol paneli açılır: mikrofon
dinlemeyi aç/kapat, sesli cevabı bağımsız olarak aç/kapat, çalan sesi anında
kesmek için bir "Kes" düğmesi. Mikrofonu açtığında (sesli mod), konuşmaya
başladığın an otomatik algılanır — hiçbir tuşa basmana gerek yok.

## Bilinen sınırlamalar

- İlk 1-2 kelime bazen kırpılabilir (pencere odaklama + tuş gönderme gecikmesi,
  mimarinin doğal bir sınırı).
- Kulaklık kullanmadan hoparlörle geri besleme riski var (kendi sesini
  mikrofon algılayabilir) — kulaklık önerilir.
- Arka plan gürültüsü nadiren yanlış tetikleyip boş bir konuşma gönderebilir.
- Sadece KDE Plasma/Wayland + Konsole için test edildi.

## Neden böyle

Bu, Claude Code'la (bende "Ortak" adıyla ikinci beynim olarak çalışıyor) elimi
klavyeden kaldırmadan, aynı canlı oturumda konuşabilmek için kendi ihtiyacımdan
çıktı. Önce kendi STT/TTS altyapımı sıfırdan kurdum, sonra Claude Code'un
yerleşik `/voice`'unu keşfedip büyük kısmını sildim — geriye kalan, sadece
gerçekten gerekli olan bu üç parça.

## Lisans

MIT — [LICENSE](./LICENSE) dosyasına bak.
