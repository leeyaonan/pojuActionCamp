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
  /** 破局行动营 ID（actionId，UUID 字符串）。可空，志愿者身份用于对接破局学员列表 */
  poju_action_id?: string | null;
}

export interface CampUpdate {
  name?: string;
  description?: string;
  total_days?: number;
  start_date?: string;
  end_date?: string;
  min_checkin_days?: number;
  /** 破局行动营 ID（actionId）。None/不传=不修改，空串=清除，非空=更新 */
  poju_action_id?: string | null;
}

export interface CampOut extends CampCreate {
  id: number;
  status: CampStatus;
  current_day?: number | null;
  valid_days: number;
  has_manual: boolean;
  has_route: boolean;
  poju_action_id?: string | null;
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
  poju_action_id?: string | null;
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
  // 迁移 0004 起扩展档案字段（破局 query-people 拉取）
  /** 学员本人 */
  full_name?: string | null;
  wechat_id?: string | null;
  phone?: string | null;
  wechat_name?: string | null;
  user_name?: string | null;
  user_number?: string | null;
  /** 组长 */
  leader_name?: string | null;
  leader_user_name?: string | null;
  leader_wechat_id?: string | null;
  /** 志愿者 */
  volunteer_name?: string | null;
  volunteer_user_name?: string | null;
  volunteer_wechat_id?: string | null;
  /** 数据官 */
  data_officer_name?: string | null;
  data_officer_user_name?: string | null;
  data_officer_wechat_id?: string | null;
  /** 打卡统计 */
  clock_in_count?: number | null;
  camp_days?: number | null;
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

/**
 * 初始化 / 刷新学员档案（query-people）的结果。
 *
 * - imported：本次新增的 Student 行数
 * - updated：本次按 (camp, poju_student_id) 覆盖更新的行数
 * - skipped：因 poju_student_id 缺失被整条跳过的记录数
 * - total_from_poju：破局接口返回的总条数（来自 data.total）
 * - pages_fetched：实际遍历的页数
 * - errors：分页失败明细（任意一页网络/业务错都会写入并继续翻页）
 */
export interface InitResult {
  success: boolean;
  imported: number;
  updated: number;
  skipped: number;
  total_from_poju: number;
  pages_fetched: number;
  errors: string[];
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

// ---------------------------------------------------------------------------
// 大模型厂商配置（AI 模型配置）
// ---------------------------------------------------------------------------

export type LlmProtocol = 'openai_compatible' | 'anthropic';
export type LlmActiveSource = 'db' | 'env' | 'none';

export interface LlmProviderOut {
  id: number;
  name: string;
  protocol: LlmProtocol;
  base_url: string;
  model: string;
  models?: string[] | null;
  api_key_masked?: string | null;
  has_api_key: boolean;
  is_preset: boolean;
  is_active: boolean;
  key_status: TokenStatus;
  last_checked_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface LlmProviderCreate {
  name: string;
  protocol?: LlmProtocol;
  base_url: string;
  model: string;
  models?: string[] | null;
  api_key?: string | null;
}

export interface LlmProviderUpdate {
  name?: string;
  protocol?: LlmProtocol;
  base_url?: string;
  model?: string;
  models?: string[] | null;
  /** None/不传=不修改，空串=清除，非空=更新 */
  api_key?: string | null;
}

export interface LlmActiveOut {
  source: LlmActiveSource;
  id?: number | null;
  name?: string | null;
  protocol?: LlmProtocol | null;
  base_url?: string | null;
  model?: string | null;
  is_active: boolean;
  key_status: TokenStatus;
  last_checked_at?: string | null;
  env_provider?: string | null;
  env_model?: string | null;
  has_api_key: boolean;
}