import { create } from 'zustand';
import type { CampOut } from '@/api/types';

/**
 * 当前选中行动营 Zustand store。
 *
 * - 仅存纯前端状态：当前高亮的 camp。
 * - 不持久化（刷新后由 useCamp 自动从 URL /:id 加载）。
 */
interface CampStoreState {
  currentCamp: CampOut | null;
  setCurrentCamp: (camp: CampOut | null) => void;
}

export const useCampStore = create<CampStoreState>((set) => ({
  currentCamp: null,
  setCurrentCamp: (camp) => set({ currentCamp: camp }),
}));

/**
 * 提交方式开关（学员打卡生成页用，前端临时状态，不入库）。
 */
interface SubmitToggleState {
  autoSubmit: boolean;
  setAutoSubmit: (auto: boolean) => void;
}

export const useSubmitToggle = create<SubmitToggleState>((set) => ({
  autoSubmit: false,
  setAutoSubmit: (auto) => set({ autoSubmit: auto }),
}));