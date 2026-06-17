class PcmCaptureProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    this.buffer = new Float32Array(0);
    this.targetFrames = 2048;
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || input[0].length === 0) {
      return true;
    }

    const channel = input[0];
    const merged = new Float32Array(this.buffer.length + channel.length);
    merged.set(this.buffer);
    merged.set(channel, this.buffer.length);
    this.buffer = merged;

    while (this.buffer.length >= this.targetFrames) {
      const chunk = this.buffer.slice(0, this.targetFrames);
      this.port.postMessage(chunk, [chunk.buffer]);
      this.buffer = this.buffer.slice(this.targetFrames);
    }

    return true;
  }
}

registerProcessor("pcm-capture-processor", PcmCaptureProcessor);
