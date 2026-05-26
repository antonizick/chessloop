/**
 * Chess piece sound effects — generated procedurally via Web Audio API.
 * No audio files needed; the sounds are synthesized inline.
 *
 * playMoveSound()    — wooden thud for a normal piece placement
 * playCaptureSound() — sharper crack for a capture
 * playCorrectSound() — ascending two-tone chime (success)
 * playWrongSound()   — descending buzz (incorrect move)
 *
 * All functions accept an optional `enabled` boolean (default true).
 * Pass `false` to silently skip — lets callers respect the user's sounds_on pref.
 */

let ctx: AudioContext | null = null;

function getAudioContext(): AudioContext {
  if (!ctx || ctx.state === "closed") {
    ctx = new (window.AudioContext || (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext)();
  }
  // Resume if suspended (browser autoplay policy)
  if (ctx.state === "suspended") {
    ctx.resume().catch(err => console.error("Failed to resume AudioContext:", err));
  }
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

/** Play a short tone at the given frequency with an ADSR-like envelope. */
function playTone(freq: number, durationSec: number, gainPeak: number, type: OscillatorType = "sine") {
  const audio = getAudioContext();
  const osc = audio.createOscillator();
  const gain = audio.createGain();

  osc.type = type;
  osc.frequency.value = freq;

  gain.gain.setValueAtTime(0, audio.currentTime);
  gain.gain.linearRampToValueAtTime(gainPeak, audio.currentTime + 0.01);
  gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + durationSec);

  osc.connect(gain);
  gain.connect(audio.destination);
  osc.start(audio.currentTime);
  osc.stop(audio.currentTime + durationSec);
}

// ─────────────────────────────────────────────────────────────────────────────

/** Standard piece placement — a soft wooden clack. */
export function playMoveSound(enabled = true): void {
  if (!enabled) {
    console.log("playMoveSound: disabled");
    return;
  }
  try {
    console.log("playMoveSound: playing");
    const ctx = getAudioContext();
    console.log("AudioContext state:", ctx.state, "sampleRate:", ctx.sampleRate);
    playNoiseBurst(0.08, 0.6, 1800, 1);
  } catch (e) {
    console.error("playMoveSound error:", e);
  }
}

/** Capture — slightly louder and brighter crack. */
export function playCaptureSound(enabled = true): void {
  if (!enabled) return;
  try {
    console.log("playCaptureSound: playing");
    playNoiseBurst(0.12, 0.75, 2400, 1.4);
  } catch (e) {
    console.error("playCaptureSound error:", e);
  }
}

/** Correct answer — ascending two-tone chime (C5 → E5). */
export function playCorrectSound(enabled = true): void {
  if (!enabled) return;
  try {
    console.log("playCorrectSound: playing");
    const audio = getAudioContext();
    playTone(523.25, 0.18, 0.5, "sine"); // C5, increased volume
    setTimeout(() => {
      // Schedule E5 slightly after so they're distinct
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.type = "sine";
      osc.frequency.value = 659.25; // E5
      gain.gain.setValueAtTime(0, audio.currentTime);
      gain.gain.linearRampToValueAtTime(0.5, audio.currentTime + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.25);
      osc.connect(gain);
      gain.connect(audio.destination);
      osc.start(audio.currentTime);
      osc.stop(audio.currentTime + 0.25);
    }, 100);
  } catch (e) {
    console.error("playCorrectSound error:", e);
  }
}

/** Wrong answer — descending buzz (A4 → E4) with noise layer. */
export function playWrongSound(enabled = true): void {
  if (!enabled) return;
  try {
    console.log("playWrongSound: playing");
    const audio = getAudioContext();
    // Low buzz
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = "sawtooth";
    osc.frequency.value = 220; // A3
    osc.frequency.exponentialRampToValueAtTime(165, audio.currentTime + 0.3); // slide down to E3
    gain.gain.setValueAtTime(0.35, audio.currentTime);
    gain.gain.exponentialRampToValueAtTime(0.001, audio.currentTime + 0.3);
    osc.connect(gain);
    gain.connect(audio.destination);
    osc.start(audio.currentTime);
    osc.stop(audio.currentTime + 0.3);
    // Noise layer for texture
    playNoiseBurst(0.15, 0.25, 800, 2);
  } catch (e) {
    console.error("playWrongSound error:", e);
  }
}

/** Navigation feedback — subtle tick for move history browsing. */
export function playNavigationSound(enabled = true): void {
  if (!enabled) return;
  try {
    console.log("playNavigationSound: playing");
    playNoiseBurst(0.04, 0.25, 2500, 0.8);
  } catch (e) {
    console.error("playNavigationSound error:", e);
  }
}
