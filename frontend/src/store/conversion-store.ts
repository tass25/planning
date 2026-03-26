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
    get().stopPolling();
    const intervalId = setInterval(async () => {
      try {
        const conv = await api.get<Conversion>(`/conversions/${id}`);
        set((s) => ({
          conversions: s.conversions.map((c) => (c.id === id ? conv : c)),
        }));
        if (conv.status === "completed" || conv.status === "failed" || conv.status === "partial") {
          get().stopPolling();
        }
      } catch (err) {
        console.error("[codara] poll failed", err);
        // Only stop polling on auth errors; retry on transient network issues
        const msg = err instanceof Error ? err.message : String(err);
        if (msg.includes("401") || msg.includes("403") || msg.includes("404")) {
          get().stopPolling();
        }
        // Otherwise keep polling — transient network hiccups should not stop progress
      }
    }, 1200);
    set({ pollingId: intervalId });
  },

  stopPolling: () => {
    const { pollingId } = get();
    if (pollingId) {
      clearInterval(pollingId);
      set({ pollingId: null });
    }
  },
}));
