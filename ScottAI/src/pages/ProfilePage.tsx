import { useState } from "react";
import { AnimatePresence } from "framer-motion";
import { User, Save, Check, ImagePlus, Trash2, Move } from "lucide-react";
import { open } from "@tauri-apps/plugin-dialog";
import { readFile } from "@tauri-apps/plugin-fs";
import { AccentButton, GhostButton } from "../components/Button";
import { StyledInput } from "../components/Input";
import { AvatarCropModal } from "../components/AvatarCropModal";
import { useProfileStore } from "../store/useProfileStore";
import { useThemeStore } from "../store/useThemeStore";
import { saveProfileSettings } from "../lib/settings";
import { bytesToDataUrl, extensionToMime } from "../lib/image";

export function ProfilePage() {
  const { name, bio, avatarDataUrl, setName, setBio, setAvatar } = useProfileStore();
  const accent = useThemeStore((s) => s.accent);
  const [savedRecently, setSavedRecently] = useState(false);
  const [avatarError, setAvatarError] = useState<string | null>(null);
  const [pickingAvatar, setPickingAvatar] = useState(false);
  const [cropSource, setCropSource] = useState<string | null>(null);

  const handleSave = async () => {
    await saveProfileSettings();
    setSavedRecently(true);
    setTimeout(() => setSavedRecently(false), 2000);
  };

  const handlePickAvatar = async () => {
    setAvatarError(null);
    try {
      const path = await open({
        multiple: false,
        filters: [{ name: "Изображения", extensions: ["png", "jpg", "jpeg", "bmp", "gif"] }],
      });
      if (!path || typeof path !== "string") return;

      setPickingAvatar(true);
      const bytes = await readFile(path);
      const rawDataUrl = bytesToDataUrl(bytes, extensionToMime(path));
      setCropSource(rawDataUrl);
    } catch (err) {
      setAvatarError(String(err));
    } finally {
      setPickingAvatar(false);
    }
  };

  const handleAdjustPosition = () => {
    if (avatarDataUrl) setCropSource(avatarDataUrl);
  };

  const handleCropConfirm = async (croppedDataUrl: string) => {
    setCropSource(null);
    setAvatar(croppedDataUrl);
    await saveProfileSettings();
  };

  const handleRemoveAvatar = async () => {
    setAvatar(null);
    await saveProfileSettings();
  };

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-2xl flex-col gap-7">
        <h1 className="text-[30px] font-bold" style={{ color: "var(--text-primary)" }}>
          Профиль
        </h1>

        <div className="flex items-center gap-6">
          <div
            className="relative flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-full"
            style={{ background: accent, boxShadow: `0 8px 20px -4px ${accent}80` }}
          >
            {avatarDataUrl ? (
              <img src={avatarDataUrl} alt="Аватар" className="h-full w-full object-cover" />
            ) : (
              <User size={44} color="white" strokeWidth={1.8} />
            )}
          </div>
          <div className="flex flex-col gap-2">
            <span className="text-xl font-bold" style={{ color: "var(--text-primary)" }}>
              {name || "Без имени"}
            </span>
            <span className="text-[13px]" style={{ color: "var(--text-muted)" }}>
              Локальный профиль Scott AI
            </span>
            <div className="flex gap-2">
              <GhostButton text={pickingAvatar ? "Загрузка..." : "Изменить фото"} icon={ImagePlus} onClick={handlePickAvatar} disabled={pickingAvatar} />
              {avatarDataUrl && <GhostButton text="Положение" icon={Move} onClick={handleAdjustPosition} />}
              {avatarDataUrl && <GhostButton icon={Trash2} danger onClick={handleRemoveAvatar} />}
            </div>
          </div>
        </div>

        {avatarError && (
          <div className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm" style={{ borderColor: "var(--danger)", color: "var(--danger)" }}>
            {avatarError}
          </div>
        )}

        <div className="flex flex-col gap-2">
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            Имя
          </span>
          <StyledInput value={name} onChange={setName} placeholder="Как к вам обращаться?" />
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            О себе
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Эта информация поможет Scott давать более персональные ответы.
          </span>
          <StyledInput
            value={bio}
            onChange={setBio}
            multiline
            placeholder="Расскажите немного о себе, ваших интересах и предпочтениях..."
          />
        </div>

        <div className="flex items-center gap-3.5">
          <AccentButton text="Сохранить" icon={Save} onClick={handleSave} className="w-[200px]" />
          {savedRecently && (
            <div className="flex items-center gap-1.5" style={{ color: "var(--success)" }}>
              <Check size={16} strokeWidth={2.5} />
              <span className="text-sm font-semibold">Сохранено</span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-1.5">
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            Вход через сторонние сервисы
          </span>
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            Появится в будущих обновлениях. Сейчас профиль хранится локально на этом устройстве.
          </span>
        </div>
      </div>

      <AnimatePresence>
        {cropSource && <AvatarCropModal imageDataUrl={cropSource} onCancel={() => setCropSource(null)} onConfirm={handleCropConfirm} />}
      </AnimatePresence>
    </div>
  );
}
