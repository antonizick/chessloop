interface TTSOptions {
  voice?: string;
  rate?: number;
  pitch?: number;
}

class TextToSpeechService {
  private synth: SpeechSynthesis;
  private isEnabled = true;
  private defaultVoice = "Microsoft Zira";
  private rate = 1;
  private pitch = 1;

  constructor() {
    this.synth = window.speechSynthesis;
  }

  setEnabled(enabled: boolean) {
    this.isEnabled = enabled;
  }

  setDefaultVoice(voice: string) {
    this.defaultVoice = voice;
  }

  setRate(rate: number) {
    this.rate = Math.max(0.5, Math.min(2, rate));
  }

  setPitch(pitch: number) {
    this.pitch = Math.max(0.5, Math.min(2, pitch));
  }

  getAvailableVoices(): SpeechSynthesisVoice[] {
    return this.synth.getVoices();
  }

  speak(text: string, options?: TTSOptions): void {
    if (!this.isEnabled || !text || !text.trim()) return;

    // Stop any current speech
    this.stop();

    const utterance = new SpeechSynthesisUtterance(text);
    const voiceName = options?.voice || this.defaultVoice;
    const voices = this.getAvailableVoices();
    const selectedVoice = voices.find((v) => v.name === voiceName) || voices[0];

    if (selectedVoice) {
      utterance.voice = selectedVoice;
    }

    utterance.rate = options?.rate ?? this.rate;
    utterance.pitch = options?.pitch ?? this.pitch;

    this.synth.speak(utterance);
  }

  stop(): void {
    if (this.synth.speaking || this.synth.pending) {
      this.synth.cancel();
    }
  }

  isSpeaking(): boolean {
    return this.synth.speaking || this.synth.pending;
  }
}

export const ttsService = new TextToSpeechService();
