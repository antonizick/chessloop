/**
 * Chess piece sound effects — generated procedurally via Web Audio API.
 * No audio files needed; the sounds are synthesized inline.
 *
 * playMoveSound()  — wooden thud for a normal piece placement
 * playCaptureSound() — sharper crack for a capture
 */

let ctx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!ctx || ctx.state === "closed") {
    ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
  }
  // Resume if suspended (browser autoplay policy)
  if (ctx.state === "suspended") ctx.resume();
  return ctx;
}

/** Short band-passed white-noise burst that sounds like wood-on-wood. */
function playNoiseBurst(
  durationSec: number,
  gainPeak: number,
  lowpassHz: number,
  pitchShift = 1,
) {
  const audio = getAudioContext();
  const sampleRate = audio.sampleRate;
  const frameCount = Math.floor(sampleRate * durationSec);

  const buffer = audio.createBuffer(1, frameCount, sampleRate);
  const data = buffer.getChannelData(0);

  // Decaying white noise — exponential envelope
  const tau = frameCount / (5 * pitchShift); // decay constant
  for (let i = 0; i < frameCount; i++) {
    data[i] = (Math.random() * 2 - 1) * Math.exp(-i / tau);
  }

  const source = audio.createBufferSource();
  source.buffer = buffer;

  // Low-pass filter → removes harsh highs, leaves wooden "thud"
  const lpf = audio.createBiquadFilter();
  lpf.type = "lowpass";
  lpf.frequency.value = lowpassHz;
  lpf.Q.value = 0.7;

  // Short peak then immediate decay
  const gain = audio.createGain();
  gain.gain.setValueAtTime(gainPeak, audio.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + durationSec);

  source.connect(lpf);
  lpf.connect(gain);
  gain.connect(audio.destination);
  source.start(audio.currentTime);
}

/** Standard piece placement — a soft wooden clack. */
export function playMoveSound(): void {
  try {
    playNoiseBurst(0.08, 0.4, 1800, 1);
  } catch {
    // Silently ignore if audio isn't available
  }
}

/** Capture — slightly louder and brighter crack. */
export function playCaptureSound(): void {
  try {
    playNoiseBurst(0.12, 0.6, 2400, 1.4);
  } catch {
    // Silently ignore if audio isn't available
  }
}
