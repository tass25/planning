import { create } from "zustand";
import type { Conversion, SasFile, ConversionConfig, PipelineStageInfo } from "@/types";
import { api } from "@/lib/api";

interface ConversionState {
  conversions: Conversion[];
  uploadedFiles: SasFile[];
  config: ConversionConfig;
  activeConversionId: string | null;
  pollingId: ReturnType<typeof setInterval> | null;
  setConfig: (config: Partial<ConversionConfig>) => void;
  addFiles: (files: SasFile[]) => void;
  removeFile: (id: string) => void;
  setActiveConversion: (id: string | null) => void;
  startConversion: (fileIds: string[]) => Promise<string>;
  updateStage: (conversionId: string, stageIndex: number, update: Partial<PipelineStageInfo>) => void;
  fetchConversions: () => Promise<void>;
  refreshConversion: (id: string) => Promise<void>;
  uploadFiles: (files: File[]) => Promise<void>;
  pollConversion: (id: string) => void;
  stopPolling: () => void;
}

export const useConversionStore = create<ConversionState>((set, get) => ({
  conversions: [],
  uploadedFiles: [],
  config: { targetRuntime: "python" as const, testCoverage: "full" as const },
  activeConversionId: null,
  pollingId: null,

  setConfig: (config) => set((s) => ({ config: { ...s.config, ...config } })),

  addFiles: (files) => set((s) => ({ uploadedFiles: [...s.uploadedFiles, ...files] })),

  removeFile: (id) => set((s) => ({ uploadedFiles: s.uploadedFiles.filter((f) => f.id !== id) })),

  setActiveConversion: (id) => set({ activeConversionId: id }),

  uploadFiles: async (files: File[]) => {
    const formData = new FormData();
    files.forEach((f) => formData.append("files", f));
    const uploaded = await api.post<SasFile[]>("/conversions/upload", formData);
    set((s) => ({ uploadedFiles: [...s.uploadedFiles, ...(uploaded ?? [])] }));
  },

  startConversion: async (fileIds) => {
    const { config } = get();
    const conv = await api.post<Conversion>("/conversions/start", { fileIds, config });
    set((s) => ({
      conversions: [conv, ...s.conversions],
      activeConversionId: conv.id,
      // Clear the upload queue — the files are now owned by the new conversion
      uploadedFiles: [],
    }));
    get().pollConversion(conv.id);
    return conv.id;
  },

  fetchConversions: async () => {
    try {
      const convs = await api.get<Conversion[]>("/conversions");
      set({ conversions: convs ?? [] });
    } catch (err) {
      console.error("[codara] fetchConversions failed", err);
    }
  },

  refreshConversion: async (id: string) => {
    try {
      const conv = await api.get<Conversion>(`/conversions/${id}`);
      if (conv) {
        set((s) => ({
          conversions: s.conversions.map((c) => (c.id === id ? conv : c)),
        }));
      }
    } catch (err) {
      console.error("[codara] refreshConversion failed", id, err);
    }
  },

  updateStage: (conversionId, stageIndex, update) =>
    set((s) => ({
      conversions: s.conversions.map((c) =>
        c.id === conversionId
          ? { ...c, stages: c.stages.map((st, i) => (i === stageIndex ? { ...st, ...update } : st)) }
          : c
      ),
    })),

  pollConversion: (id: string) => {
    // Always cancel any existing poll before starting a new one —
    // otherwise two overlapping intervals can race and double-update state.
    get().stopPolling();

    // Start at 1.2s and exponentially back off on rate-limit errors (max 30s).
    // On a successful response we reset back to 1.2s so the UI stays snappy
    // while the pipeline is actively running.
    let delay = 1200;

    const tick = async () => {
      try {
        const conv = await api.get<Conversion>(`/conversions/${id}`);
        set((s) => ({
          conversions: s.conversions.map((c) => (c.id === id ? conv : c)),
        }));

        // Stop as soon as we hit a terminal state — no point polling a finished job
        if (conv.status === "completed" || conv.status === "failed" || conv.status === "partial") {
          get().stopPolling();
          return;
        }

        delay = 1200; // reset backoff after a clean response
      } catch (err) {
        const msg = err instanceof Error ? err.message : String(err);

        // Auth errors and missing conversions are unrecoverable — stop immediately
        if (msg.includes("401") || msg.includes("403") || msg.includes("404")) {
          get().stopPolling();
          return;
        }

        // Rate limited — double the wait time up to 30s so we don't hammer the API
        if (msg.includes("429")) {
          delay = Math.min(delay * 2, 30000);
          console.warn(`[codara] rate limited, retrying in ${delay}ms`);
        }
      }

      // Schedule the next tick and store the timeout ID so stopPolling() can cancel it
      const nextId = setTimeout(tick, delay) as unknown as ReturnType<typeof setInterval>;
      set({ pollingId: nextId });
    };

    const firstId = setTimeout(tick, delay) as unknown as ReturnType<typeof setInterval>;
    set({ pollingId: firstId });
  },

  stopPolling: () => {
    const { pollingId } = get();
    if (pollingId) {
      clearTimeout(pollingId);
      set({ pollingId: null });
    }
  },
}));
