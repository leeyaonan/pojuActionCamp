/**
 * API 类型定义（对齐后端 OpenAPI schemas）。
 *
 * 这些类型由前端手写维护，便于：
 * 1. 不依赖运行期 OpenAPI 生成；
 * 2. 字段含义与 backend/app/schemas/*.py 一一对应，便于 diff 校对。
 *
 * 修改前请先核对 backend 端对应 schema。
 */

// ---------------------------------------------------------------------------
// 通用响应 {code, message, data}
// ---------------------------------------------------------------------------

export interface ApiResponse<T> {
  code: number;
  message: string;
  data: T;
}

// ---------------------------------------------------------------------------
// 通用枚举 / 字面量
// ---------------------------------------------------------------------------

export type Role = 'student' | 'volunteer';
export type CampStatus = 'not_started' | 'ongoing' | 'ended';
export type SubmitMethod = 'auto' | 'manual';
export type SyncStatus = 'pending' | 'synced' | 'failed' | 'manual';
export type GradeStatus = 'pending' | 'graded';
export type StudentStatus = 'ongoing' | 'qualified' | 'unqualified';
export type TokenStatus = 'valid' | 'invalid' | 'unknown';
export type GradeSource = 'ai' | 'manual';

// ---------------------------------------------------------------------------
// 业务错误码（对齐 backend/app/core/exceptions.py）
// ---------------------------------------------------------------------------

export const ErrorCode = {
  VALIDATION: 1001,
  NOT_FOUND: 1002,
  POJU_AUTH: 2001,
  POJU_API: 2002,
  POJU_PENDING: 2003,
  LLM_ERROR: 3001,
  MANUAL_NOT_FOUND: 3002,
  INTERNAL: 5000,
} as const;

export type ErrorCodeValue = (typeof ErrorCode)[keyof typeof ErrorCode];

// ---------------------------------------------------------------------------
// Camp
// ---------------------------------------------------------------------------

export interface CampCreate {
  name: string;
  role: Role;
  description?: string;
  total_days: number;
  start_date: string; // YYYY-MM-DD
  end_date: string;
  min_checkin_days: number;
}

export interface CampUpdate {
  name?: string;
  description?: string;
  total_days?: number;
  start_date?: string;
  end_date?: string;
  min_checkin_days?: number;
}

export interface CampOut extends CampCreate {
  id: number;
  status: CampStatus;
  current_day?: number | null;
  valid_days: number;
  has_manual: boolean;
  has_route: boolean;
  created_at: string;
  updated_at: string;
}

export interface CampSummary {
  id: number;
  name: string;
  role: Role;
  total_days: number;
  start_date: string;
  end_date: string;
  min_checkin_days: number;
  status: CampStatus;
  current_day?: number | null;
  valid_days: number;
  progress: number; // 0~1
  created_at: string;
}

// ---------------------------------------------------------------------------
// 学习路线 / 每日任务
// ---------------------------------------------------------------------------

export interface DayTaskOut {
  id: number;
  route_id: number;
  day_number: number;
  title: string;
  description?: string | null;
  tags?: Array<Record<string, unknown>> | null;
  is_completed: boolean;
  edited: boolean;
  created_at: string;
  updated_at: string;
}

export interface DayTaskUpdate {
  title?: string;
  description?: string;
  tags?: Array<Record<string, unknown>>;
}

export interface RouteOut {
  id: number;
  camp_id: number;
  generated_at?: string | null;
  source?: string | null;
  tasks: DayTaskOut[];
  created_at: string;
  updated_at: string;
}

export interface TodayOut {
  day_number?: number | null;
  task?: DayTaskOut | null;
  progress: number;
}

// ---------------------------------------------------------------------------
// 打卡
// ---------------------------------------------------------------------------

export interface CheckinGenerateIn {
  text: string;
  images?: string[];
}

export interface CheckinDraftOut {
  today_action: string;
  today_gain: string;
  good_thing: string;
  next_step: string;
}

export interface CheckinSubmitIn {
  content: string;
  auto?: boolean;
}

