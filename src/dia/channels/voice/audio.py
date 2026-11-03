"""Voice channel, audio side: microphone, utterances, speech to text, speech and playback."""

from __future__ import annotations

import asyncio
import logging
import statistics
from collections import deque
from pathlib import Path
from typing import TYPE_CHECKING

from dia.audit import ACTOR
from dia.channels.voice.helpers import VoiceBase, sentences, speakable
from dia.voice.audio import is_silent, rms, write_wav

if TYPE_CHECKING:
    pass

log = logging.getLogger("dia.voice")


class AudioMixin(VoiceBase):
    @property
    def recording(self) -> bool:
        return self._capture is not None or self.recorder.recording

    def _next_wav(self) -> Path:
        self._recordings += 1
        return self._tmp / f"request-{self._recordings}.wav"

    async def listen(self) -> None:
        ACTOR.set("voice")
        """Read the microphone continuously: wake word, then record until silence."""
        assert self.wake and self.mic
        await asyncio.to_thread(self.wake.prepare)
        await self.mic.start()
        log.info("voice: waiting for the wake word")
        samples = self.wake.chunk_samples
        chunk_s = samples / 16000
        noise: deque[float] = deque(maxlen=50)  # ~4 s of background level
        try:
            while (chunk := await self.mic.read(samples)) is not None:
                if self._capture is not None:
                    self._capture.append(chunk)
                elif self._utterance is not None:
                    self._follow_utterance(chunk, chunk_s, noise)
                elif not self._speaking:
                    noise.append(rms(chunk))
                    if self.wake.detect(chunk):
                        said = self.wake.take_text() if hasattr(self.wake, "take_text") else ""
                        voice = self.wake.take_audio() if hasattr(self.wake, "take_audio") else b""
                        self.wake.reset()
                        self.interrupt()
                        if len(said.split()) >= 2:  # "Hej Dia, jaka pogoda?" in one breath
                            self._state("processing")
                            self._spawn(self._handle_breath(said, voice))
                            continue
                        self._utterance = {"chunks": [], "speech": False, "silent": 0}
                        self._notify(self.phrases["listening"])
                        self._state("listening")
            log.warning("voice: the microphone stream ended")
        finally:
            await self.mic.stop()

    def _follow_utterance(self, chunk: bytes, chunk_s: float, noise: deque[float]) -> None:
        """Collect the request after the wake word; end it after a pause in speech."""
        u = self._utterance
        u["chunks"].append(chunk)
        floor = statistics.median(noise) if noise else 0.0
        if rms(chunk) > max(self.min_level, floor * 2.5):
            u["speech"], u["silent"] = True, 0
        elif u["speech"]:
            u["silent"] += 1
        # Durations in whole chunks: summing float seconds would drift.
        length = len(u["chunks"])
        if u["speech"] and (
            u["silent"] >= round(self.silence_s / chunk_s) or length >= self.max_s / chunk_s
        ):
            self._utterance = None
            self._spawn(self.process(write_wav(self._next_wav(), u["chunks"])))
            self._state("processing")
        elif not u["speech"] and length >= round(self.wait_s / chunk_s):
            self._utterance = None
            self._spawn(self.say(self.phrases["not_heard"]))

    async def process(self, audio: Path) -> None:
        ACTOR.set("voice")
        if is_silent(audio):
            audio.unlink(missing_ok=True)
            log.warning("recording is silent: wrong or muted input device?")
            await self.say(self.phrases["silence"])
            return
        speaker: str | None = None
        try:
            if self.speakers:
                from dia.voice.speaker import read_samples

                speaker = await self._identify(read_samples(audio))
            text = (await self.stt.transcribe(audio, self.language)).strip()
        except Exception as exc:
            log.exception("transcription failed")
            await self.say(self.phrases["error"].format(error=exc))
            return
        finally:
            audio.unlink(missing_ok=True)
        if not text:
            await self.say(self.phrases["not_heard"])
            return
        await self.handle_text(text, speaker)

    async def _identify(self, samples: list[float]) -> str | None:
        assert self.speakers
        who, score = await asyncio.to_thread(self.speakers.identify, samples)
        log.info("speaker: %s (%.2f)", who or "unknown", score)
        return who

    async def _handle_breath(self, text: str, pcm: bytes) -> None:
        """A request said with the wake word; its voice is the keyword's stretch of speech."""
        speaker = None
        if self.speakers:
            from dia.voice.speaker import pcm_samples

            speaker = await self._identify(pcm_samples(pcm))
        await self.handle_text(text, speaker)

    async def say(self, text: str) -> None:
        text = speakable(text, self.speak_max_chars)
        if not text:
            return
        if self.dia.quiet:  # quiet mode: show it, don't say it
            log.info("quiet mode, not saying: %s", text)
            self._notify(text)
            self._state("idle", text)
            return
        log.info("saying: %s", text)
        async with self._speech_lock:  # one reply at a time, never overlapping
            self._speaking = True  # so the wake word detector does not hear Dia herself
            self._interrupted = False
            self._state("speaking", text)
            try:
                await self._speak(sentences(text))
            except Exception:
                log.exception("speaking failed")
                self._notify(text)
            finally:
                self._speaking = False
                self._state("idle")
                if self.wake:
                    self.wake.reset()

    async def _speak(self, parts: list[str]) -> None:
        """Speak sentence by sentence: the next one is synthesized while the current
        one plays, so long answers start at once; an interruption ends them all."""
        if not self.tts.writes_file:
            for part in parts:
                if self._interrupted:
                    return
                await self.tts.synthesize(part, self._tmp / "reply.wav")
            return

        async def make(i: int) -> Path:
            path = self._tmp / f"reply-{i % 2}.wav"
            await self.tts.synthesize(parts[i], path)
            return path

        upcoming = asyncio.ensure_future(make(0))
        try:
            for i in range(len(parts)):
                wav = await upcoming
                if i + 1 < len(parts):
                    upcoming = asyncio.ensure_future(make(i + 1))
                if self._interrupted:
                    return
                await self.player.play(wav)
                if self._interrupted:
                    return
        finally:
            if not upcoming.done():
                upcoming.cancel()

    def interrupt(self) -> None:
        """Stop talking now (the shortcut, or the wake word, pressed while Dia talks)."""
        self._interrupted = True
        self.player.stop()
