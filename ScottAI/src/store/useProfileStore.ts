import { create } from "zustand";

interface ProfileState {
  name: string;
  bio: string;
  avatarDataUrl: string | null;
  savedRecently: boolean;
  setName: (name: string) => void;
  setBio: (bio: string) => void;
  setAvatar: (avatarDataUrl: string | null) => void;
  setSavedRecently: (v: boolean) => void;
  hydrate: (partial: { name: string; bio: string; avatarDataUrl: string | null }) => void;
}

export const useProfileStore = create<ProfileState>((set) => ({
  name: "",
  bio: "",
  avatarDataUrl: null,
  savedRecently: false,
  setName: (name) => set({ name }),
  setBio: (bio) => set({ bio }),
  setAvatar: (avatarDataUrl) => set({ avatarDataUrl }),
  setSavedRecently: (savedRecently) => set({ savedRecently }),
  hydrate: (partial) => set(partial),
}));