export interface CheckinSubmitResult {
  submitted: boolean;
  method: SubmitMethod;
  sync_status: SyncStatus;
  poju_checkin_id?: string | null;
}

export interface CheckinRecordOut {
  id: number;
  student_id: number;
  camp_id: number;
  day_number: number;
  checkin_date: string;
  content?: string | null;
  images?: Array<Record<string, unknown>> | null;
  submitted_at?: string | null;
  poju_checkin_id?: string | null;
  grade_status: GradeStatus;
  stars?: number | null;
  is_valid: boolean;
  synced_to_poju: boolean;
  synced_at?: string | null;
  created_at: string;
  updated_at: string;
}

// ---------------------------------------------------------------------------
// 志愿者 / 学员档案 / 评改
// ---------------------------------------------------------------------------

export interface StudentSummary {
  id: number;
  camp_id: number;
  nickname: string;
  wechat?: string | null;
  current_day?: number | null;
  valid_days: number;
  gap_to_min: number;
  last_stars?: number | null;
  status: StudentStatus;
  last_synced_at?: string | null;
}

export interface ArchiveTimelineItem {
  checkin_id: number;
  day_number: number;
  checkin_date: string;
  content?: string | null;
  stars?: number | null;
  is_valid: boolean;
  grade_status: string;
  synced_to_poju: boolean;
}

export interface ArchiveStats {
  total_checkins: number;
  valid_days: number;
  gap_to_min: number;
  avg_stars?: number | null;
  status: StudentStatus;
}

export interface StudentArchive {
  student: StudentSummary;
  stats: ArchiveStats;
  timeline: ArchiveTimelineItem[];
}

export interface PendingGradeOut {
  checkin_id: number;
  student_id: number;
  student_nickname: string;
  camp_id: number;
  day_number: number;
  checkin_date: string;
  content?: string | null;
  images?: Array<Record<string, unknown>> | null;
  submitted_at?: string | null;
}

export interface GradeGenerateIn {
  checkin_id: number;
}

export interface GradeConfirmIn {
  checkin_id: number;
  stars: number; // 1-3
  comment?: string;
}

export interface GradeSaveDraftIn {
  checkin_id: number;
  stars: number; // 1-3
  comment?: string;
}

export interface GradeDraftOut {
  checkin_id: number;
  stars: number;
  comment?: string | null;
  dimension_scores?: Array<Record<string, unknown>> | null;
}

export interface SyncResult {
  success: boolean;
  message: string;
  synced_at?: string | null;
}

// ---------------------------------------------------------------------------
// 手册
// ---------------------------------------------------------------------------

export interface ManualOut {
  id: number;
  camp_id: number;
  filename?: string | null;
  file_path?: string | null;
  content?: string | null;
  word_count?: number | null;
  uploaded_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ManualPreview {
  id: number;
  camp_id: number;
  filename?: string | null;
  word_count?: number | null;
  preview: string;
  uploaded_at?: string | null;
}

export interface ManualWithPreview {
  manual: ManualOut;
  preview: ManualPreview;
}

export interface PasteIn {
  content: string;
}

// ---------------------------------------------------------------------------
// 评分标准
// ---------------------------------------------------------------------------

export interface Dimension {
  key: string;
  name: string;
  desc: string;
  depends_archive?: boolean;
}

export interface StarRules {
  three: string;
  two: string;
  one: string;
}

export interface ScoringOut {
  id: number;
  dimensions: Dimension[];
  star_rules?: StarRules | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface ScoringUpdate {
  dimensions: Dimension[];
  star_rules: StarRules;
}

// ---------------------------------------------------------------------------
// 破局接口配置
// ---------------------------------------------------------------------------

export interface PojuConfigOut {
  id: number;
  token_masked?: string | null;
  base_url?: string | null;
  token_status: TokenStatus;
  last_checked_at?: string | null;
  has_token: boolean;
  created_at: string;
  updated_at: string;
}

export interface TokenUpdate {
  token: string;
}

export interface ConnectionResult {
  valid: boolean;
  message: string;
  details?: string | null;
  last_checked_at?: string | null;
}