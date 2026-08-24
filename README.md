# Sesli Ortak

> Claude Code oturumunla sesle konuş, sesli cevap al — hepsi tam o an ekranında
> açık olan **aynı** terminal oturumunda. Ayrı bir pencere, ayrı bir uygulama yok.
>
> *(EN: A lightweight voice layer for Claude Code — speak to it and hear replies,
> synced to the exact terminal session you already have open. Linux/Wayland only.)*

## Ne yapar

Elini klavyeye götürmeden, "sesli mod" açıkken konuşmaya başladığın an mikrofon
algılar, konuşmanı yazıya döker, o an odaktaki pencereye yapıştırır ve gönderir
(Enter). Pencere bulma/odaklama yok — neredeysen (Claude Code, herhangi bir
başka pencere) oraya gider. Cevap gelince de (ElevenLabs veya tamamen ücretsiz
yerel bir ses ile) sesli okur.

Uyandırma kelimesi yok — "sesli mod" düğmesini sen açıp kapatıyorsun, açıkken
her konuşma otomatik işlenir.

## Mimari

Dört bağımsız parça:

1. **Girdi — `dinleyici.py`.** Mikrofonu sürekli dinler (WebRTC VAD ile
   konuşma/sessizlik ayrımı), konuşma bitince Dikte (`~/dikte`) motorunu
   kullanıp transkribe eder, temizler, panoya kopyalar (`wl-copy`) ve
   `ydotool` ile yapıştırıp gönderir. Dikte'nin kendi felsefesi aynen
   geçerli: pencere odaklama yok, neredeysen oraya gider.
2. **Kontrol paneli — `kontrol_sunucu.py`.** `dinleyici.py` sürecini
   başlatır/durdurur, `http://127.0.0.1:5005`'te küçük bir panel sunar.
3. **Çıktı — `hook_konustur.py` + `tts.py`.** Claude Code'un `Stop` hook'undan
   tetiklenir, son cevabı ElevenLabs (birincil) ya da Piper (tamamen yerel/
   ücretsiz yedek) ile seslendirir.
4. **Ekran göstergesi — `gosterge.py`.** Ekranın sol-alt köşesinde kalıcı,
   küçük bir durum göstergesi: kapalı/dinliyor/kaydediyor/işleniyor. Kontrol
   panelini tarayıcıda açık tutmaya gerek kalmadan, sesli-ortak arka planda
   çalışırken bile "beni dinliyor mu?" sorusuna tek bakışta cevap verir.
   `kontrol_sunucu.py` tarafından otomatik başlatılır/kapatılır.

Parçalar arasında dosya tabanlı basit kilitler var (`.ortak_konusuyor` vb.) —
soket veya kuyruk yok, kasıtlı olarak basit tutuldu.

## Önkoşullar

Wayland (`wl-clipboard` panoya yazmak için) ve `ydotool` (syntetik tuş basma
için) gerekiyor; pencere yöneticisine özel bir bağımlılık yok (artık KWin/
qdbus6 gerekmiyor).

- Linux, Wayland
- Dikte kurulu olmalı (`~/dikte`) — transkripsiyon, temizleme ve pano/
  yapıştırma motoru buradan ödünç alınıyor
- `wl-clipboard` (`wl-copy`/`wl-paste`)
- `ydotool` + `ydotoold` (çalışır durumda; syntetik tuş basma için)
- [`uv`](https://docs.astral.sh/uv/) (Python paket/venv yönetimi)
- `ffmpeg`, `paplay` (ses dönüştürme/çalma)
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

Ayrıca Dikte'nin kendisi de kurulu ve yapılandırılmış olmalı (`~/dikte`,
`~/.config/dikte/config.json`) — transkripsiyon API'si, temizleme modeli gibi
ayarlar oradan okunuyor.

Claude Code tarafında, sesli cevap (çıktı) için `.claude/settings.json`
(kendi projenin kökünde):

```json
{
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

Aynı anda ekranın sol-alt köşesinde küçük bir durum göstergesi de belirir
(`gosterge.py`, otomatik başlar) — panel sekmesini açık tutmana gerek kalmadan
kapalı/dinliyor/kaydediyor/işleniyor durumunu her an gösterir.

## Bilinen sınırlamalar

- İlk ~300ms'lik konuşma başlangıcı VAD eşiğinin doğal gecikmesi yüzünden
  kırpılabilir (ön tampon bunu büyük ölçüde telafi ediyor ama tam değil).
- Kulaklık kullanmadan hoparlörle geri besleme riski var (kendi sesini
  mikrofon algılayabilir) — kulaklık önerilir.
- Arka plan gürültüsü nadiren yanlış tetikleyip boş bir konuşma gönderebilir.
- Wayland (`wl-clipboard` + `ydotool`) gerektiriyor; sadece KDE Plasma üzerinde
  test edildi ama pencere yöneticisine özel bir bağımlılığı yok.
- Ekran göstergesi (`gosterge.py`) XWayland üzerinden çalışıyor (GTK3 +
  `GDK_BACKEND=x11`) — sistem Python'unda PyGObject (`gi`) gerektirir, proje
  venv'inde değil. Bulunamazsa ya da XWayland yoksa sessizce başarısız olur,
  kontrol paneli/mikrofon bundan etkilenmez, sadece gösterge görünmez.

## Neden böyle

Bu, Claude Code'la (bende "Ortak" adıyla ikinci beynim olarak çalışıyor) elimi
klavyeden kaldırmadan, aynı canlı oturumda konuşabilmek için kendi ihtiyacımdan
çıktı. Önce kendi STT/TTS altyapımı sıfırdan kurdum, sonra Claude Code'un
yerleşik `/voice`'unu keşfedip büyük kısmını sildim; sonra da masaüstümdeki
Dikte uygulamasından ilham alıp girdi tarafını pencere odaklamayan, Dikte'nin
motorunu ödünç alan bugünkü haline getirdim — geriye kalan, sadece gerçekten
gerekli olan dört parça.

## Lisans

MIT — [LICENSE](./LICENSE) dosyasına bak.
