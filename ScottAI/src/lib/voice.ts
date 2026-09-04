// Воспроизведение TTS-ответа с лёгкой аудио-окраской в духе "ИИ-ассистента":
// не имитация конкретного голоса, а edge-tts голос (ru-RU-DmitryNeural) с
// небольшой EQ-формовкой (чуть меньше нижних частот, лёгкий подъём в
// средне-высоких для "синтетической" чёткости) — узнаваемо, но разборчиво.

let audioCtx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!audioCtx) {
    audioCtx = new AudioContext();
  }
  return audioCtx;
}

/** Возвращает промис, который резолвится когда воспроизведение ЗАВЕРШИЛОСЬ
 * (не когда началось) — нужно, чтобы фразы озвучивались по очереди, а не внахлёст.
 * sinkId — id устройства вывода (динамика), если пользователь выбрал конкретное
 * в Настройках; поддерживается не во всех версиях WebView2, ошибка тихо игнорируется. */
export async function playVoiceBlob(blob: Blob, robotic = true, sinkId?: string | null): Promise<void> {
  const ctx = getAudioContext();
  if (ctx.state === "suspended") await ctx.resume();

  if (sinkId && "setSinkId" in ctx) {
    try {
      await (ctx as AudioContext & { setSinkId(id: string): Promise<void> }).setSinkId(sinkId);
    } catch (err) {
      console.warn("[voice] setSinkId не поддерживается или недоступно устройство:", err);
    }
  }

  const arrayBuffer = await blob.arrayBuffer();
  const audioBuffer = await ctx.decodeAudioData(arrayBuffer);

  const source = ctx.createBufferSource();
  source.buffer = audioBuffer;

  if (robotic) {
    const highpass = ctx.createBiquadFilter();
    highpass.type = "highpass";
    highpass.frequency.value = 110;

    const presence = ctx.createBiquadFilter();
    presence.type = "peaking";
    presence.frequency.value = 2600;
    presence.Q.value = 1.1;
    presence.gain.value = 5;

    const lowpass = ctx.createBiquadFilter();
    lowpass.type = "lowpass";
    lowpass.frequency.value = 9500;

    const compressor = ctx.createDynamicsCompressor();
    compressor.threshold.value = -18;
    compressor.ratio.value = 3;

    source.connect(highpass).connect(presence).connect(lowpass).connect(compressor).connect(ctx.destination);
  } else {
    source.connect(ctx.destination);
  }

  return new Promise((resolve) => {
    source.onended = () => resolve();
    source.start();
  });
}
