import { useEffect, useRef, useState } from "react";
import { motion } from "framer-motion";
import { ZoomIn, X, Check } from "lucide-react";
import { AccentButton, GhostButton } from "./Button";
import { useThemeStore } from "../store/useThemeStore";

const VIEWPORT = 280; // размер видимой круглой области на экране, px
const OUTPUT = 384; // размер сохраняемого файла — крупнее видимой области про запас под retina-экраны
const MIN_ZOOM = 1;
const MAX_ZOOM = 4;
// При zoom=1 (ровный cover-fit) хотя бы одна из осей (а для квадратных фото — обе)
// заполняется впритык, без запаса — перетаскивание в её направлении упирается
// сразу в оба предела и визуально не двигается. Стартуем чуть выше MIN_ZOOM,
// чтобы с самого начала был запас на перемещение по обеим осям.
const INITIAL_ZOOM = 1.2;

interface AvatarCropModalProps {
  imageDataUrl: string;
  onCancel: () => void;
  onConfirm: (croppedDataUrl: string) => void;
}

/** Модалка выбора положения аватарки: приближение и перетаскивание, чтобы в круг попало именно лицо. */
export function AvatarCropModal({ imageDataUrl, onCancel, onConfirm }: AvatarCropModalProps) {
  const accent = useThemeStore((s) => s.accent);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const imgRef = useRef<HTMLImageElement | null>(null);
  const draggingRef = useRef<{ startX: number; startY: number; startPanX: number; startPanY: number } | null>(null);

  const [ready, setReady] = useState(false);
  const [zoom, setZoom] = useState(INITIAL_ZOOM);
  const [pan, setPan] = useState({ x: 0, y: 0 });

  const getScale = (z: number) => {
    const img = imgRef.current;
    if (!img) return 1;
    return Math.max(VIEWPORT / img.width, VIEWPORT / img.height) * z;
  };

  const clampPan = (x: number, y: number, z: number) => {
    const img = imgRef.current;
    if (!img) return { x: 0, y: 0 };
    const scale = getScale(z);
    const drawnW = img.width * scale;
    const drawnH = img.height * scale;
    const minX = VIEWPORT - drawnW;
    const minY = VIEWPORT - drawnH;
    return { x: Math.min(0, Math.max(minX, x)), y: Math.min(0, Math.max(minY, y)) };
  };

  // Загружаем изображение один раз при открытии модалки и сразу центрируем
  // его при стартовом INITIAL_ZOOM (а не через отдельный эффект — раньше
  // центрирование считалось для zoom=1 отдельно от того, что реально
  // выставлялось в качестве стартового zoom, из-за чего расхождение).
  useEffect(() => {
    const img = new Image();
    img.onload = () => {
      imgRef.current = img;
      const scale = Math.max(VIEWPORT / img.width, VIEWPORT / img.height) * INITIAL_ZOOM;
      const drawnW = img.width * scale;
      const drawnH = img.height * scale;
      setZoom(INITIAL_ZOOM);
      setPan({ x: (VIEWPORT - drawnW) / 2, y: (VIEWPORT - drawnH) / 2 });
      setReady(true);
    };
    img.src = imageDataUrl;
  }, [imageDataUrl]);

  const draw = () => {
    const canvas = canvasRef.current;
    const img = imgRef.current;
    if (!canvas || !img) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;
    const scale = getScale(zoom);
    ctx.clearRect(0, 0, VIEWPORT, VIEWPORT);
    ctx.drawImage(img, pan.x, pan.y, img.width * scale, img.height * scale);
  };

  useEffect(() => {
    draw();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [zoom, pan, ready]);

  const handleZoomChange = (z: number) => {
    setZoom(z);
    setPan((prev) => clampPan(prev.x, prev.y, z));
  };

  const handlePointerDown = (e: React.PointerEvent<HTMLCanvasElement>) => {
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
    draggingRef.current = { startX: e.clientX, startY: e.clientY, startPanX: pan.x, startPanY: pan.y };
  };

  const handlePointerMove = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const drag = draggingRef.current;
    if (!drag) return;
    const dx = e.clientX - drag.startX;
    const dy = e.clientY - drag.startY;
    setPan(clampPan(drag.startPanX + dx, drag.startPanY + dy, zoom));
  };

  const handlePointerUp = () => {
    draggingRef.current = null;
  };

  const handleWheel = (e: React.WheelEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const delta = e.deltaY > 0 ? -0.08 : 0.08;
    handleZoomChange(Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom + delta)));
  };

  const handleConfirm = () => {
    const img = imgRef.current;
    if (!img) return;
    const outputScaleFactor = OUTPUT / VIEWPORT;
    const scale = getScale(zoom) * outputScaleFactor;
    const outCanvas = document.createElement("canvas");
    outCanvas.width = OUTPUT;
    outCanvas.height = OUTPUT;
    const ctx = outCanvas.getContext("2d");
    if (!ctx) return;
    ctx.drawImage(img, pan.x * outputScaleFactor, pan.y * outputScaleFactor, img.width * scale, img.height * scale);
    onConfirm(outCanvas.toDataURL("image/jpeg", 0.9));
  };

  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <motion.div
        initial={{ opacity: 0, scale: 0.95 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass-panel flex flex-col items-center gap-5 rounded-[var(--radius-md)] border p-6"
        style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
      >
        <span className="text-[15px] font-semibold" style={{ color: "var(--text-primary)" }}>
          Выберите положение фото
        </span>

        <div
          className="relative overflow-hidden rounded-full border-2"
          style={{ width: VIEWPORT, height: VIEWPORT, borderColor: accent, cursor: ready ? "grab" : "default" }}
        >
          <canvas
            ref={canvasRef}
            width={VIEWPORT}
            height={VIEWPORT}
            onPointerDown={handlePointerDown}
            onPointerMove={handlePointerMove}
            onPointerUp={handlePointerUp}
            onPointerLeave={handlePointerUp}
            onWheel={handleWheel}
            style={{ touchAction: "none" }}
          />
          {!ready && (
            <div className="absolute inset-0 flex items-center justify-center text-xs" style={{ color: "var(--text-muted)" }}>
              Загрузка...
            </div>
          )}
        </div>

        <div className="flex w-full items-center gap-2.5">
          <ZoomIn size={16} color="var(--text-secondary)" />
          <input
            type="range"
            min={MIN_ZOOM}
            max={MAX_ZOOM}
            step={0.01}
            value={zoom}
            onChange={(e) => handleZoomChange(Number(e.target.value))}
            className="w-full accent-current"
            style={{ color: accent }}
          />
        </div>

        <span className="text-xs" style={{ color: "var(--text-muted)" }}>
          Перетащите фото и настройте масштаб, чтобы в круг попало лицо
        </span>

        <div className="flex gap-2.5">
          <GhostButton text="Отмена" icon={X} onClick={onCancel} />
          <AccentButton text="Сохранить" icon={Check} onClick={handleConfirm} disabled={!ready} />
        </div>
      </motion.div>
    </motion.div>
  );
}
