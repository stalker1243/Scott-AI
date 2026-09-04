import { create } from "zustand";

export interface ChatMessage {
  id: string;
  fromUser: boolean;
  text: string;
  time: string;
  imageDataUrl?: string;
}

interface PendingImage {
  dataUrl: string;
  name: string;
}

interface ChatState {
  messages: ChatMessage[];
  draft: string;
  sending: boolean;
  pendingImage: PendingImage | null;
  autoSpeak: boolean;
  isRecording: boolean;
  handsFreeStatus: "idle" | "listening" | "awaiting-command" | "processing";
  addMessage: (m: Omit<ChatMessage, "id">) => void;
  setDraft: (text: string) => void;
  setSending: (v: boolean) => void;
  setPendingImage: (img: PendingImage | null) => void;
  setAutoSpeak: (v: boolean) => void;
  setIsRecording: (v: boolean) => void;
  setHandsFreeStatus: (v: ChatState["handsFreeStatus"]) => void;
  newChat: () => void;
}

let idCounter = 0;
const nextId = () => `${Date.now()}-${idCounter++}`;

export const useChatStore = create<ChatState>((set) => ({
  messages: [
    {
      id: nextId(),
      fromUser: false,
      text: "Привет! Я Scott. Нажмите «Запустить Scott» на главной или просто напишите мне здесь.",
      time: new Date().toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" }),
    },
  ],
  draft: "",
  sending: false,
  pendingImage: null,
  autoSpeak: false,
  isRecording: false,
  handsFreeStatus: "idle",
  addMessage: (m) => set((state) => ({ messages: [...state.messages, { ...m, id: nextId() }] })),
  setDraft: (draft) => set({ draft }),
  setSending: (sending) => set({ sending }),
  setPendingImage: (pendingImage) => set({ pendingImage }),
  setAutoSpeak: (autoSpeak) => set({ autoSpeak }),
  setIsRecording: (isRecording) => set({ isRecording }),
  setHandsFreeStatus: (handsFreeStatus) => set({ handsFreeStatus }),
  newChat: () => set({ messages: [] }),
}));
