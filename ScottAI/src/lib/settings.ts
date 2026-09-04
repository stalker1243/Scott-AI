import { load, type Store } from "@tauri-apps/plugin-store";
import { useThemeStore } from "../store/useThemeStore";
import { useProfileStore } from "../store/useProfileStore";
import { useDeviceStore } from "../store/useDeviceStore";

const DEFAULT_BACKEND_URL = "http://127.0.0.1:8000";

let storePromise: Promise<Store> | null = null;

function getStore(): Promise<Store> {
  if (!storePromise) {
    storePromise = load("settings.json", { autoSave: false });
  }
  return storePromise;
}

export function getBackendUrl(): string {
  return DEFAULT_BACKEND_URL;
}

/** Загрузить сохранённые настройки и применить их к сторам при старте приложения. */
export async function loadSettings(): Promise<void> {
  const store = await getStore();

  const style = (await store.get<string>("style")) ?? "classic";
  const darkMode = (await store.get<boolean>("darkMode")) ?? true;
  const accent = (await store.get<string>("accent")) ?? "#3b82f6";
  const glassOpacity = (await store.get<number>("glassOpacity")) ?? 0.35;
  const profileName = (await store.get<string>("profileName")) ?? "";
  const profileBio = (await store.get<string>("profileBio")) ?? "";
  const profileAvatar = (await store.get<string>("profileAvatar")) ?? null;
  const micDeviceId = (await store.get<string>("micDeviceId")) ?? null;
  const speakerDeviceId = (await store.get<string>("speakerDeviceId")) ?? null;
  const handsFreeEnabled = (await store.get<boolean>("handsFreeEnabled")) ?? false;
  const ttsVoice = (await store.get<string>("ttsVoice")) ?? null;

  useThemeStore.getState().hydrate({
    style: style as "classic" | "glass" | "terminal",
    darkMode,
    accent,
    glassOpacity,
  });
  useProfileStore.getState().hydrate({ name: profileName, bio: profileBio, avatarDataUrl: profileAvatar });
  useDeviceStore.getState().hydrate({ micDeviceId, speakerDeviceId, handsFreeEnabled, ttsVoice });
}

/** Сохранить текущее состояние тем на диск (вызывается после каждого изменения). */
export async function saveThemeSettings(): Promise<void> {
  const store = await getStore();
  const { style, darkMode, accent, glassOpacity } = useThemeStore.getState();
  await store.set("style", style);
  await store.set("darkMode", darkMode);
  await store.set("accent", accent);
  await store.set("glassOpacity", glassOpacity);
  await store.save();
}

/** Сохранить профиль пользователя на диск. */
export async function saveProfileSettings(): Promise<void> {
  const store = await getStore();
  const { name, bio, avatarDataUrl } = useProfileStore.getState();
  await store.set("profileName", name);
  await store.set("profileBio", bio);
  await store.set("profileAvatar", avatarDataUrl);
  await store.save();
}

/** Сохранить выбор аудио-устройств (микрофон/вывод звука) и режим hands-free. */
export async function saveDeviceSettings(): Promise<void> {
  const store = await getStore();
  const { micDeviceId, speakerDeviceId, handsFreeEnabled, ttsVoice } = useDeviceStore.getState();
  await store.set("micDeviceId", micDeviceId);
  await store.set("speakerDeviceId", speakerDeviceId);
  await store.set("handsFreeEnabled", handsFreeEnabled);
  await store.set("ttsVoice", ttsVoice);
  await store.save();
}
