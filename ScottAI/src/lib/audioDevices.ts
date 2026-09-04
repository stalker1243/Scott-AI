export interface AudioDeviceInfo {
  deviceId: string;
  label: string;
}

export async function listAudioDevices(): Promise<{ mics: AudioDeviceInfo[]; speakers: AudioDeviceInfo[] }> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return {
    mics: devices
      .filter((d) => d.kind === "audioinput")
      .map((d) => ({ deviceId: d.deviceId, label: d.label || `Микрофон ${d.deviceId.slice(0, 6)}` })),
    speakers: devices
      .filter((d) => d.kind === "audiooutput")
      .map((d) => ({ deviceId: d.deviceId, label: d.label || `Устройство вывода ${d.deviceId.slice(0, 6)}` })),
  };
}

/** Разрешить доступ к микрофону кратким запросом — без этого enumerateDevices()
 * возвращает устройства без человекочитаемых названий (пустой label). */
export async function requestMicPermission(): Promise<void> {
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  stream.getTracks().forEach((t) => t.stop());
}

export function supportsOutputDeviceSelection(): boolean {
  return typeof AudioContext !== "undefined" && "setSinkId" in AudioContext.prototype;
}
