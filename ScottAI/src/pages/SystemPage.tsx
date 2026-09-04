import { useEffect, useState, useCallback } from "react";
import { RefreshCw, X, Camera, TerminalSquare, Volume2, VolumeX, Volume1, Download, Search, Trash2, FolderOpen } from "lucide-react";
import { motion } from "framer-motion";
import { open } from "@tauri-apps/plugin-dialog";
import { GhostButton } from "../components/Button";
import { StyledInput } from "../components/Input";
import { os, type ProcessInfo } from "../lib/osCommands";

export function SystemPage() {
  const [processes, setProcesses] = useState<ProcessInfo[]>([]);
  const [loading, setLoading] = useState(false);
  const [screenshot, setScreenshot] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedFile, setSelectedFile] = useState<string | null>(null);
  const [deleteStatus, setDeleteStatus] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      setProcesses(await os.listProcesses());
    } catch (err) {
      setError(String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  const handleKill = async (pid: number, name: string) => {
    if (!confirm(`Завершить процесс «${name}» (PID ${pid})?`)) return;
    try {
      await os.killProcess(pid);
      await refresh();
    } catch (err) {
      setError(String(err));
    }
  };

  const handleScreenshot = async () => {
    try {
      setScreenshot(await os.takeScreenshot());
    } catch (err) {
      setError(String(err));
    }
  };

  const downloadScreenshot = () => {
    if (!screenshot) return;
    const a = document.createElement("a");
    a.href = screenshot;
    a.download = `scottai-screenshot-${Date.now()}.png`;
    a.click();
  };

  const handleSearch = async () => {
    if (!searchQuery.trim()) return;
    try {
      await os.windowsSearch(searchQuery);
    } catch (err) {
      setError(String(err));
    }
  };

  const pickFileToDelete = async () => {
    const path = await open({ multiple: false });
    if (path && typeof path === "string") {
      setSelectedFile(path);
      setDeleteStatus(null);
    }
  };

  const handleDelete = async () => {
    if (!selectedFile) return;
    const name = selectedFile.split(/[\\/]/).pop() ?? selectedFile;
    if (!confirm(`Удалить «${name}»?\n\nФайл будет перемещён в Корзину — это можно отменить.`)) return;
    try {
      await os.deleteFile(selectedFile);
      setDeleteStatus(`Перемещено в Корзину: ${name}`);
      setSelectedFile(null);
    } catch (err) {
      setError(String(err));
    }
  };

  return (
    <div className="h-full overflow-y-auto p-10">
      <div className="flex max-w-4xl flex-col gap-8">
        <h1 className="text-[30px] font-bold" style={{ color: "var(--text-primary)" }}>
          Система
        </h1>

        {error && (
          <div
            className="rounded-[var(--radius-sm)] border px-4 py-2.5 text-sm"
            style={{ borderColor: "var(--danger)", color: "var(--danger)", background: "var(--bg-elevated)" }}
          >
            {error}
          </div>
        )}

        <section className="flex flex-wrap gap-3">
          <GhostButton text="Терминал" icon={TerminalSquare} onClick={() => os.openTerminal().catch((e) => setError(String(e)))} />
          <GhostButton text="Скриншот" icon={Camera} onClick={handleScreenshot} />
          <GhostButton icon={Volume2} text="Громче" onClick={() => os.setVolume("up").catch((e) => setError(String(e)))} />
          <GhostButton icon={Volume1} text="Тише" onClick={() => os.setVolume("down").catch((e) => setError(String(e)))} />
          <GhostButton icon={VolumeX} text="Без звука" onClick={() => os.setVolume("mute").catch((e) => setError(String(e)))} />
        </section>

        <section className="flex flex-col gap-2">
          <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
            Поиск Windows
          </span>
          <div className="flex items-center gap-2.5">
            <div className="flex-1">
              <StyledInput
                value={searchQuery}
                onChange={setSearchQuery}
                placeholder="Открыть поиск Windows и ввести запрос..."
                onEnter={handleSearch}
              />
            </div>
            <GhostButton text="Искать" icon={Search} onClick={handleSearch} disabled={!searchQuery.trim()} />
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
              Удаление файла
            </span>
            <span className="text-xs" style={{ color: "var(--text-muted)" }}>
              Всегда с подтверждением, в Корзину
            </span>
          </div>
          <div className="flex items-center gap-2.5">
            <GhostButton text="Выбрать файл" icon={FolderOpen} onClick={pickFileToDelete} />
            {selectedFile && (
              <>
                <span className="flex-1 truncate text-sm" style={{ color: "var(--text-primary)" }}>
                  {selectedFile.split(/[\\/]/).pop()}
                </span>
                <GhostButton text="Удалить" icon={Trash2} danger onClick={handleDelete} />
              </>
            )}
          </div>
          {deleteStatus && (
            <span className="text-xs" style={{ color: "var(--success)" }}>
              {deleteStatus}
            </span>
          )}
        </section>

        {screenshot && (
          <section className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <span className="text-sm font-semibold" style={{ color: "var(--text-secondary)" }}>
                Скриншот
              </span>
              <div className="flex gap-2">
                <GhostButton text="Сохранить" icon={Download} onClick={downloadScreenshot} />
                <GhostButton icon={X} onClick={() => setScreenshot(null)} />
              </div>
            </div>
            <img
              src={screenshot}
              alt="screenshot"
              className="max-h-[280px] w-full rounded-[var(--radius-md)] border object-contain"
              style={{ borderColor: "var(--border)", background: "var(--bg-elevated)" }}
            />
          </section>
        )}

        <section className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <span className="text-[15px] font-semibold" style={{ color: "var(--text-secondary)" }}>
              Процессы ({processes.length})
            </span>
            <motion.button
              onClick={refresh}
              whileHover={{ rotate: 90 }}
              whileTap={{ scale: 0.9 }}
              className="flex h-8 w-8 items-center justify-center rounded-full"
              style={{ color: "var(--text-secondary)" }}
            >
              <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
            </motion.button>
          </div>

          <div
            className="glass-panel overflow-hidden rounded-[var(--radius-md)] border"
            style={{ borderColor: "var(--border)", background: "var(--bg-surface)" }}
          >
            <div className="max-h-[420px] overflow-y-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="sticky top-0" style={{ background: "var(--bg-elevated)" }}>
                    <th className="px-3 py-2 text-left font-semibold" style={{ color: "var(--text-secondary)" }}>
                      Процесс
                    </th>
                    <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--text-secondary)" }}>
                      PID
                    </th>
                    <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--text-secondary)" }}>
                      CPU
                    </th>
                    <th className="px-3 py-2 text-right font-semibold" style={{ color: "var(--text-secondary)" }}>
                      RAM
                    </th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody>
                  {processes.map((p) => (
                    <tr key={p.pid} className="border-t" style={{ borderColor: "var(--border)" }}>
                      <td className="px-3 py-2" style={{ color: "var(--text-primary)" }}>
                        {p.name}
                      </td>
                      <td className="px-3 py-2 text-right" style={{ color: "var(--text-muted)" }}>
                        {p.pid}
                      </td>
                      <td className="px-3 py-2 text-right" style={{ color: "var(--text-muted)" }}>
                        {p.cpu_percent.toFixed(1)}%
                      </td>
                      <td className="px-3 py-2 text-right" style={{ color: "var(--text-muted)" }}>
                        {p.memory_mb} МБ
                      </td>
                      <td className="px-3 py-2 text-right">
                        <button
                          onClick={() => handleKill(p.pid, p.name)}
                          className="text-xs font-semibold hover:underline"
                          style={{ color: "var(--danger)" }}
                        >
                          Завершить
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
