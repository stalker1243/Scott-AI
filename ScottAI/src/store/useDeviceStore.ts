import { create } from "zustand";

interface DeviceState {
  micDeviceId: string | null;
  speakerDeviceId: string | null;
  handsFreeEnabled: boolean;
  ttsVoice: string | null;
  setMicDeviceId: (id: string | null) => void;
  setSpeakerDeviceId: (id: string | null) => void;
  setHandsFreeEnabled: (v: boolean) => void;
  setTtsVoice: (voice: string | null) => void;
  hydrate: (partial: { micDeviceId: string | null; speakerDeviceId: string | null; handsFreeEnabled: boolean; ttsVoice: string | null }) => void;
}

export const useDeviceStore = create<DeviceState>((set) => ({
  micDeviceId: null,
  speakerDeviceId: null,
  handsFreeEnabled: false,
  ttsVoice: null,
  setMicDeviceId: (micDeviceId) => set({ micDeviceId }),
  setSpeakerDeviceId: (speakerDeviceId) => set({ speakerDeviceId }),
  setHandsFreeEnabled: (handsFreeEnabled) => set({ handsFreeEnabled }),
  setTtsVoice: (ttsVoice) => set({ ttsVoice }),
  hydrate: (partial) => set(partial),
}));
