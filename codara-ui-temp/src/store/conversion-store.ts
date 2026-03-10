import { create } from "zustand";
import type { Conversion, SasFile, ConversionConfig, PipelineStageInfo } from "@/types";
import { mockConversions } from "@/lib/mock/data";

interface ConversionState {
  conversions: Conversion[];
  uploadedFiles: SasFile[];
  config: ConversionConfig;
  activeConversionId: string | null;
  setConfig: (config: Partial<ConversionConfig>) => void;
  addFiles: (files: SasFile[]) => void;
  removeFile: (id: string) => void;
  setActiveConversion: (id: string | null) => void;
  startConversion: (fileIds: string[]) => string;
  updateStage: (conversionId: string, stageIndex: number, update: Partial<PipelineStageInfo>) => void;
}

export const useConversionStore = create<ConversionState>((set, get) => ({
  conversions: mockConversions,
  uploadedFiles: [],
  config: { targetRuntime: "python", testCoverage: "full" },
  activeConversionId: null,

  setConfig: (config) => set((s) => ({ config: { ...s.config, ...config } })),

  addFiles: (files) => set((s) => ({ uploadedFiles: [...s.uploadedFiles, ...files] })),

  removeFile: (id) => set((s) => ({ uploadedFiles: s.uploadedFiles.filter((f) => f.id !== id) })),

  setActiveConversion: (id) => set({ activeConversionId: id }),

  startConversion: (fileIds) => {
    const id = `conv-${Date.now()}`;
    const file = get().uploadedFiles.find((f) => fileIds.includes(f.id));
    const stages = ["file_process","sas_partition","strategy_select","translate","validate","repair","merge","finalize"] as const;
    const newConversion: Conversion = {
      id,
      fileName: file?.name || "unknown.sas",
      status: "running",
      runtime: get().config.targetRuntime,
      duration: 0,
      accuracy: 0,
      createdAt: new Date().toISOString(),
      stages: stages.map((s) => ({ stage: s, status: "pending", retryCount: 0, warnings: [] })),
    };
    set((s) => ({ conversions: [newConversion, ...s.conversions], activeConversionId: id }));
    return id;
  },

  updateStage: (conversionId, stageIndex, update) =>
    set((s) => ({
      conversions: s.conversions.map((c) =>
        c.id === conversionId
          ? { ...c, stages: c.stages.map((st, i) => (i === stageIndex ? { ...st, ...update } : st)) }
          : c
      ),
    })),
}));
