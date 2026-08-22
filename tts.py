"""Metni sese cevirir. Once ElevenLabs (birincil), basarisiz olursa Piper (yerel fallback)."""

import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
PIPER_VOICE = HERE / "voices" / "tr_TR-dfki-medium.onnx"
PIPER_ARGS = [
    "--noise-scale", "1.0",
    "--noise-w-scale", "1.1",
    "--length-scale", "0.92",
    "--sentence-silence", "0.25",
]


def _load_env():
    env_path = HERE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip()
        if key and value and key not in os.environ:
            os.environ[key] = value


ELEVEN_MP3_PATH = HERE / "_son_cevap_elevenlabs.mp3"
ELEVEN_WAV_PATH = HERE / "_son_cevap_elevenlabs.wav"


def _speak_elevenlabs(text: str) -> bool:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        return False
    try:
        from elevenlabs.client import ElevenLabs
        from elevenlabs.types.voice_settings import VoiceSettings

        client = ElevenLabs(api_key=api_key)
        voice_id = os.environ.get("ELEVENLABS_VOICE_ID") or None
        audio_chunks = client.text_to_speech.convert(
            voice_id=voice_id or "j82ax9yhzfYwq9lDvRWL",  # varsayilan: Kadir Kayışcı (anadili Turkce, erkek)
            text=text,
            model_id="eleven_multilingual_v2",
            output_format="mp3_44100_128",  # ucretsiz planda calisan format
            voice_settings=VoiceSettings(speed=1.2),  # daha hizli (kullanici tekrar yavas buldu)
        )
        audio = b"".join(audio_chunks)
        ELEVEN_MP3_PATH.write_bytes(audio)

        # ffplay'i canli pipe ile her seferinde yeniden acmak yerine, mp3'u
        # bir kere wav'a cevirip paplay ile calıyoruz (Piper'la ayni yontem).
        conv = subprocess.run(
            ["ffmpeg", "-y", "-i", str(ELEVEN_MP3_PATH), str(ELEVEN_WAV_PATH)],
            capture_output=True,
        )
        if conv.returncode != 0:
            print(f"[tts] ffmpeg donusumu basarisiz: {conv.stderr.decode(errors='ignore')}", file=sys.stderr)
            return False

        subprocess.run(["paplay", str(ELEVEN_WAV_PATH)])
        return True
    except Exception as exc:
        print(f"[tts] ElevenLabs basarisiz oldu, Piper'a dusuluyor: {exc}", file=sys.stderr)
        return False


def _speak_piper(text: str) -> None:
    out_path = HERE / "_son_cevap.wav"
    proc = subprocess.run(
        ["python3", "-m", "piper", "-m", str(PIPER_VOICE), "-f", str(out_path)] + PIPER_ARGS,
        input=text,
        text=True,
        cwd=HERE,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"[tts] Piper de basarisiz oldu:\n{proc.stderr}", file=sys.stderr)
        return
    subprocess.run(["paplay", str(out_path)])


def speak(text: str) -> None:
    _load_env()
    text = text.strip()
    if not text:
        return
    if _speak_elevenlabs(text):
        return
    _speak_piper(text)


if __name__ == "__main__":
    ornek = sys.argv[1] if len(sys.argv) > 1 else "Merhaba, ben Ortak. Ses sistemi calisiyor."
    speak(ornek)
